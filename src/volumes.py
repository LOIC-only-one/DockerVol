import os
import sys
import tarfile
import paramiko
import socket
import getpass
import logging
import time
import subprocess
global PATH
PATH = "/var/lib/docker/volumes/"

logging.basicConfig(filename='docker_volume_transfer.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def check_user_permissions():
    if os.geteuid() != 0:
        print("Ce script doit être exécuté avec des privilèges root.")
        sys.exit(1)

def get_docker_volumes():
    """
    Permet de récuperer la liste des volumes Docker présents sur le système.
    """
    volumes = []
    for volume in os.listdir(PATH):
        if os.path.isdir(os.path.join(PATH, volume)):
            volumes.append(volume)
    return volumes

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
    top = os.path.join(PATH, volume_name, "_data")
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
    volume_path = os.path.join(PATH, volume_name, "_data")
    if volume_name not in get_docker_volumes():
        raise ValueError(f"Volume inconnu : {volume_name}")
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
