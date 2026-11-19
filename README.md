<p align="center"><img src="src/static/logo.svg" width="96" alt="DockerVol"></p>

<h1 align="center">DockerVol</h1>

<p align="center">Sauvegarde et réplication de volumes Docker via une interface web légère.</p>

DockerVol liste les volumes Docker d'un hôte, les archive en `tar.gz` et peut les répliquer vers un serveur distant via SSH/SFTP, depuis une interface web Flask.

## Fonctionnalités

- **Inventaire** des volumes avec leur emplacement réel, quelle que soit l'installation de Docker (voir [Emplacement des volumes](#emplacement-des-volumes))
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

Une seule commande, quelle que soit l'installation de Docker (standard, `data-root` personnalisé, rootless, snap). Choisissez l'une des deux méthodes.

**Avec Python** (depuis le dossier du projet, après l'[installation](#installation)) :

```bash
sudo DOCKER_HOST="$(docker context inspect -f '{{.Endpoints.docker.Host}}')" .venv/bin/python main.py
```

**Avec Docker** (image publiée sur GitHub Container Registry) :

```bash
docker run -d --name dockervol \
  -p 127.0.0.1:5000:5000 \
  -v "$(docker info -f '{{.DockerRootDir}}')/volumes:/var/lib/docker/volumes:ro" \
  -v "$PWD/archives:/archives" \
  ghcr.io/<owner>/<repo>:latest
```

Puis ouvrir <http://127.0.0.1:5000>.

Ce que font ces commandes :

- `docker context inspect` / `docker info` demandent à Docker où il se trouve : rien n'est écrit en dur, donc la même commande marche partout.
- `sudo` est nécessaire en Python : les volumes ne sont lisibles qu'en root.
- Les volumes sont montés en **lecture seule** (`:ro`) : DockerVol ne fait que les lire.
- Les archives et le fichier de log sont écrits dans `./archives` (Docker) ou le dossier courant (Python).
- `127.0.0.1` garde l'interface accessible uniquement depuis la machine (voir [Sécurité](#sécurité)).

Construire l'image soi-même : `docker build -t dockervol .`

Lister les volumes sans l'interface : `sudo .venv/bin/python src/volumes.py`

### Variables d'environnement

| Variable           | Défaut           | Rôle                                          |
|--------------------|------------------|-----------------------------------------------|
| `DOCKERVOL_HOST`   | `127.0.0.1` (`0.0.0.0` dans l'image) | Adresse d'écoute de l'interface |
| `DOCKERVOL_PORT`   | `5000`           | Port d'écoute                                  |
| `DOCKERVOL_SECRET` | aléatoire        | Clé de session Flask (à fixer en production)  |
| `DOCKERVOL_PATH`   | non défini       | Force la lecture de ce dossier de volumes au lieu de la commande `docker` |

## Emplacement des volumes

En Python, DockerVol utilise `docker volume inspect` pour connaître le dossier exact de chaque volume. Si la commande `docker` n'est pas disponible (c'est le cas dans l'image), il lit le dossier des volumes et le fichier `opts.json` que Docker écrit pour les volumes créés avec des options.

| Cas                                            | Prise en charge |
|------------------------------------------------|-----------------|
| Docker standard, `data-root` personnalisé, rootless, snap | Oui |
| Volume `bind` (`--opt o=bind --opt device=…`)  | Oui : le dossier source est archivé. Avec l'image Docker, montez aussi ce dossier : `-v /source:/source:ro` |
| Volume NFS / CIFS / tmpfs                      | Seulement quand il est monté (un conteneur l'utilise) ; sinon il est signalé et non archivable |
| Driver tiers (plugin)                          | Si son point de montage est accessible |
| Docker Desktop (macOS / Windows)               | Non : les volumes sont dans la machine virtuelle de Docker Desktop |

Un volume qui ne peut pas être archivé est affiché avec la raison, et son bouton est désactivé : DockerVol ne produit jamais d'archive vide par erreur. La source utilisée est indiquée en haut à droite de l'interface.

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
    ├── static/          # Logo et polices (Atkinson Hyperlegible, IBM Plex Mono ; licence OFL)
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
