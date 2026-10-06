"""Accent- and case-insensitive LIKE matching (portable: SQL translate(), no extension)."""

from __future__ import annotations

import unicodedata

from sqlalchemy import func
from sqlalchemy.sql.elements import ColumnElement

_ACCENTED = "àáâãäåçèéêëìíîïñòóôõöùúûüýÿœæ’"
_PLAIN = "aaaaaaceeeeiiiinooooouuuuyy" + "oa'"  # œ/æ keep first letter, ’ -> '


def fold(text: str) -> str:
    """Python-side fold matching :func:`folded` (lowercase, accents stripped)."""
    decomposed = unicodedata.normalize("NFKD", text.lower().replace("’", "'"))
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def folded(column) -> ColumnElement:
    return func.translate(func.lower(column), _ACCENTED, _PLAIN)


def escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def fuzzy_contains(column, query: str) -> ColumnElement:
    """`column` contains `query`, ignoring case and accents ("societe" matches "SOCIÉTÉ")."""
    return folded(column).like(f"%{escape_like(fold(query))}%", escape="\\")
