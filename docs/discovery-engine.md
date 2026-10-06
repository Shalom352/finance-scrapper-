# Entity & Source Discovery Engine (Phase 15)

Coverage-driven discovery of the UMOA financial universe. First universe: **UMOA.BANKING** (banks of
the 8 UMOA countries). The engine answers *"have we really recorded every bank we claim to cover,
and what is still missing, and why?"* — from PostgreSQL, never from hand-typed figures.

## Chain

```
OFFICIAL REFERENCE LIST (BCEAO / CB-UMOA)  →  dated snapshot (expected counts read in the PDF)
  → ENTITY HUB (resolution, identifiers, name history, branches)
  → SOURCES (regulatory listing, website, publications, market) with lifecycle
  → DOCUMENTS (regulatory fascicle, institution PDFs)  → FINANCIAL DATA (catalogue metrics only)
  → COVERAGE (entity / source / document / data / validation)  → GAP QUEUE
  → next strategy able to close an open gap → … → STOP CONDITION
```

## Official reference

| Source | Document | Parsed by |
|---|---|---|
| BCEAO | *Liste des établissements de crédit agréés dans l'UMOA au <date>* (communiqué found through the BCEAO site search; summary table + one section per country) | `scraping/universe/reference_list.py` |
| CB-UMOA | *Listes des banques et des établissements financiers à caractère bancaire de l'UMOA (mise à jour au <date>)* (page "Établissements assujettis") | same parser |

- Every snapshot is kept (`reference_universes`, one UMOA row + one row per country). The **current**
  expected universe is the most recent snapshot whose self-check passed.
- Self-check: parsed rows = country header counts = summary table; subsidiaries / branches counts;
  continuous row numbering; unique registration numbers. A failed self-check makes the snapshot
  `AMBIGUOUS`: it is kept as evidence, never made current, nothing is created from it.
- `expected_count` is `NULL` (coverage **UNKNOWN**) when the document does not state it.

## Entity resolution (`scraping/universe/resolution.py`)

1. registration number (e.g. `B 0061 F`) — strong key;
2. exact official / former name, same country, same form;
3. name without country words / acronym / former acronym, unique in the country;
4. anything weaker → **ambiguous**: candidates stored on the member line, nothing linked, gap
   `ENTITY_UNRESOLVED` for a human. Generic words (BANK, BANQUE, INTERNATIONAL…) are never evidence.

Never across countries; a branch ("SUCCURSALE") is never merged with its parent (a `branch_of`
relationship is created only when the parent resolves unambiguously); an entity carrying another
registration number is another licensed entity. A human decision (`review_decision`) is never
overridden; a confirmed link receives the official evidence at the next reading of the list.

Names are append-only (`entity_names`): a newer official list with another name for the same
registration number closes the previous official name (`valid_to`) and becomes the canonical name.

## Strategies (one round each, by source priority)

| Order | Code | Source | Closes gaps |
|---|---|---|---|
| always | `bceao_reference_list` | BCEAO list (regulator) | universe |
| always | `cb_umoa_reference_list` | CB-UMOA list (supervisor) | universe |
| 1 | `bceao_regulatory_fascicle` | BCEAO *Bilans et comptes de résultat des banques et établissements financiers* | FINANCIAL_DOCUMENT, FINANCIAL_DATA |
| 2 | `official_links_in_documents` | website addresses printed in entity-specific official documents | OFFICIAL_WEBSITE |
| 3 | `official_website_crawl` | VERIFIED websites (robots.txt, home + 1 level) | ANNUAL_REPORT, FINANCIAL_DOCUMENT |
| 4 | `brvm_market_listings` | BRVM listed-company pages | OFFICIAL_WEBSITE, ANNUAL_REPORT |
| — | `secondary_verified` | disabled by policy (no search provider) | — |

A `SearchProvider` interface exists (`strategies/base.py`) but is deliberately not implemented.
No URL is ever guessed from a bank name.

Fascicle data: only published lines mapped 1:1 to an existing catalogue metric are read
(`TOTAL DE L'ACTIF`, `CREANCES SUR LA CLIENTELE`, `CREANCES INTERBANCAIRES`, `DETTES A L'EGARD DE LA
CLIENTELE`, `DETTES INTERBANCAIRES`, `CAPITAUX PROPRES ET RESSOURCES ASSIMILEES`, `PRODUIT NET
BANCAIRE`, `RESULTAT D'EXPLOITATION`, `RESULTAT NET`). A blank / non-numeric cell stays missing.
Every observation goes through the Phase-13 scope guard (`needs_review`, "scope not detected");
reviewed / verified / rejected rows are never touched.

## Source lifecycle

`CANDIDATE` (found) → `VERIFIED` (the page names the entity) → `ACTIVE` (it produced a stored
document); `BLOCKED` (401/403/429, robots.txt); `RETIRED`. HTTP 200 is not proof (bceao.int answers
unknown paths with its homepage and 200 — detected as a soft 404).

## Stop conditions (`discovery_runs.stop_condition`)

- `A_UNIVERSE_COVERED` — every official line resolved and no discoverable gap left (open or pending retry);
- `B_STRATEGIES_EXHAUSTED` — every applicable strategy tried, last pass without progress; remaining
  gaps become `NOT_FOUND` with `next_attempt_at` (retried later — an empty source is never final);
- `C_REFERENCE_UNAVAILABLE` — no self-consistent official list: **COVERAGE INCOMPLETE**;
- `SAFETY_CAP_REACHED` — technical round cap, explicitly not a completion.

## Commands

```bash
cd backend
python -m app.discovery.run --universe UMOA.BANKING                       # full run + report
python -m app.discovery.run --universe UMOA.BANKING --countries CI,SN      # subset
python -m app.discovery.run --universe UMOA.BANKING --report-only --report-file coverage.md
```

Recurring runs: `DISCOVERY_ENABLED=true` and `DISCOVERY_SCHEDULE="0 3 * * *"` (disabled by default).

## Tables (migration `0011_entity_source_discovery`)

`reference_universes`, `reference_universe_members`, `entity_identifiers`, `entity_names`,
`entity_sources`, `document_entities`, `discovery_runs`, `discovery_rounds`, `discovery_gaps`;
`sources.lifecycle_status` (+ last check columns); `documents.entity_id`.
Downgrade to `0010` drops only these objects.

Entities that no official list line supports (demo / legacy rows) are listed as *outside the
official universe* and never counted in any coverage figure.
