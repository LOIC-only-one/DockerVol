import os
import posixpath

import flask

import volumes

app = flask.Flask(__name__)
app.secret_key = os.environ.get("DOCKERVOL_SECRET", os.urandom(24))
app.jinja_env.autoescape = True  # .j2 templates are not auto-escaped by default


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
    try:
        path = volumes.create_archive(_volume_or_404(name))
        flask.flash(f"Archive créée : {path}", "ok")
    except Exception as e:
        flask.flash(f"Échec de l'archivage de {name} : {e}", "err")
    return flask.redirect(flask.url_for("index"))


@app.post("/archive-all")
def archive_all():
    for name in volumes.get_docker_volumes():
        archive(name)
    return flask.redirect(flask.url_for("index"))


@app.post("/transfer/<name>")
def transfer(name):
    f = flask.request.form
    client = volumes.connexion_ssh(f["host"], f["user"], f["password"])
    if client is None:
        flask.flash(f"Connexion SSH impossible vers {f['host']}", "err")
        return flask.redirect(flask.url_for("index"))
    try:
        local = volumes.create_archive(_volume_or_404(name))
        remote = posixpath.join(f.get("remote_dir") or "/tmp", os.path.basename(local))
        if volumes.transfer_archive(client, local, remote):
            flask.flash(f"{name} transféré vers {f['host']}:{remote}", "ok")
        else:
            flask.flash(f"Échec du transfert de {name} (voir le log)", "err")
    except Exception as e:
        flask.flash(f"Échec du transfert de {name} : {e}", "err")
    finally:
        client.close()
    return flask.redirect(flask.url_for("index"))
