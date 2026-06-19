"""Identifier map for the transition to nanopub-based identifiers.

Records, per term, the mapping from its old/local identifier to the new
nanopub-based identifiers minted for it: the term's thing URI (its trusty
artifact-code URI) and the URI of its defining nanopub.

The map is meant to be kept permanently and grown incrementally, so old
identifiers stay resolvable and re-runs can append without losing prior entries.
It round-trips to a tab-separated file (a superset of a simple redirect table)
and to JSON.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional, Union

from pubmate.minting import MintBatch

_TSV_HEADER = ("old_id", "thing_uri", "np_uri")


@dataclass(frozen=True)
class IdMapEntry:
    """One term's old identifier and its new nanopub-based identifiers."""

    old_id: str
    thing_uri: str
    np_uri: str


class IdMap:
    """A collection of :class:`IdMapEntry`, keyed by ``old_id``."""

    def __init__(self, entries: Optional[Iterable[IdMapEntry]] = None):
        self._entries: Dict[str, IdMapEntry] = {}
        for entry in entries or ():
            self.add(entry)

    # -- population -------------------------------------------------------

    def add(self, entry: IdMapEntry, *, overwrite: bool = False) -> None:
        """Add an entry; conflicting ``old_id`` raises unless ``overwrite``.

        Re-adding an identical entry is always allowed (idempotent).
        """
        existing = self._entries.get(entry.old_id)
        if existing is not None and existing != entry and not overwrite:
            raise ValueError(
                f"conflicting id-map entry for {entry.old_id!r}: "
                f"{existing} vs {entry} (pass overwrite=True to replace)."
            )
        self._entries[entry.old_id] = entry

    def merge(self, other: "IdMap", *, overwrite: bool = False) -> None:
        """Merge another map into this one (see :meth:`add` for conflicts)."""
        for entry in other:
            self.add(entry, overwrite=overwrite)

    @classmethod
    def from_batch(cls, batch: MintBatch) -> "IdMap":
        """Build a map from a :class:`~pubmate.minting.MintBatch`.

        The minter's ``term_id`` is used as the old identifier.
        """
        return cls(
            IdMapEntry(old_id=t.term_id, thing_uri=t.thing_uri, np_uri=t.np_uri)
            for t in batch.terms
        )

    # -- access -----------------------------------------------------------

    def __contains__(self, old_id: object) -> bool:
        return old_id in self._entries

    def __getitem__(self, old_id: str) -> IdMapEntry:
        return self._entries[old_id]

    def __iter__(self) -> Iterator[IdMapEntry]:
        return iter(self._entries.values())

    def __len__(self) -> int:
        return len(self._entries)

    @property
    def thing_uri_map(self) -> Dict[str, str]:
        """``old_id -> thing URI``."""
        return {e.old_id: e.thing_uri for e in self}

    @property
    def np_uri_map(self) -> Dict[str, str]:
        """``old_id -> nanopub URI``."""
        return {e.old_id: e.np_uri for e in self}

    def _sorted(self) -> List[IdMapEntry]:
        return sorted(self._entries.values(), key=lambda e: e.old_id)

    # -- serialization ----------------------------------------------------

    def to_tsv(self) -> str:
        lines = ["\t".join(_TSV_HEADER)]
        lines += ["\t".join((e.old_id, e.thing_uri, e.np_uri)) for e in self._sorted()]
        return "\n".join(lines) + "\n"

    @classmethod
    def from_tsv(cls, text: str) -> "IdMap":
        id_map = cls()
        lines = [ln for ln in text.splitlines() if ln.strip()]
        for line in lines:
            fields = line.split("\t")
            if tuple(fields) == _TSV_HEADER:
                continue
            if len(fields) != 3:
                raise ValueError(f"expected 3 tab-separated fields, got {len(fields)}: {line!r}")
            id_map.add(IdMapEntry(*fields))
        return id_map

    def to_json(self) -> str:
        return json.dumps([asdict(e) for e in self._sorted()], indent=2) + "\n"

    @classmethod
    def from_json(cls, text: str) -> "IdMap":
        return cls(IdMapEntry(**row) for row in json.loads(text))

    def write_tsv(self, path: Union[str, Path]) -> None:
        Path(path).write_text(self.to_tsv(), encoding="utf-8")

    def write_json(self, path: Union[str, Path]) -> None:
        Path(path).write_text(self.to_json(), encoding="utf-8")

    @classmethod
    def read_tsv(cls, path: Union[str, Path]) -> "IdMap":
        return cls.from_tsv(Path(path).read_text(encoding="utf-8"))

    @classmethod
    def read_json(cls, path: Union[str, Path]) -> "IdMap":
        return cls.from_json(Path(path).read_text(encoding="utf-8"))
