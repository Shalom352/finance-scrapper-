"""
Pure ranking functions (no database).

Tie rule — standard competition ranking ("1224"):
  equal values share the same rank and the next rank skips accordingly
  (A=100 → 1, B=100 → 1, C=90 → 3). Institution name then id only make the
  display order deterministic; they never change a rank.
"""
from collections.abc import Sequence
from decimal import Decimal
from typing import TypeVar

from scraping.rankings.models import Coverage

T = TypeVar("T")


def competition_ranks(
    items: Sequence[T],
    *,
    value: "callable[[T], Decimal]",
    name: "callable[[T], str]",
    ident: "callable[[T], str]",
    descending: bool = True,
) -> list[tuple[int, T]]:
    """Rank items by value with shared ranks for ties (1, 1, 3)."""
    ordered = sorted(items, key=lambda it: (name(it).casefold(), ident(it)))
    ordered = sorted(ordered, key=value, reverse=descending)  # stable: keeps name/id order within ties

    ranked: list[tuple[int, T]] = []
    previous: Decimal | None = None
    current_rank = 0
    for position, item in enumerate(ordered, start=1):
        v = value(item)
        if previous is None or v != previous:
            current_rank = position
            previous = v
        ranked.append((current_rank, item))
    return ranked


def compute_coverage(
    eligible_count: int,
    expected_count: int,
    ranked_count: int | None = None,
    available: bool = True,
) -> Coverage:
    """Real coverage of a ranking.

    - ratio = ranked / expected when the ranking is computed;
    - None when no institution is expected (never max(..., 1));
    - None with status "unavailable" when the ranking cannot be computed although
      eligible values exist (e.g. heterogeneous currencies): never 0/N.
    eligible_count is always the real number of admissible values.
    """
    ranked = eligible_count if ranked_count is None else ranked_count
    if not available:
        return Coverage(eligible_count=eligible_count, ranked_count=0, expected_count=expected_count,
                        coverage_ratio=None, coverage_status="unavailable")
    if expected_count <= 0:
        return Coverage(eligible_count=eligible_count, ranked_count=ranked, expected_count=expected_count,
                        coverage_ratio=None, coverage_status="unavailable")
    return Coverage(eligible_count=eligible_count, ranked_count=ranked, expected_count=expected_count,
                    coverage_ratio=round(ranked / expected_count, 4), coverage_status="available")


def distinct_currencies(currencies: Sequence[str | None]) -> set[str | None]:
    """Currencies of eligible values; an unknown currency (None) counts as distinct."""
    return set(currencies)


def is_currency_homogeneous(currencies: Sequence[str | None]) -> bool:
    return len(distinct_currencies(currencies)) <= 1


def paginate(items: Sequence[T], page: int, page_size: int) -> tuple[list[T], bool, bool]:
    """Slice an already ranked list: ranks never depend on the page."""
    offset = (page - 1) * page_size
    return list(items[offset : offset + page_size]), offset + page_size < len(items), page > 1
