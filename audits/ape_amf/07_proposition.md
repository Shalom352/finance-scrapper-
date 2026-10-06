# 07 — Modèle cible : décisions validées et spécification pour l'implémentation

Statut : **décisions validées le 05/10/2026**. Rien n'est implémenté : la migration et le code seront faits plus tard par la session chargée de l'implémentation, **après la fin du Lot 0**. Le pilote préalable est décrit dans `08_pilote.md`.
Point de départ : l'existant (`backend/app/constants/deals.py` : `DEAL_TYPES`, `PARTICIPANT_ROLES`, `deal_participants`, `deal_sources`, `deal_field_sources`), étendu le moins possible. Les noms de champs et de tables restent indicatifs.

## 0. Décisions validées

| # | Décision | Conséquence |
|---|---|---|
| D1 | Séparation **arrangeur / chef de file** | « Arrangeur et chef de file : X » donne deux participations (`arranger`, `lead_manager`) qui partagent le même extrait |
| D2 | `acteurLib` (API AMF) reste un champ brut « SGI déclarante », **jamais un rôle** | champ `filing_agent_raw` sur le deal (ou la source AMF), sans ligne dans `deal_participants` |
| D3 | Lien SGI → banque à **deux niveaux** : banque si documenté, sinon groupe seulement ; **jamais** d'attribution à une banque précise par supposition | table `institution_links` (§4) ; un lien de niveau groupe ne propage aucun deal vers une banque |
| D4 | Presse **dans le périmètre** : on stocke titre, date, URL, source, faits extraits et citations courtes, **jamais l'article entier** ; classe `press_reported`, toujours `needs_review` sans recoupement avec une source primaire ; usage interne | §5 et §6 |
| D5 | **Pas d'OCR** des décisions de visa pour l'instant | ces décisions ne sont pas utilisées comme source de rôle ; la lecture visuelle manuelle reste possible pendant le pilote |

Principes inchangés : DATA MISSING > DATA WRONG ; rôles seulement s'ils sont nommés ; aucune participation déduite ; tout ce qui est extrait est `needs_review` ; BOAD, IFC et BAD exclus pour l'instant (leurs mentions sont conservées dans l'extrait brut, sans entité ni participation).

## 1. Taxonomie fermée des types de deal (`DEAL_TYPES`)

**Ajouts** (les valeurs existantes sont conservées pour ne rien casser) :

| Valeur | Définition | Source primaire attendue |
|---|---|---|
| `sovereign_bond_ape` | emprunt obligataire d'État par appel public à l'épargne (syndiqué, avec note) | AMF (nature APE) + note d'information |
| `debt_buyback` | rachat de titres publics (volet « RA- » des adjudications) | compte rendu UMOA-Titres |
| `debt_exchange` | échange de titres de dette (dont OPE sur obligations) | communiqué du Trésor / AMF |
| `debt_reprofiling` | reprofilage annoncé comme tel par l'émetteur | communiqué officiel |
| `corporate_bond_ape` | obligation non souveraine par appel public | AMF APE + note |
| `corporate_bond_private` | obligation par placement privé | AMF EOP ; souvent presse seulement |
| `securitisation` | titrisation (FCTC) | AMF, rapports annuels |
| `capital_increase` | augmentation de capital (actions nouvelles, avec ou sans DPS) | AMF OPV + note |
| `share_sale_public` | cession d'actions existantes par OPV (privatisation, par ex.) | AMF OPV + note |
| `takeover_offer` | OPA, OPR, OPE sur actions | AMF |

**Conservées et alimentées par communiqués ou presse** : `syndicated_loan`, `project_finance`, `term_loan`, `trade_finance`, `guarantee`, `m_and_a`, `sukuk`, `blended_finance`, `ipo`, `other`.
**Existant à clarifier** : `sovereign_bond` reste le type des OAT/BAT par adjudication UMOA-Titres (les 590 deals, contexte sans rôles, avec `instrument_type` OAT/BAT) ; `bond`, `corporate_bond` et `equity` sont gelés pour les nouvelles saisies au profit des valeurs plus précises ci-dessus.
**Règle** : le type se déduit de la **nature AMF** et du document, jamais du seul libellé. En cas de doute : `other` + `needs_review`.

## 2. Rôles fermés (`PARTICIPANT_ROLES`), uniquement s'ils sont nommés

| Rôle | Libellé source déclencheur (exemples réels) | Statut |
|---|---|---|
| `arranger` | « Arrangeur », « Arrangeur principal » | existant |
| `co_arranger` | « Co-arrangeur » (Société Générale Sénégal, Vista Bank) | existant |
| `lead_manager` | « Chef de file (du syndicat de placement) » | **nouveau** (D1) |
| `co_lead_manager` | « Co-chef(s) de file » | **nouveau** |
| `placement_syndicate_member` | seulement si la note **énumère** des membres ; « toutes les SGI agréées » ne crée aucune ligne | **nouveau** |
| `financial_advisor` | « Conseil financier » (BOA Capital) | **nouveau** (distinct d'`advisor`, qui reste générique) |
| `anchor_investor` | « Investisseur d'ancrage » / « Investisseur de référence » (SG Côte d'Ivoire pour AFINHAB 2026) | **nouveau** |
| `refinanced_lender` | prêteur dont le prêt est refinancé par l'opération, s'il est nommé (NSIA Banque CI pour Emergence Plaza) | **nouveau** |
| `selling_shareholder` | cédant dans une OPV (État du Bénin pour la BIIC) | **nouveau** |
| `paying_agent` | « Service financier / agent payeur » nommé | **nouveau** |
| `issuer`, `borrower`, `guarantor`, `lender`, `investor`, `underwriter`, `agent`, `facility_agent`, `security_agent`, `trustee`, `sponsor`, `advisor`, `insurer`, `reinsurer` | — | existants |

`guarantor` n'est utilisé que si un garant est nommé. « Garantie souveraine de l'État de X » donne `guarantor` = l'État, avec extrait et page.
Chaque participation porte : nom tel qu'imprimé, `deal_source_id`, page, extrait, `extraction_method` ∈ {`text`, `visual_logo`, `visual_scan`}. Les lectures `visual_*` sont toujours `needs_review`.
Les contradictions sont conservées sans arbitrage. Exemple : BOA Mali 2015, où la p.9 et la p.56 de la note diffèrent ; on garde deux participations, chacune avec sa page.

## 3. Utilisation des fonds

- `use_of_proceeds` : texte cité, avec page et extrait obligatoires (ajouté à `PROVENANCE_FIELDS`).
- `use_of_proceeds_category`, liste fermée : `budget_financing`, `infrastructure_project`, `refinancing`, `working_capital`, `capital_adequacy`, `housing_refinancing`, `sme_financing`, `green`, `social`, `privatisation`, `other`. Valeurs multiples permises (Petro Ivoire : `infrastructure_project` + `refinancing`).
- Projet nommé : `project_name`, champ existant (Port de Ndayane, centrale de Bagré-Aval).

## 4. Lien SGI → banque (D3)

Table `institution_links` :

| Champ | Contenu |
|---|---|
| `from_entity_id` | SGI (entité) |
| `link_level` | `documented_bank` / `documented_group_only` |
| `to_entity_id` | banque de la liste CB-UMOA, **seulement si** `documented_bank` |
| `group_label` | libellé du groupe tel qu'écrit dans la source, si `documented_group_only` |
| `relation`, `pct` | `subsidiary` / `shareholder`, pourcentage si la source le donne |
| `source_url`, `excerpt`, `observed_at`, `status` | obligatoires ; `status` = `needs_review` par défaut |

Aucune ligne sans source ; aucune ligne par ressemblance de nom ou par le champ « site web » de l'AMF. La validité est datée (`observed_at`), car les actionnariats changent.
État de l'audit : `documented_bank` = BNI Finances → BNI (`bni.ci`) et BICI Bourse → BICICI 70 % (`bicibourse.ci`) ; `documented_group_only` = SG-CSWA (groupe Société Générale), EIC/EDC (groupe Ecobank), Coris Bourse (groupe Coris), Atlantique Finance (groupe BCP), Oragroup Securities (groupe Orabank).

## 5. Classes de confiance des sources

| Classe | Exemples | Plafond automatique | Peut fonder un rôle ? |
|---|---|---|---|
| `primary_regulatory` | note d'information visée | `needs_review` (revue humaine pour `verified`) | oui |
| `primary_market` | comptes rendus UMOA-Titres, avis BRVM, fiches DC/BR | `needs_review` | rarement (pas de noms) |
| `issuer_official` | communiqué sur le domaine de l'émetteur ou de la banque | `needs_review` | oui |
| `regulator_index` | API AMF (métadonnées) | — | **non** (D2) ; pays et émetteur à recouper |
| `press_reported` | Financial Afrik, Agence Ecofin, Sika Finance | **toujours** `needs_review` sans recoupement primaire (D4) | oui, s'il est nommé, avec citation courte |

## 6. Stockage de la presse (D4)

- Champs : `title`, `published_at`, `url`, `publisher`, `retrieved_at`, `facts` (champs extraits), `excerpts` (citations courtes, une ou deux phrases par fait), `paywalled` (booléen). **Aucun corps d'article stocké** : pas de HTML archivé dans les tables, ni dans le stockage de documents.
- Pour un article payant : seulement titre, date et URL, sans extraction.
- En cas de conflit entre la presse et une source primaire, la source primaire prévaut ; le conflit est conservé et affiché.
- Pour le fichier `audits/ape_amf/press/` (copies HTML faites pendant l'audit) : à supprimer une fois le pilote terminé, ou à ne jamais réutiliser pour l'ingestion.
- Collecte : agent identifiable, robots.txt respectés, au plus une requête toutes les 5 s, aucun contournement de paywall ni de 403. Usage interne.

## 7. Vues « deals par banque » (ordre d'affichage)

1. **Banque → deals avec rôle direct** : rôle, but (`use_of_proceeds`), montant, taux, durée, source et page, statut, classe de source.
2. **Banque → deals via sa SGI** : uniquement `documented_bank`, affiché comme « via BICI Bourse (filiale, 70 %) — chef de file », avec la source du lien.
3. **Groupe → deals** : vue séparée pour `documented_group_only`, sans attribution à une banque de la liste.
4. Contexte : OAT/BAT, rachats et échanges par État (sans banque).
5. En dernier : classement financier (existant).

## 8. Hors périmètre pour l'instant

OCR des décisions de visa (D5) ; BOAD, IFC et BAD comme entités ; euro-obligations ; ingestion massive (après le pilote seulement).
