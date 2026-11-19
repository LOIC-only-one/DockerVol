# Changelog

Toutes les modifications notables de ce projet sont consignées ici.

Le format suit [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/) et le projet respecte le [Semantic Versioning](https://semver.org/lang/fr/).

## [Unreleased]

## [0.1.0] - 2026-11-19

### Ajouté
- Interface web Flask : liste des volumes, archivage unitaire ou global, réplication SSH.
- Point d'entrée `main.py` (écoute sur `127.0.0.1:5000` par défaut, configurable par variables d'environnement).
- `README.md`, `CHANGELOG.md`, `requirements.txt`.

### Modifié
- `src/inspect.py` renommé en `src/volumes.py` (le nom masquait le module standard `inspect` utilisé par Flask) ; `src/runtime.py` contient l'interface Flask.
- `create_archive` renvoie le chemin de l'archive et vérifie que le volume existe.
- `transfer_archive` renvoie `True`/`False` selon le résultat.

### Sécurité
- `create_archive` n'utilise plus `shell=True` (risque d'injection de commande via le nom du volume).
