# Deal Intelligence (Phase 13)

Suivi des transactions de financement (prêts, prêts syndiqués, financements de projet,
obligations, garanties…) **lorsque l'information existe réellement dans les sources**.
Même plateforme, même provenance, même Review Center, même piste d'audit que les données
financières des banques.

## 1. Principes

- **Une seule porte d'écriture** : l'importeur structuré (CLI, JSON / CSV, validation Pydantic).
  Les collecteurs automatiques (UMOA-Titres §7, BRVM, AMF-UMOA, IFC, BOAD, Proparco §11) produisent
  des enregistrements de ce même format et passent par ce même importeur.
- **Provenance obligatoire** : chaque transaction cite au moins un document existant, sa source
  et une page ; chaque champ non nul et chaque participant est attribué à une de ces sources.
- **Statut initial `needs_review`**, toujours. Un statut fourni dans le fichier est refusé.
- **Champs non publiés = NULL** (affichés « Non publié »), jamais 0 ni moyenne de marché : montant,
  taux, marge, maturité, différé, commissions, garanties, dette, fonds propres, dates.
- **Rôles explicites**, attestés par une source, jamais déduits : `borrower`, `lender`, `arranger`,
  `co_arranger`, `agent`, `guarantor`, `sponsor`, `advisor`, `investor`.
- **Aucune conversion de devise**, aucun total entre devises ou unités différentes.
- **Descriptif uniquement** : aucune note, aucun classement, aucune recommandation.

## 2. Modèle (migration `0007_deal_intelligence`)

| Table | Contenu |
|---|---|
| `deals` | intitulé, type, pays, secteur, projet, montant publié (`amount_original`) et normalisé (`amount`, `currency`, `unit`), taux, type de taux, référence, marge (pb), maturité / différé (mois), commissions, garanties, 4 dates, statut, `merged_into_deal_id` |
| `deal_participants` | nom, `institution_id` (référentiel `institutions`, NULL si hors répertoire), rôle, engagement, source attestant le rôle |
| `deal_sources` | document, source, page, extrait (provenance au niveau transaction) |
| `deal_field_sources` | champ → source(s) qui l'attestent (provenance au niveau champ) |
| `deal_duplicate_candidates` | paire de transactions, critères concordants (liste explicite, sans score), état, décision humaine |

Emprunteur, sponsor, arrangeur et co-arrangeur sont des **participants** avec ce rôle
(0..n chacun) — une seule source de vérité.

## 3. Import

```bash
cd backend
python -m scraping import-deals --file deals.json --actor analyste-1 --dry-run   # valide, n'écrit rien
python -m scraping import-deals --file deals.json --actor analyste-1             # tout ou rien
```

Codes de sortie : `0` importé (ou dry run valide), `2` refusé (rien n'est écrit).

### JSON (liste d'objets)

```json
[{
  "title": "Prêt syndiqué — Autoroute du Nord",
  "deal_type": "syndicated_loan", "country_code": "SN", "project_name": "Autoroute du Nord",
  "amount_original": "25 milliards FCFA", "amount": "25000000000", "currency": "XOF", "unit": "units",
  "signing_date": "2024-03-15",
  "participants": [
    {"role": "borrower", "name": "État du Sénégal", "source_ref": "s1"},
    {"role": "arranger", "name": "Banque A", "institution_id": "<id institution>", "source_ref": "s1"}
  ],
  "sources": [{"ref": "s1", "document_id": "<id document>", "source_id": "<id source>", "page": 3,
               "excerpt": "…", "fields": ["title", "deal_type", "country_code", "project_name",
               "amount_original", "amount", "currency", "unit", "signing_date"]}]
}]
```

### CSV

Colonnes plates (noms identiques au JSON), plus deux colonnes encodées :

- `sources` : `ref|document_id|source_id|page|champ,champ,…[|extrait]`, séparées par `;`
- `participants` : `role|nom|institution_id|source_ref[|montant|devise]`, séparés par `;`

Une cellule vide = non publié = NULL.

### Refus (rien n'est écrit)

JSON / CSV invalide, champ obligatoire manquant, type incorrect, date non ISO, devise hors
ISO 4217, montant ≤ 0, rôle inconnu, statut fourni, document / source / pays / établissement
inexistant, document d'une autre source, page hors du document, champ non nul sans source,
source attestant un champ vide. Chaque problème est rapporté avec le numéro d'enregistrement,
le champ et un code. Rien n'est jamais créé implicitement (un participant sans
`institution_id` reste hors répertoire).

## 4. Doublons potentiels

À l'import, chaque nouvelle transaction est comparée aux transactions existantes non rejetées :

| Critère | Règle |
|---|---|
| `borrower` | même emprunteur (même `institution_id` ou même nom normalisé) |
| `project` | même projet (nom normalisé) |
| `currency_amount` | même devise et montants à ±5 % |
| `dates` | signatures ou annonces à ≤ 90 jours |
| `deal_type` | même type |
| `participants` | au moins un participant commun (hors emprunteur et hors émetteur) |
| `issuer` | même émetteur (entité de l'Entity Hub, sinon nom normalisé) — l'émetteur n'est compté que par ce critère |
| `instrument` | même ISIN **et** même date de valeur (ancrage) |
| `counterparty` | l'emprunteur de l'une est l'émetteur de l'autre (prêt d'une IFD ↔ obligation cotée) — ancrage ; ajouté seulement si `borrower` et `issuer` n'ont pas concordé (une partie n'est jamais comptée deux fois) |
| `isin` | même ISIN, date de valeur absente ou différente — **pas** un ancrage (une réouverture reste une autre transaction) |
| `label_issuer` | intitulés obligataires publiés (« PAD 6,60% 2020-2027 ») dont les mots, hors coupon, années et termes génériques, se recouvrent à ≥ 60 % — ancrage |
| `coupon` | même coupon imprimé dans l'intitulé |
| `tenor_years` | mêmes années d'émission et d'échéance dans l'intitulé |

`project` accepte aussi deux intitulés de projet dont les mots significatifs se recouvrent à ≥ 80 %
(au moins trois mots chacun). Les critères d'intitulé ne sont lus que sur un titre imprimant **à la
fois** un coupon et une plage d'années. Ils rapprochent l'index AMF (sans participant) de la cote BRVM.

Un **doublon potentiel** est créé si un ancrage (emprunteur, projet, instrument, contrepartie ou
émetteur de l'intitulé) concorde **et** au moins
trois critères au total. Les critères sont stockés et affichés tels quels. Aucune fusion,
aucune suppression automatique. Libellés : « Doublon potentiel — à revoir » ; jamais
« doublon confirmé » avant décision.

Décision humaine (`POST /api/v1/data-quality/deal-duplicates/{id}/decide`) :
`same_deal`, `distinct_deals` ou `same_deal_multi_source`. « Même transaction » rattache la
transaction secondaire à la principale (`merged_into_deal_id`) ; ses sources, participants et
historique restent visibles sur la fiche principale. La vérification d'une transaction est
refusée (409 `unresolved_duplicate_candidate`) tant qu'un doublon potentiel la concernant n'est
pas décidé. Chaque décision est tracée (acteur, motif, date) sur les deux transactions.

## 5. API

| Méthode | Route | Rôle |
|---|---|---|
| GET | `/api/v1/deals` | explorateur (filtres `country`, `bank`, `deal_type`, `sector`, `year`, `currency`, `status`, `participant_role`, `borrower`, `arranger`, `include_merged` ; pagination ≤ 100) |
| GET | `/api/v1/deals/{id}` | fiche : conditions, dette / fonds propres et ratio, participants, chronologie, provenance (avec la citation par champ `field_excerpts`), doublons, transactions rattachées |
| GET | `/api/v1/deals/{id}/history` | piste d'audit |
| GET | `/api/v1/deals/analytics?dimension=country\|year\|type\|sector\|institution` | comptages ; montants par devise **et** unité (transactions revues / vérifiées uniquement) |
| GET | `/api/v1/data-quality/deals` | file de revue |
| POST | `/api/v1/data-quality/deals/{id}/review\|verify\|reject` | décisions (actor, motif, 404 / 409 / 422) |
| GET | `/api/v1/data-quality/deal-duplicates` | doublons potentiels ouverts |
| POST | `/api/v1/data-quality/deal-duplicates/{id}/decide` | décision sur un doublon |
| POST | `/api/v1/ingestion/trigger?source=…&scope=all\|financial\|deals&since=…&until=…` | collecte à la demande (§11.4) |

Année d'une transaction : date de signature, sinon date d'annonce, sinon date de valeur (titres
publics) — règle documentée, identique côté API et interface.

## 6. Interface

- `/[locale]/deals` : explorateur (filtres dans l'URL, pagination) + vue descriptive.
- `/[locale]/deals/[dealId]` : résumé, conditions financières, participants, chronologie,
  projet / emprunteur, garanties, sources / provenance (par champ), doublons, historique.
- `/[locale]/data-quality?tab=deals` et `/[locale]/data-quality/deals/[dealId]` : revue.
- Liens : établissement → « Transactions impliquant cet établissement » (`/deals?bank=<id>`) ;
  participant → fiche établissement.

## 7. Titres publics UMOA-Titres (migration `0014_public_debt_instruments`)

Première source réelle : les **résultats d'adjudication** publiés par l'Agence UMOA-Titres
(`python -m app.deals.umoa_titres_run --since 2025-01-01`). Périmètre initial : **OAT** des
8 États depuis le 01/01/2025. Les annonces (avis d'appel d'offres, termes et conditions) ne
créent jamais de transaction.

- Source de vérité : le PDF « Compte rendu d'adjudication » de chaque émission, contrôlé avec
  les résultats imprimés sur la page d'émission (montant retenu, rendement, dates, échéance).
  Une contradiction entre les deux → l'adjudication entière est écartée et signalée.
- Une transaction `sovereign_bond` par **tranche OAT dont le montant retenu est > 0**. Tranche à
  `0`, `--` ou sans résultat → aucune transaction (jamais un montant 0). Plusieurs tranches →
  plusieurs transactions, jamais fusionnées.
- Valeurs telles que publiées : montant en millions de F CFA (`unit = millions`, `currency =
  XOF`), coupon (`interest_rate`, fixe), rendement moyen pondéré (`yield_rate`), ISIN, référence
  d'adjudication, dates d'adjudication / de valeur / d'échéance. Seule transformation : la durée
  « N ans » exprimée en mois (N × 12) ; une durée en jours laisse `maturity_months` NULL.
  Une valeur ambiguë (ex. coupon imprimé « 0,057 » sans %) reste NULL.
- Émetteur : participant `issuer` rattaché (`deal_participants.entity_id`) à l'une des 8 entités
  `sovereign_state`, uniquement si l'émetteur imprimé (« ETAT DU MALI ») et le préfixe pays de
  l'ISIN désignent le même pays. Aucune entité n'est créée.
- Provenance : PDF (page) + page d'émission, champ par champ ; extrait indiquant la méthode
  (`pdf_text` / `web_html`), la référence d'adjudication et l'ISIN. Import par l'importeur
  Phase 13 : statut `needs_review`, événement d'audit `import`.
- Idempotence : `ingestion_key` déterministe (pays, référence d'adjudication, ISIN, date de
  valeur), unique parmi les transactions non supprimées. Relancer ne recrée rien.
- Doublons potentiels : ancrage supplémentaire `instrument` (même ISIN **et** même date de
  valeur) + critère `issuer`. Deux tranches d'une adjudication (ISIN différents) ou deux
  réouvertures d'un ISIN (dates de valeur différentes) ne sont jamais signalées.
- Le downgrade de la migration 0014 est refusé tant qu'une transaction utilise ces champs.
- Formats lus : comptes rendus à plusieurs titres et à titre unique ; documents « EC »
  (émission + rachat) : la page de rachat (références `RA-…` ou titre « COMPTE RENDU DE RACHAT »
  sans référence `ADJ-…`) n'est jamais une émission. Références d'adjudication conservées telles
  qu'imprimées (année tronquée, espace parasite). Deux montants de tranche fusionnés sur une même
  ligne restent refusés (séparateurs de milliers ambigus).
- **Drapeaux de validation** (`deals.validation_flags`, migration `0015_deal_validation_flags`),
  liste fermée, jamais de modification de valeur ni de statut :
  - `global_total_rounded` : le total global imprimé est un entier (aucune décimale imprimée) égal
    à l'arrondi de la somme des tranches ; les montants de tranche du PDF sont conservés. Tout autre
    écart refuse le document (pas d'élargissement général de la tolérance) ;
  - `issuer_label_truncated` : émetteur imprimé tronqué (« ETAT DE GUINÉE-BISSA »), accepté
    uniquement si le préfixe ISIN de chaque titre est `GW` ; la règle est écrite dans l'extrait de
    provenance (`règle truncated_label_confirmed_by_isin_prefix_GW`) ;
  - `page_lists_buyback_securities` : la page d'émission d'une adjudication « émission + rachat »
    liste aussi les titres rachetés. Appariement par **sous-ensemble vérifié** uniquement : chaque
    tranche du PDF a sa ligne (clé type + échéance unique des deux côtés) et concorde (montant,
    rendement, échéance) ; chaque ligne en trop est sans montant retenu **et** figure sur la page de
    rachat du même PDF. Le détail du drapeau cite la page de rachat et ses références `RA-…`. Une
    ligne de rachat ne crée jamais de transaction.
- Rapport d'exécution : chaque URL de l'index reçoit une seule issue (hors périmètre, BAT seules,
  résultats non publiés, compte rendu absent, mise en page non reconnue, rachat seul, écartée par
  motif, aucune OAT émise, déjà importée, produite…) ; l'entonnoir se réconcilie exactement. Les
  adjudications écartées gardent le champ en conflit et les valeurs page / PDF.

## 8. Limites

- Extraction automatique : UMOA-Titres (§7) et les sources du §11 ; le reste dépend d'imports
  structurés. Les limites propres à chaque source sont au §11.6.
- Détection de doublons en Python sur les transactions portant un ancrage, un émetteur ou un intitulé
  obligataire (volume V1).

## 9. Sourcing des rôles (Phase 19, migration `0016_deal_sourcing_roles`)

Implémente les décisions D1 à D5 du 05/10/2026 (`audits/ape_amf/07_proposition.md`).

- **Types** ajoutés : `sovereign_bond_ape`, `corporate_bond_ape`, `corporate_bond_private`, `debt_buyback`,
  `debt_exchange`, `debt_reprofiling`, `securitisation`, `capital_increase`, `share_sale_public`,
  `takeover_offer`. Les valeurs existantes restent valides ; `bond`, `corporate_bond` et `equity` ne
  sont plus utilisés pour les nouvelles saisies. Le type vient de la nature AMF et du document, jamais
  du seul libellé.
- **Rôles** ajoutés, uniquement s'ils sont nommés : `lead_manager`, `co_lead_manager`,
  `placement_syndicate_member` (seulement si la note énumère les membres), `financial_advisor`,
  `anchor_investor`, `refinanced_lender`, `selling_shareholder`, `paying_agent`.
  « Arrangeur et chef de file : X » = deux participations (`arranger` + `lead_manager`, D1).
  Chaque participation peut porter sa page, sa citation et sa méthode de lecture
  (`text`, `visual_logo`, `visual_scan`).
- **Utilisation des fonds** : `use_of_proceeds` (citation) et `use_of_proceeds_categories` (liste fermée,
  plusieurs valeurs), avec provenance au niveau du champ.
- **`filing_agent_raw`** : la SGI déclarante de l'API AMF, stockée en texte brut. Ce n'est jamais un rôle (D2) :
  une source `regulator_index` ne peut attester aucune participation.
- **Classes de source** (`deal_sources.source_class`) : `primary_regulatory`, `primary_market`,
  `issuer_official`, `issuer_press_release`, `regulator_index`, `press_reported`. Presse : éditeur, titre,
  URL, date, `paywalled` ; jamais le corps de l'article (D4). Un article payant n'atteste aucun champ ni rôle.
- **Garde de vérification** : une transaction attestée uniquement par `press_reported` / `regulator_index`
  ne peut pas passer `verified` (409 `secondary_source_only`) tant qu'une source primaire n'est pas ajoutée.
- **`institution_links`** : lien SGI → banque à deux niveaux (D3). `documented_bank` désigne une
  institution de la liste officielle ; `documented_group_only` ne garde que le libellé du groupe et
  n'attribue aucune transaction à une banque. Source, citation et date d'observation obligatoires ;
  statut `needs_review` par défaut.
- Le downgrade de `0016` est refusé tant que le nouveau vocabulaire ou les nouvelles colonnes sont utilisés.

## 10. Pilote (Phase 19) — saisie contrôlée de deals réels

Protocole : `audits/ape_amf/08_pilote.md`. Manifeste : `backend/pilot/build_manifest.py` → `backend/pilot/pilot_manifest.json`
(13 deals dont la référence est établie dans l'audit, 15 documents, 5 liens SGI → banque).

```bash
cd backend
python pilot/build_manifest.py                      # régénère le manifeste
DATABASE_URL=postgresql+asyncpg://…/umoa_pilot \
python -m app.deals.pilot_load --manifest pilot/pilot_manifest.json --expect-db umoa_pilot \
       --files ../audits/ape_amf --actor <identifiant> --dry-run   # puis sans --dry-run
```

- Base dédiée obligatoire (`--expect-db`), jamais `umoa_banking`, révision Alembic `0016` minimum.
- Sources et documents enregistrés explicitement depuis le manifeste (rapprochés par URL). Avec `--files`,
  la copie locale donne le SHA-256 et le nombre de pages, et **chaque citation lue dans le texte est
  recherchée sur sa page** : une seule citation introuvable refuse tout le chargement (58 citations
  vérifiées sur le manifeste livré). Les lectures `visual_logo` / `visual_scan` sont laissées à la revue humaine.
- Banques rattachées **par nom officiel exact** uniquement ; sinon participant « hors répertoire ».
  Un lien `documented_bank` dont la banque n'est pas trouvée exactement n'est pas créé.
- Tout passe par l'importeur Phase 13 : `needs_review`, provenance par champ, événement d'audit.
  Idempotent (`ingestion_key = pilot:<clé>`).

## 11. Collecte automatique de deals publics (migration `0020_deal_collection`)

### 11.1 Chaîne

```
discover()  ── sitemap / index / API de la source, fenêtre since–until
   │           (point de contrôle : une page inchangée — même lastmod — n'est pas relue)
   ▼
PoliteFetcher ── robots.txt (jokers * et $), Crawl-delay par hôte, accès restreint signalé
   ▼
read()      ── parseur pur de la source → enregistrements d'import (2 passes : identifiant
   │           provisoire pour décider, puis identifiant du document enregistré)
   ▼
DocumentRegistrar (SHA-256) + import_deals(validate_records(…))  ── une seule transaction
```

Code : `backend/scraping/deals/collect/` (`base.py`, `amounts.py`, un module par source) ;
orchestration : `backend/app/services/deal_collection.py`.

Chaque URL candidate reçoit **une** issue parmi les suivantes :
- `produced`, `already_imported`, `out_of_scope`, `not_a_deal` ;
- `refused` (contradiction ou valeur ambiguë), `import_refused` ;
- `fetch_failed`, `restricted` (robots.txt, 401 / 402 / 403 / 451, mur de connexion — jamais contourné) ;
- `error`.

Les issues sont conservées dans `deal_collection_checkpoints`. Les issues transitoires (`fetch_failed`,
`restricted`, `error`) sont retentées au passage suivant.

### 11.2 Règles communes

- **Statut** : `needs_review` à la création (importeur) ; `reviewed` / `verified` seulement par le
  workflow de revue. Une transaction attestée uniquement par l'index AMF (`regulator_index`) ne peut
  pas être vérifiée (409 `secondary_source_only`).
- **Citation par champ** : chaque champ non nul porte sa citation (`deal_field_sources.excerpt`). S'y
  ajoutent l'extrait de la source (`deal_sources.excerpt`), la page (PDF), l'URL, l'éditeur et la date
  de publication.
- **Montants** : lus seulement avec une devise et une échelle explicites (`10 Mds FCFA`,
  `79.29 million (USD)`, `20 MUSD`). Un texte portant deux montants, aucune devise ou un séparateur
  ambigu (`1.250`) ne donne **rien**. « FCFA » est lu comme XOF seulement pour les éditeurs de l'UMOA
  (BOAD) et les montants que l'IFC publie en XOF ; « dollars » seul n'est jamais lu (seulement
  « dollars américains / US ») ; aucune conversion.
- **Convention de stockage (audit du 22/10/2026)** : `amount` est le chiffre **tel que publié dans son
  unité** et `amount × échelle(unit)` est la valeur, pour toutes les sources : « 10 Mds FCFA » →
  `amount = 10, unit = billions` ; UMOA-Titres « 4 431,25 millions » → `amount = 4431.25, unit =
  millions`. Les totaux, l'affichage et la détection de doublons appliquent l'échelle ; deux unités
  différentes ne sont jamais additionnées telles quelles.
- **Points de reprise** : chaque collecteur a une `parser_version` (migration 0023). Une page dont la
  lecture s'est terminée par un résultat « final » (`not_a_deal`, `refused`…) est relue quand la version
  du parseur change ; `python -m app.deals.collect_run --recheck` relit tout.
- **Échecs partiels** : une page d'index BRVM ou un flux presse indisponible, un robots.txt illisible
  (5xx) ou une liste AMF tronquée sont signalés dans les erreurs du run (`deals_discovery`), qui se
  termine alors en `partial_failure` — jamais en silence.
- **Rôles** : seulement quand la source les nomme, jamais déduits du contexte.
- **Dette / fonds propres** : `debt_amount` et `equity_amount` seulement s'ils sont publiés comme tels.
  Le ratio dette / fonds propres n'est pas stocké : l'API le calcule (`debt_equity_ratio`) uniquement
  si les deux montants sont publiés pour la même transaction. Aucune des sources actuelles ne publie
  cette structure de façon fiable, donc ces champs restent vides pour elles (§11.6).
- **Classe `dfi_official`** : divulgation sur le domaine de l'institution de financement elle-même.
  Elle est primaire pour **sa propre** participation. La transaction enregistrée est l'opération de
  financement de cette institution, et le montant est son engagement publié (drapeau
  `dfi_own_commitment_only` ; le coût total du projet n'est pas repris).
- **Doublons** : critères du §4, contre toutes les transactions existantes, toutes sources confondues.
  Toujours `duplicate_candidate`, **jamais de fusion automatique**.

### 11.3 Sources et champs réellement extraits

| Source | Découverte | Classe | Champs extraits | Jamais extraits (non publiés à cet endroit) |
|---|---|---|---|---|
| **UMOA-Titres** (OAT) | index des émissions + comptes rendus PDF (§7) | `primary_market` | titre, type, pays, montant retenu, devise, unité, coupon, type de taux, maturité, ISIN, référence, dates d'adjudication / valeur / échéance, rendement moyen pondéré, émetteur (entité souveraine) ; citation par champ ajoutée en 0020 | arrangeur, garanties |
| **BRVM** | BOC quotidiens (`/fr/bulletins-officiels-de-la-cote`), table « OPERATIONS EN COURS », lignes « Première cotation » de symboles obligataires `.O<n>` | `primary_market` | intitulé + symbole, coupon imprimé, date du bulletin (annonce), émetteur (colonne « Emetteur ») | montant, ISIN, arrangeur, échéance, type (drapeau `listing_notice_only`) |
| **AMF-UMOA** | API publique `service/api/elastic/operation` (index) | `regulator_index` | intitulé ; type, déduit de la nature AMF **et** de l'intitulé (APE → `sovereign_bond_ape` / `corporate_bond_ape`, EOP → `corporate_bond_private`, OPV → `share_sale_public` ou `capital_increase`, OPA → `takeover_offer` ; contradiction → vide) ; pays, seulement s'il est nommé dans l'intitulé ; `filing_agent_raw` | montant, taux, durée, émetteur de l'API, rôles (décision D2) |
| **IFC** | sitemap public de `disclosures.ifc.org` (pages SII) | `dfi_official` | n° et nom du projet, pays, secteur (Industry), date de divulgation (annonce), date de signature (« Signed »), investissement approuvé par le Conseil (montant, devise, unité), lignes de produit → IFC `lender` / `investor` / `guarantor` avec engagement, entreprise `borrower` (prêt) ou `issuer` (fonds propres seuls) | coût total du projet (texte libre), autres financeurs, taux, maturité |
| **BOAD** | « Nos projets approuvés » (données Inertia de la page) | `dfi_official` | intitulé, date d'approbation, pays, domaine → secteur, montant (`10 Mds FCFA`), objectifs → `use_of_proceeds` ; BOAD `lender` / `guarantor` / `investor` **si l'intitulé nomme l'instrument** ; bénéficiaire (« en faveur de … ») `borrower` | répartition du financement (« graph »), coût total, taux, durée |
| **Proparco** | sitemap public, fiches `/fr/carte-des-projets/<slug>` | `dfi_official` | date de signature, localisation → pays, montant du financement (€), détail par instrument → Proparco `lender` (senior, subordonné…) / `guarantor` / `investor` avec engagement et devise, client `borrower` / `issuer`, nature du client → secteur, n° de projet | subventions et assistance technique (aucun rôle de financement), taux, maturité |

Drapeaux de validation :
- `dfi_own_commitment_only` ;
- `pre_approval_disclosure` (IFC sans approbation publiée) ;
- `program_level_amount` (IFC GTFP / GTLP / RSF… : l'enveloppe du programme n'est **pas** le montant de
  la banque nommée, et le montant reste vide) ;
- `listing_notice_only` (BRVM).

### 11.4 Déclenchement

| Mode | Commande |
|---|---|
| Planifié (8 h / 20 h, avec la collecte bancaire) | phase « deals » de chaque run (`DEAL_COLLECTION_ENABLED`, `DEAL_COLLECTION_SOURCES`, fenêtre `DEAL_COLLECTION_LOOKBACK_DAYS` = 120 j) |
| API | `POST /api/v1/ingestion/trigger?source=boad&scope=deals&since=2025-01-01` |
| Interface | Paramètres → « Lancer une collecte » (source, portée, date « depuis ») |
| CLI (run complet) | `python -m app.ingestion.run --source ifc --scope deals --since 2025-01-01` |
| CLI (contrôlée) | `python -m app.deals.collect_run --source ifc,proparco --since 2024-01-01 --expect-db <base> [--report-file r.json]` |

Le paramètre `scope` vaut :
- `financial` : états financiers bancaires (BCEAO, CB-UMOA, BRVM, UMOA-Titres) ;
- `deals` : UMOA-Titres, BRVM, AMF-UMOA, IFC, BOAD, Proparco ;
- `all` : les deux.

BRVM et UMOA-Titres alimentent les deux phases. Une source deal seule (IFC, etc.) n'entre jamais dans
la chaîne d'extraction des bilans.

Verrous : chaque source prend son propre verrou consultatif PostgreSQL. UMOA-Titres partage celui de
`umoa_titres_run`, donc les deux ne tournent jamais ensemble.

Rythme :
- `DEAL_COLLECTION_DELAY_SECONDS` (2 s) est un minimum par hôte, relevé par un `Crawl-delay`
  (BRVM : 10 s) ;
- `DEAL_COLLECTION_MAX_PAGES` (200) borne les pages lues par source et par passage ; le reste est lu
  aux passages suivants.

Le résumé par source (issues, deals créés, déjà importés, doublons potentiels, contrôle de cohérence
« chaque deal créé est attesté par un document de cette source ») est enregistré dans
`ingestion_runs.deal_summary`. Il est exposé par `GET /api/v1/ingestion/runs/{id}`.

### 11.5 Tests (sans réseau)

- `backend/tests/test_deal_collection_unit.py` :
  - parseurs sur **pages réelles** capturées le 21/10/2026 et allégées
    (`backend/tests/fixtures/deals/README.md`) ;
  - montants, dates, pays ;
  - robots.txt et crawl-delay ;
  - schéma et critères de doublon.
- `backend/tests/test_deal_collection_postgres.py` :
  - migration 0020 aller-retour et refus de downgrade ;
  - collecte de bout en bout des cinq sources ;
  - idempotence et points de contrôle ;
  - page 403 signalée et non contournée ;
  - doublon AMF ↔ BRVM signalé sans fusion ;
  - vérification uniquement par le workflow ;
  - phase « deals » du run et API de déclenchement.

### 11.6 Limites

- **AMF-UMOA** : les notes d'information ne sont pas servies (fichiers de 0 octet, constaté à nouveau
  le 21/10/2026), et les décisions de visa sont des scans (OCR hors périmètre, décision D5). Les
  transactions AMF restent donc des entrées d'index, non vérifiables sans source primaire.
- **BRVM** : les avis de cotation complets ne sont pas publiés de façon systématique. La ligne du BOC ne
  donne ni montant, ni ISIN, ni arrangeur. La date d'annonce est celle du premier BOC lu dans la fenêtre.
- **IFC** : l'API de recherche exige une clé d'abonnement ; elle n'est pas utilisée. Le premier passage
  parcourt le sitemap (≈ 13 500 URL, dont environ la moitié en SII), borné par
  `DEAL_COLLECTION_MAX_PAGES`, de sorte que la couverture complète se construit sur plusieurs passages.
  Les montants du texte libre ne sont jamais lus.
- **BOAD** : les données du CMS contiennent des valeurs de test (constaté le 21/10/2026). Seuls
  l'en-tête affiché et les objectifs sont lus. Sans mot d'instrument dans l'intitulé, BOAD n'a pas de
  rôle (`boad_instrument_not_published`).
- **Dette / fonds propres** : supportés de bout en bout (schéma, API, interface), mais aucune source
  actuelle ne publie la structure de financement d'un projet de façon exploitable.
- **Structure des pages** : elle peut changer. Une page non reconnue donne `not_a_deal`, `refused` ou
  une erreur de découverte dans `ingestion_runs.errors`, jamais une valeur devinée.

## 12. Presse financière (Sika Finance, Agence Ecofin, Financial Afrik) — décision D4

Collecteur `press` (`backend/scraping/deals/collect/press.py`), source « Presse financière »
(migration `0021_press_source`). Il est **disponible à la demande** et n'entre dans le run planifié que
si `press` est ajouté à `DEAL_COLLECTION_SOURCES`. Ce choix revient au propriétaire : il dépend de
l'accord des éditeurs, puisqu'aucun n'affiche de conditions d'utilisation (audit
`audits/ape_amf/04b_press_feasibility_sourced.md`).

- **Découverte :** flux RSS publics uniquement (`/rss/actualites_bourse_brvm`, `component/obrss/…`,
  `/feed/`). Un préfiltre sur le titre et le résumé garde les nouvelles de deals UMOA. Il exclut :
  - les pays hors UMOA nommés dans le titre (Congo, Guinée, Kenya…) ;
  - les comptes rendus d'adjudication du Trésor, dont UMOA-Titres est la source primaire.
- **Rythme :** une requête toutes les 5 s au plus par site, plus robots.txt. Un site qui refuse l'agent
  (403) est signalé `restricted`.
- **Article payant** (« réservé aux abonnés », « Sika Premium »… dans le **corps** de l'article ; les
  liens de menu ne comptent pas) : rien n'est créé (`restricted`). Titre, date et lien ne suffisent pas
  à attester un champ.
- **Stockage :** **le corps de l'article n'est jamais stocké.** Le document enregistré est une fiche de
  preuve JSON : URL, titre, éditeur, date et citations courtes (300 caractères au plus).
- **Champs lus, seulement s'ils sont explicites :**
  - titre de l'article et pays (un seul pays UMOA dans le titre, sinon dans l'article) ;
  - montant, s'il apparaît **une seule fois** dans le titre, sinon un champ « Montant : … » de la fiche
    de l'opération (FCFA = XOF parce que la transaction est UMOA) ;
  - taux et maturité, seulement s'il n'y a qu'une valeur et **aucune tranche** (un emprunt en deux
    tranches ne donne ni taux ni durée) ;
  - utilisation des fonds (phrase « serviront à financer… ») ;
  - type : `sukuk`, ou APE / placement privé quand l'article le dit.
- **Rôles nommés uniquement :**
  - « Chef de file et Arrangeur : X » → `arranger` + `lead_manager` ;
  - « Arrangée par X qui en est le chef de file » → idem ;
  - « Co-arrangeur : X » → `co_arranger` ;
  - « Investisseur d'ancrage / de référence : X » ou « X, investisseur de référence » →
    `anchor_investor` ;
  - « Garant : X » → `guarantor` ;
  - « X et Y » donne deux participants ;
  - « avec l'appui de » et « en partenariat avec » ne donnent aucun rôle.
- **Classe et statut :** `press_reported`, avec `publisher`, `url` et `published_at` renseignés.
  Toujours `needs_review`, et **jamais vérifiable** sans source primaire (409 `secondary_source_only`).
  Les critères de doublon du §4 rattachent l'article au deal AMF, BRVM, UMOA-Titres ou IFD
  correspondant, pour revue humaine.
- **Tests :** `backend/tests/test_deal_collection_press_unit.py` (articles réels de l'audit,
  Sika / Ecofin, et flux réels du 21/10/2026) et `test_deal_collection_postgres.py::test_7`.
- **Limites :**
  - seuls les ≈ 30 derniers articles de chaque flux sont vus : pas de reprise d'archives ;
  - lecture par motifs : un rôle formulé autrement (« la SGI X a piloté l'opération ») n'est pas lu, et
    reste à saisir en revue ;
  - un changement de gabarit d'un site donne `not_a_deal`, jamais une valeur devinée.
