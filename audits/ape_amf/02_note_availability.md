# 02 — Disponibilité publique des notes d'information (opérations ≥2020)

Détail ligne à ligne : `02_note_availability.csv` (script `availability.py`). Candidats et vérification : `note_candidates.tsv`, `notes_verified.tsv`, `notes_index.json`, PDF dans `notes/`.

## Méthode

- Univers : 215 opérations ≥2020. **Échantillon stratifié de 150** (graine 20261005, `profile_ops.py`) : APE 117 (proportionnel par année × catégorie, ≥1 par strate), EOP 15, PE 8, OPV 7, PPA 2, OPA 1 → 117 instruments distincts.
- Recherche : une requête moteur par émetteur × année (ou par instrument pour le non-souverain), puis téléchargement et vérification de chaque PDF candidat (p.1-3 : libellé + visa).
- « note_publique_verifiee » = PDF de note téléchargé **et** visa API = visa du document avec libellé concordant, ou libellé exact quand le texte n'expose pas le visa (5 cas listés dans `availability.py`, motivés).
- Dépliants (2 p.) et comptes rendus d'émission (1 p.) ≠ note → « document_partiel_seulement ».

## Résultats

| Strate | n | Note publique vérifiée | Partiel | Indexée mais 404 | Non trouvée |
|---|---|---|---|---|---|
| APE | 117 | **22 (18,8 %)** | 2 | 2 | 91 |
| EOP (placement privé) | 15 | 0 | 1 (dépliant Oragroup) | 0 | 14 |
| OPV | 7 | 1 (SAFCA 2026) | 0 | 0 | 6 |
| OPA / PE / PPA | 11 | 0 | 0 | 0 | 11 |
| **Total** | **150** | **23 (15,3 %)** | 3 | 2 | 122 |

APE par année (vérifiées / échantillon) : 2020 8/18 · 2021 5/10 · 2022 1/10 · 2023 1/15 · 2024 1/14 · 2025 4/33 · 2026 2/17.
APE souverains 20/108 ; APE non souverains 2/9.

Lecture : le taux est une **borne basse** (1 requête moteur par groupe, sans parcours exhaustif des sites de SGI). Il chute nettement après 2021 : le Trésor CI publiait ses notes en 2020-2021 sur tresor.gouv.ci, plus ensuite (page « Notes d'informations » : seule une note de 2017). Les notes récentes ne subsistent que sur des sites de SGI/banques, avec **rotation de liens** (2 notes SG CI indexées par les moteurs renvoient 404 : NOTE_D_INFORMATION_-TPCI-FEV-2026.pdf, EOS_4_2025_-_NOTE_D_INFORMATION_-_VF.pdf).
Placements privés (EOP/PPA) et placements auprès de salariés (PE) : aucune diffusion publique attendue ni constatée.

## Où se trouvent les notes (dépôts constatés)

| Dépôt | Type | robots.txt | Exemples |
|---|---|---|---|
| tresor.gouv.ci (certificat valide pour `tresor.gouv.ci`, **pas** `www.`) | Trésor CI | absent (404) | notes TPCI 2020-2021 |
| sgibenin.com/opportunites/… | SGI | autorise (sauf /wp-admin/) | TPBF 2021, TPCI 07/2021, Mali 2020, PAD 2020 |
| africabourse.com/uploads/opportunite/… | SGI | autorise | TPCI 2020, Mali 2020, TPTG 2025, OPV BIIC, OPV BOA Mali |
| invictuscapfin.com | SGI | autorise | TPCI 10/2024 |
| sginiger.com | SGI | autorise | TPNE 2022, TPNE 2025 |
| fgi-bourse.com | SGI | autorise | Sénégal 06/2025, Petro Ivoire |
| diaspora-bond-burkina.com | site d'opération | Crawl-delay 60 | Diaspora Bonds 2026 |
| brvm.org | Bourse | Crawl-delay 10 | SAFCA 2026 |
| afinhab.org / crrhuemoa.org | émetteur | autorise | CRRH 9e emprunt |
| particuliers/institutionnel.societegenerale.ci | banque | Crawl-delay 10 | liens 404 au moment de l'audit |
| dcbruemoa.org/fiche-technique/… | dépositaire central | autorise | fiches techniques (ISIN, montant effectif) **sans rôles ni note** |
| richbourse.com | agrégateur | **robots.txt → 403** : exclu | — |
| scribd.com | — | compte requis : exclu | Sunu Bank Togo AK 2024 |

## Requêtes web

Total de l'audit : **239 requêtes** (`requests_log.csv`) = 148 requêtes HTTP directes (dont 42 robots.txt) + 68 requêtes moteur + 23 WebFetch.
Dont étape 2 (disponibilité) : 59 requêtes moteur + 58 téléchargements de vérification + ~19 robots.txt. Délais : 3-5 s entre requêtes, Crawl-delay respecté (10 s / 60 s).
