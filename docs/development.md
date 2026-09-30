# Développement

Commandes vérifiées lors de la Phase 13 (Windows + Git Bash ; adapter l'activation du venv
sous Linux / macOS : `source .venv/bin/activate`).

## Prérequis

- Docker Desktop (PostgreSQL 16 en conteneur)
- Python 3.11 (virtualenv `backend/.venv`)
- Node.js ≥ 20 (le build Docker utilise Node 22 LTS)

## Configuration

```bash
cp .env.example .env            # puis renseigner POSTGRES_PASSWORD (jamais commité)
```

## Base de données (développement)

```bash
docker compose up -d postgres   # uniquement PostgreSQL
```

## Backend

```bash
cd backend
python -m venv .venv
.venv/Scripts/activate           # Windows (Git Bash) ; Linux/macOS : source .venv/bin/activate
pip install -r requirements-dev.txt
alembic upgrade head
uvicorn app.main:app --reload    # http://localhost:8000 — docs : /docs (hors production)
```

Import de transactions (structuré, jamais automatique) :

```bash
python -m scraping import-deals --file deals.json --actor analyste-1 --dry-run
python -m scraping import-deals --file deals.json --actor analyste-1
```

## Frontend

```bash
cd frontend
npm install
npm run dev                      # http://localhost:3000/fr
```

## Tests et qualité

```bash
# Backend (depuis backend/)
ruff check .
pytest -q                        # unitaires + intégration PostgreSQL
alembic check                    # modèles ORM == schéma migré

# Frontend (depuis frontend/)
npm run lint
npm test                         # Vitest
npm run build
```

### Tests d'intégration PostgreSQL

Les fichiers `tests/test_*_postgres*.py` créent chacun une base temporaire
`<POSTGRES_DB>_<phase>_pytest` sur le serveur configuré dans `.env`, appliquent les migrations,
puis la suppriment. **Ils sont ignorés (`skipped`) si aucun serveur PostgreSQL ne répond** :
vérifier que le compte `skipped` vaut 0 (`pytest -q -rs`) avant de conclure. Le rôle PostgreSQL
doit pouvoir créer des bases.

### Tester les migrations sur une base temporaire

```bash
# créer une base vide (ex. umoa_tmp) puis, depuis backend/ :
DATABASE_URL= POSTGRES_DB=umoa_tmp alembic upgrade head
DATABASE_URL= POSTGRES_DB=umoa_tmp alembic downgrade base
DATABASE_URL= POSTGRES_DB=umoa_tmp alembic upgrade head
```

`DATABASE_URL=` (vide) force la construction du DSN depuis les variables `POSTGRES_*`.

## Règles

- Voir `docs/dev-rules.md`, `docs/data-quality.md` et `docs/specification-v1.md`.
- Aucune valeur inventée, aucun 0 à la place d'une donnée absente, aucune conversion de devise.
- Aucun vocabulaire évaluatif (meilleur, pire, top, leader, recommandation…) : garde automatique
  dans `frontend/src/__tests__/contract.test.ts` (dictionnaires FR/EN + tout le code `src/`).
