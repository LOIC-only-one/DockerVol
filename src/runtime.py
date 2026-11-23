import os
import queue
import threading
import time
import uuid

import flask

import remote
import volumes

app = flask.Flask(__name__)
app.secret_key = os.environ.get("DOCKERVOL_SECRET", os.urandom(24))
app.jinja_env.autoescape = True  # les templates .j2 ne sont pas échappés par défaut

MAX_JOBS = 20

# Tâches en cours et terminées : {id: tâche}.
# shortcut: gardées en mémoire, donc perdues au redémarrage ; passer à SQLite si besoin de les garder.
jobs = {}

# File d'attente des tâches, traitées une par une par worker().
job_queue = queue.Queue()


#### Tâches en arrière-plan ####

def new_job(volume, action, stop=False, target=None):
    """
    Crée une tâche ("archive" ou "migrate") et la met dans la file d'attente.
    stop : arrêter les conteneurs du volume pendant l'archivage.
    target : infos SSH et mode de restauration, seulement pour "migrate".
    """
    job = {
        "id": str(uuid.uuid4()),
        "volume": volume,
        "action": action,
        "stop": stop,
        "status": "queued",       # queued -> running -> done / error
        "phase": "En attente",
        "done": 0,                # octets traités dans la phase en cours
        "total": 0,               # octets à traiter dans la phase en cours
        "phase_started": None,
        "error": None,
        "result": None,
        "target": target,
    }
    jobs[job["id"]] = job
    remove_old_jobs()
    job_queue.put(job)
    return job


def remove_old_jobs():
    """
    Garde au maximum MAX_JOBS tâches en supprimant les plus anciennes déjà terminées.
    """
    for job_id in list(jobs):
        if len(jobs) <= MAX_JOBS:
            break
        if jobs[job_id]["status"] in ("done", "error"):
            del jobs[job_id]


def start_phase(job, phase, total):
    job["phase"] = phase
    job["total"] = total
    job["done"] = 0
    job["phase_started"] = time.time()


def run_archive(job):
    stopped = []
    if job["stop"]:
        start_phase(job, "Arrêt des conteneurs", 0)
        stopped = volumes.containers_using(job["volume"])
        volumes.stop_containers(stopped)
    try:
        start_phase(job, "Archivage", volumes.get_volume_size(job["volume"]))

        def on_progress(nb_bytes):
            job["done"] += nb_bytes

        job["result"] = volumes.create_archive(job["volume"], on_progress)
        job["done"] = job["total"]
    finally:
        # Toujours relancer, même si l'archivage a échoué.
        volumes.start_containers(stopped)


def run_migrate(job):
    t = job["target"]
    start_phase(job, "Connexion SSH", 0)
    client = remote.connect(t["host"], t["user"], t["password"], t["key_path"], t["port"])
    try:
        run_archive(job)

        def on_progress(sent, total):
            job["done"] = sent

        job["result"] = t["host"] + " : " + remote.migrate(
            client, job["result"], job["volume"], t["mode"], t["shared_dir"],
            lambda phase, total: start_phase(job, phase, total), on_progress)
    finally:
        client.close()


def worker():
    """
    Traite les tâches une par une : archiver plusieurs volumes en même temps
    ne ferait que ralentir le disque.
    """
    while True:
        job = job_queue.get()
        job["status"] = "running"
        try:
            if job["action"] == "archive":
                run_archive(job)
            else:
                run_migrate(job)
            job["status"] = "done"
        except Exception as e:
            job["status"] = "error"
            job["error"] = str(e)
            volumes.logging.error(f"Tâche {job['volume']} : {e}")
        finally:
            job["target"] = None  # ne pas garder le mot de passe en mémoire


threading.Thread(target=worker, daemon=True).start()


#### Pages ####

@app.route("/")
def index():
    try:
        volume_list = volumes.get_docker_volumes()
        error = None
    except OSError as e:
        volume_list = {}
        error = f"Impossible de lire {volumes.PATH} : {e}"
    return flask.render_template("index.j2", volumes=volume_list, error=error, source=volumes.SOURCE,
                                 archives=volumes.list_archives(), can_stop=volumes.docker_available())


def selected_volumes():
    """
    Volumes cochés dans le formulaire, seulement ceux qui existent et sont archivables.
    """
    available = volumes.get_docker_volumes()
    names = [n for n in flask.request.form.getlist("names") if n in available and available[n]["problem"] is None]
    if not names:
        flask.flash("Aucun volume archivable sélectionné.", "err")
    return names


@app.post("/archive")
def archive():
    stop = "stop" in flask.request.form
    for name in selected_volumes():
        new_job(name, "archive", stop)
    return flask.redirect(flask.url_for("index"))


@app.post("/migrate")
def migrate():
    form = flask.request.form
    if form.get("mode") == "shared" and not form.get("shared_dir"):
        flask.flash("Indiquez le dossier partagé.", "err")
        return flask.redirect(flask.url_for("index"))
    target = {
        "host": form["host"],
        "port": int(form.get("port") or 22),
        "user": form["user"],
        "password": form.get("password"),
        "key_path": form.get("key_path"),
        "mode": form.get("mode", "node"),
        "shared_dir": form.get("shared_dir"),
    }
    stop = "stop" in form
    for name in selected_volumes():
        new_job(name, "migrate", stop, dict(target))
    return flask.redirect(flask.url_for("index"))


@app.get("/sizes")
def sizes():
    """
    Taille de chaque volume, chargée après la page (le calcul parcourt tous les fichiers).
    """
    result = {}
    for name, info in volumes.get_docker_volumes().items():
        result[name] = volumes.get_volume_size(name) if info["problem"] is None else None
    return flask.jsonify(result)


def check_archive(name):
    # Seuls les noms listés sont acceptés : pas de "../" possible.
    if name not in {a["name"] for a in volumes.list_archives()}:
        flask.abort(404)


@app.get("/archives/<name>")
def download_archive(name):
    check_archive(name)
    return flask.send_from_directory(os.getcwd(), name, as_attachment=True)


@app.post("/archives/<name>/delete")
def delete_archive(name):
    check_archive(name)
    os.remove(name)
    flask.flash(f"Archive {name} supprimée.", "ok")
    return flask.redirect(flask.url_for("index"))


@app.get("/jobs")
def job_list():
    """
    État des tâches en JSON, lu chaque seconde par la page pour la barre de progression.
    """
    now = time.time()
    result = []
    for job in reversed(list(jobs.values())):
        # Temps restant = temps écoulé x (octets restants / octets déjà traités).
        eta = None
        if job["status"] == "running" and job["done"] > 0 and job["total"] > 0:
            elapsed = now - job["phase_started"]
            eta = elapsed * (job["total"] - job["done"]) / job["done"]

        result.append({
            "id": job["id"],
            "volume": job["volume"],
            "action": job["action"],
            "status": job["status"],
            "phase": job["phase"],
            "done": job["done"],
            "total": job["total"],
            "error": job["error"],
            "result": job["result"],
            "eta": eta,
        })
    return flask.jsonify(result)
