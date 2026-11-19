# Changelog

Toutes les modifications notables de ce projet sont consignées ici.

Le format suit [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/) et le projet respecte le [Semantic Versioning](https://semver.org/lang/fr/).

## [Unreleased]

### Ajouté
- Workflow GitHub Actions : build de l'image Docker et publication sur GHCR (`latest`, branche, SHA, tags semver).
- `.dockerignore`.
- Logo SVG (`src/static/logo.svg`), utilisé dans l'interface, comme favicon et dans le README.

### Modifié
- Dockerfile : base `python:3.13-alpine` (au lieu d'`alpine:3.18`, en fin de vie), dépendances installées depuis `requirements.txt`, archives écrites dans le volume `/archives`, port 5000 exposé.
- Interface plus sobre : en-tête neutre avec logo, plus de dégradé ni d'emoji, tableau et formulaires plus compacts.

### Corrigé
- L'image plantait au démarrage : `paramiko` n'était pas installé.

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
