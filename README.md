# 🐳 DockerVol

> Sauvegarde et réplication de volumes Docker via une interface web légère.

DockerVol liste les volumes Docker d'un hôte, les archive en `tar.gz` et peut les répliquer vers un serveur distant via SSH/SFTP, depuis une interface web Flask.

## Fonctionnalités

- 📦 **Inventaire** des volumes présents dans `/var/lib/docker/volumes/`
- 🗜️ **Archivage** d'un volume ou de tous les volumes en `tar.gz`
- 🚀 **Réplication** d'un volume vers un serveur distant (SSH + SFTP)
- 🖥️ **Interface web** claire, avec thème clair/sombre automatique
- 📝 **Journalisation** des erreurs dans `docker_volume_transfer.log`

## Prérequis

- Linux avec Docker (accès à `/var/lib/docker/volumes/`)
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

### Variables d'environnement

| Variable           | Défaut           | Rôle                                          |
|--------------------|------------------|-----------------------------------------------|
| `DOCKERVOL_HOST`   | `127.0.0.1`      | Adresse d'écoute de l'interface               |
| `DOCKERVOL_PORT`   | `5000`           | Port d'écoute                                  |
| `DOCKERVOL_SECRET` | aléatoire        | Clé de session Flask (à fixer en production)  |

### Ligne de commande

Lister les volumes sans l'interface :

```bash
sudo python3 src/volumes.py
```

## Structure du projet

```
.
├── main.py              # Point d'entrée (lance l'interface web)
├── requirements.txt
├── CHANGELOG.md
└── src/
    ├── runtime.py       # Interface web (routes Flask)
    ├── volumes.py       # Logique : volumes, archives, SSH/SFTP
    └── templates/       # Gabarits Jinja (base.j2, index.j2)
```

Les archives sont créées dans le répertoire courant, sous le nom `<volume>.tar.gz`.

## Sécurité

⚠️ L'interface **n'a pas d'authentification** et tourne en root.

- Elle écoute uniquement sur `127.0.0.1` par défaut. Pour un accès distant, passez par un tunnel SSH (`ssh -L 5000:127.0.0.1:5000 hôte`) ou un reverse proxy avec authentification.
- Les clés d'hôte SSH distantes sont acceptées automatiquement (`AutoAddPolicy`) : réservé aux réseaux de confiance.
- Les mots de passe SSH ne sont ni stockés ni journalisés.

## Personnalisation

La couleur principale de l'interface se règle avec la variable `--primary` dans [src/templates/base.j2](src/templates/base.j2).

## Feuille de route

- [ ] Authentification de l'interface
- [ ] Authentification SSH par clé
- [ ] Restauration d'une archive vers un volume
- [ ] Image Docker du projet

## Changelog

Voir [CHANGELOG.md](CHANGELOG.md).

## Licence

À définir.
