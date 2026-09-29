# Spécification Technique V1 — UMOA Banking Intelligence

**Statut : VALIDÉE — Référence canonique du projet**
**Portée : V1 (Data Platform)**

> Ce document est la référence de vérité pour la V1.
> Aucune implémentation ne doit contredire cette spécification.
> Toute évolution passe par une révision explicite de ce document.

---

## 0. Objectif V1

Construire une base de données financière **fiable, traçable et exploitable** permettant de rechercher, consulter et comparer les données financières **publiées** des institutions de l'UMOA.

Priorités : fiabilité, traçabilité, données sourcées, normalisation, validation humaine, architecture extensible, séparation stricte des responsabilités.

Aucune donnée n'est inventée, estimée ou déduite sans règle explicitement documentée.

---

## 1. État du repository (référence d'implémentation)

**Backend** : Python 3.11+, FastAPI, SQLAlchemy 2.x async, asyncpg, Pydantic v2, Alembic, structlog.

Modèles existants : `Country`, `Source`, `BankingGroup`, `Institution`.
Base déclarative : `id` (UUID string), `created_at`, `updated_at`, `deleted_at` (soft delete).

**Frontend** : Next.js (App Router), React, TypeScript, Tailwind CSS, next-intl (fr/en), routing `[locale]`.

**Absent en V1 initial** : `metric_definitions`, `documents`, `financial_data`, migrations métier, pipeline scraping, connecteur BCEAO, API métier complète, pages métier, rankings, recherche.

---

## 2. Architecture V1

```
Sources officielles → Discovery → Download → Storage → Parsing
→ Normalization → Validation → PostgreSQL → FastAPI → Next.js
```

Séparation obligatoire : **Scraping ≠ Parsing ≠ Normalization ≠ Validation ≠ API ≠ UI**.

- Tous les endpoints métier sous `/api/v1/`.
- Configuration via variables d'environnement uniquement ; aucun secret dans le code.
- Toute modification du schéma PostgreSQL passe par Alembic.

---

## 3. Principes de données

Aucune donnée inventée. Sont interdits :

- estimation ;
- approximation ;
- interpolation ;
- remplissage automatique d'une donnée absente ;
- déduction présentée comme donnée publiée.

Une donnée absente reste absente.

---

## 4. Traçabilité

Chaque donnée financière est retraçable selon la chaîne suivante :

```
Institution → Source → Document → Page → Période → Métrique
→ Valeur originale → Unité originale → Devise originale
→ Valeur normalisée → Unité normalisée → Devise normalisée
→ Méthode d'extraction → Statut de validation
```

- `financial_data.document_id` est **NOT NULL**.
- Une donnée issue d'une page web est matérialisée comme un `Document` (`document_type = web_page`).

---

## 5. Unités et devises

**Règle fondatrice : unité et devise sont deux concepts distincts.**
Ne jamais utiliser la devise comme substitut de l'unité, ni l'unité comme substitut de la devise.

`financial_data` conserve **six champs** :

```
value_original,   unit_original,   currency_original
value_normalized, unit_normalized, currency_normalized
```

### 5.1 Règle de normalisation par `value_type` (déterministe)

| `value_type` | `unit_normalized` | `value_normalized` |
|--------------|-------------------|--------------------|
| `amount` | `"absolute"` | `value_original × multiplicateur unitaire` |
| `percentage` | `"%"` | valeur numérique en pourcentage |
| `ratio` | `"ratio"` | valeur décimale |
| `rate` | `"%"` | valeur numérique en pourcentage |

**Multiplicateurs unitaires pour `amount`** (aucune conversion de devise) :

```
absolute / unit / units         → ×1
thousand / mille                → ×1 000
million / millions              → ×1 000 000
milliard / milliards / billion  → ×1 000 000 000
```

`million` et `billion` peuvent figurer dans `unit_original` mais **ne sont jamais des unités normalisées** pour un montant.

### 5.2 Exemples

**Montant XOF**

```
value_original      = "8542"      unit_original = "million"    currency_original = "XOF"
value_normalized    = 8542000000  unit_normalized = "absolute" currency_normalized = "XOF"
```

**Pourcentage**

```
value_original      = "57"        unit_original = "%"          currency_original = NULL
value_normalized    = 57          unit_normalized = "%"        currency_normalized = NULL
```

**Ratio**

```
value_original      = "1,25"      unit_original = "ratio"      currency_original = NULL
value_normalized    = 1.25        unit_normalized = "ratio"    currency_normalized = NULL
```

**Taux**

```
value_original      = "6,25 %"    unit_original = "%"          currency_original = NULL
value_normalized    = 6.25        unit_normalized = "%"        currency_normalized = NULL
```

### 5.3 Devise

**Décision : `currency_normalized = currency_original` en V1. Aucune conversion FX.**

```
value_original      = "125.4"     unit_original = "million"    currency_original = "USD"
value_normalized    = 125400000   unit_normalized = "absolute" currency_normalized = "USD"
```

La normalisation d'un montant **n'est pas** une conversion de devise.

Toute future conversion FX (V2) devra fournir au minimum : taux, date du taux, devise source, devise cible, source du taux, méthode de conversion.

### 5.4 Rankings — comparabilité stricte

Une comparaison n'est possible qu'à conditions identiques :

- même `metric_code` ;
- même `period_type` ;
- même `period_year` / `period_label` ;
- même `scope` ;
- unités compatibles ;
- **même `currency_normalized`**.

---

## 6. Table `metric_definitions`

Catalogue officiel des métriques.

```
id
code                UNIQUE NOT NULL
label_fr
label_en
definition_fr
definition_en
statement_type
category
value_type
currency_type
is_calculated
is_active
is_debt_related
display_order
description_synth
```

- `financial_data.metric_code` référence `metric_definitions.code`.
- Le catalogue est évolutif (ajout de métriques sans casser l'existant).

---

## 7. Catalogue des 26 métriques V1 (codes figés)

**Actifs** : `total_actifs`, `tresorerie`, `creances_clients`, `creances_banques`, `immobilisations`, `autres_actifs`

**Passifs** : `total_passifs`, `depots_clients`, `depots_banques`, `emprunts_bancaires`, `obligations_emises`, `dettes_totales`, `autres_passifs`

**Capitaux propres** : `capitaux_propres`

**Compte de résultat** : `produit_net_bancaire`, `produits_totaux`, `charges_totales`, `resultat_exploitation`, `resultat_net`, `chiffre_affaires`

**Flux de trésorerie** : `flux_exploitation`, `flux_investissement`, `flux_financement`

**Dette / indicateurs publiés** : `facilities_de_change`, `taux_interet_moyen`, `endettement_actifs`

La V1 contient officiellement **26 métriques**.

---

## 8. Catalogue complet des 26 métriques (métadonnées)

Colonnes : `code` | `label_fr / label_en` | `statement_type` | `category` | `value_type` | `currency_type` | `is_calculated` | `is_debt_related` | `display_order`

| # | code | label_fr / label_en | statement_type | category | value_type | currency_type | calc | debt | ord |
|---|------|---------------------|----------------|----------|-----------|---------------|------|------|-----|
| 1 | `total_actifs` | Total actifs / Total assets | balance_sheet | assets | amount | monetary | false | false | 1 |
| 2 | `tresorerie` | Trésorerie / Cash and cash equivalents | balance_sheet | assets | amount | monetary | false | false | 2 |
| 3 | `creances_clients` | Créances clients / Customer loans | balance_sheet | assets | amount | monetary | false | false | 3 |
| 4 | `creances_banques` | Créances banques / Interbank claims | balance_sheet | assets | amount | monetary | false | false | 4 |
| 5 | `immobilisations` | Immobilisations / Fixed assets | balance_sheet | assets | amount | monetary | false | false | 5 |
| 6 | `autres_actifs` | Autres actifs / Other assets | balance_sheet | assets | amount | monetary | false | false | 6 |
| 7 | `total_passifs` | Total passifs / Total liabilities | balance_sheet | liabilities | amount | monetary | false | false | 7 |
| 8 | `depots_clients` | Dépôts clients / Customer deposits | balance_sheet | liabilities | amount | monetary | false | false | 8 |
| 9 | `depots_banques` | Dépôts banques / Interbank deposits | balance_sheet | liabilities | amount | monetary | false | false | 9 |
| 10 | `emprunts_bancaires` | Emprunts bancaires / Bank borrowings | balance_sheet | liabilities | amount | monetary | false | true | 10 |
| 11 | `obligations_emises` | Obligations émises / Debt securities issued | balance_sheet | liabilities | amount | monetary | false | true | 11 |
| 12 | `dettes_totales` | Dettes totales / Total debt | balance_sheet | liabilities | amount | monetary | false | true | 12 |
| 13 | `autres_passifs` | Autres passifs / Other liabilities | balance_sheet | liabilities | amount | monetary | false | false | 13 |
| 14 | `capitaux_propres` | Capitaux propres / Equity | balance_sheet | equity | amount | monetary | false | false | 14 |
| 15 | `produit_net_bancaire` | Produit net bancaire / Net banking income | income_statement | income_statement | amount | monetary | false | false | 15 |
| 16 | `produits_totaux` | Produits totaux / Total income | income_statement | income_statement | amount | monetary | false | false | 16 |
| 17 | `charges_totales` | Charges totales / Total expenses | income_statement | income_statement | amount | monetary | false | false | 17 |
| 18 | `resultat_exploitation` | Résultat d'exploitation / Operating result | income_statement | income_statement | amount | monetary | false | false | 18 |
| 19 | `resultat_net` | Résultat net / Net result | income_statement | income_statement | amount | monetary | false | false | 19 |
| 20 | `chiffre_affaires` | Chiffre d'affaires / Revenue | income_statement | income_statement | amount | monetary | false | false | 20 |
| 21 | `flux_exploitation` | Flux exploitation / Operating cash flow | cash_flow_statement | cash_flow | amount | monetary | false | false | 21 |
| 22 | `flux_investissement` | Flux investissement / Investing cash flow | cash_flow_statement | cash_flow | amount | monetary | false | false | 22 |
| 23 | `flux_financement` | Flux financement / Financing cash flow | cash_flow_statement | cash_flow | amount | monetary | false | false | 23 |
| 24 | `facilities_de_change` | Facilités de change / FX facilities | off_balance_sheet | debt_indicator | amount | monetary | false | true | 24 |
| 25 | `taux_interet_moyen` | Taux d'intérêt moyen / Average interest rate | not_applicable | debt_indicator | rate | non_monetary | false | true | 25 |
| 26 | `endettement_actifs` | Endettement sur actifs / Debt-to-assets ratio | not_applicable | debt_indicator | ratio | non_monetary | false | true | 26 |

### Définitions (FR / EN)

1. **`total_actifs`** — Somme totale des actifs telle que publiée au bilan. *Exclut* : engagements hors bilan, postes de passif. / Total assets as published in the balance sheet. *Excludes*: off-balance-sheet commitments, liability items.
2. **`tresorerie`** — Disponibilités, caisse et comptes auprès d'instituts d'émission/correspondants, tels que publiés. *Exclut* : créances interbancaires classées en `creances_banques`. / Cash, balances with central banks/correspondents as published. *Excludes*: interbank claims recorded under `creances_banques`.
3. **`creances_clients`** — Créances sur la clientèle telles que publiées (brut ou net selon le libellé source, précisé dans `notes`). *Exclut* : créances sur banques. / Loans and receivables from customers as published (gross or net per source label, noted in `notes`). *Excludes*: claims on banks.
4. **`creances_banques`** — Créances sur les établissements de crédit (interbancaire actif) telles que publiées. / Claims on credit institutions (interbank assets) as published.
5. **`immobilisations`** — Immobilisations corporelles et incorporelles publiées. *Exclut* : actifs financiers. / Property, plant, equipment and intangibles as published. *Excludes*: financial assets.
6. **`autres_actifs`** — Actifs publiés ne relevant d'aucune autre catégorie d'actif. / Published assets not covered by any other asset category.
7. **`total_passifs`** — Somme totale des passifs telle que publiée. / Total liabilities as published.
8. **`depots_clients`** — Dépôts et comptes créditeurs de la clientèle publiés. / Customer deposits and credit balances as published.
9. **`depots_banques`** — Dépôts et emprunts interbancaires reçus, publiés. / Interbank deposits received, as published.
10. **`emprunts_bancaires`** — Montant des emprunts contractés auprès d'établissements de crédit ou d'autres contreparties financières, tel que présenté dans les états financiers ou les notes annexes. *Exclut* : dépôts clientèle, dépôts interbancaires, titres de créance émis, capitaux propres. / Borrowings from credit institutions or other financial counterparties, as presented in financial statements or notes. *Excludes*: customer deposits, interbank deposits, issued debt securities, equity.
11. **`obligations_emises`** — Titres de créance émis (obligations, BMT/BTA émis) publiés. / Debt securities issued (bonds, issued T-bills/bonds) as published.
12. **`dettes_totales`** — Total des dettes financières publiées (emprunts et titres de créance émis). / Total financial debt as published (borrowings and issued debt securities).
13. **`autres_passifs`** — Passifs publiés ne relevant d'aucune autre catégorie de passif. / Published liabilities not covered by any other liability category.
14. **`capitaux_propres`** — Capitaux propres publiés (capital, réserves, report à nouveau, résultat). *Exclut* : dettes subordonnées classées en dettes. / Published equity (share capital, reserves, retained earnings, result). *Excludes*: subordinated debt classified as debt.
15. **`produit_net_bancaire`** — Produit net bancaire publié. *Exclut* : produits accessoires non inclus dans le PNB publié. / Net banking income as published. *Excludes*: ancillary income not included in published NBI.
16. **`produits_totaux`** — Total des produits publiés. / Total income as published.
17. **`charges_totales`** — Total des charges publiées. / Total expenses as published.
18. **`resultat_exploitation`** — Résultat d'exploitation publié. / Operating result as published.
19. **`resultat_net`** — Résultat net publié (part du groupe si précisé). / Net result as published (group share where specified).
20. **`chiffre_affaires`** — Chiffre d'affaires publié explicitement et identifié comme tel. **Interdiction de dériver le chiffre d'affaires du produit net bancaire.** Le PNB et le CA restent deux métriques distinctes. / Revenue explicitly published and identified as such. **Deriving revenue from net banking income is forbidden.** NBI and revenue remain two distinct metrics.
21. **`flux_exploitation`** — Flux net de trésorerie lié aux activités d'exploitation. / Net cash flow from operating activities.
22. **`flux_investissement`** — Flux net de trésorerie lié aux activités d'investissement. / Net cash flow from investing activities.
23. **`flux_financement`** — Flux net de trésorerie lié aux activités de financement. / Net cash flow from financing activities.
24. **`facilities_de_change`** — Montant publié sous un libellé source explicite de facilités/engagements de change. **Collecte uniquement lorsqu'un document publie un poste explicitement intitulé comme tel ; aucun mapping automatique approximatif.** Le libellé source exact est conservé dans `notes`. *Limitation documentée* : si les sources V1 ne permettent pas une identification fiable et reproductible, la métrique reste au catalogue **sans collecte** ; aucune donnée n'est produite. / Amount published under an explicit source label for foreign-exchange facilities/commitments. **Collected only when a document publishes a line explicitly labelled as such; no approximate automatic mapping.** The exact source label is kept in `notes`. *Documented limitation*: if V1 sources do not allow reliable, reproducible identification, the metric stays in the catalogue **without collection**; no data is produced.
25. **`taux_interet_moyen`** — Taux d'intérêt moyen publié, exprimé en pourcentage. Aucun calcul en V1. / Average interest rate as published, expressed as a percentage. No computation in V1.
26. **`endettement_actifs`** — Ratio d'endettement sur actifs publié, exprimé en ratio. Collecté uniquement lorsqu'il est explicitement publié ; aucun recalcul. / Debt-to-assets ratio as published, expressed as a ratio. Collected only when explicitly published; no recomputation.

### Vérification

Les 26 métriques disposent toutes de : `code`, `label_fr`, `label_en`, `definition_fr`, `definition_en`, `statement_type`, `category`, `value_type`, `currency_type`, `is_calculated`, `is_debt_related`. Aucune classification n'est laissée indéterminée.

---

## 9. Données publiées vs calculées

`metric_definitions.is_calculated` distingue « donnée publiée par la source » de « indicateur calculé par la plateforme ».

**En V1, les 26 métriques ont `is_calculated = false`** (collecte de valeurs publiées uniquement).

`endettement_actifs` n'est jamais recalculé. Les ratios calculés et leurs formules sont reportés en V2.

---

## 10. Table `documents`

```
id
title
document_type
institution_id            (nullable)
source_id                 (NOT NULL)
url
file_hash                 (UNIQUE when present)
file_size
storage_path
download_status
page_count
extraction_status
extracted_at
published_at
period_year
period_type
language
collected_at
error_message
```

- `institution_id` nullable : un document peut concerner une source générale ou plusieurs institutions.
- `source_id` NOT NULL.
- **Déduplication** : `file_hash` = SHA-256, **UNIQUE lorsqu'il est renseigné**. Stockage adressé par contenu.
- Ne jamais dédupliquer par `institution + année`. Deux documents de même année peuvent coexister.
- `file_hash` nul n'empêche pas l'enregistrement (document non encore téléchargé).

---

## 11. Versionnement des documents

Une nouvelle version ou correction d'un document ne doit **jamais** écraser silencieusement l'ancienne.

```
Rapport annuel 2024 — version initiale  → Document A → FinancialData A
Rapport annuel 2024 — version corrigée  → Document B → FinancialData B
```

- Les données restent liées au document exact dont elles proviennent.
- La provenance historique n'est **jamais** modifiée rétroactivement.
- **Pas de `supersedes_document_id` en V1.** Le versionnement repose sur des Documents distincts.

---

## 12. Table `financial_data`

```
id
institution_id            NOT NULL
source_id                 NOT NULL
document_id               NOT NULL
metric_code               NOT NULL
scope                     NOT NULL
period_type               NOT NULL
period_year               NOT NULL
period_label
value_original            NOT NULL
unit_original
currency_original         (nullable — NULL si non monétaire)
value_normalized
unit_normalized
currency_normalized
page_number
extraction_method
confidence_score
status                    NOT NULL
notes
extracted_at
verified_at
verified_by
```

### Contraintes

- FK `institution_id`, `source_id`, `document_id` NOT NULL ;
- `metric_code` NOT NULL → FK `metric_definitions.code` ;
- `value_original` NOT NULL ;
- `confidence_score` ∈ [0, 1] ;
- `page_number > 0` lorsqu'il existe ;
- `status ∈ {reviewed, verified}` ⇒ `value_normalized` NOT NULL ;
- `status = verified` ⇒ `verified_at` NOT NULL ET `verified_by` NOT NULL ;
- `currency_original` NULL autorisé (%, ratio, taux) — cohérence avec `metric_definitions.currency_type` contrôlée au niveau applicatif ;
- `period_label` cohérent avec `period_type` / `period_year` (§14) ;
- `scope` limité à `individual` / `consolidated` (§13) ;
- `unit_normalized` conforme à `value_type` (§5.1) — contrôlé applicativement.

---

## 13. Scopes

`financial_data.institution_id` étant NOT NULL, la V1 n'autorise que des scopes **rattachables à une institution** :

```
individual   → données publiées pour une institution prise isolément
consolidated → données publiées pour l'entité sur base consolidée (rattachées à l'institution déclarante)
```

**Interdits en V1** (aucune donnée `financial_data` créée avec ces valeurs) :

```
country   → agrégat pays
sector    → agrégat secteur
umoa      → agrégat union
```

Ces agrégats ne sont pas des données publiées stockées ; ils seront **calculés ultérieurement** à partir des données institutionnelles. Aucune institution artificielle ne sera créée pour les représenter.

**Conséquence rankings** : les classements sectoriels/UMOA V1 fonctionnent exclusivement par agrégation des données institutionnelles existantes (au niveau API/UI), sans jamais créer de donnée agrégée fictive stockée.

---

## 14. Énumérations de référence

**`document_type`**

```
annual_report | financial_statement | regulatory_report | press_release | web_page | other
```

**`source_type`** (canonique — identique backend/frontend)

```
regulatory | central_bank | bank | banking_group | government | financial_market | secondary
```

**`period_type`**

```
annual | semi_annual | quarterly
```

**`period_label`**

```
annual      → "YYYY"                (ex. 2024)
semi_annual → "S1 YYYY" | "S2 YYYY"
quarterly   → "T1 YYYY" | "T2 YYYY" | "T3 YYYY" | "T4 YYYY"
```

**`extraction_method`**

```
pdf_table | pdf_text | ocr | web_html | manual
```

**`status`**

```
extracted | needs_review | reviewed | verified | rejected
```

**`scope`**

```
individual | consolidated
```

**`statement_type`**

```
balance_sheet | income_statement | cash_flow_statement | off_balance_sheet | not_applicable
```

**`category`**

```
assets | liabilities | equity | income_statement | cash_flow | debt_indicator
```

**`value_type`**

```
amount | percentage | ratio | rate
```

**`currency_type`**

```
monetary | non_monetary
```

**`download_status`**

```
pending | downloaded | failed
```

**`extraction_status`**

```
pending | extracted | failed | skipped
```

---

## 15. Workflow de validation

**Règle absolue : aucun processus automatique d'extraction, de parsing ou de normalisation ne peut attribuer directement `verified`.**

Transitions autorisées :

```
extracted ──▶ needs_review ──▶ reviewed ──▶ verified
     │              │              │
     └──────────────┴──────────────┴──▶ rejected
```

- **Interdit** : `extracted → verified` (et toute transition sautant `reviewed`).
- **`needs_review`** : extraction incertaine / valeur ambiguë / règle d'identification incertaine.
- **`reviewed`** : examen humain effectué. Condition : `value_normalized` NOT NULL.
- **`verified`** : confronté à la source originale. Conditions : `value_normalized` NOT NULL **ET** `verified_at` NOT NULL **ET** `verified_by` NOT NULL.
- **`rejected`** : valeur incorrecte/inexploitable. Conservée (jamais supprimée physiquement).

Seule une **action humaine explicite** peut produire `reviewed`, `verified` ou `rejected`. Les transitions sont contrôlées par la logique applicative et couvertes par des tests.

### Conditions par étape

```
reviewed
→ value_normalized NOT NULL

verified
→ value_normalized NOT NULL
→ verified_at NOT NULL
→ verified_by NOT NULL
```

---

## 16. `verified_by`

Aucune table `User` n'existe en V1.

`verified_by` est un **identifiant texte du validateur** (`String(100)`), documenté comme **identifiant technique de validation** (ex. code d'agent ou adresse e-mail) et **non comme un nom libre destiné à l'affichage**. Il ne doit pas être exposé comme nom d'affichage.

Une future authentification remplacera ce champ par une FK utilisateur — migration prévue sans rupture de provenance.

---

## 17. Déduplication et versionnement

- **Même `file_hash`** ⇒ déduplication (pas de second enregistrement du fichier).
- **`file_hash` différent** ⇒ nouveau Document potentiel, **même** institution et **même** période.
- Documents corrigés / republiés ⇒ nouveaux Documents distincts (§11).
- L'`URL` seule ne suffit pas à dédupliquer.
- Aucun remplacement silencieux d'un Document existant.

Règle :

> Même fichier = déduplication.
> Fichier différent = nouveau Document potentiel, même s'il concerne la même institution et la même période.

---

## 18. Contrat API V1

Base `/api/v1/`.

Pagination commune : `page` (≥1, défaut 1), `page_size` (défaut 20, max 100).
Réponse liste : `PaginatedResponse<T>` (`items, total, page, page_size, has_next, has_prev`).
Routes **sans slash final**.
Erreurs : `400` (paramètre invalide), `404`, `422` (validation), `500`.

```
GET /api/v1/health
GET /api/v1/countries              ?is_active,page,page_size
GET /api/v1/sources                ?source_type,is_active,page,page_size
GET /api/v1/banking-groups         ?search,page,page_size
GET /api/v1/metrics                ?statement_type,category,is_active,is_debt_related,page,page_size
GET /api/v1/metrics/{code}
GET /api/v1/institutions           ?country_code,banking_group_id,institution_type,status,search,page,page_size
GET /api/v1/institutions/{id}
GET /api/v1/documents              ?institution_id,source_id,document_type,period_year,download_status,extraction_status,page,page_size
GET /api/v1/documents/{id}
GET /api/v1/financial-data         ?institution_id,metric_code,period_type,period_year,period_label,scope,status,currency_normalized,page,page_size
GET /api/v1/financial-data/{id}
GET /api/v1/rankings               ?metric_code(requis),period_type,period_year,period_label,scope,currency_normalized,order(asc|desc),limit
GET /api/v1/search                 ?q(requis),types,page,page_size
```

**`/api/v1/rankings`** — n'inclut que `status = verified`. Refuse (`400`) toute comparaison de `currency_normalized` différentes ou d'unités incompatibles. Si plusieurs devises sont présentes sans filtre `currency_normalized`, renvoie `400`. Réponse par devise : `{rank, institution_id, institution_name, country, value_normalized, unit_normalized, currency_normalized, period_label, scope}`. Les vues sectorielles/UMOA sont produites côté API **par agrégation** des données institutionnelles (jamais par données stockées fictives).

**`/api/v1/financial-data`** — expose systématiquement la provenance complète (§4) et le statut.

**`/api/v1/search`** — recherche multi-entités (`types ∈ {institutions, documents, financial_data}`), correspondance `ILIKE` en V1 (pas d'index full-text). Réponse : résultats groupés par type + total par groupe.

---

## 19. Frontend V1

Routes :

```
/[locale]                     (Dashboard)
/[locale]/institutions
/[locale]/institutions/[id]
/[locale]/documents
/[locale]/documents/[id]
/[locale]/financial-data
/[locale]/rankings
/[locale]/search
```

- **Dashboard** : synthèse (nb institutions, sources, documents, données par statut). Aucune donnée fictive.
- **Institutions** / détail : filtres (pays, groupe, type, statut), pagination, provenance.
- **Documents** / détail : filtres (type, année, statut), provenance, lien source.
- **Financial Data** : filtres (métrique, période, scope, statut, devise) ; affichage **valeur originale + unité + devise** ET **valeur normalisée + unité + devise** ; page, méthode, statut.
- **Rankings** : uniquement `verified`, devise unique, indisponible si devises hétérogènes ; vues sectorielles/UMOA par agrégation à l'affichage.
- **Search** : recherche globale avec filtres par entité.
- **Transversal** : affichage provenance + statut systématique ; FR/EN via next-intl ; états vides conformes.
- **Alignement types** : `DocumentType` (+`web_page`) ; `Source.type` (`group` → `banking_group`) ; ajout champs devise + `unit_normalized` ; ajout `MetricDefinition` ; `period_type` canonique (`semi_annual`).

### Filtres, pagination, comparaison

- Filtres et pagination communs à toutes les listes.
- **Comparaison** : uniquement entre données comparables (§5.4).
- **Provenance** et **statut** affichés partout où une donnée est présentée.
- FR/EN pour toutes les chaînes de l'interface.

---

## 20. Critères d'acceptation

### Base de données

- migration exécutable depuis une base vide ;
- FK valides ;
- CHECK valides ;
- 26 métriques présentes ;
- aucune donnée fictive.

### Traçabilité

Toute `financial_data` `verified` doit pouvoir retrouver : institution, source, document, page si disponible, période, valeur originale, unité originale, devise originale, valeur normalisée, unité normalisée, devise normalisée, méthode d'extraction.

### Rankings

- impossible d'inclure une donnée non `verified` ;
- impossible de comparer des devises différentes.

### Scraping

Le connecteur BCEAO doit fonctionner uniquement à partir de données/sources réelles ou de fixtures explicitement identifiées comme fixtures de test.

### Workflow

- `extracted → verified` est rejeté ;
- `extracted → needs_review → reviewed → verified` est accepté si toutes les conditions sont remplies.

### Tests supplémentaires exigés

**Normalisation**

```
"8 542 millions XOF" → value_normalized = 8542000000, unit_normalized = "absolute", currency_normalized = "XOF"
                       (aucune conversion FX)
```

**Devises**

```
"125.4 million USD" → value_normalized = 125400000, unit_normalized = "absolute", currency_normalized = "USD"
                      (ne devient jamais XOF)
```

**Unités non monétaires**

```
"6,25 %"  → value_normalized = 6.25,  unit_normalized = "%",     currency_normalized = NULL
"1,25"    → value_normalized = 1.25,  unit_normalized = "ratio", currency_normalized = NULL
```

**Scope**

```
Création financial_data avec scope = "sector" ou "umoa" → rejetée (422).
scope ∈ {"individual", "consolidated"} uniquement.
```

**Workflow**

```
extracted → verified                              → rejetée
extracted → needs_review → reviewed → verified    → acceptée si value_normalized, verified_at, verified_by renseignés
```

---

## 21. Règles de garde (implémentation)

### Garde n°1 — `facilities_de_change`

- **Aucun mapping sémantique automatique.** Un poste bancaire « proche » (engagements de financement, lignes de crédit confirmées, facilités de caisse, concours bancaires, position de change) ne doit **jamais** être converti en `facilities_de_change` par ressemblance de libellé.
- Collecte **uniquement** si un document publie un poste explicitement identifiable comme facilité/engagement de change.
- Le libellé source exact est conservé dans `notes` ; en cas de doute → `needs_review`, jamais `extracted`.
- Si aucun libellé exploitable n'existe, la métrique reste au catalogue **sans collecte**.

### Garde n°2 — données `consolidated`

- Pour toute donnée `scope = consolidated`, l'`institution_id` **doit** correspondre à l'**entité déclarante/consolidante** identifiée dans le document (l'entité dont les comptes consolidés sont publiés), **jamais** à une filiale mentionnée dans le périmètre de consolidation.
- Si l'entité déclarante/signataire n'est pas identifiable sans ambiguïté → donnée bloquée en `needs_review` et rattachement non forcé.

---

## 22. Plan d'implémentation (phases)

- **Phase 0** — Documentation et alignement des règles.
- **Phase 1** — Modèles SQLAlchemy (`MetricDefinition`, `Document`, `FinancialData`) + catalogue des 26 métriques.
- **Phase 2** — Migration Alembic + contraintes (FK/CHECK/UNIQUE) + seeds (26 métriques).
- **Phase 3** — Services backend + API `/api/v1/`.
- **Phase 4** — Pipeline scraping (interfaces) : discovery → download → storage → parsing → normalization → validation.
- **Phase 5** — Connecteur BCEAO.
- **Phase 6** — Frontend.
- **Phase 7** — Tests complets.
- **Phase 8** — Intégration et documentation finale.

Protocole : chaque phase est implémentée, testée et validée avant de passer à la suivante. Aucune phase ne tente d'implémenter l'ensemble du projet en une seule passe.

---

## 23. Impact sur l'existant (alignement)

| Fichier | Alignement requis |
|---|---|
| `docs/architecture.md` | Unité/devise (§5), `semi-annual`→`semi_annual`, nouvelles tables, endpoints |
| `docs/dev-rules.md` | Distinction unité/devise, 26 métriques, versionnement, `verified_by`, gardes |
| `backend/app/models/__init__.py` | Exporter `MetricDefinition`, `Document`, `FinancialData` |
| `backend/migrations/env.py` | Importer les nouveaux modèles |
| `backend/app/api/v1/` | Nouveaux routers métier |
| `backend/app/main.py` | Enregistrer les routers métier |
| `frontend/src/types/index.ts` | `group`→`banking_group`, `web_page`, champs devise, `MetricDefinition`, `period_type` |
| `frontend/src/lib/api.ts` | Slash final, nouveaux endpoints |
| `.env.example` | Aucun changement bloquant (stockage déjà présent) |