"""
Row-level qualification of observations for the data explorer.

Every stored observation keeps its real status. On top of it, each row is told
where it stands in the EXISTING authority rule applied to its logical key
(institution, metric, year, period_type, scope):

  - "authoritative": the value the platform uses for this key;
  - "superseded":    another observation of the same key is authoritative;
  - "conflict":      divergent unverified values — no value is certified;
  - "needs_review":  the authoritative candidate still needs review (not certified);
  - "rejected":      rejected observation — never a valid financial value;
  - "missing_value": no normalized value stored — never shown as 0.

The rule itself is not reimplemented: qualify_metric → EligibilityEngine.
"""
from collections import defaultdict
from collections.abc import Iterable
from typing import Literal

from scraping.analytics.eligibility import EligibilityEngine
from scraping.consolidation.models import ObservationSummary
from scraping.rankings.eligibility import qualify_metric

Qualification = Literal["authoritative", "superseded", "conflict", "needs_review", "rejected", "missing_value"]

LogicalKey = tuple[str, str, int, str, str | None]


def logical_key(obs: ObservationSummary) -> LogicalKey:
    return (obs.institution_id, obs.metric_code, obs.period_year, obs.period_type, obs.scope)


def qualify_rows(
    rows: Iterable[ObservationSummary],
    siblings: Iterable[ObservationSummary],
    engine: EligibilityEngine | None = None,
) -> dict[str, tuple[Qualification, str | None]]:
    """Qualification of each row, computed on ALL observations sharing its logical key.

    `siblings` must contain every stored observation of the keys of `rows` (the page
    alone is not enough: the authority rule is decided over the whole key).
    """
    engine = engine or EligibilityEngine()
    groups: dict[LogicalKey, list[ObservationSummary]] = defaultdict(list)
    for o in siblings:
        groups[logical_key(o)].append(o)

    decisions = {key: qualify_metric("", group, engine) for key, group in groups.items()}
    out: dict[str, tuple[Qualification, str | None]] = {}
    for o in rows:
        if o.status == "rejected":
            out[o.id] = ("rejected", None)
            continue
        if o.value_normalized is None:
            out[o.id] = ("missing_value", None)
            continue
        cand = decisions.get(logical_key(o))
        if cand is None:
            out[o.id] = ("missing_value", None)
        elif cand.eligible:
            out[o.id] = ("authoritative", None) if cand.data_id == o.id else ("superseded", cand.data_id)
        elif cand.reason == "conflict":
            out[o.id] = ("conflict", None)
        else:
            out[o.id] = ("needs_review", None)
    return out
