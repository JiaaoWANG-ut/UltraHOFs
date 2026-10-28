from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base
from ._common import ts_column


class GeneratedStructure(Base):
    """A periodic structure built (and optionally relaxed) on the platform."""

    __tablename__ = "generated_structures"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("orgs.id"), index=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(200), default="")
    components: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    topology: Mapped[str] = mapped_column(String(40), default="")
    dimensionality: Mapped[int] = mapped_column(Integer, default=3)
    options: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    cell: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    formula: Mapped[str] = mapped_column(String(200), default="")
    n_atoms: Mapped[int] = mapped_column(Integer, default=0)
    density: Mapped[float | None] = mapped_column(Float, nullable=True)
    cif_path: Mapped[str] = mapped_column(Text, default="")
    qc: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    analysis: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    relax: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("generated_structures.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="built")
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = ts_column()
