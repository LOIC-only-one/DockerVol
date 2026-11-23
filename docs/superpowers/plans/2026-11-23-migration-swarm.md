# Migration vers Swarm — plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans (choix : natif). Étapes en `- [ ]`.

**Goal:** migrer des volumes vers un nœud Swarm ou un stockage partagé via SSH, avec vérification sha256, arrêt optionnel des conteneurs, lots, archives horodatées et UI refondue.

**Architecture:** `volumes.py` (local : volumes, archives, conteneurs), nouveau `remote.py` (SSH : connexion, envoi, commandes de restauration pures et testables), `runtime.py` (file de tâches + routes), templates refondus.

**Tech Stack:** Python 3.13, Flask, paramiko, tarfile, hashlib ; tests `unittest` (pas de nouvelle dépendance).

**Spec:** `docs/superpowers/specs/2026-11-23-migration-swarm-design.md`

## Global Constraints
- Jamais écraser un volume / dossier partagé non vide sur la cible.
- Conteneurs arrêtés toujours relancés (`finally`).
- Toute commande distante construite avec `shlex.quote`.
- Pas de nouvelle dépendance Python. Image : `apk add docker-cli`.
- Interface en français, charte existante (`--primary`, Atkinson/IBM Plex).

## Review Focus
1. Nom de volume avec caractères spéciaux (`a.b_c-d`) → commandes correctement quotées (test Task 2).
2. Volume déjà présent sur le nœud → échec « existe déjà », rien d'extrait (test Task 2 : commande de refus en tête).
3. Archive corrompue en transit → échec sha256, pas de restauration (ordre vérifié Task 2).
4. Échec d'archivage avec conteneurs arrêtés → conteneurs relancés (Task 3, `finally`).
5. Téléchargement/suppression d'archive avec `../` → refusé (Task 3 : nom validé contre `list_archives()`).

---

### Task 1 : volumes.py — archives horodatées, liste, sha256, conteneurs
**Files:** Modify `src/volumes.py` ; Test `tests/test_volumes.py`
**Produces:**
- `archive_name(volume: str, now: datetime) -> str` → `"<volume>_AAAAMMJJ-HHMMSS.tar.gz"`
- `create_archive(volume, progress=None) -> str` (chemin absolu, nom horodaté)
- `list_archives() -> list[dict(name, size, mtime)]` (fichiers `*.tar.gz` du dossier courant, plus récent d'abord)
- `sha256_file(path) -> str`
- `docker_available() -> bool` ; `containers_using(volume) -> list[str]` ; `stop_containers(ids)` ; `start_containers(ids)`
- Dans un conteneur (`IN_CONTAINER`), la liste vient toujours du dossier (chemins de l'hôte ≠ chemins du conteneur).
- [ ] Test `archive_name("a.b", datetime(2026,11,23,9,5,7)) == "a.b_20261123-090507.tar.gz"` ; `sha256_file` d'un fichier `b"abc"` == `ba7816bf…15ad`.
- [ ] Implémenter, `python -m unittest discover tests` → OK, commit.

### Task 2 : remote.py — SSH et restauration
**Files:** Create `src/remote.py` ; Modify `src/volumes.py` (retirer le SSH) ; Test `tests/test_remote.py`
**Produces:**
- `connect(host, user, password=None, key_path=None, port=22) -> SSHClient` (lève `RuntimeError` avec message clair)
- `restore_steps(mode: "node"|"shared", volume, remote_archive, shared_dir=None) -> list[tuple[str, str]]` : (commande, message d'erreur), chaque commande doit sortir en 0. Node : refus si `docker volume inspect` réussit, `docker volume create`, `docker run --rm -v V:/v -v DIR:/a:ro alpine tar xzf /a/FICHIER -C /v`. Shared : refus si `<dir>/<V>` non vide, `mkdir -p`, `tar xzf`.
- `migrate(client, local_path, volume, mode, shared_dir, start_phase, on_progress) -> str` : envoi SFTP vers `/tmp/dockervol-<uuid>.tar.gz`, `sha256sum` distant comparé, étapes, `rm -f` en `finally`.
- [ ] Tests : volume `"a b"` quoté ; première étape = refus ; mode shared sans dossier → `ValueError`.
- [ ] Implémenter, tests OK, commit.

### Task 3 : runtime.py — tâches et routes
**Files:** Modify `src/runtime.py`
- Tâche : `{volume, action: "archive"|"migrate", stop: bool, target: dict|None}` ; arrêt/relance autour de l'archivage.
- Routes : `POST /archive` (champs `names[]`, `stop`), `POST /migrate` (+ host, port, user, password, key_path, mode, shared_dir), `GET /sizes` (JSON), `GET /jobs`, `GET /archives/<name>` (téléchargement), `POST /archives/<name>/delete`. Nom d'archive accepté seulement s'il est dans `list_archives()`.
- [ ] Vérif : `app.test_client()` → `/`, `/sizes`, `/jobs` = 200 ; `/archives/..%2Fetc` = 404. Commit.

### Task 4 : UI
**Files:** Modify `src/templates/base.j2`, `src/templates/index.j2`
- Tableau volumes : case, nom, taille (via `/sizes`), problème ; filtre ; barre d'actions (n sélectionnés, Archiver, Migrer, case « arrêter les conteneurs » grisée si `docker_available()` faux).
- Formulaire migration : hôte, port, utilisateur, mot de passe ou chemin de clé, mode (nœud / partagé + dossier).
- Section archives : nom, taille, date, Télécharger, Supprimer. Section tâches existante conservée.
- [ ] Vérif : lancer l'app avec `DOCKERVOL_PATH` sur un dossier de test, capture de la page. Commit.

### Task 5 : Image et docs
**Files:** `Dockerfile`, `README.md`, `CHANGELOG.md`
- [ ] `apk add --no-cache docker-cli` ; README : migration Swarm (2 modes, prérequis cible, socket `-v /var/run/docker.sock:/var/run/docker.sock` pour l'arrêt des conteneurs) ; CHANGELOG. Commit.
