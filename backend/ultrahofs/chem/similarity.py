"""Fingerprint similarity and substructure search over an in-memory molecule index."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field

from rdkit import Chem, DataStructs
from rdkit.Chem import rdFingerprintGenerator

_MORGAN = rdFingerprintGenerator.GetMorganGenerator(radius=2, fpSize=2048)


def morgan_fp(mol: Chem.Mol):
    return _MORGAN.GetFingerprint(mol)


def fp_to_bytes(fp) -> bytes:
    return DataStructs.BitVectToBinaryText(fp)


def fp_from_bytes(b: bytes):
    return DataStructs.CreateFromBinaryText(b)


@dataclass
class FingerprintIndex:
    ids: list[int] = field(default_factory=list)
    smiles: list[str] = field(default_factory=list)
    fps: list = field(default_factory=list)
    pfps: list = field(default_factory=list)
    mols: list = field(default_factory=list)

    def add(self, mol_id: int, smiles: str) -> None:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return
        self.ids.append(mol_id)
        self.smiles.append(smiles)
        self.mols.append(mol)
        self.fps.append(morgan_fp(mol))
        self.pfps.append(Chem.PatternFingerprint(mol))

    def __len__(self) -> int:
        return len(self.ids)

    def similar(self, mol: Chem.Mol, top_k: int = 10, threshold: float = 0.0) -> list[tuple[int, float]]:
        if not self.fps:
            return []
        sims = DataStructs.BulkTanimotoSimilarity(morgan_fp(mol), self.fps)
        order = sorted(range(len(sims)), key=lambda i: -sims[i])
        return [(self.ids[i], round(float(sims[i]), 4)) for i in order[:top_k] if sims[i] >= threshold]

    def max_similarity(self, mol: Chem.Mol) -> float | None:
        if not self.fps:
            return None
        return float(max(DataStructs.BulkTanimotoSimilarity(morgan_fp(mol), self.fps)))

    def substructure(self, query: Chem.Mol, limit: int = 500) -> list[int]:
        qfp = Chem.PatternFingerprint(query)
        hits = []
        for i, pfp in enumerate(self.pfps):
            if not DataStructs.AllProbeBitsMatch(qfp, pfp):
                continue
            if self.mols[i].HasSubstructMatch(query):
                hits.append(self.ids[i])
                if len(hits) >= limit:
                    break
        return hits


class IndexRegistry:
    """Lazily (re)built indices keyed by name; invalidated after data changes."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._indices: dict[str, FingerprintIndex] = {}

    def get(self, name: str, loader) -> FingerprintIndex:  # noqa: ANN001
        with self._lock:
            idx = self._indices.get(name)
            if idx is None:
                idx = FingerprintIndex()
                for mol_id, smi in loader():
                    idx.add(mol_id, smi)
                self._indices[name] = idx
            return idx

    def invalidate(self, name: str | None = None) -> None:
        with self._lock:
            if name is None:
                self._indices.clear()
            else:
                self._indices.pop(name, None)


registry = IndexRegistry()
