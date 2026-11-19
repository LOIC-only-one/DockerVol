import os
import queue
import threading
import time
import uuid

import flask

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

def new_job(volume, action, ssh=None):
    """
    Crée une tâche ("archive" ou "transfer") et la met dans la file d'attente.
    ssh : infos de connexion, seulement pour "transfer".
    """
    job = {
        "id": str(uuid.uuid4()),
        "volume": volume,
        "action": action,
        "status": "queued",       # queued -> running -> done / error
        "phase": "En attente",
        "done": 0,                # octets traités dans la phase en cours
        "total": 0,               # octets à traiter dans la phase en cours
        "phase_started": None,
        "error": None,
        "result": None,
        "ssh": ssh,
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
    start_phase(job, "Archivage", volumes.get_volume_size(job["volume"]))

    def on_progress(nb_bytes):
        job["done"] += nb_bytes

    job["result"] = volumes.create_archive(job["volume"], on_progress)
    job["done"] = job["total"]


def run_transfer(job):
    ssh = job["ssh"]
    start_phase(job, "Connexion SSH", 0)
    client = volumes.connexion_ssh(ssh["host"], ssh["user"], ssh["password"])
    if client is None:
        raise RuntimeError(f"Connexion SSH impossible vers {ssh['host']}")

    try:
        run_archive(job)
        local_path = job["result"]
        remote_path = ssh["remote_dir"].rstrip("/") + "/" + os.path.basename(local_path)

        start_phase(job, "Transfert", os.path.getsize(local_path))

        def on_progress(sent, total):
            job["done"] = sent

        if not volumes.transfer_archive(client, local_path, remote_path, on_progress):
            raise RuntimeError("Échec du transfert (voir le log)")
        job["result"] = f"{ssh['host']}:{remote_path}"
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
                run_transfer(job)
            job["status"] = "done"
        except Exception as e:
            job["status"] = "error"
            job["error"] = str(e)
            volumes.logging.error(f"Tâche {job['volume']} : {e}")
        finally:
            job["ssh"] = None  # ne pas garder le mot de passe en mémoire


threading.Thread(target=worker, daemon=True).start()


#### Pages ####

def check_volume_exists(name):
    if name not in volumes.get_docker_volumes():
        flask.abort(404)


@app.route("/")
def index():
    try:
        volume_list = volumes.get_docker_volumes()
        error = None
    except OSError as e:
        volume_list = {}
        error = f"Impossible de lire {volumes.PATH} : {e}"
    return flask.render_template("index.j2", volumes=volume_list, error=error, source=volumes.SOURCE)


@app.post("/archive/<name>")
def archive(name):
    check_volume_exists(name)
    new_job(name, "archive")
    return flask.redirect(flask.url_for("index"))


@app.post("/archive-all")
def archive_all():
    for name, info in volumes.get_docker_volumes().items():
        if info["problem"] is None:
            new_job(name, "archive")
    return flask.redirect(flask.url_for("index"))


@app.post("/transfer/<name>")
def transfer(name):
    check_volume_exists(name)
    form = flask.request.form
    ssh = {
        "host": form["host"],
        "user": form["user"],
        "password": form["password"],
        "remote_dir": form.get("remote_dir") or "/tmp",
    }
    new_job(name, "transfer", ssh)
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
            "status": job["status"],
            "phase": job["phase"],
            "done": job["done"],
            "total": job["total"],
            "error": job["error"],
            "result": job["result"],
            "eta": eta,
        })
    return flask.jsonify(result)
