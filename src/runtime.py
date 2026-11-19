import os
import posixpath
import queue
import threading
import time
import uuid

import flask

import volumes

app = flask.Flask(__name__)
app.secret_key = os.environ.get("DOCKERVOL_SECRET", os.urandom(24))
app.jinja_env.autoescape = True  # .j2 templates are not auto-escaped by default

# shortcut: jobs live in memory of a single process (lost on restart, wrong with several
# gunicorn workers); move to a store like SQLite if the app is ever run multi-process.
jobs = {}
_queue = queue.Queue()
MAX_JOBS = 20


def _worker():
    # One job at a time: archiving several volumes in parallel would only fight for the disk.
    while True:
        job, task = _queue.get()
        job["status"] = "running"
        try:
            task(job)
            job["status"] = "done"
        except Exception as e:
            job["status"], job["error"] = "error", str(e)
            volumes.logging.error(f"Tâche {job['volume']} : {e}")


threading.Thread(target=_worker, daemon=True).start()


def _set_phase(job, phase, total):
    job.update(phase=phase, total=total, done=0, phase_started=time.time())


def _enqueue(volume, task):
    job = dict(id=uuid.uuid4().hex, volume=volume, status="queued", phase="En attente",
               total=0, done=0, phase_started=None, error=None, result=None)
    jobs[job["id"]] = job
    finished = [k for k, j in jobs.items() if j["status"] in ("done", "error")]
    for k in finished[:max(0, len(jobs) - MAX_JOBS)]:
        del jobs[k]
    _queue.put((job, task))


def _archive(job):
    _set_phase(job, "Archivage", volumes.get_volume_size(job["volume"]))

    def progress(n):
        job["done"] += n

    job["result"] = volumes.create_archive(job["volume"], progress)
    job["done"] = job["total"]


def _transfer(host, user, password, remote_dir):
    def task(job):
        _set_phase(job, "Connexion SSH", 0)
        client = volumes.connexion_ssh(host, user, password)
        if client is None:
            raise RuntimeError(f"Connexion SSH impossible vers {host}")
        try:
            _archive(job)
            local = job["result"]
            remote = posixpath.join(remote_dir, os.path.basename(local))
            _set_phase(job, "Transfert", os.path.getsize(local))
            if not volumes.transfer_archive(client, local, remote,
                                            lambda done, total: job.update(done=done)):
                raise RuntimeError("Échec du transfert (voir le log)")
            job["result"] = f"{host}:{remote}"
        finally:
            client.close()
    return task


def _volume_or_404(name):
    if name not in volumes.get_docker_volumes():
        flask.abort(404)
    return name


@app.route("/")
def index():
    try:
        names = volumes.get_docker_volumes()
        error = None
    except OSError as e:
        names, error = [], f"Impossible de lire {volumes.PATH} : {e}"
    return flask.render_template("index.j2", volumes=names, error=error)


@app.post("/archive/<name>")
def archive(name):
    _enqueue(_volume_or_404(name), _archive)
    return flask.redirect(flask.url_for("index"))


@app.post("/archive-all")
def archive_all():
    for name in volumes.get_docker_volumes():
        _enqueue(name, _archive)
    return flask.redirect(flask.url_for("index"))


@app.post("/transfer/<name>")
def transfer(name):
    f = flask.request.form
    _enqueue(_volume_or_404(name),
             _transfer(f["host"], f["user"], f["password"], f.get("remote_dir") or "/tmp"))
    return flask.redirect(flask.url_for("index"))


@app.get("/jobs")
def job_list():
    now, out = time.time(), []
    for j in reversed(list(jobs.values())):
        eta = None
        if j["status"] == "running" and j["done"] and j["total"]:
            eta = (now - j["phase_started"]) * (j["total"] - j["done"]) / j["done"]
        out.append({k: j[k] for k in ("id", "volume", "status", "phase", "total", "done",
                                      "error", "result")} | {"eta": eta})
    return flask.jsonify(out)
