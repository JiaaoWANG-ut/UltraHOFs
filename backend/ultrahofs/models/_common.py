from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime


def utcnow() -> datetime:
    return datetime.now(UTC)


def ts_column(**kw):  # noqa: ANN003, ANN201
    from sqlalchemy.orm import mapped_column

    return mapped_column(DateTime(timezone=True), default=utcnow, **kw)
