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

> Référence de vérité : `docs/specification-v1.md`. En cas de divergence, la spécification prévaut.

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
│   ├── models/               # Modèles SQLAlchemy
│   ├── schemas/              # Schémas Pydantic
│   ├── services/             # Logique métier
│   └── api/
│       └── v1/               # Endpoints versionnés
├── scraping/                 # Pipeline de scraping (Phase 4+)
│   ├── discovery/            # Détection de nouveaux documents
│   ├── download/             # Téléchargement, hash, dédup
│   ├── parsing/              # Extraction PDF / HTML
│   ├── normalization/        # Standardisation des valeurs
│   └── validation/           # Contrôle qualité
├── migrations/               # Migrations Alembic
│   └── versions/
└── tests/
```

#### API versioning

Tous les endpoints métier sont préfixés `/api/v1/`. Les routes sont canoniques **sans slash final**.

```
GET /health                     → Statut de l'application
GET /api/v1/health              → Statut complet (incl. base de données)

GET /api/v1/countries           → Pays UMOA
GET /api/v1/sources             → Sources officielles
GET /api/v1/banking-groups      → Groupes bancaires
GET /api/v1/metrics             → Catalogue des métriques (26)
GET /api/v1/metrics/{code}      → Détail d'une métrique
GET /api/v1/institutions        → Liste des institutions
GET /api/v1/institutions/{id}   → Détail d'une institution
GET /api/v1/documents           → Documents collectés
GET /api/v1/documents/{id}      → Détail d'un document
GET /api/v1/financial-data      → Données financières (avec provenance)
GET /api/v1/financial-data/{id} → Détail d'une donnée financière
GET /api/v1/rankings            → Classements (données verified uniquement)
GET /api/v1/search              → Recherche multi-entités
```

Contrat complet (filtres, pagination, erreurs) : voir `docs/specification-v1.md` §18.

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
- Les 26 métriques de la V1 sont définies dans la table `metric_definitions` (voir `docs/specification-v1.md` §6–§9)

#### Modèles

**Référentiels (existants)** : `Country`, `Source`, `BankingGroup`, `Institution`.

**Métier (V1)** :

- `metric_definitions` — catalogue officiel des métriques (`code` UNIQUE ; `financial_data.metric_code` y fait référence)
- `documents` — documents collectés (`source_id` NOT NULL ; `file_hash` UNIQUE lorsqu'il est renseigné ; stockage adressé par contenu)
- `financial_data` — données financières (`institution_id`, `source_id`, `document_id`, `metric_code`, `value_original` NOT NULL)

#### Unités et devises — distinction stricte

**L'unité et la devise sont deux concepts distincts.** Ne jamais utiliser la devise comme substitut de l'unité.

`financial_data` conserve six champs :

```
value_original,   unit_original,   currency_original
value_normalized, unit_normalized, currency_normalized
```

Règle de normalisation par `value_type` :

- `amount`      → `unit_normalized = "absolute"`, `value_normalized = value_original × multiplicateur`
- `percentage`  → `unit_normalized = "%"`
- `ratio`       → `unit_normalized = "ratio"`
- `rate`        → `unit_normalized = "%"`

Multiplicateurs unitaires (`amount`) : `absolute/unit` ×1 · `thousand` ×1 000 · `million` ×1 000 000 · `milliard/billion` ×1 000 000 000.

**Aucune conversion de devise en V1 : `currency_normalized = currency_original`.**

#### Traçabilité obligatoire des données financières

```
institution_id      → quelle institution
source_id           → quelle source officielle
document_id         → quel document (NOT NULL)
page_number         → quelle page du document
period_type         → 'annual' | 'semi_annual' | 'quarterly'
period_year         → année de référence
period_label        → libellé contrôlé (ex: "2024", "S1 2024", "T1 2024")
metric_code         → code de la métrique (FK metric_definitions.code)
scope               → 'individual' | 'consolidated'
value_original      → valeur telle qu'extraite (string)
unit_original       → unité originale (ex: "million")
currency_original   → devise originale (ex: "XOF", "USD" ; NULL si non monétaire)
value_normalized    → valeur normalisée (Decimal)
unit_normalized     → unité normalisée ("absolute" | "%" | "ratio")
currency_normalized → devise normalisée (= currency_original en V1)
extraction_method   → 'pdf_table' | 'pdf_text' | 'ocr' | 'web_html' | 'manual'
status              → 'extracted' | 'needs_review' | 'reviewed' | 'verified' | 'rejected'
confidence_score    → 0.0 à 1.0
```

#### Scopes V1

`financial_data.institution_id` étant NOT NULL, seuls les scopes rattachables à une institution sont autorisés :

```
individual   → données publiées pour une institution isolée
consolidated → données publiées pour l'entité consolidante (rattachées à l'institution déclarante)
```

Les agrégats `country`, `sector`, `umoa` ne sont **pas** stockés comme `financial_data` ; ils sont calculés à partir des données institutionnelles.

#### Versionnement des documents

Une nouvelle version ou correction d'un document ne remplace jamais l'ancienne : elle produit un **nouveau Document** avec ses propres `financial_data`. La provenance historique n'est jamais modifiée rétroactivement. Pas de `supersedes_document_id` en V1.

---

### Frontend — `frontend/`

**Framework** : Next.js (App Router)
**Langage** : TypeScript
**Styling** : Tailwind CSS
**i18n** : next-intl (bilingue fr/en)

#### Structure

```
frontend/src/
├── app/
│   ├── [locale]/             # Routing i18n
│   │   ├── layout.tsx
│   │   ├── page.tsx
│   │   └── ...
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

#### Routes V1

```
/[locale]                          (Dashboard)
/[locale]/institutions
/[locale]/institutions/[id]
/[locale]/countries
/[locale]/countries/[country]
/[locale]/analytics
/[locale]/rankings
/[locale]/comparisons
/[locale]/financial-data           (Financial Data Explorer)
/[locale]/data-quality             (Review Center : observations | transactions)
/[locale]/data-quality/[dataId]
/[locale]/data-quality/deals/[dealId]
/[locale]/deals                    (Deal Explorer — Phase 13)
/[locale]/deals/[dealId]
/[locale]/documents
/[locale]/search
```

#### Internationalisation

- URL locale : `/fr/...`, `/en/...`
- Langue par défaut : français (`fr`) ; langue supportée : anglais (`en`)
- Toutes les chaînes de l'interface passent par le système de traductions

#### Affichage et comparabilité

- **Provenance** et **statut** affichés partout où une donnée est présentée.
- **Comparaison** uniquement entre données comparables (même métrique, période, scope, type de période, unité, devise normalisée).
- Les **classements** n'utilisent que les valeurs admissibles selon la règle d'éligibilité
  (jamais `rejected`, jamais un conflit, jamais une valeur `needs_review`) dans une devise unique :
  voir `docs/data-quality.md`.

#### Authentification

**Aucune authentification n'existe** dans cette version (limite connue, voir `docs/deployment.md`).
Les décisions humaines enregistrent un identifiant `actor` **déclaré** par l'opérateur. La plateforme
doit être déployée derrière un accès réseau restreint (VPN / reverse proxy authentifiant).

---

### Infrastructure — Docker

**Fichiers** :
- `docker-compose.yml` : `postgres`, `backend` (FastAPI, migrations Alembic au démarrage), `frontend` (Next.js standalone)
- `backend/Dockerfile`, `frontend/Dockerfile` : images non-root avec healthchecks
- `docker-compose.override.yml.example` : services optionnels (pgAdmin)
- `scripts/backup.sh`, `scripts/restore.sh` : sauvegarde / restauration PostgreSQL

**Volumes** :
- `postgres_data` : persistance des données PostgreSQL
- `documents_data` : documents téléchargés (backend)

Déploiement détaillé : `docs/deployment.md`.

---

### Deal Intelligence (Phase 13)

Module intégré à la même plateforme (`app/models/deal.py`, `scraping/deals/`, `app/api/v1/deals.py`,
`frontend/src/app/[locale]/deals`). Réutilise : `institutions`, `documents`, `sources` (provenance),
les règles de transition du Review Center et la table d'audit unique. Alimentation par import
structuré uniquement (pas d'extracteur). Voir `docs/deal-intelligence.md`.

**Networks** :
- `umoa_network` : communication inter-services

---

## Règles d'architecture

1. **Séparation des couches** : scraping ≠ parsing ≠ normalization ≠ validation ≠ API ≠ UI
2. **Pipeline scraping** : discovery → download → storage → parsing → normalization → validation (chaque étape isolée)
3. **Traçabilité** : aucune donnée financière sans provenance complète
4. **Versioning API** : tous les endpoints métier sous `/api/v1/`, sans slash final
5. **Configuration** : 100% via variables d'environnement, aucun secret dans le code
6. **Migrations** : toute modification du schéma via Alembic
7. **Tests** : tout code nouveau doit avoir des tests associés
8. **Aucune donnée inventée** : voir `docs/dev-rules.md` et `docs/specification-v1.md`

---

## Évolution vers V2 et V3

L'architecture est conçue pour supporter :

**V2** : conversion FX (taux, date, source, méthode), ratios calculés et formules, module `backend/ai/` (LLM, classification de documents, recherche NLP)

**V3** : modules `backend/transactions/` et `backend/relationships/` pour M&A, obligations, actionnaires

Aucune reconstruction architecturale majeure ne sera nécessaire.

> État au terme de la Phase 13 (dernière phase) : le suivi des transactions de financement est
> livré sous forme de *Deal Intelligence* (import structuré, sans extraction automatique). Les
> éléments V2/V3 ci-dessus non livrés restent des pistes, pas des engagements.