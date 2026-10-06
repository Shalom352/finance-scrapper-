# UMOA Banking Intelligence

Plateforme de collecte, structuration et exploitation des données financières des établissements bancaires de l'Union Monétaire Ouest-Africaine (UMOA) — **Bank Financial Intelligence + Deal Intelligence**.

```
Sources officielles → Discovery → Download → Storage → Parsing → Normalization → Validation
→ PostgreSQL → FastAPI → Next.js (Dashboard / Recherche / Analytics / Classements / Transactions / Review Center)
```

---

## Objectif

Fournir une base de données financière fiable, traçable et exploitable sur les banques et institutions financières des 8 pays de l'UMOA :
Bénin, Burkina Faso, Côte d'Ivoire, Guinée-Bissau, Mali, Niger, Sénégal, Togo.

## Versions

| Version | Nom | Objectif |
|---------|-----|---------|
| V1 | Data Platform | Collecte, structuration, historisation |
| V2 | AI Banking Intelligence | Veille automatique, extraction IA, alertes |
| V3 | UMOA Financial Intelligence | M&A, obligations, actionnaires, API |

---

## Démarrage rapide

### Prérequis

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installé et démarré
- [Python 3.11+](https://www.python.org/)
- [Node.js 20+](https://nodejs.org/) (image Docker : Node 22)

Stack : FastAPI · Pydantic v2 · SQLAlchemy 2 (async) · PostgreSQL 16 · Alembic · Next.js 16 · TypeScript · Tailwind 4 · next-intl (FR/EN) · pytest · Vitest · Docker.

### 1. Cloner le repository

```bash
git clone https://github.com/Shalom352/finance-scrapper-.git
cd finance-scrapper-
```

### 2. Configurer l'environnement

```bash
cp .env.example .env
# Éditer .env avec vos valeurs (le mot de passe PostgreSQL en particulier)
```

### 3. Démarrer PostgreSQL

```bash
docker compose up -d postgres
```

> Pile complète conteneurisée (PostgreSQL + API + interface, migrations au démarrage) :
> `docker compose up -d --build` — voir [docs/deployment.md](./docs/deployment.md).

### 4. Démarrer le backend

```bash
cd backend
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/Mac
source .venv/bin/activate

pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload
```

Le backend est disponible sur http://localhost:8000
Documentation API : http://localhost:8000/docs (désactivée si `APP_ENV=production`)

### 5. Démarrer le frontend

```bash
cd frontend
npm install
npm run dev
```

Le frontend est disponible sur http://localhost:3000

---

## Structure du projet

```
finance-scrapper/
├── backend/              # Python / FastAPI / SQLAlchemy
│   ├── app/              # Application principale
│   │   ├── api/          # Endpoints FastAPI
│   │   ├── core/         # Configuration, logging
│   │   └── db/           # Base de données
│   ├── migrations/       # Migrations Alembic
│   ├── scraping/         # Pipeline de scraping (V1+)
│   └── tests/            # Tests automatisés
├── frontend/             # Next.js / TypeScript / Tailwind
│   └── src/
│       ├── app/          # Pages (App Router)
│       ├── components/   # Composants réutilisables
│       ├── lib/          # Utilitaires, client API
│       └── messages/     # Traductions (fr/en)
├── docs/                 # Documentation
├── scripts/              # Sauvegarde / restauration PostgreSQL
├── docker-compose.yml    # Services Docker (postgres, backend, frontend)
└── .env.example          # Template de configuration
```

---

## Principe fondamental — Qualité des données

> Aucune donnée financière ne peut être inventée ou estimée sans signalement explicite.

Chaque valeur financière est reliée à :
`source → document → page → période → valeur originale → unité → valeur normalisée → méthode d'extraction → statut de validation`

Statuts : `extracted` | `needs_review` | `reviewed` | `verified` | `rejected` — qualifications calculées : `conflict`, `unavailable`.

**DATA MISSING > DATA WRONG** : jamais de valeur inventée, jamais 0 à la place d'une absence, jamais de
conversion de devise, jamais de mélange de périmètres ou de périodes. Toute décision humaine est tracée
(`financial_data_review_events`). Détails : [docs/data-quality.md](./docs/data-quality.md).

---

## Tests

```bash
cd backend && ruff check . && pytest -q -rs     # PostgreSQL requis pour les tests d'intégration (sinon skipped)
cd frontend && npm run lint && npm test && npm run build
```

Voir [docs/development.md](./docs/development.md).

---

## Sources de données

| Priorité | Source |
|---------|--------|
| 1 | [BCEAO](https://www.bceao.int) |
| 1 | [Commission Bancaire de l'UMOA](https://www.cb-umoa.org) |
| 2 | Sites officiels des banques et groupes bancaires |
| 3 | Autres sources institutionnelles |

---

## Documentation

- [Architecture](./docs/architecture.md)
- [Modèle de données](./docs/data-model.md)
- [Qualité des données & Review Center](./docs/data-quality.md)
- [Deal Intelligence](./docs/deal-intelligence.md)
- [Moteur de découverte (Phase 15)](./docs/discovery-engine.md)
- [Audit AMF-UMOA, SGI, presse (05/10/2026)](./audits/ape_amf/00_RAPPORT.md)
- [Développement](./docs/development.md)
- [Déploiement, sauvegarde, limites connues](./docs/deployment.md)
- [Règles de développement](./docs/dev-rules.md)
- [Spécification V1](./docs/specification-v1.md)

---

## Licence

Usage interne — Tous droits réservés.
