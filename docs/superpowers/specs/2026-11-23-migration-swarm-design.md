# DockerVol : migration vers Swarm — design

## Intention
Outil réel pour migrer les volumes d'un serveur Docker legacy vers un cluster Swarm, en une interface, sans rien installer sur la cible (SSH uniquement).

## Objectifs
1. **Restauration distante**, 2 modes :
   - *Nœud* : `docker volume create <nom>` puis extraction via conteneur jetable `alpine` sur le nœud choisi.
   - *Partagé* : `tar xzf` dans `<dossier partagé>/<nom>` (NFS/Gluster/Ceph monté sur le nœud SSH).
2. **Intégrité** : sha256 local comparé à `sha256sum` distant avant restauration ; archive distante temporaire supprimée après.
3. **Cohérence** : option « arrêter les conteneurs pendant l'archivage » (`docker ps -q --filter volume=<nom>`), relance garantie en `finally`.
4. **Lot** : cases à cocher sur les volumes, actions « Archiver » et « Migrer » sur la sélection.
5. **SSH par clé** (chemin de clé sur l'hôte DockerVol) ou mot de passe ; port configurable.
6. **Archives** horodatées `<volume>_<AAAAMMJJ-HHMMSS>.tar.gz` ; section listant les archives (taille, date, télécharger, supprimer).
7. **UI** : refonte (tableau avec cases, taille de chaque volume chargée en asynchrone, filtre de recherche, barre d'actions, formulaire de migration avec choix du mode), même charte (couleurs, polices).

## Non-objectifs
- Pas d'authentification de l'interface (reste sur 127.0.0.1).
- Pas de profils de cibles enregistrés, pas de planification.
- Pas de restauration locale.

## Anti-objectifs
- **Jamais écraser** : si le volume existe déjà sur le nœud, ou si le dossier partagé n'est pas vide, la tâche échoue avec un message clair.
- Jamais laisser un conteneur arrêté après une erreur.
- Aucune injection : toutes les commandes distantes passent par `shlex.quote`.

## Contraintes
- Cible : SSH + Docker (mode nœud, utilisateur root ou groupe docker, image `alpine` tirable) ou droit d'écriture (mode partagé).
- Image DockerVol : ajouter `docker-cli` (apk) ; l'arrêt des conteneurs n'est disponible que si `docker` répond (socket monté), sinon l'option est grisée.
- Clés d'hôte : `AutoAddPolicy` conservé (documenté).

## Approches
- **A (retenue)** : tout par SSH depuis le serveur source, rien sur la cible.
- B : DockerVol installé sur chaque nœud avec un bouton Restaurer — trop de manipulations pour une migration.
- C : `docker -H ssh://` — équivalent à A, n'aide pas le mode partagé.

## Laissé au builder
Découpage du code (`volumes.py` logique, `remote.py` SSH/restauration si utile), style exact de l'UI, tests ciblés (nom d'archive, construction des commandes distantes, refus d'écrasement).
