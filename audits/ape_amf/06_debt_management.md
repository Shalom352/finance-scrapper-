# 06 — Gestion de la dette : rachats, échanges, reprofilage

## 1. Déjà vu dans UMOA-Titres (base umoa_discovery_e2e, SELECT uniquement)

- 69 des 590 deals portent le drapeau `page_lists_buyback_securities`. Ils correspondent à **42 opérations distinctes « rachat et émission simultanée »** du 09/01/2025 au 02/07/2026 : CI 9, ML 10, NE 10, SN 7, TG 4, GW 2 (détail : `db_buyback_operations.txt` — date, pays, page d'émission, compte rendu PDF ; `db_buyback_deals.txt` — deals et pages sources).
- En base, seul le **volet émission** est stocké. Le volet rachat est ignoré par conception.
- Contenu du volet rachat, d'après l'exemple `umoatitres/CR-CI-EC-09.01.2025.pdf` (https://www.umoatitres.org/wp-content/uploads/2025/01/Compte-rendu-CI-EC-09.01.2025-1.pdf), p.2 : 8 lignes rachetées, avec les ISIN (CI0000005138…), des numéros « RA-CI0000005138-12-2025 », les échéances, un montant global de 80 507 millions FCFA, le nombre de participants (1 à 2) et le taux/prix. **Aucun participant n'est nommé.**
- Ce qu'on peut en tirer : la date, l'émetteur, les titres et montants rachetés et la ligne d'émission associée. C'est utile pour une vue « gestion de la dette par État », mais pas pour les rôles bancaires. Le dernier deal (NE, 02/07/2026, intitulé « émission simultanée ») porte le drapeau ; le libellé est à vérifier.

## 2. Autres sources possibles

| Source | Constat | Statut |
|---|---|---|
| Comptes rendus UMOA-Titres (volet RA-) | structurés, réguliers | primaire — sans rôles |
| Sika Finance, 12/02/2025, « UMOA-Titres : Entre rachat et émission, le Sénégal réussit une double opération financière » (sikafinance.com/marches/…_50902) | montants, part des « investisseurs locaux », sans noms | presse |
| Échange ou reprofilage du Trésor CI, mars 2025 (> 450 Md FCFA, « échange de titres arrivant à échéance contre des obligations plus longues ») | vu seulement dans un résumé de moteur citant businessactuality.com | **non vérifié** — chercher le communiqué sur tresor.gouv.ci / portaildettepublique.gouv.ci |
| finances.gouv.tg (communiqués DGTCP Togo) | pages accessibles | à explorer |
| AMF-UMOA, nature OPE | 2 opérations dans toute l'API, aucune depuis 2020 | marginal |
| Euro-obligations (rachats ou échanges hors marché régional) | hors périmètre de cet audit | — |

Conclusion : la gestion de la dette est bien documentée côté **montants** (UMOA-Titres) mais n'apporte **pas de rôles bancaires**. La rattacher aux banques n'est possible que pour les opérations syndiquées (APE et échanges par APE), où la note nomme l'arrangeur.
