"""
Réplication et restauration d'un volume sur un serveur distant, par SSH uniquement.

Deux modes :
- "node"   : le volume est recréé sur ce nœud (docker volume create + extraction
             par un conteneur alpine jetable) ;
- "shared" : l'archive est extraite dans <dossier partagé>/<volume> (NFS, GlusterFS...).
Dans les deux cas, rien n'est jamais écrasé.
"""
import os
import shlex
import socket
import uuid

import paramiko

import volumes


def connect(host, user, password=None, key_path=None, port=22):
    """
    Ouvre une connexion SSH par clé (key_path) ou mot de passe.
    """
    client = paramiko.SSHClient()
    # shortcut: clé d'hôte acceptée sans vérification, réservé aux réseaux de confiance.
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(host, port=port, username=user, password=password or None,
                       key_filename=key_path or None, timeout=15)
    except (paramiko.SSHException, socket.error) as e:
        client.close()
        raise RuntimeError(f"Connexion SSH impossible vers {host} : {e}")
    return client


def run(client, command):
    """
    Lance une commande distante. Renvoie (code de sortie, sortie, erreurs).
    """
    _, stdout, stderr = client.exec_command(command)
    code = stdout.channel.recv_exit_status()
    return code, stdout.read().decode(errors="replace"), stderr.read().decode(errors="replace")


def restore_steps(mode, volume, remote_archive, shared_dir=None):
    """
    Commandes de restauration, dans l'ordre : [(commande, message si elle échoue)].
    Chaque commande doit se terminer avec le code 0. La première refuse d'écraser.
    """
    v = shlex.quote(volume)
    archive = shlex.quote(remote_archive)

    if mode == "node":
        folder = shlex.quote(os.path.dirname(remote_archive))
        name = shlex.quote("/a/" + os.path.basename(remote_archive))
        return [
            (f"! docker volume inspect {v} >/dev/null 2>&1",
             f"le volume {volume} existe déjà sur ce nœud (rien n'est écrasé)"),
            (f"docker volume create {v} >/dev/null", "docker volume create a échoué"),
            (f"docker run --rm -v {v}:/v -v {folder}:/a:ro alpine tar xzf {name} -C /v",
             "extraction dans le volume impossible"),
        ]

    if mode == "shared":
        if not shared_dir:
            raise ValueError("dossier partagé manquant")
        target = shlex.quote(shared_dir.rstrip("/") + "/" + volume)
        return [
            (f'[ -z "$(ls -A {target} 2>/dev/null)" ]',
             f"{shared_dir.rstrip('/')}/{volume} n'est pas vide (rien n'est écrasé)"),
            (f"mkdir -p {target}", "impossible de créer le dossier"),
            (f"tar xzf {archive} -C {target}", "extraction impossible"),
        ]

    raise ValueError(f"mode inconnu : {mode}")


def migrate(client, local_path, volume, mode, shared_dir, start_phase, on_progress):
    """
    Envoie l'archive, vérifie son sha256 sur place, puis la restaure.
    start_phase(nom, total) et on_progress(envoyés, total) mettent à jour la tâche.
    Renvoie une description de la destination.
    """
    remote_archive = f"/tmp/dockervol-{uuid.uuid4().hex}.tar.gz"
    steps = restore_steps(mode, volume, remote_archive, shared_dir)

    # Refus d'écrasement vérifié avant d'envoyer des gigaoctets pour rien.
    code, _, _ = run(client, steps[0][0])
    if code != 0:
        raise RuntimeError(steps[0][1])

    try:
        start_phase("Transfert", os.path.getsize(local_path))
        sftp = client.open_sftp()
        try:
            sftp.put(local_path, remote_archive, callback=on_progress)
        finally:
            sftp.close()

        start_phase("Vérification sha256", 0)
        code, out, err = run(client, f"sha256sum {shlex.quote(remote_archive)}")
        if code != 0:
            raise RuntimeError(f"sha256sum distant impossible : {err.strip()}")
        if out.split()[0] != volumes.sha256_file(local_path):
            raise RuntimeError("l'archive reçue est différente de l'originale (sha256)")

        start_phase("Restauration", 0)
        for command, message in steps:
            code, _, err = run(client, command)
            if code != 0:
                raise RuntimeError(f"{message}{' : ' + err.strip() if err.strip() else ''}")
    finally:
        run(client, f"rm -f {shlex.quote(remote_archive)}")

    if mode == "node":
        return f"volume {volume} sur le nœud"
    return f"{shared_dir.rstrip('/')}/{volume}"
