"""Current definitions of vocabulary terms, as the network sees them.

Which nanopub defines a term *now* is decided by the vocabulary query, not by the
id-map: the newest nanopub that ``npx:introduces`` the term and is signed by a
member of a maintaining space wins, and it may have been published by someone
else (an edit in Nanodash, another bot's override). Updates must therefore build
on the definition the query returns:

* compare the submitted content against *that* assertion to tell an unchanged
  term from a changed one (instead of a fingerprint the id-map may lack or
  that may describe an outdated version), and
* link the update to *that* nanopub, with ``npx:supersedes`` when it was signed
  with the same key (only then does supersession take effect) and with
  ``prov:wasDerivedFrom`` otherwise (an override, as Nanodash does it).

:class:`QueryDefinitions` reads the vocabulary query (one request, the class and
nanopub columns) and fetches a term's defining nanopub only when that term is
processed. :class:`StaticDefinitions` serves a fixed set, for tests and offline
use.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Callable, Dict, Mapping, Optional, Protocol

import rdflib
from nanopub.namespaces import NPX

from pubmate.download import fetch_url
from pubmate.fingerprint import canonical_assertion

logger = logging.getLogger(__name__)

NP = rdflib.Namespace("http://www.nanopub.org/nschema#")


@dataclass(frozen=True)
class CurrentDefinition:
    """The nanopub that currently defines a term, per the vocabulary query.

    Attributes:
        thing_uri: the term's URI.
        np_uri: the defining nanopub's URI.
        assertion: its assertion, with the nanopub's blank-node URIs
            (``<np>/_b1``) turned back into blank nodes, so it compares equal to
            a freshly built assertion with the same content.
        public_key: the key it was signed with (``npx:hasPublicKey``), or ``""``.
    """

    thing_uri: str
    np_uri: str
    assertion: rdflib.Graph
    public_key: str = ""

    def same_content(self, assertion: rdflib.Graph) -> bool:
        """Whether ``assertion`` states exactly what this definition states."""
        return canonical_assertion(assertion) == canonical_assertion(self.assertion)


class CurrentDefinitions(Protocol):
    """Looks up a term's current definition; ``None`` if it has none (any more)."""

    def get(self, thing_uri: str) -> Optional[CurrentDefinition]: ...


def normalize_key(key: Optional[str]) -> str:
    """A public key without PEM header/footer and whitespace, for comparison."""
    if not key:
        return ""
    for marker in ("-----BEGIN PUBLIC KEY-----", "-----END PUBLIC KEY-----"):
        key = key.replace(marker, "")
    return "".join(key.split())


def _blank_node_prefixes(np_uri: str) -> tuple[str, ...]:
    base = np_uri.rstrip("/#")
    return (f"{base}/_", f"{base}#_")


def definition_from_trig(trig: str, *, thing_uri: str, np_uri: str) -> CurrentDefinition:
    """Read a defining nanopub (TriG) into a :class:`CurrentDefinition`."""
    dataset = rdflib.Dataset()
    dataset.parse(data=trig, format="trig")
    assertion_ids = {o for g in dataset.graphs() for o in g.objects(None, NP.hasAssertion)}
    if len(assertion_ids) != 1:
        raise ValueError(f"{np_uri}: expected one assertion graph, found {len(assertion_ids)}")
    source = dataset.graph(next(iter(assertion_ids)))

    prefixes = _blank_node_prefixes(np_uri)

    def unskolem(node):
        if isinstance(node, rdflib.URIRef):
            for prefix in prefixes:
                if str(node).startswith(prefix):
                    return rdflib.BNode(str(node)[len(prefix) :])
        return node

    assertion = rdflib.Graph()
    for s, p, o in source:
        assertion.add((unskolem(s), p, unskolem(o)))

    key = next((str(o) for g in dataset.graphs() for o in g.objects(None, NPX.hasPublicKey)), "")
    return CurrentDefinition(thing_uri=thing_uri, np_uri=np_uri, assertion=assertion, public_key=normalize_key(key))


class StaticDefinitions:
    """A fixed ``thing URI -> CurrentDefinition`` lookup."""

    def __init__(self, definitions: Mapping[str, CurrentDefinition] = ()):
        self._definitions: Dict[str, CurrentDefinition] = dict(definitions)

    def get(self, thing_uri: str) -> Optional[CurrentDefinition]:
        return self._definitions.get(thing_uri)


Fetcher = Callable[..., bytes]


class QueryDefinitions:
    """Current definitions from a vocabulary query (SPARQL-JSON API URL).

    The query must return one row per current term, with the term in
    ``class_column`` and its defining nanopub in ``np_column`` -- as the Nanodash
    vocabulary queries (e.g. ``get-approved-classes-of-an-ontology-from-space-members``)
    do. The query runs once, on first use; each nanopub is fetched (as
    ``<np>.trig``) only when its term is looked up.
    """

    def __init__(
        self,
        query_url: str,
        *,
        class_column: str = "class",
        np_column: str = "np",
        timeout: int = 120,
        retries: int = 3,
        fetch: Optional[Fetcher] = None,
    ):
        self.query_url = query_url
        self.class_column = class_column
        self.np_column = np_column
        self.timeout = timeout
        self.retries = retries
        self._fetch = fetch
        self._np_by_thing: Optional[Dict[str, str]] = None
        self._cache: Dict[str, Optional[CurrentDefinition]] = {}

    def _load(self) -> Dict[str, str]:
        if self._np_by_thing is None:
            payload = (self._fetch or fetch_url)(
                self.query_url,
                accept="application/sparql-results+json",
                timeout=self.timeout,
                retries=self.retries,
            )
            rows = json.loads(payload).get("results", {}).get("bindings", [])
            mapping: Dict[str, str] = {}
            for row in rows:
                thing = row.get(self.class_column, {}).get("value")
                np_uri = row.get(self.np_column, {}).get("value")
                if not thing or not np_uri:
                    continue
                if mapping.get(thing, np_uri) != np_uri:
                    raise RuntimeError(f"The vocabulary query returned two current definitions for {thing}.")
                mapping[thing] = np_uri
            if not mapping:
                raise RuntimeError(f"The vocabulary query returned no terms: {self.query_url}")
            logger.info("Vocabulary query: %d current term definition(s).", len(mapping))
            self._np_by_thing = mapping
        return self._np_by_thing

    def get(self, thing_uri: str) -> Optional[CurrentDefinition]:
        if thing_uri not in self._cache:
            np_uri = self._load().get(thing_uri)
            if np_uri is None:
                self._cache[thing_uri] = None
            else:
                trig = (self._fetch or fetch_url)(
                    f"{np_uri}.trig", accept="application/trig", timeout=self.timeout, retries=self.retries
                )
                self._cache[thing_uri] = definition_from_trig(trig.decode("utf-8"), thing_uri=thing_uri, np_uri=np_uri)
        return self._cache[thing_uri]
