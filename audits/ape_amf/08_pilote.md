# 08 — Plan de pilote : 28 deals réels avant toute ingestion massive

Objectif : tester la taxonomie (`07_proposition.md`) et la vue « deals par banque » sur des cas réels et variés, **en saisie contrôlée** (pas d'ingestion automatique), puis décider de l'ingestion à grande échelle.
Exécution : par la session chargée de l'implémentation, **après la fin du Lot 0** et la migration validée. Cet audit ne code rien et ne migre rien.

## 1. Protocole

1. **Base** : une base de pilote dédiée (jamais `umoa_banking` ; ni `umoa_discovery_e2e` pendant un run).
2. Pour chaque deal ci-dessous : créer le deal, ses sources (URL et fichier local `audits/ape_amf/notes/…` quand il existe), puis ses participations et champs **à la main ou par extraction assistée**, chacun avec page et citation, statut `needs_review`.
3. **Valeurs de référence** : pour les deals marqués ✔ dans la colonne « Réf. », les valeurs attendues sont dans `03_notes_roles.md` ou `04b_press_feasibility_sourced.md`. L'écart entre saisie et référence mesure la fiabilité de l'extraction. Pour les deals marqués ○, la référence est à établir pendant le pilote.
4. **Recoupement** : pour les paires presse ↔ note (P1 à P4), créer **un seul** deal à deux sources et vérifier que la règle « primaire prévaut » et l'affichage des conflits fonctionnent.
5. **Liens SGI → banque** : charger uniquement les 7 liens de `05_sgi_links.md` (2 `documented_bank`, 5 `documented_group_only`).
6. Revue humaine de chaque participation, puis passage à `verified` ou `rejected`. Mesurer le temps passé par deal.

## 2. Liste des deals et sources exactes

Légende des colonnes : **Réf.** ✔ = valeurs de référence déjà établies dans l'audit, ○ = à établir pendant le pilote ; **Méthode** `text` ou `visual` (lecture d'image) ; les URL de notes ont été vérifiées le 05/10/2026 (PDF téléchargé, page 1 contrôlée).

### A. Souverains par appel public — `sovereign_bond_ape` (12)

| # | Deal | Source primaire (note) | Source complémentaire | Réf. | Ce que le cas teste |
|---|---|---|---|---|---|
| 1 | TPCI 5,80 % 2021-2028 & 5,90 % 2021-2031 (EE/21-07, 08) | https://tresor.gouv.ci/tres/wp-content/uploads/2021/06/NOTE-DINFO-TRESOR-16-06.pdf | — | ✔ N01 | chef de file seul (aucun arrangeur), 4 co-chefs, garantie souveraine ; nom « EDC » ≠ `acteurLib` « Ecobank IC » |
| 2 | TPCI avril 2021 (EE/21-05, 06) | https://tresor.gouv.ci/tres/wp-content/uploads/2021/05/VF-NOTE-DINFO-TPCI-AVRIL-2021.cleaned_ok1.pdf | — | ○ | même émetteur, autre syndicat de tête |
| 3 | TPCI février 2021 (EE/21-01, 02) | https://tresor.gouv.ci/tres/wp-content/uploads/2021/02/NOTE-DINFORMATION-TPCI-FEV2021-small.pdf | — | ○ | deux tranches dans une seule note |
| 4 | TPCI 2020, emprunt n°03 (EE/20-07, 08) | https://tresor.gouv.ci/tres/wp-content/uploads/2020/08/note_information_EMPRUNT_TPCI_n%C2%B003_2020.pdf | — | ○ | — |
| 5 | TPCI octobre 2024 (EE/24-21, 22) | https://invictuscapfin.com/wp-content/uploads/2024/11/NOTE-DINFO-TPCI-OCT-2024_Version-10.pdf | — | ○ | note hébergée par une SGI |
| 6 | État du Sénégal, juin 2025, 4 tranches (EE/25-13 à 16) | https://www.fgi-bourse.com/wp-content/uploads/2025/06/Note-dinformation_Ape-Tresor-Public-SN.pdf | — | ✔ N02 | **banque co-arrangeur** (Société Générale Sénégal) ; rapprochement AMF « probable » (visa tronqué) |
| 7 | TPTG 6,45 % 2025-2030 & 6,60 % 2025-2032 (EE/25-05, 06) | https://www.africabourse.com/uploads/opportunite/34e14a00c02791123e74ed452c80a9f9.pdf | dépliant https://www.africabourse.com/uploads/opportunite/8e7e707f9b20c5747b506b44bbbdb66d.pdf | ✔ N03 | `visual_logo` (co-chefs), police non décodable |
| 8 | TPBF 6,50 % 2021-2031 (EE/21-03) | https://sgibenin.com/opportunites/2021/BF/Note%20d'information%20TPBF%206.50%25%202021-2031.pdf | — | ○ | — |
| 9 | TPBF Diaspora Bonds 2026 (EE/26-09, 10) | https://www.diaspora-bond-burkina.com/docs/note-information.pdf | dépliant https://www.diaspora-bond-burkina.com/docs/depliant.pdf | ✔ N11 | **banque co-arrangeur** (Vista Bank, entité à valider), projet nommé, Crawl-delay 60 |
| 10 | TPNE 6,15 % 2022-2034 (EE/22-06) | https://sginiger.com/wp-content/uploads/2022/05/NOTE-DINFORMATION-TPNE-615-2022-2034.pdf | dépliant https://sginiger.com/wp-content/uploads/2022/05/Depliant-TPNE-615-2022-2034.pdf | ○ | visa lu sur le dépliant seulement |
| 11 | TPNE 6,60 % 2025-2030 & 6,90 % 2025-2032 | https://sginiger.com/wp-content/uploads/2025/02/Note-dinformation-2025-ok.pdf | **P1** Sika 13/12/2024 https://www.sikafinance.com/marches/le-niger-signe-son-retour-sur-le-marche-financier-avec-une-emission-obligataire-de-200-milliards-fcfa_49800 | ○ (presse ✔) | recoupement presse ↔ note |
| 12 | État du Mali 6,50 % 2020 (EE/20-21) | https://africabourse.com/uploads/opportunite/07941e7d3ac71e316cffc2945adafcc8.pdf | — | ○ | — |

### B. Entreprises, banques et organismes régionaux avec note (6)

| # | Deal | Type attendu | Source primaire | Complément | Réf. | Ce que le cas teste |
|---|---|---|---|---|---|---|
| 13 | PAD 6,60 % 2020-2027 (EOP/20-02) | `corporate_bond_ape` | https://sgibenin.com/opportunites/2020/sn/APE_PAD2020/Note_Information__APE_PAD_6.60_2020_2027.pdf | **P2** FA 01/10/2020 https://www.financialafrik.com/2020/10/01/le-port-autonome-de-dakar-lance-une-emission-de-60-milliards-de-fcfa-pour-decongestionner-son-trafic/ | ✔ N06 | concordance presse ↔ note ; projet nommé |
| 14 | Petro Ivoire 6,80 % 2022-2029 (EP/22-03) | `corporate_bond_ape` | https://www.fgi-bourse.com/wp-content/uploads/2024/08/Emprunt-Obligataire-PETRO-IVOIRE-680-2022-2029.pdf | — | ✔ N07 | 2 catégories de but ; visa API erroné |
| 15 | Fidelis Finance CAP25 7 % 2023-2028 (EOP/23-25) | `corporate_bond_ape` | https://africabourse.com/images/Opportunite/OppPdf/ni_fidelis_ape.pdf | — | ○ | établissement financier non bancaire |
| 16 | Augmentation de capital Alios Finance CI / SAFCA (OA/26-02) | `capital_increase` | https://www.brvm.org/sites/default/files/20260413_-_note_dinformation_-_augmentation_de_capital_-_safca_ci.pdf | — | ✔ N08 | catégorie `capital_adequacy` ; Crawl-delay 10 |
| 17 | OPV BIIC, cession par l'État du Bénin (OA/24-02) | `share_sale_public` | https://www.africabourse.com/uploads/opportunite/8330f0533e80a60db70e6d274099be60.pdf | **P3** FA 13/01/2025 https://www.financialafrik.com/2025/01/13/offre-publique-de-vente-letat-du-benin-cede-ses-17-558-979-actions-detenues-dans-le-capital-de-la-banque-biic/ | ✔ N04 (presse ○) | `selling_shareholder` ; **banque objet** (BIIC dans la liste) ; absente de l'API AMF |
| 18 | CRRH-UEMOA 6,10 % 2022-2037 (EOP/22-02) | `corporate_bond_ape` (émetteur régional) | https://afinhab.org/sites/default/files/documents/note%20d'info%209e%20emprunt-avec%20compression.pdf | — | ✔ N09 | bénéficiaires non nommés : **aucune** participation ne doit être créée pour « 10 banques » |

### C. Presse seule, sans note publique (6)

| # | Deal | Type attendu | Source(s) | Réf. | Ce que le cas teste |
|---|---|---|---|---|---|
| 19 | Oragroup SA 7,15 % 2021-2028 (EOP/21-02) | `corporate_bond_ape` | FA 22/09/2021 https://www.financialafrik.com/2021/09/22/emprunt-obligataire-oragroup-s-a-recherche-50-milliards-fcfa-sur-le-marche-financier-de-lumoa/ ; FA 13/01/2022 https://www.financialafrik.com/2022/01/13/hudson-cie-annonce-la-cotation-de-lemprunt-obligataire-doragroup-sa/ ; dépliant https://www.orabank.net/sites/default/files/2021-10/EXE-DEPLIANT%20EMPRUNT%20OBLIGATAIRE%20ORABANK%202021%20(VERSION%20MAIL).pdf | ○ (but ✔) | **émetteur = groupe bancaire** ; rôle seulement dans le 2e article |
| 20 | Baobab CI Sustainability-Linked Bond 2026 (EOP/26-06) | `corporate_bond_ape` | Ecofin https://www.agenceecofin.com/actualites-finance/1409-141527-baobab-cote-d-ivoire-lance-le-premier-sustainability-linked-bond-d-une-imf-dans-l-umoa | ✔ | IFC exclu → mention conservée sans entité ; absent de l'API AMF |
| 21 | Social Bond AFINHAB 6 % 2026-2041 (EOP/26-01) | `corporate_bond_ape` | Ecofin https://www.agenceecofin.com/actualites-finance/2807-140577-afinhab-cloture-son-emission-de-social-bond-de-40-milliards-fcfa-et-franchit-le-cap-des-100-milliards-fcfa-d-obligations-sociales | ✔ | **banque `anchor_investor`** (SG CI) ; deux arrangeurs |
| 22 | Gender Bond Ecobank CI 6,50 % 2024-2029 (EOP/24-28) | `corporate_bond_ape` | Ecofin https://www.agenceecofin.com/actualites-finance/2802-126261-cote-d-ivoire-le-premier-gender-bond-d-ecobank-attendu-pour-le-3-mars-2025 ; communiqué https://ecobank.africa-newsroom.com/press/ecobank-cote-divoire-launches-west-africas-first-gender-bond-to-accelerate-financial-inclusion-for-women-entrepreneurs?lang=en | ○ (but ✔) | **banque émettrice** (ECOBANK - COTE D'IVOIRE) ; classe `issuer_official` contre `press_reported` |
| 23 | Emergence Plaza 7,5 % 2021 (EP/21-01) | `corporate_bond_private` | Sika 06/07/2021 https://www.sikafinance.com/marches/cote-divoire-emergence-plaza-prepare-un-green-bond-de-10-milliards-fcfa_29107 | ✔ | **banque `refinanced_lender`** (NSIA Banque CI) ; placement privé |
| 24 | Bénin Petro 7,50 % 2020-2027 (EP/20-01) | `corporate_bond_private` | FA 27/08/2020 https://www.financialafrik.com/2020/08/27/africabourse-mobilise-avec-succes-2-milliards-de-fcfa-pour-benin-petro-s-a/ | ○ | arrangeur SGI cité en presse (« SGI AFRICABOURSE, as arranger » d'après le résumé moteur, à relire) |

### D. Gestion de la dette, contexte sans banque (4)

| # | Deal | Type attendu | Source(s) | Réf. | Ce que le cas teste |
|---|---|---|---|---|---|
| 25 | Rachat CI du 09/01/2025 (8 lignes RA-) | `debt_buyback` | https://www.umoatitres.org/wp-content/uploads/2025/01/Compte-rendu-CI-EC-09.01.2025-1.pdf (p.2) | ✔ (06) | lien avec le volet émission déjà en base ; **zéro participation** |
| 26 | Rachat SN du 10/02/2025 | `debt_buyback` | https://www.umoatitres.org/wp-content/uploads/2025/02/Compte-Rendu-SN-EC-10.02.2025.pdf | **P4** Sika 12/02/2025 https://www.sikafinance.com/marches/umoa-titres-entre-rachat-et-emission-le-senegal-reussit-une-double-operation-financiere_50902 | ○ | recoupement des montants presse ↔ UMOA-Titres (rapprochement de date à confirmer) |
| 27 | Rachat ML du 19/02/2025 | `debt_buyback` | https://www.umoatitres.org/wp-content/uploads/2025/02/Compte-Rendu-ML-EC-19.02.2025.pdf | ○ | autre émetteur |
| 28 | Échange ou reprofilage Trésor CI, mars 2025 (> 450 Md annoncés) | `debt_exchange` ou `debt_reprofiling` | **source primaire à trouver** (tresor.gouv.ci / portaildettepublique.gouv.ci) ; presse non vérifiée | ○ | règle « pas de deal sans source » : si rien de primaire, `press_reported` seulement, ou abandon |

Optionnels, pour tester les contradictions internes (antérieurs à 2020) : OPV BOA-Mali (https://africabourse.com/images/Opportunite/note-d-information-opv-boa-mali.pdf, réf. N05) et CRRH 6 % 2013-2023 (https://www.impaxis-securities.com/sites/default/files/note_dinformation_crrh_6_2013_-_2023.pdf, réf. N10).

Couverture : 28 deals (12 souverains, 6 non souverains avec note, 6 presse seule, 4 gestion de la dette), dont 4 paires presse ↔ primaire. **Banques de la liste attendues dans la vue « par banque »** : Société Générale Sénégal (n°6), Vista Bank Burkina, à valider (n°9), BIIC (n°17), Ecobank Côte d'Ivoire (n°22), SG Côte d'Ivoire (n°21), NSIA Banque CI (n°23), BNI et BICICI via leur SGI (là où BNI Finances / BICI Bourse ont un rôle : n°1 co-chef BNI Finances ; les autres sont à constater).

## 3. Critères de réussite (go / no-go pour l'ingestion massive)

1. **Couverture de la taxonomie** : chaque rôle et chaque type rencontré entre dans la liste fermée ; sinon, le consigner et le soumettre avant d'étendre la liste.
2. **Exactitude contre la référence** (deals ✔) : 100 % des rôles saisis présents dans la source avec page et citation ; zéro rôle déduit ; zéro participation « syndicat » créée pour « toutes les SGI ».
3. **Garde-fous** : aucun deal attribué à une banque via un lien `documented_group_only` ; aucun rôle tiré d'`acteurLib` ; BOAD, IFC et BAD sans entité.
4. **Vue « deals par banque »** : affiche les niveaux direct, via SGI et groupe séparément, avec statut et classe de source sur chaque ligne.
5. **Coût** : temps moyen de revue par deal (texte contre `visual`) pour dimensionner l'ingestion.
6. **Presse** : aucun corps d'article stocké ; payant = métadonnées seules ; conflits affichés.

## 4. Livrable du pilote

Un rapport court avec les écarts par critère, la liste des valeurs hors taxonomie, le temps de revue, et la décision proposée sur l'ingestion massive (périmètre, sources prioritaires, besoin éventuel d'OCR, qui reste reporté).
