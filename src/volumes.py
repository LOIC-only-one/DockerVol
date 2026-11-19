import os
import sys
import tarfile
import paramiko
import socket
import getpass
import logging
import time
import subprocess
import glob
import json
import http.client
global PATH
# Dossier lu quand l'API Docker n'est pas joignable (ou imposé avec DOCKERVOL_PATH).
PATH = os.environ.get("DOCKERVOL_PATH", "/var/lib/docker/volumes/")
SOURCE = PATH  # d'où vient la dernière liste de volumes (affiché dans l'interface)

logging.basicConfig(filename='docker_volume_transfer.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def check_user_permissions():
    if os.geteuid() != 0:
        print("Ce script doit être exécuté avec des privilèges root.")
        sys.exit(1)

class _UnixHTTPConnection(http.client.HTTPConnection):
    def __init__(self, socket_path):
        super().__init__("localhost", timeout=5)
        self.socket_path = socket_path

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self.socket_path)

def _docker_sockets():
    host = os.environ.get("DOCKER_HOST", "")
    if host.startswith("unix://"):
        yield host[len("unix://"):]
    yield "/var/run/docker.sock"
    # Docker rootless : sudo efface DOCKER_HOST, on cherche donc les sockets des utilisateurs.
    yield from sorted(glob.glob("/run/user/*/docker.sock"))

def _describe(v):
    """Chemin réel des données d'un volume (réponse de l'API Docker) et problème éventuel."""
    opts = v.get("Options") or {}
    if v.get("Driver") == "local" and "bind" in opts.get("o", "").split(","):
        path = opts.get("device", "")  # volume "bind" : les données sont dans le dossier source
    else:
        path = v["Mountpoint"]
    problem = None
    if opts.get("type") and opts["type"] != "none" and not os.path.ismount(path):
        problem = f"volume {opts['type']} monté seulement quand un conteneur l'utilise"
    elif not os.path.isdir(path):
        problem = f"données introuvables : {path}"
    return {"path": path, "problem": problem}

def _api_volumes():
    """{nom: infos} via l'API Docker, ou None si aucun socket n'est joignable."""
    for sock in _docker_sockets():
        try:
            conn = _UnixHTTPConnection(sock)
            conn.request("GET", "/volumes")
            resp = conn.getresponse()
            if resp.status != 200:
                continue
            data = json.load(resp)
        except (OSError, ValueError, http.client.HTTPException):
            continue
        finally:
            conn.close()
        global SOURCE
        SOURCE = f"API Docker ({sock})"
        return {v["Name"]: _describe(v) for v in sorted(data.get("Volumes") or [], key=lambda v: v["Name"])}
    return None

def get_docker_volumes():
    """
    Permet de récuperer les volumes Docker présents sur le système : {nom: {"path", "problem"}}.
    Utilise l'API Docker (chemins exacts quel que soit data-root, rootless, snap, volumes bind/nfs),
    sinon lit le dossier PATH.
    """
    global SOURCE
    if "DOCKERVOL_PATH" not in os.environ:
        volumes = _api_volumes()
        if volumes is not None:
            return volumes
    SOURCE = PATH
    return {v: {"path": os.path.join(PATH, v, "_data"), "problem": None}
            for v in sorted(os.listdir(PATH)) if os.path.isdir(os.path.join(PATH, v))}

def _walk_entries(top):
    """Tous les chemins sous top (dossiers, fichiers, liens), sans suivre les liens symboliques."""
    for root, dirs, files in os.walk(top):
        yield root
        for d in dirs:
            if os.path.islink(os.path.join(root, d)):
                yield os.path.join(root, d)
        for f in files:
            yield os.path.join(root, f)

def get_volume_size(volume_name):
    """
    Taille en octets des fichiers réguliers d'un volume (base du calcul de progression).
    """
    top = get_docker_volumes()[volume_name]["path"]
    return sum(os.lstat(p).st_size for p in _walk_entries(top)
               if os.path.isfile(p) and not os.path.islink(p))

class _CountingReader:
    def __init__(self, f, progress):
        self.f, self.progress = f, progress
    def read(self, n=-1):
        data = self.f.read(n)
        self.progress(len(data))
        return data

def create_archive(volume_name, progress=None):
    """
    Permet de créer une archive tar.gz d'un volume Docker.
    progress(n) est appelé avec le nombre d'octets lus à chaque bloc.
    """
    info = get_docker_volumes().get(volume_name)
    if info is None:
        raise ValueError(f"Volume inconnu : {volume_name}")
    if info["problem"]:
        raise ValueError(f"{volume_name} : {info['problem']}")
    volume_path = info["path"]
    archive_name = os.path.abspath(f"{volume_name}.tar.gz")
    progress = progress or (lambda n: None)
    try:
        with tarfile.open(archive_name, "w:gz") as tar:
            for path in _walk_entries(volume_path):
                rel = os.path.relpath(path, volume_path)
                info = tar.gettarinfo(path, arcname="." if rel == "." else "./" + rel)
                if info is None:  # sockets : ignorés, comme tar
                    continue
                if info.isreg():
                    with open(path, "rb") as f:
                        tar.addfile(info, _CountingReader(f, progress))
                else:
                    tar.addfile(info)
    except BaseException:
        # Never leave a truncated archive that looks valid.
        if os.path.exists(archive_name):
            os.remove(archive_name)
        raise
    print(f"Archive créée : {archive_name}")
    return archive_name

def create_archive_for_all_volumes():
    """
    Permet de créer une archive tar.gz pour tous les volumes Docker présents sur le système.
    """
    volumes = get_docker_volumes()
    for volume in volumes:
        create_archive(volume)



#### Création du handler qui permet de repliquer les volumes Docker sur un autre serveur distant via SSH. ####

def connexion_ssh(hostname, username, password):
    """
    Permet d'établir une connexion SSH avec un serveur distant.
    """
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(hostname, username=username, password=password)
        return client
    except (paramiko.AuthenticationException, paramiko.SSHException, socket.error) as e:
        logging.error(f"Erreur lors de la connexion SSH : {e}")
        return None

def transfer_archive(client, local_path, remote_path, progress=None):
    """
    Permet de transférer une archive tar.gz vers un serveur distant via SFTP.
    progress(transferes, total) est appelé par paramiko pendant l'envoi.
    """
    try:
        sftp = client.open_sftp()
        sftp.put(local_path, remote_path, callback=progress)
        sftp.close()
        print(f"Transfert réussi : {local_path} -> {remote_path}")
        return True
    except Exception as e:
        logging.error(f"Erreur lors du transfert de l'archive : {e}")
        return False




if __name__ == "__main__":
    if check_user_permissions():
        sys.exit(1)
    else:
        volumes = get_docker_volumes()
        for volume in volumes:
            print(volume)
