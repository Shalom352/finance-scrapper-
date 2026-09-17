# UMOA Banking Intelligence

Plateforme de collecte, structuration et exploitation des données financières des établissements bancaires de l'Union Monétaire Ouest-Africaine (UMOA).

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
- [Node.js 20+](https://nodejs.org/)

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
docker-compose up -d postgres
```

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
Documentation API : http://localhost:8000/docs

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
├── docker-compose.yml    # Services Docker
└── .env.example          # Template de configuration
```

---

## Principe fondamental — Qualité des données

> Aucune donnée financière ne peut être inventée ou estimée sans signalement explicite.

Chaque valeur financière est reliée à :
`source → document → page → période → valeur originale → unité → valeur normalisée → méthode d'extraction → statut de validation`

Statuts : `extracted` | `needs_review` | `reviewed` | `verified` | `rejected`

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
- [Règles de développement](./docs/dev-rules.md)

---

## Licence

Usage interne — Tous droits réservés.
