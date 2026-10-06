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

## 4. Transactions (0007, 0014, 0015) — voir `deal-intelligence.md`

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
| `0008_automated_ingestion` | journal `ingestion_runs` (exécutions automatiques 2×/jour et manuelles) | oui |
| `0009_unified_financial_intelligence` | Entity Hub : `entities`, `entity_relationships` ; `institutions.entity_id` ; `financial_data.entity_id`, `observation_level`, `consolidation_scope` ; `metric_definitions.sector`, `metric_family` | oui |
| `0010_seed_markets_and_public_debt` | sources de marché (BRVM, UMOA-Titres, AMF-UMOA, DC/BR), entités de marché et 8 Trésors, métriques marché / dette souveraine | oui |
| `0011_entity_source_discovery` | moteur de découverte : `reference_universes`, `reference_universe_members`, `entity_identifiers`, `entity_names`, `entity_sources`, `document_entities`, `discovery_runs`, `discovery_rounds`, `discovery_gaps` ; cycle de vie des sources ; `documents.entity_id` | oui |
| `0012_scope_evidence_and_document_scope` | preuve de périmètre (`scope_evidence_class`, `scope_reason_code`, `quality_flags`…) ; `documents.document_scope` | oui |
| `0013_institutional_discovery` | taxonomie des manques Phase 17 ; `documents.text_layer_status`, `file_format`, `reporting_year` | oui |
| `0014_public_debt_instruments` | titres publics dans `deals` (`instrument_type`, `isin`, dates d'adjudication / valeur / échéance, `yield_rate`, `ingestion_key`) ; `deal_participants.entity_id` | refusé tant qu'une transaction utilise ces colonnes |
| `0015_deal_validation_flags` | `deals.validation_flags` (JSONB) | refusé tant qu'une transaction porte un drapeau |
| `0016_deal_sourcing_roles` | types et rôles étendus, page / citation / méthode des participations, utilisation des fonds, `filing_agent_raw`, classes de source, `institution_links` | refusé tant que le nouveau vocabulaire est utilisé |
| `0017_directory_and_mandates` | type `guarantee_fund`, `entities.website`, `mandates`, `mandate_counterparties` | refusé tant qu'un mandat ou une entrée d'annuaire existe |

Aucune migration n'est destructive à la montée. `alembic check` : aucun écart entre les
modèles et le schéma migré (vérifié jusqu'à `0017`, le 06/10/2026). Tables de découverte et Entity Hub :
voir `discovery-engine.md`.
