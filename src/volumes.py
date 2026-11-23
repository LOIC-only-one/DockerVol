import os
import sys
import json
import glob
import hashlib
import tarfile
import logging
import subprocess
from datetime import datetime

# Dossier des volumes, utilisé quand la commande docker n'est pas disponible
# (par exemple dans l'image Docker de DockerVol) ou quand DOCKERVOL_PATH est défini.
PATH = os.environ.get("DOCKERVOL_PATH", "/var/lib/docker/volumes/")

# D'où vient la dernière liste de volumes (affiché en haut de l'interface).
SOURCE = PATH

# Vrai si DockerVol tourne lui-même dans un conteneur.
IN_CONTAINER = os.path.exists("/.dockerenv")

logging.basicConfig(filename='docker_volume_transfer.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


def check_user_permissions():
    if os.geteuid() != 0:
        print("Ce script doit être exécuté avec des privilèges root.")
        sys.exit(1)


#### Liste des volumes ####

def list_volumes_with_docker():
    """
    Demande la liste des volumes à la commande docker (docker volume ls + docker volume inspect).
    Docker donne l'emplacement exact de chaque volume, quelle que soit l'installation.
    Renvoie None si la commande docker n'est pas disponible.
    """
    try:
        result = subprocess.run(["docker", "volume", "ls", "-q"], capture_output=True, text=True, check=True)
        names = sorted(result.stdout.split())
        if not names:
            return []
        result = subprocess.run(["docker", "volume", "inspect"] + names, capture_output=True, text=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        return None
    ## format de sortie : [{"Name": "nom", "Driver": "local", "Mountpoint": "/var/lib/docker/volumes/nom/_data", "Options": {...}}, ...]
    return json.loads(result.stdout)


def list_volumes_in_folder():
    """
    Lit les volumes directement dans le dossier PATH.
    Renvoie la même forme que docker volume inspect : Name, Driver, Mountpoint, Options.
    """
    volumes = []
    for name in sorted(os.listdir(PATH)):
        folder = os.path.join(PATH, name)
        if not os.path.isdir(folder):
            continue

        # Docker écrit opts.json pour les volumes créés avec des options (nfs, bind...).
        options = {}
        opts_file = os.path.join(folder, "opts.json")
        if os.path.exists(opts_file):
            with open(opts_file) as f:
                saved = json.load(f)
            options = {
                "type": saved.get("MountType", ""),
                "o": saved.get("MountOpts", ""),
                "device": saved.get("MountDevice", ""),
            }

        volumes.append({
            "Name": name,
            "Driver": "local",
            "Mountpoint": os.path.join(folder, "_data"),
            "Options": options,
        })
    ## format de sortie : [{"Name": "nom", "Driver": "local", "Mountpoint": "/var/lib/docker/volumes/nom/_data", "Options": {...}}, ...]
    return volumes


def check_volume(volume):
    """
    Trouve le dossier qui contient les données d'un volume.
    Renvoie (dossier, probleme) ; probleme vaut None si le volume peut être archivé.
    """
    options = volume.get("Options") or {}
    mount_type = options.get("type", "")
    mount_options = options.get("o", "").split(",")

    # Volume "bind" : les données sont dans le dossier source, pas dans _data.
    is_bind = volume.get("Driver") == "local" and "bind" in mount_options
    if is_bind:
        path = options.get("device", "")
    else:
        path = volume["Mountpoint"]

    if is_bind and IN_CONTAINER and not os.path.ismount(path):
        # Sans ce montage, on archiverait un dossier du conteneur au lieu de celui de l'hôte.
        return path, f"volume bind : montez {path} dans le conteneur (-v {path}:{path}:ro)"

    if mount_type not in ("", "none") and not os.path.ismount(path):
        # Un volume nfs/cifs/tmpfs n'est monté que quand un conteneur l'utilise :
        # sinon _data est vide et l'archive le serait aussi.
        return path, f"volume {mount_type} monté seulement quand un conteneur l'utilise"

    if not os.path.isdir(path):
        return path, f"données introuvables : {path}"

    return path, None


def get_docker_volumes():
    """
    Permet de récuperer les volumes Docker présents sur le système.
    Renvoie un dictionnaire {nom: {"path": dossier des données, "problem": None ou message}}.
    """
    global SOURCE

    volumes = None
    # Dans un conteneur, docker donnerait les chemins de l'hôte : on lit le dossier monté.
    if "DOCKERVOL_PATH" not in os.environ and not IN_CONTAINER:
        volumes = list_volumes_with_docker()

    if volumes is None:
        volumes = list_volumes_in_folder()
        SOURCE = PATH
    else:
        SOURCE = "docker volume inspect"

    result = {}
    for volume in volumes:
        path, problem = check_volume(volume)
        result[volume["Name"]] = {"path": path, "problem": problem}
    return result


#### Archivage ####

def list_entries(top):
    """
    Liste tous les chemins sous top : dossiers, fichiers et liens symboliques.
    Les liens ne sont pas suivis (on archive le lien, pas sa cible).
    """
    entries = []
    for root, dirs, files in os.walk(top):
        entries.append(root)
        for d in dirs:
            if os.path.islink(os.path.join(root, d)):
                entries.append(os.path.join(root, d))
        for f in files:
            entries.append(os.path.join(root, f))
    return entries


def get_volume_size(volume_name):
    """
    Taille en octets des fichiers d'un volume (sert à calculer la progression).
    """
    top = get_docker_volumes()[volume_name]["path"]
    total = 0
    for path in list_entries(top):
        if os.path.isfile(path) and not os.path.islink(path):
            total += os.lstat(path).st_size
    return total


class ProgressFile:
    """
    Enveloppe un fichier ouvert : à chaque lecture, appelle progress(nombre d'octets lus).
    tarfile lit le fichier par blocs, ce qui permet de suivre l'avancement.
    """
    def __init__(self, f, progress):
        self.f = f
        self.progress = progress

    def read(self, size=-1):
        data = self.f.read(size)
        if self.progress is not None:
            self.progress(len(data))
        return data


def create_archive(volume_name, progress=None):
    """
    Permet de créer une archive tar.gz d'un volume Docker.
    progress(n), si donné, est appelé avec le nombre d'octets lus à chaque bloc.
    """
    volumes = get_docker_volumes()
    if volume_name not in volumes:
        raise ValueError(f"Volume inconnu : {volume_name}")
    if volumes[volume_name]["problem"]:
        raise ValueError(f"{volume_name} : {volumes[volume_name]['problem']}")

    volume_path = volumes[volume_name]["path"]
    archive_path = os.path.abspath(archive_name(volume_name, datetime.now()))

    try:
        with tarfile.open(archive_path, "w:gz") as tar:
            for path in list_entries(volume_path):
                # Noms dans l'archive : ".", "./fichier", "./dossier/fichier"... comme tar -C dossier .
                relative = os.path.relpath(path, volume_path)
                if relative == ".":
                    name_in_archive = "."
                else:
                    name_in_archive = "./" + relative

                entry = tar.gettarinfo(path, arcname=name_in_archive)
                if entry is None:
                    continue  # socket : impossible à archiver, ignoré comme le fait tar

                if entry.isreg():
                    with open(path, "rb") as f:
                        tar.addfile(entry, ProgressFile(f, progress))
                else:
                    tar.addfile(entry)
    except BaseException:
        # Ne jamais laisser une archive incomplète qui aurait l'air valide.
        if os.path.exists(archive_path):
            os.remove(archive_path)
        raise

    print(f"Archive créée : {archive_path}")
    return archive_path


def archive_name(volume_name, now):
    """
    Nom horodaté : une nouvelle archive n'écrase jamais la précédente.
    """
    return f"{volume_name}_{now:%Y%m%d-%H%M%S}.tar.gz"


def list_archives():
    """
    Archives du dossier courant, la plus récente d'abord : [{"name", "size", "mtime"}].
    """
    result = []
    for path in glob.glob("*.tar.gz"):
        st = os.stat(path)
        result.append({"name": path, "size": st.st_size, "mtime": st.st_mtime})
    return sorted(result, key=lambda a: a["mtime"], reverse=True)


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


#### Conteneurs (arrêt pendant l'archivage) ####

def docker(*args):
    return subprocess.run(["docker", *args], capture_output=True, text=True, check=True).stdout


def docker_available():
    """
    Vrai si la commande docker répond (dans l'image : socket Docker monté).
    """
    try:
        docker("version", "-f", "{{.Server.Version}}")
        return True
    except (OSError, subprocess.CalledProcessError):
        return False


def containers_using(volume_name):
    """
    Identifiants des conteneurs en marche qui utilisent ce volume.
    """
    return docker("ps", "-q", "--filter", f"volume={volume_name}").split()


def stop_containers(ids):
    if ids:
        docker("stop", *ids)


def start_containers(ids):
    if ids:
        docker("start", *ids)


if __name__ == "__main__":
    check_user_permissions()
    for volume in get_docker_volumes():
        print(volume)
