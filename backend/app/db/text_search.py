"""Accent- and case-insensitive LIKE matching (portable: SQL translate(), no extension)."""

from __future__ import annotations

import unicodedata

from sqlalchemy import and_, case, func, or_
from sqlalchemy.sql.elements import ColumnElement

_ACCENTED = "àáâãäåçèéêëìíîïñòóôõöùúûüýÿœæ’"
_PLAIN = "aaaaaaceeeeiiiinooooouuuuyy" + "oa'"  # œ/æ keep first letter, ’ -> '


def fold(text: str) -> str:
    """Python-side fold matching :func:`folded` (lowercase, accents stripped)."""
    # œ / æ: same first letter as the SQL side (translate), so both folds always agree.
    decomposed = unicodedata.normalize("NFKD", text.lower().replace("’", "'").replace("œ", "o").replace("æ", "a"))
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def folded(column) -> ColumnElement:
    return func.translate(func.lower(column), _ACCENTED, _PLAIN)


def escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def fuzzy_contains(column, query: str) -> ColumnElement:
    """`column` contains `query`, ignoring case and accents ("societe" matches "SOCIÉTÉ")."""
    return folded(column).like(f"%{escape_like(fold(query))}%", escape="\\")


# Word search: punctuation is a word separator, apostrophes are dropped ("D'IVOIRE" -> "divoire"), so
# "Ecobank Côte d'Ivoire", "ecobank cote divoire" and "ECOBANK - CÔTE D'IVOIRE" are the same words.
_SEPARATORS = "-./,()&:;_|+"
_DROPPED = "'"


def normalized(column) -> ColumnElement:
    return func.translate(folded(column), _SEPARATORS + _DROPPED, " " * len(_SEPARATORS))


def query_words(query: str) -> list[str]:
    text = fold(query).replace("'", "")
    return [w for w in "".join(c if c.isalnum() else " " for c in text).split() if w]


def all_words(columns, query: str) -> ColumnElement | None:
    """Every word of the query appears in one of ``columns`` (any order). None for a query without words."""
    words = query_words(query)
    if not words:
        return None
    return and_(*[or_(*[normalized(c).like(f"%{escape_like(w)}%", escape="\\") for c in columns]) for w in words])


def rank(column, query: str) -> ColumnElement:
    """0 = the whole name, 1 = the name starts with the query, 2 = anywhere (descriptive order, not a score)."""
    q = " ".join(query_words(query))
    return case((normalized(column) == q, 0), (normalized(column).like(f"{escape_like(q)}%", escape="\\"), 1),
                else_=2)
