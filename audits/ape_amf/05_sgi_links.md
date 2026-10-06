# 05 — SGI nommées dans les notes et rattachement à une banque de la liste CB-UMOA

Référence : 137 banques, univers courants `reference_universe_members` (umoa_discovery_e2e, SELECT du 05/10/2026, export `banks_137.txt`).
⚠ La liste officielle **n'a pas de champ « groupe »** : `parent_name_raw` n'est rempli que pour les succursales. Un lien n'est donc retenu que si une source publique nomme **une entité précise** de la liste. Une appartenance « au groupe X » est consignée à part (niveau groupe), sans lien vers une banque.
Aucun lien n'est déduit d'une ressemblance de nom (UCA/UBA, BOA Capital/BOA, SBIF/BIB…) ni du champ « site web » de l'API AMF (qui pointe pour certaines SGI vers le domaine d'une banque : ecobank.com, bni.ci, sgbci.ci, sib.ci, biao.ci, bank-of-africa.net — **indice seulement**).

## Statuts

- **A — documenté vers une banque de la liste** (source citée, entité nommée)
- **B — documenté au niveau groupe seulement** (la source ne nomme pas une banque de la liste)
- **C — non trouvé** (recherche limitée : 1-2 requêtes + page « à propos » de la SGI)

| SGI (nom AMF, agrément) | Rôles vus dans les notes | Statut | Preuve (citation, URL) | Banque(s) de la liste concernée(s) |
|---|---|---|---|---|
| BNI FINANCES SA (SG/19-2003) | co-chef N01 | **A** | « BNI FINANCES, filiale de la Banque Nationale d'Investissement de Côte d'Ivoire (BNI) » — https://www.bni.ci/groupe-bni/bni-finances | BANQUE NATIONALE D'INVESTISSEMENT (BNI) |
| BICI BOURSE (15/12/004/97) | consortium arrangeur/CdF N10 | **A** | « Son capital se reparti entre BICI de Côte d'Ivoire (70,0%), BICI Sénégal (20%), SUNU ASSURANCE-VIE (5%), AXA ASSURANCES COTE D'IVOIRE (5%) » ; « Sa filiation à la BICICI » — https://www.bicibourse.ci/nous-connaitre/bici-bourse/ (date de mise à jour inconnue) | BICICI. « BICI Sénégal » : pas d'entité de ce nom dans la liste → non lié |
| SOCIÉTÉ GÉNÉRALE CAPITAL SECURITIES WEST AFRICA (15/12/009/97) | arrangeur/CdF N07, N09 ; co-chef N02 | **B** | « Société Générale Capital Securities West Africa est la filiale du groupe Société Générale » — note Sénégal 06/2025, p.52 (source primaire datée) | aucune entité nommée (la liste contient SG Bénin, BF, CI, Sénégal ; actionnariat actuel des filiales à vérifier, cessions récentes du groupe possibles) |
| EDC INVESTMENT CORPORATION / ECOBANK INVESTMENT CORPORATION (EIC, 15/12/012/97) | CdF N01, arrangeur/CdF N04, co-chef N09 | **B** | « EDC Investment Corporation, la SGI du groupe Ecobank dans la zone UEMOA » — Financial Afrik, 17/11/2023 (presse). Équivalence EDC IC = Ecobank IC : **non documentée** (l'AMF ne liste que « Ecobank Investment Corporation ») | aucune entité nommée |
| CORIS BOURSE (SGI/2010-02) | co-chef N03 | **B** | « Filiale du groupe Coris, Coris Bourse… » — https://coris-bourse.com/en/coris-bourse/presentation | aucune entité nommée |
| ATLANTIQUE FINANCE (SGI-017/2001) | co-chef N09 | **B** | « filiale du Groupe Banque Centrale Populaire (BCP) du Maroc » — https://www.atlantiquefinance.net/presentation/ | aucune entité nommée |
| ORAGROUP SECURITIES (SGI/2022-01) | co-chef N03, co-arrangeur/co-chef N11 | **B** | Titre : « Le Groupe Orabank annonce l'obtention de l'agrément en qualité de SGI de sa filiale Oragroup Securities » — communiqué repris par Financial Afrik, 15/08/2022 (orabank.net : 403) | aucune entité nommée |
| BOA CAPITAL SECURITIES (15/12/010/97) | CdF N05 | **C** | Site : ex-ACTIBOURSE renommée en 2015, **aucun actionnaire indiqué** (https://boacapitalsecurities.com/en/about-us). Le résumé moteur « filiale de BOA Capital » n'est pas confirmé sur source | — |
| BIIC FINANCIAL SERVICES (BFS, 15/12/002/97) | co-chef N01, N03, N04 | **C** | Page d'accueil BFS : aucune mention de l'actionnariat ; affirmation « filiale de BIIC » vue seulement dans un résumé moteur | — (BIIC est dans la liste, lien non prouvé) |
| SBIF (15/12/003/97) | CdF + co-arrangeur N11 | **C** | Page « Qui sommes-nous » sans actionnariat. Un article leFaso.net (2010, résumé moteur) cite la « Banque internationale du Burkina (BIB) » comme actionnaire principal : ancien, non vérifié, BIB absente de la liste | — |
| SGI TOGO (15/12/008/97) | arrangeur/CdF N03 | **C** | Actionnaires décrits par catégories (« banques commerciales (40,48 %) ») sur un site non officiel ; aucune banque nommée | — |
| SGI BÉNIN SA, SGI NIGER | co-chefs N03/N04 | **C** | Pages « à propos » consultées : pas d'actionnariat | — |
| UNITED CAPITAL FOR AFRICA (SGI/2017-02) | co-chef N03, N04, N07 | **C** | Aucune source ; **ne pas** relier à United Bank for Africa sur la seule ressemblance de nom | — |
| CGF BOURSE, INVICTUS CAPITAL FINANCE, GEK CAPITAL, IMPAXIS SECURITIES, MAC AFRICAN SGI, AGI, FGI, SA2IF, AFRICABOURSE | divers rôles | **C** | Non recherché en profondeur (aucun indice de rattachement bancaire) | — |

Bilan : 23 SGI nommées dans un rôle → **2 en A** (BNI Finances → BNI ; BICI Bourse → BICICI), **5 en B** (groupe seulement), **16 en C**.

## Banques nommées directement dans un rôle (sans passer par une SGI)

| Banque (texte de la source) | Rôle nommé | Source | Entité de la liste |
|---|---|---|---|
| Société Générale Sénégal | co-arrangeur | note SN 06/2025 p.52 | SOCIETE GENERALE SENEGAL (correspondance exacte) |
| Vista Bank | co-arrangeur | note Diaspora Bonds p.14 | candidat : VISTA BANK BURKINA — **à valider** (la note dit « Vista Bank ») |
| Société Générale Côte d'Ivoire | « Investisseur de référence » | communiqué AFINHAB, Agence Ecofin 28/07/2026 | SOCIETE GENERALE COTE D'IVOIRE (presse → à recouper) |
| NSIA Banque Côte d'Ivoire | prêteur du « prêt senior » refinancé | Sika Finance 06/07/2021, citant la note Emergence Plaza | NSIA BANQUE COTE D'IVOIRE (presse → à recouper) |
| BIIC ; BOA-Mali | société dont les actions sont cédées/émises | notes N04, N05 | B.I.I.C ; BANK OF AFRICA - MALI |

Ces liens directs sont plus précieux pour l'objectif « quelle banque a fait quel deal » que le passage par les SGI.
