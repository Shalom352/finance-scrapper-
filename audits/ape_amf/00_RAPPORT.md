# Audit APE AMF-UMOA, SGI, gestion de la dette, presse — rapport de synthèse

Audit en lecture seule, réalisé le 05/10/2026. Aucun fichier du dépôt n'a été modifié, rien n'a été écrit en base (SELECT ponctuels sur `umoa_discovery_e2e` uniquement), aucun commit.

## Résumé

| Question | Réponse |
|---|---|
| Taux de notes disponibles (≥2020) | **APE : 22 sur 117 (18,8 %)** sur un échantillon stratifié de 150 opérations ; toutes natures confondues : 23 sur 150 (15,3 %). C'est une borne basse, en forte baisse après 2021 (2020 : 8 sur 18 ; 2022-2024 : 3 sur 39). Placements privés et placements auprès de salariés : 0, diffusion non attendue. L'AMF ne sert pas les notes (fichier de 0 octet) mais sert les **décisions de visa** (scans). |
| Signification d'`acteurLib` | Sur 9 opérations rapprochables : égal à la SGI arrangeur ou chef de file dans 5 cas, partiel dans 1, discordant dans 2, indéterminé dans 1. Vaut « ETAT » pour 51 opérations, même quand la décision de visa nomme une SGI. Ce n'est **pas un rôle** : c'est probablement la SGI qui a saisi l'AMF. À stocker comme `filing_agent_raw`, jamais comme rôle. |
| Rattachement SGI → banque | 23 SGI nommées. **2 documentées vers une banque de la liste** : BNI Finances → BNI, BICI Bourse → BICICI. **5 au niveau groupe seulement** : SG-CSWA, EIC/EDC, Coris Bourse, Atlantique Finance, Oragroup Securities. **16 non trouvées.** Un lien plus utile existe : des banques nommées **directement** (Société Générale Sénégal co-arrangeur, Vista Bank co-arrangeur, SG CI investisseur de référence, NSIA Banque CI prêteur refinancé). |
| Gestion de la dette | 42 opérations « rachat et émission simultanée » (01/2025 à 07/2026) déjà repérées via UMOA-Titres. Le volet rachat donne ISIN et montants mais **aucun participant nommé**. Un échange ou reprofilage CI de mars 2025 a été vu en presse, non vérifié. |
| Faisabilité presse | Techniquement accessible (robots.txt permissifs pour les articles, flux RSS). Pas de CGU explicites : stockage limité aux métadonnées et citations courtes. Rôles nommés dans 6 articles sur 9, but dans 8 sur 9. La presse est la seule source pour certains liens banque → deal. Classe `press_reported` proposée, plafonnée à `needs_review`. |

## Livrables

| Fichier | Contenu |
|---|---|
| `01_ape_profile.md` | profil des 551 opérations, routes API, **défauts de qualité de l'API** (131 émetteurs génériques erronés, visas incohérents) |
| `02_note_availability.md` + `.csv` | méthode, échantillon, taux, dépôts de notes, nombre de requêtes |
| `03_notes_roles.md` | 11 notes : rôles, garant, utilisation des fonds (page et URL) ; tableau `acteurLib` ; rapports annuels AMF |
| `04b_press_feasibility_sourced.md` | robots.txt, CGU, fréquence, 9 articles, classe `press_reported` (remplace `04_press_feasibility.md`, non sourcé) |
| `05_sgi_links.md` | SGI → banque (A/B/C) et banques nommées directement |
| `06_debt_management.md` | inventaire des rachats et autres sources |
| `07_proposition.md` | taxonomie fermée, rôles, `use_of_proceeds`, `institution_links`, classes de confiance, vues « deals par banque » — **à valider avant migration** |
| données | `notes/` (34 PDF), `visas/`, `rapports_amf/`, `umoatitres/`, `press/`, `robots/`, `roles_raw/`, `requests_log.csv` (239 requêtes), `banks_137.txt`, `db_buyback_*.txt`, `raw_*.json` |
| scripts jetables | `profile_ops.py`, `verify_notes.py`, `availability.py`, `extract_roles.py`, `grep_note.py` (Python système, PyMuPDF déjà installé ; rien installé) |

## Exemples clés (avec provenance)

- PAD 6,60 % 2020-2027 : arrangeur et chef de file Invictus Capital & Finance (note p.55) ; « Financer les infrastructures terrestres du Port de Ndayane » (p.53). Concordant avec `acteurLib` et avec Financial Afrik (01/10/2020).
- État du Sénégal, juin 2025 (300 Md) : arrangeur et chef de file CGF Bourse (p.15) ; **co-arrangeur Société Générale Sénégal** (p.52) ; besoins de la LFI 2025 et « Sénégal Vision 2050 » (p.11). `acteurLib` de l'API = ABCO Bourse (simple membre du syndicat).
- Diaspora Bonds Burkina 2026 : co-arrangeurs **Vista Bank**, SBIF et Oragroup Securities ; chef de file SBIF (p.14, p.20) ; centrale de Bagré-Aval (p.14) ; garantie souveraine (p.19).
- CRRH-UEMOA 2022 : refinancement de « Dix (10) banques actionnaires » (p.14), **non nommées**.

## Limites

- Échantillon à une requête moteur par groupe : le taux de disponibilité est une borne basse.
- Une seule décision de visa a été lue (scan) : l'hypothèse « `acteurLib` = SGI déclarante » reste à confirmer sur d'autres décisions.
- Fréquence presse mesurée sur les flux du jour, pas sur un mois.
- Deux notes antérieures à 2020 ont été utilisées (BOA Mali 2015, CRRH 2013), faute de notes bancaires ou régionales récentes publiques hors BOAD/IFC/BAD.
- Lectures visuelles (logos, police non décodable) : traçables par fichier image dans `roles_raw/`, à revoir par un humain.
- Le fichier hérité `04_press_feasibility.md` et le fichier vide `test_note.pdf` ; `raw_acteurs.json` (vide) a été remplacé par `raw_actualite_categories.json` (réponse de `/acteur/group-by-categorie`, catégories d’actualités) et `raw_sgi_amf.json` (41 SGI) proviennent de la session précédente.

## Mise à jour du 05/10/2026 (après revue)

Décisions D1 à D5 validées et intégrées dans `07_proposition.md` (arrangeur ≠ chef de file ; `acteurLib` = champ brut « SGI déclarante » ; lien SGI → banque à deux niveaux ; presse dans le périmètre en `press_reported`, toujours `needs_review` sans recoupement ; pas d'OCR pour l'instant). Plan de pilote sur 28 deals réels : `08_pilote.md`. La section ci-dessous est conservée pour l'historique.

## Décisions demandées (historique)

1. Valider ou amender la taxonomie et les rôles de `07_proposition.md`, notamment la séparation `arranger` / `lead_manager` et l'interdiction de convertir `acteurLib` en rôle.
2. Valider le modèle `institution_links` à deux niveaux (banque documentée / groupe seulement).
3. Décider si la presse (`press_reported`) entre dans le périmètre, et s'il faut contacter les éditeurs pour un accord de réutilisation.
4. Décider si l'on exploite les décisions de visa AMF (scans, donc OCR à installer : décision séparée).
