from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base
from ._common import ts_column

# Tri-state evidence labels kept separate on purpose: an entry can be crystalline and
# H-bonded without demonstrated permanent porosity, and "not reported" is never "no".
EVIDENCE_LABELS = (
    "crystal_structure_reported",
    "extended_hbond_network",
    "geometric_porosity",
    "activation_retained",
    "measured_porosity",
)
EVIDENCE_VALUES = ("yes", "no", "unknown")
CURATION_STATUSES = ("auto", "needs_review", "verified", "candidate", "rejected")


def default_evidence() -> dict[str, dict[str, str]]:
    return {k: {"value": "unknown", "source": "", "note": ""} for k in EVIDENCE_LABELS}


class HOFEntry(Base):
    """An experimentally reported crystalline phase of a (multi-)component H-bonded framework."""

    __tablename__ = "hof_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), default="", index=True)
    system_id: Mapped[int | None] = mapped_column(ForeignKey("component_systems.id"), nullable=True, index=True)
    ccdc_numbers: Mapped[list[str]] = mapped_column(JSON, default=list)
    csd_refcodes: Mapped[list[str]] = mapped_column(JSON, default=list)
    cif_raw_path: Mapped[str] = mapped_column(Text, default="")
    cif_clean_path: Mapped[str] = mapped_column(Text, default="")
    cleaning_log: Mapped[list[str]] = mapped_column(JSON, default=list)
    formula: Mapped[str] = mapped_column(String(200), default="")
    cell: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    space_group: Mapped[str] = mapped_column(String(40), default="")
    density: Mapped[float | None] = mapped_column(Float, nullable=True)
    topology: Mapped[str] = mapped_column(String(40), default="", index=True)
    topology_source: Mapped[str] = mapped_column(String(40), default="")
    hbond_dimensionality: Mapped[int | None] = mapped_column(Integer, nullable=True)
    interpenetration: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pore: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSON, default=default_evidence)
    hbond_class: Mapped[str] = mapped_column(String(80), default="", index=True)
    application: Mapped[str] = mapped_column(Text, default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    year: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    source_dataset: Mapped[str] = mapped_column(String(80), default="")
    source_record: Mapped[str] = mapped_column(String(200), default="")
    license: Mapped[str] = mapped_column(String(80), default="")
    curation_status: Mapped[str] = mapped_column(String(20), default="auto", index=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    issues: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = ts_column()
    updated_at: Mapped[datetime] = ts_column()

    system = relationship("ComponentSystem")
    conditions: Mapped[list[SynthesisCondition]] = relationship(
        back_populates="entry", cascade="all, delete-orphan"
    )
    properties: Mapped[list[Property]] = relationship(back_populates="entry", cascade="all, delete-orphan")
    references: Mapped[list[EntryReference]] = relationship(
        back_populates="entry", cascade="all, delete-orphan"
    )


class SynthesisCondition(Base):
    __tablename__ = "synthesis_conditions"

    id: Mapped[int] = mapped_column(primary_key=True)
    entry_id: Mapped[int] = mapped_column(ForeignKey("hof_entries.id", ondelete="CASCADE"), index=True)
    solvents: Mapped[list[str]] = mapped_column(JSON, default=list)
    temperature: Mapped[str] = mapped_column(String(80), default="")
    temperature_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    time_h: Mapped[float | None] = mapped_column(Float, nullable=True)
    additive: Mapped[str] = mapped_column(Text, default="")
    method: Mapped[str] = mapped_column(Text, default="")
    raw: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    entry: Mapped[HOFEntry] = relationship(back_populates="conditions")


class Property(Base):
    __tablename__ = "properties"

    id: Mapped[int] = mapped_column(primary_key=True)
    entry_id: Mapped[int] = mapped_column(ForeignKey("hof_entries.id", ondelete="CASCADE"), index=True)
    # bet | gas_uptake | stability | application | other
    kind: Mapped[str] = mapped_column(String(40))
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit: Mapped[str] = mapped_column(String(40), default="")
    text: Mapped[str] = mapped_column(Text, default="")
    conditions: Mapped[str] = mapped_column(Text, default="")
    reference_id: Mapped[int | None] = mapped_column(ForeignKey("references.id"), nullable=True)

    entry: Mapped[HOFEntry] = relationship(back_populates="properties")


class EntryReference(Base):
    __tablename__ = "entry_references"

    entry_id: Mapped[int] = mapped_column(ForeignKey("hof_entries.id", ondelete="CASCADE"), primary_key=True)
    reference_id: Mapped[int] = mapped_column(ForeignKey("references.id"), primary_key=True)
    # primary | structure | property | related
    role: Mapped[str] = mapped_column(String(20), default="primary")

    entry: Mapped[HOFEntry] = relationship(back_populates="references")
    reference = relationship("Reference")
