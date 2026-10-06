# Ciblage des financeurs, annuaire et mandats internes (Phase 20)

Objectif TOMASTEED : **pour une transaction donnée, savoir vers quelles banques et institutions se tourner**,
avec des critères vérifiables plutôt qu'un avis.

## 1. Annuaire

- **Banques** : la liste officielle BCEAO / CB-UMOA (moteur de découverte, Phase 15). Rien n'est ajouté à la main.
- **Institutions de financement** (BOAD, BIDC, BAD, Afreximbank, AFC, Africa50, IFC, BEI, BID, SID, AFD,
  Proparco, FMO, DEG, BII) et **fonds de garantie** (GARI, AGF) : `backend/reference/financing_institutions.json`,
  chaque entrée enregistrée depuis **son propre site officiel**, rien d'autre n'est déduit.

```bash
cd backend
python -m app.directory.seed --file reference/financing_institutions.json --expect-db <base> --dry-run
```

Une entité qui existe déjà (même nom canonique ou abrégé) n'est jamais modifiée.

## 2. Mandats internes (données TOMASTEED, jamais publiées)

Modèles : `backend/reference/templates/mandates.csv` et `mandate_contacts.csv`.

```bash
python -m app.mandates.importer --mandates mandates.csv --counterparties contacts.csv \
       --actor <identifiant> --expect-db <base> --dry-run
```

- Un mandat est identifié par son `code` (mis à jour s'il existe).
- Chaque ligne de contact est un **événement** (historique conservé) : `approached`, `interested`, `declined`,
  `term_sheet`, `committed`, `disbursed`, `withdrawn`. Une ligne identique déjà enregistrée est ignorée.
- `institution_name` / `entity_name` doivent correspondre **exactement** à l'annuaire, sinon le fichier est refusé.
- Montants jamais convertis ; cellule vide = non renseigné.

## 3. Ciblage — `GET /api/v1/targeting`, page `/[locale]/targeting`

Paramètres : `country`, `sector`, `deal_type`, `amount` (en unités), `currency`, `kind` (`all` | `banks` | `institutions`),
`capacity_ratio` (0,25 par défaut).

Chaque établissement reçoit des **critères explicites**, chacun `met` / `not_met` / `unknown`, avec sa preuve :

| Critère | Règle |
|---|---|
| Présence | banque agréée dans le pays ; institution : transaction enregistrée dans le pays |
| Expérience | rôles de financement **nommés** (`lender`, `arranger`, `lead_manager`, `guarantor`, `anchor_investor`…) dans des transactions comparables (même secteur, type ou pays) ; transactions rejetées ou rattachées exclues ; `needs_review` signalé « à confirmer » |
| Capacité indicative | banques : `capacity_ratio` × derniers **capitaux propres publiés** (individuel, annuel, même devise). La norme UMOA de division des risques porte sur les fonds propres effectifs, non publiés : **indication seulement**. Devise différente → `unknown`, jamais de conversion |
| Relation TOMASTEED | dernier stade par mandat dans l'historique des contacts |
| Via sa SGI | transactions où la SGI filiale (lien `documented_bank` uniquement) a un rôle de financement |

Absence d'information = `unknown`, jamais un refus. **Aucun score** : l'ordre d'affichage est le nombre de critères
satisfaits, puis le nombre de transactions comparables, puis le nom. Le vocabulaire interdit (meilleur, top,
recommandation…) reste interdit dans l'interface (`contract.test.ts`).

## 4. Limites

- La qualité du ciblage dépend des transactions enregistrées : tant que le pilote et les mandats internes ne sont
  pas chargés, la plupart des critères « Expérience » et « Relation » restent `unknown`.
- L'ingestion automatique des bases de projets des bailleurs (IFC, BAD, BEI, Proparco…) n'est pas implémentée :
  ces sites n'étaient pas accessibles depuis l'environnement de développement. Les transactions de bailleurs
  entrent par l'import structuré (Phase 13) ou le chargeur du pilote.
- Pas d'authentification : les mandats internes sont visibles de toute personne ayant accès à la plateforme
  (déploiement derrière un accès restreint obligatoire, voir `deployment.md`).
