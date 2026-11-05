# Deal collection fixtures (captured 21/10/2026)

Real pages of the official sources, captured once with a polite fetch (robots.txt honoured,
BRVM crawl-delay 10 s), then **trimmed** to the markup around the parsed fields. Nothing inside the kept
fragments was rewritten. The tests never touch the network.

| Folder | Origin | Trimming |
|---|---|---|
| `brvm/boc_2026101{3,4}.pdf` | `https://www.brvm.org/sites/default/files/boc_2026101{3,4}_2.pdf` | pages kept: cover, "OBLIGATIONS D'ENTREPRISES", "OPERATIONS EN COURS" (fonts subset) |
| `brvm/boc_index.html` | `https://www.brvm.org/fr/bulletins-officiels-de-la-cote` | the first four BOC links only |
| `amf/operations.json` | `https://www.amf-umoa.org/service/api/elastic/operation?size=2000` | 8 operations kept verbatim (APE, EOP, OPV, PE; label / nature contradiction of op. 393) |
| `ifc/sii_*.html` | `https://disclosures.ifc.org/project-detail/SII/<n>/<slug>` | summary grid + "Total Project Cost" + "Investment as Approved by the Board" panels |
| `ifc/sitemap*.xml` | `https://disclosures.ifc.org/sitemap.xml` and one chunk | five entries kept (real `lastmod`) |
| `boad/*.html` | `https://www.boad.org/fr/nos-publications/nos-projets-approuves/...` | Inertia `data-page` JSON reduced to `page` + first two blocks (list: first 6 projects, SEO fields dropped) |
| `proparco/*.html` | `https://www.proparco.fr/fr/carte-des-projets/<slug>` | `<h1>` + the `<dl>` of the sheet |
| `proparco/sitemap*.xml` | `https://www.proparco.fr/sitemap.xml` | four sheets (FR/EN) + one news URL; `lastmod` of `dakar-mobilite` is real, the three others are test values |
| `press/*.html` | Sika Finance / Agence Ecofin articles captured by the audit of 05/10/2026 (`audits/ape_amf/press/`), Financial Afrik article of 21/10/2026 | head metadata (og:title, og:url, published date) + the article container; a `<nav>` line "S'abonner · Connexion · Sika Premium" is ADDED to check that menus are not taken for a paywall |
| `press/*_feed.xml` | the three RSS feeds of 21/10/2026 | first twelve items, verbatim |

The BOAD list data carries the CMS placeholder content observed on the live site (e.g. "Laravel has
wonderful documentation", impacts "TEST"): the parser must ignore it, and a test checks that it does.
