# 04b — Presse et communiqués : faisabilité (version sourcée)

> Remplace `04_press_feasibility.md` (session précédente), conservé tel quel mais **à ne pas utiliser** : robots.txt supposés (« typical »), exemples sans URL, affirmation non vérifiée (« notes hébergées sur UMOA-Titres »).

Copies des robots.txt : `robots/`. Flux et articles : `press/`. Collecte du 05/10/2026.

## 1. Accès, robots.txt, conditions d'utilisation

| Site | robots.txt (réel) | Conditions d'utilisation | Accès constaté |
|---|---|---|---|
| Financial Afrik | `User-agent: *` : interdit /calendar-2/…, /wp-admin/, /membership-login/… ; articles autorisés ; sitemaps /en/sitemap.xml, /en/google-news-sitemap.xml | Pages « Charte de Financial Afrik » et « Clause de non-responsabilité » : **aucune clause** sur la reproduction ou l'extraction | RSS /feed/ OK ; articles OK ; certains articles sont **réservés aux abonnés** (ex. CRRH 12/01/2026 : seule l'introduction est visible) |
| Agence Ecofin | interdit /api/, /tags/, /author/, /a-la-une/recherche-article/… ; **Bytespider : Disallow /** ; flux annoncé `RSS : …/obrss-2/ecofin-ugb-all-secteurs` | Aucune page de CGU trouvée (le lien « droits-rss » est un flux) | RSS et curl OK ; **WebFetch → 403** (protection anti-robots sur certains agents) |
| Sika Finance | interdit /listes/displaylist, /portif/displayp, /docs/* ; nombreux robots bloqués (Semrush, Diffbot, MJ12, AwarioRssBot…) | Pied de page : « Copyright © 2026 sikafinance.com - Tous droits réservés » ; pas de CGU trouvées | RSS /rss/actualites_bourse_brvm et articles OK ; « Sika Premium » sur une partie du contenu |
| Sites de banques | orabank.net : **403** pour l'agent automatique ; bni.ci, bicibourse.ci : pas de robots.txt (404) ; bank-of-africa.net, ecobank.africa-newsroom.com : accessibles | non examinées | communiqués rares sur les deals (Ecobank Gender Bond : communiqué de groupe) |

Faute de CGU explicites, on applique le régime par défaut du droit d'auteur : stocker **les métadonnées** (titre, date, URL), **des citations courtes** pour preuve et nos champs extraits, jamais l'article intégral, et toujours avec un lien vers la source. Pour un usage systématique, demander l'accord écrit des éditeurs. Agent identifiable, au plus une requête toutes les 5 s, aucun contournement de paywall.

## 2. Structure et fréquence (mesure sur les flux du 05/10/2026, pas sur un mois)

| Site | Volume observé | Part des deals |
|---|---|---|
| Financial Afrik | 17 articles en ~3 h (flux RSS) | 4 titres « financement / prêt / Eurobond » dans la fenêtre, aucun UMOA |
| Agence Ecofin | 42 articles en ~28 h (sitemap news), tous secteurs | 3 à 4 titres financement, dont 1 UEMOA (BOAD) |
| Sika Finance | 32 articles en ~3,3 jours (RSS BRVM) | 1 titre lié (BOAD) |

Limite : la mesure de fréquence sur un mois prévue au plan n'a pas été faite (archives non parcourues). Les deals UMOA ne représentent qu'**une petite part** du flux, ce qui impose un filtrage par mots-clés suivi d'une revue.

## 3. Qualité sur 9 articles réels

(Dates Ecofin déduites du préfixe d'URL JJMM + contexte de l'article ; dates Sika lues dans les métadonnées `datePublished` ; dates FA dans l'URL.)

| Article | Rôle bancaire/SGI nommé | Utilisation des fonds | Comparaison avec la note (si disponible) |
|---|---|---|---|
| FA 01/10/2020, PAD (financialafrik.com/2020/10/01/le-port-autonome-de-dakar-lance-…) | « la SGI Invictus Capital & Finance, en tant qu'arrangeur et chef de file du syndicat de placement » | « financer le projet de construction et de développement du port à Ndayane » | **concordant** avec N06 p.55 |
| FA 22/09/2021, Oragroup 50 Md | non mentionné | « 70 % … refinancement de la dette, 20 % … développement commercial des filiales et 10 % à des projets stratégiques » | note non trouvée ; dépliant seulement |
| FA 12/01/2026, Social Bond CRRH | **paywall** : non accessible | non accessible | — |
| Ecofin 14/09/2026, Baobab CI SLB (…/1409-141527-…) | « Chef de file et Arrangeur : CGF Bourse » ; « Investisseur d'ancrage : IFC » (IFC exclu pour l'instant) | « financeront les micro, petites et moyennes entreprises dirigées par des femmes… » ; visa EOP/26-06 cité | opération **absente de l'API AMF** (plus récente) : la presse est en avance |
| Ecofin 28/02/2025, Gender Bond Ecobank CI | non mentionné | « faciliter l'accès au financement des entreprises dirigées par des femmes… » | — |
| Ecofin 28/07/2026, AFINHAB Social Bond | « Arrangeurs et Chefs de File : SGCS et FGI » ; « Investisseur de référence : Société Générale Côte d'Ivoire » | logement abordable | format **communiqué** (fiche technique en fin d'article) |
| Sika 13/12/2024, Niger 200 Md | « Arrangée par SGI Niger qui en est le chef de file » | « financer les projets inscrits dans le budget 2024 et à régler les impayés sur le marché régional » | concordant avec la note TPNE 2025 (SGI Niger, dépôt sginiger.com) — rôle non relu dans la note |
| Sika 12/02/2025, rachat-émission Sénégal | aucun nom (part des « investisseurs locaux ») | n/a | concordant avec UMOA-Titres pour les montants |
| Sika 06/07/2021, Emergence Plaza (EOP) | « arrangé par la SGI HUDSON & Cie » ; refinancement du « prêt senior conclu avec NSIA Banque Côte d'Ivoire » | « refinancer à hauteur de 8,21 milliards FCFA le prêt senior… ; le solde… » (citant la note) | note privée non publique : la presse est **la seule** source |

Bilan : 6 articles sur 9 nomment un rôle, 8 sur 9 donnent un but, 1 paywall. Les articles au format communiqué (Ecofin) sont les plus structurés. La presse **apporte des liens banque → deal absents des sources primaires publiques** (NSIA Banque CI prêteur, SG CI investisseur), mais au conditionnel journalistique.

## 4. Classe de confiance proposée : `press_reported`

- La source est un article de presse ou un communiqué repris par la presse ; elle ne peut jamais dépasser `needs_review`.
- Un rôle n'est retenu que s'il est **nommé explicitement** dans l'article (citation exacte stockée). « Arrangée par X » donne `arranger` ; « chef de file » donne `lead_manager`. Aucun rôle n'est déduit (« avec l'appui de », « en partenariat avec » → pas de rôle).
- Le passage à `verified` exige un recoupement avec une source primaire : note, décision de visa, communiqué de l'émetteur ou de la banque sur son domaine officiel, compte rendu UMOA-Titres ou BRVM.
- Sous-classe `issuer_press_release` (communiqué signé de l'émetteur, publié sur son domaine ou reproduit intégralement) : confiance supérieure à `press_reported`, toujours en `needs_review`.
- Pour un article payant, on ne stocke que le titre, la date et l'URL, sans extraction.
- En cas de conflit entre la presse et la note, la note prévaut et le conflit est conservé et affiché.
