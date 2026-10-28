from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base
from ._common import ts_column


class Reference(Base):
    __tablename__ = "references"

    id: Mapped[int] = mapped_column(primary_key=True)
    doi: Mapped[str | None] = mapped_column(String(200), unique=True, index=True, nullable=True)
    title: Mapped[str] = mapped_column(Text, default="")
    authors: Mapped[list[dict[str, str]]] = mapped_column(JSON, default=list)
    journal: Mapped[str] = mapped_column(Text, default="")
    journal_abbrev: Mapped[str] = mapped_column(Text, default="")
    year: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    volume: Mapped[str] = mapped_column(String(40), default="")
    issue: Mapped[str] = mapped_column(String(40), default="")
    pages: Mapped[str] = mapped_column(String(60), default="")
    url: Mapped[str] = mapped_column(Text, default="")
    publisher: Mapped[str] = mapped_column(Text, default="")
    raw_citation: Mapped[str] = mapped_column(Text, default="")
    crossref: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    # crossref | manual | hofsyn
    source: Mapped[str] = mapped_column(String(20), default="manual")
    created_at: Mapped[datetime] = ts_column()


class DataSource(Base):
    __tablename__ = "data_sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(60), unique=True)
    name: Mapped[str] = mapped_column(Text)
    version: Mapped[str] = mapped_column(String(40), default="")
    url: Mapped[str] = mapped_column(Text, default="")
    license: Mapped[str] = mapped_column(String(80), default="")
    attribution: Mapped[str] = mapped_column(Text, default="")
    retrieved_at: Mapped[datetime] = ts_column()
