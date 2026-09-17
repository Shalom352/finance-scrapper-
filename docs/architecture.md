# Architecture — UMOA Banking Intelligence

## Vue d'ensemble

UMOA Banking Intelligence est une plateforme monorepo composée de trois couches principales :

```
Sources officielles (BCEAO, CB-UMOA, banques)
        ↓
Pipeline de scraping (Discovery → Download → Storage)
        ↓
Pipeline d'extraction (Parsing → Normalization → Validation)
        ↓
PostgreSQL (données financières structurées)
        ↓
FastAPI (API REST)
        ↓
Next.js (Dashboard / Recherche / Classements)
```

---

## Composants

### Backend — `backend/`

**Langage** : Python 3.11+
**Framework** : FastAPI (async)
**ORM** : SQLAlchemy 2.0 (async)
**Validation** : Pydantic v2
**Migrations** : Alembic
**Tests** : pytest + pytest-asyncio

#### Structure

```
backend/
├── app/
│   ├── main.py               # Point d'entrée FastAPI
│   ├── core/
│   │   ├── config.py         # Configuration centralisée (pydantic-settings)
│   │   └── logging.py        # Logging structuré
│   ├── db/
│   │   ├── base.py           # SQLAlchemy DeclarativeBase
│   │   ├── engine.py         # Création de l'engine async
│   │   └── session.py        # Factory de sessions
│   ├── models/               # Modèles SQLAlchemy (Phase 1+)
│   ├── schemas/              # Schémas Pydantic (Phase 1+)
│   ├── services/             # Logique métier (Phase 1+)
│   └── api/
│       └── v1/               # Endpoints versionnés
├── scraping/                 # Pipeline de scraping (Phase 2+)
│   ├── discovery/            # Détection de nouveaux documents
│   ├── download/             # Téléchargement, hash, dédup
│   ├── parsing/              # Extraction PDF (PyMuPDF, pdfplumber)
│   ├── normalization/        # Standardisation des valeurs
│   └── validation/           # Contrôle qualité
├── migrations/               # Migrations Alembic
│   └── versions/
└── tests/
```

#### API versioning

Tous les endpoints sont préfixés `/api/v1/`. Le versioning permet d'évoluer sans casser les clients existants.

```
GET /health                     → Statut de l'application
GET /api/v1/                    → Version de l'API
GET /api/v1/institutions/       → Liste des institutions (Phase 1)
GET /api/v1/documents/          → Documents téléchargés (Phase 2)
GET /api/v1/financial-data/     → Données financières (Phase 3)
```

---

### Base de données — PostgreSQL

**Version** : PostgreSQL 16
**Driver** : asyncpg (async)
**Hébergement** : Docker Compose (dev), compatible cloud

#### Principes de modélisation

- Chaque table a un `id` UUID (généré côté application)
- `created_at` et `updated_at` sur chaque table
- Soft delete via `deleted_at` nullable (jamais de suppression physique de données financières)
- Toute donnée financière porte la traçabilité complète (voir ci-dessous)

#### Traçabilité obligatoire des données financières

```
source_id         → quelle source officielle
document_id       → quel document
page_number       → quelle page du document
period_year       → année de référence
period_type       → 'annual' | 'semi-annual' | 'quarterly'
value_original    → valeur telle qu'extraite (string)
unit_original     → unité originale (ex: "millions FCFA")
value_normalized  → valeur normalisée (Decimal)
unit_normalized   → unité normalisée (ex: "FCFA")
extraction_method → 'pdf_table' | 'pdf_text' | 'ocr' | 'manual'
status            → 'extracted' | 'needs_review' | 'reviewed' | 'verified' | 'rejected'
confidence_score  → 0.0 à 1.0
```

---

### Frontend — `frontend/`

**Framework** : Next.js 14 (App Router)
**Langage** : TypeScript
**Styling** : Tailwind CSS
**i18n** : next-intl (bilingue fr/en)

#### Structure

```
frontend/src/
├── app/
│   ├── [locale]/             # Routing i18n
│   │   ├── layout.tsx
│   │   └── page.tsx
│   └── globals.css
├── components/               # Composants réutilisables
│   ├── ui/                   # Composants de base
│   └── layout/               # Composants de mise en page
├── lib/
│   ├── api.ts                # Client API FastAPI
│   └── utils.ts
├── messages/
│   ├── fr.json               # Traductions françaises
│   └── en.json               # English translations
└── types/
    └── index.ts              # Types TypeScript partagés
```

#### Internationalisation

- URL locale : `/fr/dashboard`, `/en/dashboard`
- Langue par défaut : français (`fr`)
- Langue supportée : anglais (`en`)
- Toutes les chaînes de l'interface passent par le système de traductions

#### Authentification (future)

L'architecture est préparée pour l'ajout d'authentification sans reconstruction :
- Middleware Next.js pour la protection des routes
- Providers de contexte utilisateur
- Backend : structure JWT-ready

---

### Infrastructure — Docker

**Fichiers** :
- `docker-compose.yml` : services requis (PostgreSQL)
- `docker-compose.override.yml.example` : services optionnels (pgAdmin)

**Volumes** :
- `postgres_data` : persistance des données PostgreSQL

**Networks** :
- `umoa_network` : communication inter-services

---

## Règles d'architecture

1. **Séparation des couches** : scraping ≠ extraction ≠ API ≠ UI
2. **Pipeline scraping** : discovery → download → storage → parsing → normalization → validation (chaque étape isolée)
3. **Traçabilité** : aucune donnée financière sans provenance complète
4. **Versioning API** : tous les endpoints sous `/api/v1/`
5. **Configuration** : 100% via variables d'environnement, aucun secret dans le code
6. **Migrations** : toute modification du schéma via Alembic
7. **Tests** : tout code nouveau doit avoir des tests associés

---

## Évolution vers V2 et V3

L'architecture est conçue pour supporter :

**V2** : ajout du module `backend/ai/` (LLM integration, document classification, NLP search)

**V3** : ajout des modules `backend/transactions/` et `backend/relationships/` pour M&A, obligations, actionnaires

Aucune reconstruction architecturale majeure ne sera nécessaire.
