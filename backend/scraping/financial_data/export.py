"""
CSV export of the data explorer view.

- Exactly the filtered rows (same filters as the table), rejected excluded unless
  explicitly requested — and then labelled "rejected", never as valid data.
- Values exported as stored (normalized value + unit + currency): no conversion,
  no rounding, no total; a missing value is an empty cell, never 0.
- Bounded: above EXPORT_MAX_ROWS the export is refused (refine the filters).
"""
import csv
import io
import re
from collections.abc import Iterable
from decimal import Decimal

EXPORT_MAX_ROWS = 5000

CSV_COLUMNS = (
    "institution",
    "institution_id",
    "country",
    "indicator",
    "year",
    "period_type",
    "period_label",
    "scope",
    "value_normalized",
    "unit",
    "currency",
    "value_original",
    "unit_original",
    "currency_original",
    "status",
    "qualification",
    "source",
    "document",
    "page",
    "data_id",
)


class ExportTooLargeError(ValueError):
    def __init__(self, total: int) -> None:
        super().__init__(f"{total} rows exceed the export limit of {EXPORT_MAX_ROWS}")
        self.total = total


_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")
_PLAIN_NUMBER = re.compile(r"^-[\d\s.,\u00a0\u202f]+$")


def _cell(value) -> str:
    if value is None:
        return ""  # missing stays missing
    if isinstance(value, Decimal):
        return format(value, "f")  # exact stored value, no float rounding / exponent
    text = str(value)
    # CSV/formula injection: scraped text starting like a formula is neutralized for
    # spreadsheets (a plain negative number such as "-1 250,5" is kept as published).
    if text.startswith(_FORMULA_PREFIXES) and not _PLAIN_NUMBER.match(text):
        return "'" + text
    return text


def build_csv(items: Iterable) -> str:
    """CSV text for explorer items (attributes named like FinancialDataExplorerItem)."""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(CSV_COLUMNS)
    for it in items:
        writer.writerow(
            [
                _cell(it.institution_name),
                _cell(it.institution_id),
                _cell(it.country_code),
                _cell(it.metric_code),
                _cell(it.period_year),
                _cell(it.period_type),
                _cell(it.period_label),
                _cell(it.scope),
                _cell(it.value_normalized),
                _cell(it.unit_normalized),
                _cell(it.currency_normalized),
                _cell(it.value_original),
                _cell(it.unit_original),
                _cell(it.currency_original),
                _cell(it.status),
                _cell(it.qualification),
                _cell(it.source_name),
                _cell(it.document_title),
                _cell(it.page_number),
                _cell(it.id),
            ]
        )
    return buf.getvalue()
