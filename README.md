<p align="center"><img src="src/static/logo.svg" width="96" alt="DockerVol"></p>

<h1 align="center">DockerVol</h1>

<p align="center">Sauvegarde et réplication de volumes Docker via une interface web légère.</p>

DockerVol liste les volumes Docker d'un hôte, les archive en `tar.gz` et peut les répliquer vers un serveur distant via SSH/SFTP, depuis une interface web Flask.

## Fonctionnalités

- **Inventaire** des volumes via l'API Docker : emplacement réel de chaque volume, quelle que soit l'installation (voir [Emplacement des volumes](#emplacement-des-volumes))
- **Archivage** d'un volume ou de tous les volumes en `tar.gz`
- **Réplication** d'un volume vers un serveur distant (SSH + SFTP)
- **Suivi des tâches** : barre de progression et temps restant pour l'archivage et le transfert
- **Interface web** claire, avec thème clair/sombre automatique
- **Journalisation** des erreurs dans `docker_volume_transfer.log`

## Prérequis

- Linux avec Docker
- Python ≥ 3.9
- Droits **root** (lecture des volumes Docker)

## Installation

```bash
git clone <url-du-depot> dockervol
cd dockervol
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Utilisation

```bash
sudo .venv/bin/python main.py
```

Puis ouvrir <http://127.0.0.1:5000>.

### Avec Docker

L'image est publiée sur GitHub Container Registry :

```bash
docker run -d --name dockervol \
  -p 127.0.0.1:5000:5000 \
  -v /var/lib/docker/volumes:/var/lib/docker/volumes:ro \
  -v "$PWD/archives:/archives" \
  ghcr.io/<owner>/<repo>:latest
```

- `/var/lib/docker/volumes` est monté en **lecture seule** : DockerVol ne fait que lire les volumes.
- Sans le socket Docker, l'image lit simplement ce dossier. Si votre `data-root` est ailleurs, montez-le à la place (`-v /mon/data-root/volumes:/var/lib/docker/volumes:ro`).
- Les archives et le fichier de log sont écrits dans `/archives`.
- `-p 127.0.0.1:5000:5000` garde l'interface accessible uniquement depuis l'hôte (voir [Sécurité](#sécurité)).

Construire l'image localement :

```bash
docker build -t dockervol .
```

### Variables d'environnement

| Variable           | Défaut           | Rôle                                          |
|--------------------|------------------|-----------------------------------------------|
| `DOCKERVOL_HOST`   | `127.0.0.1` (`0.0.0.0` dans l'image) | Adresse d'écoute de l'interface |
| `DOCKERVOL_PORT`   | `5000`           | Port d'écoute                                  |
| `DOCKERVOL_SECRET` | aléatoire        | Clé de session Flask (à fixer en production)  |
| `DOCKERVOL_PATH`   | non défini       | Force la lecture de ce dossier au lieu de l'API Docker |
| `DOCKER_HOST`      | non défini       | Socket Docker à utiliser (`unix://…` uniquement) |

### Ligne de commande

Lister les volumes sans l'interface :

```bash
sudo python3 src/volumes.py
```

## Emplacement des volumes

DockerVol interroge l'API Docker (`GET /volumes`) pour connaître le chemin réel de chaque volume. Socket utilisé, dans l'ordre : `DOCKER_HOST` (si `unix://`), `/var/run/docker.sock`, puis `/run/user/*/docker.sock` (Docker rootless). Si aucun n'est joignable, il lit le dossier `/var/lib/docker/volumes/` (ou `DOCKERVOL_PATH`).

| Installation                                   | Prise en charge |
|------------------------------------------------|-----------------|
| Docker standard                                | Oui |
| `data-root` personnalisé (`daemon.json`)       | Oui, via l'API |
| Docker rootless                                | Oui, via `/run/user/<uid>/docker.sock` |
| Docker snap                                    | Oui, via l'API |
| Volume `bind` (`--opt o=bind --opt device=…`)  | Oui : le dossier source est archivé |
| Volume NFS / CIFS / tmpfs                      | Seulement s'il est monté (un conteneur l'utilise) ; sinon le volume est signalé et non archivable |
| Driver tiers (plugin)                          | Si son point de montage est accessible depuis l'hôte |
| Docker Desktop (macOS / Windows)               | Non : les volumes sont dans la VM de Docker Desktop |
| `DOCKER_HOST` en `tcp://` / `ssh://`           | Non : lecture du dossier à la place |

Les volumes non archivables sont affichés avec la raison, et leur bouton est désactivé. La source utilisée est indiquée en haut à droite de l'interface.

## Structure du projet

```
.
├── main.py              # Point d'entrée (lance l'interface web)
├── requirements.txt
├── Dockerfile
├── CHANGELOG.md
├── .github/workflows/
│   └── docker.yml       # Build et publication de l'image sur GHCR
└── src/
    ├── runtime.py       # Interface web (routes Flask)
    ├── volumes.py       # Logique : volumes, archives, SSH/SFTP
    ├── static/          # Logo et polices (IBM Plex, licence OFL)
    └── templates/       # Gabarits Jinja (base.j2, index.j2)
```

Les archives sont créées dans le répertoire courant (`/archives` dans l'image), sous le nom `<volume>.tar.gz`.

## Intégration continue

Le workflow [.github/workflows/docker.yml](.github/workflows/docker.yml) construit l'image à chaque push et pull request, et la publie sur `ghcr.io/<owner>/<repo>` :

| Événement               | Tags publiés                                 |
|-------------------------|----------------------------------------------|
| Push sur `main`         | `main`, `latest`, `sha-<commit>`             |
| Tag `v1.2.3`            | `1.2.3`, `1.2`, `sha-<commit>`               |
| Pull request            | Image construite, **non publiée**            |

Publier une version :

```bash
git tag v0.1.0
git push origin v0.1.0
```

> Au premier push, le paquet GHCR est privé : rendez-le public dans *GitHub → Packages → dockervol → Package settings* si besoin.

## Sécurité

L'interface **n'a pas d'authentification** et tourne en root.

- Elle écoute uniquement sur `127.0.0.1` par défaut. Pour un accès distant, passez par un tunnel SSH (`ssh -L 5000:127.0.0.1:5000 hôte`) ou un reverse proxy avec authentification.
- Les clés d'hôte SSH distantes sont acceptées automatiquement (`AutoAddPolicy`) : réservé aux réseaux de confiance.
- Les mots de passe SSH ne sont ni stockés ni journalisés.

## Personnalisation

La couleur principale de l'interface se règle avec la variable `--primary` dans [src/templates/base.j2](src/templates/base.j2).

## Feuille de route

- [ ] Authentification de l'interface
- [ ] Authentification SSH par clé
- [ ] Restauration d'une archive vers un volume
- [x] Image Docker du projet

## Changelog

Voir [CHANGELOG.md](CHANGELOG.md).

## Licence

À définir.
