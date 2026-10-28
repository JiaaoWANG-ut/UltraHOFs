from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Integer, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base
from ._common import ts_column


class Molecule(Base):
    """A molecular species (one protonation/tautomeric microstate)."""

    __tablename__ = "molecules"

    id: Mapped[int] = mapped_column(primary_key=True)
    smiles: Mapped[str] = mapped_column(Text)
    inchi: Mapped[str] = mapped_column(Text, default="")
    inchikey: Mapped[str] = mapped_column(String(27), unique=True, index=True)
    # InChIKey of the neutralised canonical-tautomer parent (matches across protonation states).
    parent_key: Mapped[str] = mapped_column(String(27), index=True, default="")
    # First InChIKey block of the parent: connectivity only (ignores stereo/isotopes).
    skeleton_key: Mapped[str] = mapped_column(String(14), index=True, default="")
    name: Mapped[str] = mapped_column(Text, default="")
    synonyms: Mapped[list[str]] = mapped_column(JSON, default=list)
    formula: Mapped[str] = mapped_column(String(120), default="")
    mw: Mapped[float] = mapped_column(Float, default=0.0)
    charge: Mapped[int] = mapped_column(Integer, default=0)
    heavy_atoms: Mapped[int] = mapped_column(Integer, default=0)
    synthons: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    n_connect: Mapped[int] = mapped_column(Integer, default=0)
    core_class: Mapped[str] = mapped_column(String(60), default="")
    descriptors: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    score: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    fp: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    # experimental | generated | user
    origin: Mapped[str] = mapped_column(String(20), default="user", index=True)
    is_experimental_tecton: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    provenance: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = ts_column()


class ComponentSystem(Base):
    """A set of molecular components with stoichiometry (single- or multi-component HOF)."""

    __tablename__ = "component_systems"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(Text, default="")
    # canonical key: sorted "INCHIKEY*stoich" for framework-forming components
    system_key: Mapped[str] = mapped_column(String(400), unique=True, index=True)
    n_components: Mapped[int] = mapped_column(Integer, default=1)
    charge_assisted: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = ts_column()

    components: Mapped[list[Component]] = relationship(
        back_populates="system", cascade="all, delete-orphan", order_by="Component.id"
    )


class Component(Base):
    __tablename__ = "components"

    id: Mapped[int] = mapped_column(primary_key=True)
    system_id: Mapped[int] = mapped_column(ForeignKey("component_systems.id", ondelete="CASCADE"), index=True)
    molecule_id: Mapped[int] = mapped_column(ForeignKey("molecules.id"), index=True)
    # tecton | co_tecton | counterion | template | solvent | guest
    role: Mapped[str] = mapped_column(String(20), default="tecton")
    stoichiometry: Mapped[float] = mapped_column(Float, default=1.0)

    system: Mapped[ComponentSystem] = relationship(back_populates="components")
    molecule: Mapped[Molecule] = relationship()
