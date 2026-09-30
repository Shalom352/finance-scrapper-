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
| `participants` | au moins un participant commun (hors emprunteur) |

Un **doublon potentiel** est créé si un ancrage (emprunteur ou projet) concorde **et** au moins
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

Année d'une transaction : date de signature, sinon date d'annonce (règle documentée, identique
côté API et interface).

## 6. Interface

- `/[locale]/deals` : explorateur (filtres dans l'URL, pagination) + vue descriptive.
- `/[locale]/deals/[dealId]` : résumé, conditions financières, participants, chronologie,
  projet / emprunteur, garanties, sources / provenance (par champ), doublons, historique.
- `/[locale]/data-quality?tab=deals` et `/[locale]/data-quality/deals/[dealId]` : revue.
- Liens : établissement → « Transactions impliquant cet établissement » (`/deals?bank=<id>`) ;
  participant → fiche établissement.

## 7. Limites

- Pas d'extracteur automatique : l'alimentation dépend d'imports structurés.
- Détection de doublons en Python sur les transactions portant un ancrage (volume V1).
