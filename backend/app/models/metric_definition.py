"""
UMOA Banking Intelligence — Metric Definition Model

Official catalogue of financial metrics (V1).

This table is the reference for ``financial_data.metric_code``.
It is seeded from ``app.constants.metrics`` (single source of truth).
Never invent a metric at runtime.

Reference: docs/specification-v1.md sections 6, 7, 8, 14.

Enumerations (open strings, guarded by CHECK constraints):
  statement_type : balance_sheet | income_statement | cash_flow_statement
                   | off_balance_sheet | not_applicable
  category       : assets | liabilities | equity | income_statement
                   | cash_flow | debt_indicator
  value_type     : amount | percentage | ratio | rate
  currency_type  : monetary | non_monetary

V1: all 26 metrics have ``is_calculated = false`` (published values only).
"""

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.constants.metrics import METRIC_FAMILIES, SECTORS, sql_in
from app.db.base import Base

if TYPE_CHECKING:  # relationship targets, resolved by SQLAlchemy at runtime
    from app.models.financial_data import FinancialData


class MetricDefinition(Base):
    """
    Official financial metric definition.

    Represents a metric that may be recorded in ``financial_data``.
    The catalogue is evolutive: new metrics can be added without breaking
    existing data, provided their ``code`` is unique.
    """

    __tablename__ = "metric_definitions"
    __table_args__ = (
        UniqueConstraint("code", name="uq_metric_definitions_code"),
        CheckConstraint(
            f"sector IN ({sql_in(SECTORS)})",
            name="ck_metric_definitions_sector",
        ),
        CheckConstraint(
            f"metric_family IN ({sql_in(METRIC_FAMILIES)})",
            name="ck_metric_definitions_metric_family",
        ),
        CheckConstraint(
            "statement_type IN ('balance_sheet', 'income_statement', "
            "'cash_flow_statement', 'off_balance_sheet', 'not_applicable')",
            name="ck_metric_definitions_statement_type",
        ),
        CheckConstraint(
            "category IN ('assets', 'liabilities', 'equity', "
            "'income_statement', 'cash_flow', 'debt_indicator')",
            name="ck_metric_definitions_category",
        ),
        CheckConstraint(
            "value_type IN ('amount', 'percentage', 'ratio', 'rate')",
            name="ck_metric_definitions_value_type",
        ),
        CheckConstraint(
            "currency_type IN ('monetary', 'non_monetary')",
            name="ck_metric_definitions_currency_type",
        ),
    )

    # Technical identifier (e.g. "resultat_net") — referenced by financial_data
    code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # Sector and Family taxonomies (Phase 14)
    sector: Mapped[str] = mapped_column(String(50), nullable=False, default="banking", index=True, server_default="banking")
    metric_family: Mapped[str] = mapped_column(String(50), nullable=False, default="balance_sheet", index=True, server_default="balance_sheet")

    # User-facing labels
    label_fr: Mapped[str] = mapped_column(String(150), nullable=False)
    label_en: Mapped[str] = mapped_column(String(150), nullable=False)

    # Precise definitions (what the metric is / what it excludes)
    definition_fr: Mapped[str] = mapped_column(Text, nullable=False)
    definition_en: Mapped[str] = mapped_column(Text, nullable=False)

    # Financial statement the metric belongs to
    statement_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)

    # Reporting category
    category: Mapped[str] = mapped_column(String(30), nullable=False, index=True)

    # Type of value: amount | percentage | ratio | rate
    value_type: Mapped[str] = mapped_column(String(20), nullable=False)

    # Monetary vs non-monetary (drives currency_* rules)
    currency_type: Mapped[str] = mapped_column(String(20), nullable=False)

    # True only for platform-computed indicators. V1: always false.
    is_calculated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Whether the metric is currently active in the catalogue
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Whether the metric relates to corporate debt
    is_debt_related: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Display ordering in the catalogue
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Short synthetic description (catalogue listing) — optional
    description_synth: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    financial_data: Mapped[list["FinancialData"]] = relationship(  # type: ignore[name-defined]
        "FinancialData", back_populates="metric", lazy="noload"
    )

    def __repr__(self) -> str:
        return f"<MetricDefinition {self.code!r}>"
