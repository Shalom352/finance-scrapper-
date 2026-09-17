"""
UMOA Banking Intelligence — SQLAlchemy Declarative Base

All models inherit from Base. Provides:
- UUID primary keys (generated application-side for portability)
- created_at / updated_at timestamps (auto-managed)
- deleted_at for soft deletes (financial data is never physically deleted)
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    """Return current UTC time (timezone-aware)."""
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """
    SQLAlchemy declarative base with common audit fields.

    All models should inherit from this base.
    """

    # UUID primary key — generated application-side
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    # Audit timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
        nullable=False,
    )

    # Soft delete — financial data is never physically deleted
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} id={self.id!r}>"
