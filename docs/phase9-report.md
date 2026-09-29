# Phase 9 — Rankings & Comparisons : rapport de clôture

**Statut : PHASE 9 — CORRECTED AND VALIDATED**

Principe directeur : **DATA MISSING > DATA WRONG**. Les classements sont descriptifs (ordre numérique d'une valeur) : aucun jugement qualitatif, aucun score, aucune recommandation d'investissement.

Base : commit Phase 8C `cf4a359`. Aucune fonctionnalité de Phase 10.

---

## 1. Architecture

`backend/scraping/rankings/` orchestre les briques existantes sans réimplémenter leurs règles :
`EligibilityEngine.select_authoritative_observation`, `AnalyticsService.get_growth` / `get_ratios` / `get_aggregations`, `SECTOR_SCOPE`.

| Fichier | Rôle |
|---|---|
| `definitions.py` | 18 indicateurs classables : 6 postes publiés, 6 variations annuelles (`growth_*`), 6 ratios |
| `eligibility.py` | Sélection de la valeur d'autorité par institution (règles existantes) |
| `calculator.py` | Fonctions pures : rang de compétition, couverture, homogénéité de devise, pagination |
| `service.py` | `RankingService` : classement, historique, comparaisons |
| `models.py` | Modèles de réponse |

## 2. Endpoints

| Endpoint | Rôle |
|---|---|
| `GET /api/v1/rankings` | Refondu (même URL, contrat mis en conformité) |
| `GET /api/v1/rankings/history` | Rang observé par exercice pour une institution |
| `GET /api/v1/comparisons` | 2 à 5 institutions (sinon 422) |
| `GET /api/v1/comparisons/sector` | Institution ↔ secteur national |
| `GET /api/v1/comparisons/country` | Pays ↔ UMOA |

`/api/v1/analytics/compare` (Phase 7) est conservé ; l'interface utilise la page `/[locale]/comparisons`.

## 3. Règles

- **Un classement = un indicateur, une année, un `period_type`, un `data_scope`.** Défauts : `annual` + `individual`. Aucun mélange individuel / consolidé ni annuel / semestriel.
- **Année** : paramètre explicite, sinon dernière année disposant de données ; sinon `unavailable` / `no_period`. Jamais une constante.
- **Éligibilité** : une seule valeur d'autorité par institution. `verified` / `reviewed` / `extracted` selon les règles existantes ; `rejected`, conflit non résolu et `needs_review` exclus. Ratios et variations : statuts `calculated` / `calculated_from_verified` uniquement ; annuels uniquement (sinon `period_type_not_supported`).
- **Ex æquo** : rang de compétition (1, 1, 3). Le tri secondaire nom puis identifiant ne sert qu'à stabiliser l'affichage.
- **Donnée manquante** : l'institution est listée dans `unavailable` avec sa raison ; jamais classée, jamais 0, jamais en dernière position.
- **Devises** : pour un poste publié, devises hétérogènes → `needs_review` / `heterogeneous_currency`, classement vide, aucune conversion. Les pourcentages (ratios, variations) ne sont pas concernés.
- **Provenance** : chaque ligne porte `data_id` (poste publié) ou la liste de ses composants (ratio, variation) ; le panneau de provenance charge l'enregistrement réel via `GET /api/v1/financial-data/{id}`.

### Couverture

| Champ | Signification |
|---|---|
| `eligible_count` | Institutions avec une valeur admissible — jamais remis à 0 artificiellement |
| `ranked_count` | Institutions effectivement classées |
| `expected_count` | Univers attendu (pays ou UMOA) |
| `coverage_ratio` | `ranked_count / expected_count` ; `null` si le classement est incalculable ou l'univers vide |
| `coverage_status` | `available` / `unavailable` |

Devises hétérogènes (ex. 5 éligibles) : `eligible_count = 5`, `ranked_count = 0`, `coverage_ratio = null`, `coverage_status = unavailable`. L'interface affiche « Couverture : — » et « Couverture indisponible — Devises incompatibles », jamais « 0/N » ni « 0 % ».

### Libellés des ratios

L'interface affiche les libellés du catalogue backend (`RATIO_DEFINITIONS.name_fr` / `name_en`), par exemple « Ratio dépôts sur actifs » / « Deposits to Assets Ratio ». Le code (`DEPOTS_ACTIFS`) reste utilisé dans l'API et l'URL. Aucun libellé dupliqué.

### Pays ↔ UMOA et institution ↔ secteur

Postes publiés : comparaison sur comptes individuels annuels (règle Phase 8C) ; part calculée uniquement si l'institution contribue au total, dans la même devise.

Ratios et variations : aucune méthode d'agrégation n'existe et aucune n'a été inventée → `status = unavailable`, `reason = aggregate_not_supported`, totaux et parts `null`. L'interface affiche « Indisponible » et « Non disponible pour cet indicateur », sans aucune ligne chiffrée.

## 4. Résultats des tests (mesurés à la clôture)

Environnement : Windows, Python 3.11.9, pytest 8.3.3 ; PostgreSQL 16.15 réel (conteneur Docker `umoa_postgres`, joint via `127.0.0.1`).

### Backend — `POSTGRES_HOST=127.0.0.1 pytest`

| Mesure | Valeur |
|---|---|
| Tests collectés | **330** |
| Réussis | **330** |
| Échoués | 0 |
| Ignorés (skipped) | 0 |
| Erreurs | 0 |
| Avertissements | 6 |
| Durée | 11,60 s |
| Code de sortie | 0 |

Répartition par fichier :

| Fichier | Tests |
|---|---|
| `test_health.py` | 3 |
| `test_migration_phase2.py` | 46 |
| `test_migration_postgres_phase2.py` (PostgreSQL réel) | 1 |
| `test_models_phase1.py` | 27 |
| `test_phase3_api.py` | 49 |
| `test_phase4_scraping.py` | 26 |
| `test_phase5a_pdf_parser.py` | 19 |
| `test_phase5b_financial_extraction.py` | 32 |
| `test_phase5c_reconciliation_workflow.py` | 16 |
| `test_phase6_consolidation_history.py` | 19 |
| `test_phase7_analytics_ratios.py` | 25 |
| `test_phase8c_analytics_contract.py` | 8 |
| `test_phase8c_postgres_integration.py` (PostgreSQL réel) | 14 |
| `test_phase9_rankings_postgres.py` (PostgreSQL réel) | 15 |
| `test_phase9_rankings_unit.py` | 30 |
| **Total** | **330** |

Les 6 avertissements sont liés à l'outillage de test, sans effet fonctionnel :
- `DeprecationWarning` : alias `anyio.abc.BlockingPortal` utilisé par le `TestClient` de Starlette (préexistant) ;
- `RuntimeWarning` : coroutine asyncpg `Connection._cancel` non attendue lors de la fermeture de connexions de test.

Les lignes « ERROR » visibles avec `-rA` sont des **journaux capturés**, pas des tests en erreur : les tests `TestRouteExistence` (Phase 3) vérifient uniquement qu'une route existe (réponse ≠ 405) contre la base principale, qui n'est pas migrée dans le conteneur ; un test PDF ouvre volontairement un fichier invalide.

Condition d'exécution sur ce poste : lancer `pytest` avec `POSTGRES_HOST=127.0.0.1`. Un second PostgreSQL (WSL) écoute sur `[::1]:5432` ; avec `localhost`, les bases temporaires des tests risqueraient d'être créées sur cette autre instance.

### Frontend

| Commande | Résultat |
|---|---|
| `npm run lint` | 0 erreur, 0 avertissement |
| `npm run build` | succès (routes `/[locale]/rankings` et `/[locale]/comparisons` incluses) |
| `npm test` (Vitest) | **79 / 79** réussis, 6 fichiers |

### Ruff — `ruff check backend/app backend/scraping`

28 erreurs, **toutes préexistantes** (20 F821, 6 W292, 1 I001, 1 UP017), non corrigées volontairement. **0 erreur** dans les fichiers créés ou modifiés en Phase 9.

### Vérification fonctionnelle

Rendu Chrome headless des pages `/fr` et `/en` (classements national et UMOA, variation annuelle, ratio, semestriel non supporté, comparaisons) contre l'API réelle et une base de démonstration temporaire, supprimée ensuite : ex æquo 1, 1, 3 ; section « Données indisponibles » ; couverture « — » avec sa raison en cas de devises hétérogènes ; libellés de ratio FR/EN ; « Indisponible » pour pays ↔ UMOA sur un ratio ; aucun motif interdit, aucun vocabulaire qualitatif, aucun texte français dans les pages EN ; liens FR↔EN conservant les filtres.

## 5. DATA MISSING > DATA WRONG

| Cas | Comportement |
|---|---|
| Donnée manquante | Pas de rang ; section « indisponible » avec raison |
| `rejected` / conflit / `needs_review` | Exclus du classement ; raison affichée |
| Autre périmètre ou autre période | Classement séparé, jamais mélangé |
| Devises hétérogènes | `needs_review`, aucune conversion, couverture indisponible (pas `0/N`) |
| Univers vide | Couverture `null` (« — ») |
| Année absente | Jamais inventée |
| Total sectoriel inconnu | Part `null`, jamais 0 % |
| Ratio / variation en agrégat | `aggregate_not_supported`, aucune méthode inventée |

## 6. Défauts détectés et corrigés pendant la phase

- Collision de clé de traduction `comparisons.country` (libellé et groupe) → renommée `country_label`.
- Caractères « retour arrière » (au lieu de `\b`) introduits par l'échappement shell dans deux regex de test, dont le test backend de vocabulaire interdit qui ne vérifiait donc pas `best`, `worst`, `pire`, `buy`, `sell`, `top bank`. Corrigé et vérifié ; aucun caractère de contrôle ne subsiste dans les sources.
- `docs/specification-v1.md` décrivait l'ancien contrat de `/rankings` (`verified` seul, erreur `400` sur devises). Aligné sur le contrat validé en Phase 9.

## 7. Limitations

- Parts de marché arrondies à 4 décimales (règle Phase 7) : leur somme peut valoir 99,9999 %.
- `/api/v1/analytics/compare` (Phase 7) coexiste avec `/api/v1/comparisons` ; l'interface n'utilise plus que ce dernier.
