# 01 — Profil des 551 opérations de l'API AMF-UMOA

Source : `https://www.amf-umoa.org/service/api/elastic/operation` (sauvegarde `raw_operations.json`, collectée le 05/10/2026 par la session précédente), émetteurs `raw_emetteurs.json`. Script : `profile_ops.py` → `ops_profile.csv`, `profile_summary.txt`, `mismatch_emetteur.csv`.
Pas de robots.txt sur amf-umoa.org (l'URL renvoie le HTML de l'application Angular). Routes API relevées dans le bundle `main.acf865e5e2be8d64.js` (classe `JupiterPortailService`).

## Répartition

| Nature (`natureCode`) | n | dont ≥2020 |
|---|---|---|
| APE — Emprunt obligataire par appel public à l'épargne | 317 | 168 |
| EOP — Emprunt obligataire privé (placement privé) | 104 | 29 |
| OPV — Offre publique de vente | 71 | 7 |
| PE — Placement étranger (actions de groupes étrangers auprès des salariés) | 41 | 8 |
| PPA — Placement privé d'actions | 7 | 2 |
| OPA | 5 | 1 |
| OPR | 3 | 0 |
| OPE — Offre publique d'échange | 2 | 0 |
| SO — Stock option | 1 | 0 |

Années (`dateVisa`) : 1997 → 2026 ; 215 opérations depuis 2020 (2020 : 37, 2021 : 23, 2022 : 20, 2023 : 29, 2024 : 27, 2025 : 51, 2026 : 28 au 26/06/2026 — dernière opération de l'API ; l'opération Baobab CI visée EOP/26-06 le 17/08/2026, citée par Agence Ecofin, n'y est pas encore).
Pays de l'émetteur (via `raw_emetteurs.json`) : Côte d'Ivoire 261, Togo 66, Sénégal 59, Burkina 48, France 42 (PE), Mali 29, Bénin 25, Niger 17, États-Unis 2. **Champ peu fiable** (voir plus bas).
Catégorie d'émetteur (heuristique de libellé, utilisée seulement pour stratifier) : souverain 216, entreprise/autre 222, banque 71, organisme régional 29, BOAD/IFC/BAD 13.
Montant demandé (`mtDemande`, 550 renseignés) : <1 Md 65 · 1-10 Md 152 · 10-50 Md 153 · 50-100 Md 94 · ≥100 Md 86.

## Champs et taux de remplissage

`emetteurDesignation` 549 · `acteurLib` 534 · `visa` 538 · `nomination` 551 · `taux` 250 · `duree` 250 · `mtDemande` 550 · `mtSouscrit` 444 · `decision` (fichier de décision de visa) 284 · `noteInfo` (fichier de note) 139.
**Champs de rôle : un seul, `acteurLib`/`acteurId`** — 40 valeurs distinctes : SGI (BICI Bourse 63, BOA Capital Securities 53, SG-CSWA 45, SGI Togo 36, EIC 31…), mais aussi « ETAT » (51), BOAD, Bridge Bank Group CI, sociétés de gestion d'actifs (Kaydan, Baobab AM, CGF Gestion) ; 17 vides. Signification : voir `03_notes_roles.md` (ne correspond pas toujours à l'arrangeur).

## Téléchargements

- `/download/files/<noteInfo>` → **200, 0 octet** (testé NIF_2025-019.pdf) ; `/download/operation/<id>/noteInfo/` → 400. Les notes ne sont pas servies par l'AMF.
- `/download/files/<decision>` → **200, PDF** (VISA_2025-199.pdf, 181 Ko, scan sans couche texte, 3 p.). La décision nomme la SGI qui a saisi l'AMF « pour le compte de l'émetteur ». Source exploitable (OCR/lecture visuelle nécessaire).
- Rapports annuels : `/actualite?categorie=Rapport` + `/download/files/<documentUrl>` → PDF OK.
- Liste des SGI agréées : `/acteur?page=N&size=8&typeId=3` (des pages plus grandes renvoient 500 « buffer limit ») → 41 SGI (`raw_sgi_amf.json`) : nom, pays, site web, n° d'agrément. Pas d'actionnariat.

## Qualité des données de l'API (à ne jamais prendre pour vérité)

1. **Émetteur générique erroné** : 131 opérations ont pour émetteur « Trésor Public de Côte d'Ivoire » alors que le libellé est non souverain ou d'un autre pays (ex. 1000003006 « BRIDGE BANK GROUPE CÔTE D'IVOIRE 7,75 % 2023-2030 », 1000003701 « GREEN BOND PORO POWER »). 31 opérations souveraines ont un pays d'émetteur ≠ pays du libellé (ex. 1000003008 « ETAT DU SENEGAL 6,25 % 2024-2029 » → émetteur Trésor CI). Liste : `mismatch_emetteur.csv`.
2. **Visas incohérents** : 1000003056 Petro Ivoire porte EOP/23-25 (= visa de la note Fidelis CAP25) au lieu de EP/22-03 ; 1000003691/94 TPTG 2026 portent EE/26-09/10 = visas des Diaspora Bonds BF (dépliant officiel) ; visas tronqués « EE/25- » (Sénégal 2025).
3. **Valeurs aberrantes** : 1000003008 `taux` 6,0 pour un libellé 6,25 % ; `fin` = 1970-01-01.
4. **Fichiers mal appariés** : `decision` = VISA_2025-199.pdf contient la décision n°025/AMF-UMOA/**2024**.
5. **Incomplétude** : la note CRRH-UEMOA 9e emprunt (EOP/22-02) et l'OPV BIIC (OA/24-02) n'ont pas d'opération correspondante.
6. Doublons fonctionnels : un même emprunt a souvent plusieurs entrées (décision initiale, complémentaire, par tranche) → 150 opérations de l'échantillon = 117 instruments distincts.

Conséquence : l'API est un **index de découverte** (nature, libellé, visa, montant, SGI déclarante), jamais une source de rôle ni de pays sans recoupement documentaire.
