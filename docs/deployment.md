# Déploiement

## 1. Pile Docker Compose

| Service | Image | Port hôte | Santé |
|---|---|---|---|
| `postgres` | `postgres:16-alpine` | `${POSTGRES_PORT:-5432}` | `pg_isready` |
| `backend` | `backend/Dockerfile` (Python 3.11, utilisateur `app`) | `${BACKEND_PORT:-8000}` | `GET /api/v1/health` = 200 |
| `frontend` | `frontend/Dockerfile` (Node 22, Next.js standalone, utilisateur `node`) | `${FRONTEND_PORT:-3000}` | `GET /fr` = 200 |

Ordre de démarrage : `postgres` sain → `backend` (applique `alembic upgrade head`, puis démarre
uvicorn ; ne démarre pas si une migration échoue) → `frontend`.

```bash
cp .env.example .env        # renseigner POSTGRES_PASSWORD, APP_ENV=production, CORS_ORIGINS
docker compose config --quiet
docker compose up -d --build
docker compose ps           # les trois services doivent être "healthy"
```

Volumes : `postgres_data` (base), `documents_data` (documents téléchargés).
`docker compose down` conserve les données ; `docker compose down -v` les **supprime**.

## 2. Variables d'environnement (voir `.env.example`, placeholders uniquement)

| Variable | Rôle |
|---|---|
| `APP_ENV` | `production` : docs API (`/docs`, `/redoc`, `/openapi.json`) désactivées, logs JSON, garde-fous de configuration |
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | base ; le mot de passe est obligatoire et n'est jamais écrit dans les fichiers versionnés |
| `CORS_ORIGINS` | origines explicites ; `*` est **refusé** en production (le backend ne démarre pas) |
| `BACKEND_DEBUG` | doit être `false` en production (sinon refus de démarrer) |
| `NEXT_PUBLIC_API_URL` | URL de l'API vue par le navigateur (figée au build de l'image frontend) |
| `INTERNAL_API_URL` | URL de l'API pour le rendu serveur (compose : `http://backend:8000`) |

> Le `.env` racine prime sur les valeurs par défaut du compose : pour un déploiement de production,
> `APP_ENV=production` doit y figurer explicitement.

## 3. Sécurité

- En-têtes sur toutes les réponses API : `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
  `Referrer-Policy: strict-origin-when-cross-origin` ; pas d'en-tête `Server` ni `X-Powered-By`.
- Erreurs au format `{"error": {"code", "message", "details"}}` (y compris 404 / 405 de routage) ;
  jamais de trace de pile côté client (journalisée côté serveur uniquement).
- `/api/v1/health` : 200 si la base répond, **503** sinon ; aucun hôte, port ni message du pilote n'est renvoyé.
- Journal d'accès applicatif : méthode, chemin, statut, durée — jamais corps, en-têtes, query string ni secret.
- Export CSV : cellules commençant par `=`, `+`, `-`, `@` neutralisées (injection de formules).
- Conteneurs non-root, aucun secret dans les images.
- **Pas d'authentification** (voir §6) : exposer la plateforme uniquement derrière un accès restreint
  (VPN, reverse proxy authentifiant, TLS terminé au proxy).

## 4. Sauvegarde / restauration

```bash
scripts/backup.sh                         # base POSTGRES_DB du conteneur → backups/<db>_<horodatage>.dump
scripts/backup.sh umoa_banking out.dump   # base et fichier explicites
scripts/restore.sh out.dump umoa_restore  # restaure dans une NOUVELLE base (refuse d'écraser)
```

- `PG_CONTAINER` : nom du conteneur PostgreSQL (défaut `umoa_postgres`).
- `pg_dump` / `pg_restore` s'exécutent dans le conteneur avec ses propres identifiants : aucun mot de
  passe sur la ligne de commande ni dans les fichiers.
- Format `custom` : schéma, contraintes, index, données, provenance et piste d'audit.
- La restauration se fait toujours dans une base neuve, en une transaction, arrêt à la première erreur ;
  basculer ensuite explicitement (`POSTGRES_DB`) après vérification.
- `backups/` et `*.dump` sont ignorés par Git.

## 5. Migrations

Appliquées automatiquement au démarrage du backend (`alembic upgrade head`, idempotent).
Retour arrière : `alembic downgrade <révision>` dans le conteneur backend, après sauvegarde. La
descente sous `0007` est refusée tant que des événements d'audit de transactions existent
(aucune perte silencieuse de piste d'audit).

## 6. Known limitations

Limites constatées lors de l'audit final (Phase 13) :

- **Aucune authentification ni autorisation** : `actor` des décisions est déclaré par l'opérateur.
- Piste d'audit append-only garantie par le code applicatif (test automatique), pas par un trigger
  ou des droits PostgreSQL.
- Le périmètre (individuel / consolidé) des observations extraites n'est pas détecté : elles sont
  placées en `needs_review` avec la note `scope not detected` jusqu'à confirmation humaine.
- Pas d'extracteur automatique de transactions : Deal Intelligence est alimenté par import structuré.
- Listes de doublons / conflits d'observations paginées en Python après calcul complet (adapté au
  volume V1, à revoir si le volume croît fortement).
- Les tests d'intégration PostgreSQL sont ignorés (`skipped`) si aucun serveur ne répond : vérifier
  `skipped = 0`.
- `NEXT_PUBLIC_API_URL` est figée au build de l'image frontend (reconstruire l'image si elle change).
