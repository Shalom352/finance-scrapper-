# Deal Intelligence (Phase 13)

Suivi des transactions de financement (prêts, prêts syndiqués, financements de projet,
obligations, garanties…) **lorsque l'information existe réellement dans les sources**.
Même plateforme, même provenance, même Review Center, même piste d'audit que les données
financières des banques.

## 1. Principes

- **Import structuré uniquement** (CLI, JSON / CSV, validation Pydantic). Aucun extracteur
  automatique ni pattern matching sur les documents dans cette version.
- **Provenance obligatoire** : chaque transaction cite au moins un document existant, sa source
  et une page ; chaque champ non nul et chaque participant est attribué à une de ces sources.
- **Statut initial `needs_review`**, toujours. Un statut fourni dans le fichier est refusé.
- **Champs non publiés = NULL** (« Non disponible »), jamais 0 : montant, taux, marge, maturité,
  différé, commissions, garanties, dates.
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

Un **doublon potentiel** est créé si un ancrage (emprunteur, projet ou instrument) concorde **et** au moins
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
| GET | `/api/v1/deals/{id}` | fiche : conditions, participants, chronologie, provenance, doublons, transactions rattachées |
| GET | `/api/v1/deals/{id}/history` | piste d'audit |
| GET | `/api/v1/deals/analytics?dimension=country\|year\|type\|sector\|institution` | comptages ; montants par devise **et** unité (transactions revues / vérifiées uniquement) |
| GET | `/api/v1/data-quality/deals` | file de revue |
| POST | `/api/v1/data-quality/deals/{id}/review\|verify\|reject` | décisions (actor, motif, 404 / 409 / 422) |
| GET | `/api/v1/data-quality/deal-duplicates` | doublons potentiels ouverts |
| POST | `/api/v1/data-quality/deal-duplicates/{id}/decide` | décision sur un doublon |

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

- Extraction automatique limitée aux résultats d'adjudication UMOA-Titres (OAT) ; les autres
  transactions dépendent d'imports structurés.
- Détection de doublons en Python sur les transactions portant un ancrage (volume V1).
