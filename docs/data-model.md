# Modèle de données (PostgreSQL 16)

Toutes les tables héritent de `Base` : `id` (UUID applicatif, `String(36)`), `created_at`,
`updated_at`, `deleted_at` (suppression logique — aucune donnée financière n'est supprimée
physiquement). Toutes les clés étrangères vers les données financières sont en `ON DELETE RESTRICT`.

## 1. Référentiel

| Table | Rôle | Clés / contraintes notables |
|---|---|---|
| `countries` | 8 pays de l'UMOA (seed 0003) | `code` unique (ISO alpha-2) |
| `sources` | Sources officielles (seed 0004), priorité 1–3 | — |
| `banking_groups` | Groupes bancaires documentés | `source_id` → sources (SET NULL) |
| `institutions` | Établissements | `country_id` → countries (RESTRICT) ; groupe / source (SET NULL) |
| `metric_definitions` | Catalogue des 26 indicateurs V1 (seed 0002) | `code` unique |
| `documents` | Artefacts sources (PDF, pages web) | `file_hash` unique ; `source_id` (RESTRICT) ; `page_count > 0` |

## 2. Données financières

`financial_data` — une valeur traçable par établissement × indicateur × période × périmètre :

- provenance obligatoire : `institution_id`, `source_id`, `document_id`, `metric_code` (NOT NULL, RESTRICT), `page_number` ;
- valeur originale (jamais écrasée) + valeur normalisée, unité et devise distinctes, aucune conversion ;
- `scope` ∈ {`individual`, `consolidated`}, `period_type` ∈ {`annual`, `semi_annual`, `quarterly`} ;
- `status` ∈ {`extracted`, `needs_review`, `reviewed`, `verified`, `rejected`} ;
- CHECK : `reviewed`/`verified` ⇒ valeur normalisée ; `verified` ⇒ `verified_at` + `verified_by` ;
- index de la clé logique `(institution_id, metric_code, period_year, period_type, scope)` (0005).

Plusieurs observations peuvent partager une clé logique (plusieurs sources) : la règle
d'autorité choisit, ou signale un conflit (voir `data-quality.md`).

## 3. Piste d'audit — `financial_data_review_events` (0006, généralisée en 0007)

Journal unique, append-only (aucun chemin de code ne met à jour ni ne supprime une ligne) :

| Colonne | |
|---|---|
| `financial_data_id` **ou** `deal_id` | cible (CHECK : exactement une) |
| `deal_duplicate_candidate_id` | décision sur un doublon potentiel (uniquement avec `deal_id`) |
| `action` | `review`, `verify`, `reject`, `import`, `mark_same_deal`, `mark_distinct`, `mark_same_deal_multi_source` |
| `previous_status` → `new_status` | `none` pour un import |
| `reason`, `actor` | motif, identifiant déclaré (≤ 255) |
| `value_before`, `value_after` | valeur normalisée (observation) ou montant (transaction) |
| `created_at` | horodatage (UTC) |

Index : `(financial_data_id, created_at)`, `(deal_id, created_at)`.

## 4. Transactions (0007) — voir `deal-intelligence.md`

`deals`, `deal_sources`, `deal_field_sources`, `deal_participants`, `deal_duplicate_candidates`.
CHECK notables : montant > 0 si présent, devise `^[A-Z]{3}$`, maturité > 0, différé ≥ 0, types /
rôles / statuts fermés, `verified` ⇒ validateur, paire de doublons ordonnée et unique, décision
de doublon ⇒ `decided_by` + `decided_at`, une transaction n'est jamais rattachée à elle-même.

## 5. Migrations (Alembic, chaîne linéaire)

| Révision | Contenu | Downgrade |
|---|---|---|
| `0001_initial_schema` | tables du référentiel, documents, financial_data | oui |
| `0002_seed_metric_catalogue` | 26 indicateurs | oui |
| `0003_seed_countries_and_constraints` | 8 pays + CHECK | oui |
| `0004_seed_official_sources` | sources officielles | oui |
| `0005_financial_data_explorer_indexes` | 3 index composites | oui |
| `0006_financial_data_review_events` | journal d'audit | oui |
| `0007_deal_intelligence` | transactions + journal unique + `verified_by` 255 | oui (refusé s'il existe des événements de transaction : aucune perte silencieuse) |

Aucune migration n'est destructive à la montée. `alembic check` : aucun écart entre les
modèles et le schéma migré.
