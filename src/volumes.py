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

def create_archive(volume_name):
    """
    Permet de créer une archive tar.gz d'un volume Docker.
    """
    volume_path = os.path.join(PATH, volume_name, "_data")
    if volume_name not in get_docker_volumes():
        raise ValueError(f"Volume inconnu : {volume_name}")
    archive_name = os.path.abspath(f"{volume_name}.tar.gz")
    subprocess.run(["tar", "-czf", archive_name, "-C", volume_path, "."], check=True)
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

def transfer_archive(client, local_path, remote_path):
    """
    Permet de transférer une archive tar.gz vers un serveur distant via SFTP.
    """
    try:
        sftp = client.open_sftp()
        sftp.put(local_path, remote_path)
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
