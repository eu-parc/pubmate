"""Utility helpers for pubmate."""

from __future__ import annotations

import pathlib
from typing import Mapping, Optional

import nanopub
import rdflib

#: Curated prefix bindings applied when rendering nanopubs, so common
#: namespaces show as meaningful prefixes (``schema:``, ``pehterms:``, …) rather
#: than rdflib's auto-numbered ``ns1:``/``ns2:``. nanopub-py already binds the
#: nanopub-machinery prefixes (np, npx, this, sub, orcid, …); these cover the
#: vocabulary side. Callers can extend/override via ``serialize_nanopub``.
WELL_KNOWN_PREFIXES: dict[str, str] = {
    "schema": "http://schema.org/",
    "obo": "http://purl.obolibrary.org/obo/",
    "skos": "http://www.w3.org/2004/02/skos/core#",
    "prov": "http://www.w3.org/ns/prov#",
    "dcterms": "http://purl.org/dc/terms/",
    "foaf": "http://xmlns.com/foaf/0.1/",
    "frbr": "http://purl.org/vocab/frbr/core#",
    "nt": "https://w3id.org/np/o/ntemplate/",
    # PEH vocabulary (see schema/peh.yaml in biochementity-vocabulary)
    "pehterms": "https://w3id.org/peh/terms/",
    "biochementity": "https://w3id.org/peh/biochementities/",
}

#: Prefixes pinned to the top of the header, in this order; the rest follow
#: alphabetically. ``this:`` (the nanopub) and ``sub:`` (its sub-graphs) anchor
#: every nanopub, so leading with them makes the structure read top-down.
_LEADING_PREFIXES = ("this", "sub")


def load_nanopub_assertion(path: str | pathlib.Path) -> rdflib.Graph:
    """Load a nanopublication ``.trig`` file and return its assertion graph.

    Thin wrapper over nanopub-py: ``Nanopub(rdf=...).assertion`` is the assertion
    named graph as an :class:`rdflib.Graph`, which serializes to plain Turtle
    (with the right prefixes) on its own. Useful for downstream consumers that
    read assertions only — e.g. the vocabulary-browser site, which cannot parse
    the four-graph ``.trig`` itself.
    """
    return nanopub.Nanopub(rdf=pathlib.Path(path)).assertion


def _prefix_sort_key(line: str) -> tuple[int, str]:
    """Sort key for ``@prefix`` lines: leading prefixes first, then alphabetical."""
    name = line.split(None, 2)[1].rstrip(":")  # "@prefix this: <...> ." -> "this"
    order = _LEADING_PREFIXES.index(name) if name in _LEADING_PREFIXES else len(_LEADING_PREFIXES)
    return (order, name)


def serialize_nanopub(np: nanopub.Nanopub, *, prefixes: Optional[Mapping[str, str]] = None) -> str:
    """Serialize a nanopub to TriG with graphs in canonical order.

    rdflib's TriG serializer emits named graphs in arbitrary store-iteration
    order. The nanopublication convention (and the Java tooling) presents the
    four graphs as Head, assertion, provenance, pubinfo. This produces that
    order with a single deduplicated prefix block (``this:``/``sub:`` first, the
    rest alphabetical) and only the prefixes actually used — for human-readable,
    diff-friendly ``.trig`` output.

    Args:
        prefixes: extra/override prefix bindings merged over
            :data:`WELL_KNOWN_PREFIXES` (so the common vocabulary namespaces
            render as meaningful prefixes instead of ``ns1:``/``ns2:``).

    The order is resolved from the Head graph: ``np.metadata`` is populated by
    nanopub-py by following ``np:hasAssertion`` / ``np:hasProvenance`` /
    ``np:hasPublicationInfo`` out of the graph that declares the nanopub, so this
    is data-driven rather than relying on graph names (a plain ASCII sort of the
    graph URIs happens to match only because "Head" is capitalized — fragile).

    Graph *order* carries no RDF semantics (named graphs are an unordered set),
    so the result is equivalent to ``np.rdf.serialize(format="trig")``; it is
    purely a nicer rendering.
    """
    dataset = np.rdf
    namespace_manager = dataset.namespace_manager
    metadata = np.metadata

    # Bind meaningful prefixes so the serializer never falls back to ns1:/ns2:.
    for prefix, uri in {**WELL_KNOWN_PREFIXES, **(prefixes or {})}.items():
        namespace_manager.bind(prefix, rdflib.Namespace(uri), override=True, replace=True)

    prefix_lines: set[str] = set()
    blocks: list[str] = []
    for graph_id in (metadata.head, metadata.assertion, metadata.provenance, metadata.pubinfo):
        # Per-graph turtle gives us correct prefix detection (only used ones) and
        # rdflib's predicate-object grouping; we re-indent it under the graph block.
        graph = rdflib.Graph(identifier=graph_id)
        graph.namespace_manager = namespace_manager
        for triple in dataset.get_context(graph_id):
            graph.add(triple)

        body: list[str] = []
        for line in graph.serialize(format="turtle").splitlines():
            stripped = line.strip()
            if stripped.startswith("@prefix"):
                prefix_lines.add(stripped)
            elif stripped:
                body.append("    " + line.rstrip())

        blocks.append(f"{graph_id.n3(namespace_manager)} {{\n" + "\n".join(body) + "\n}")

    header = "\n".join(sorted(prefix_lines, key=_prefix_sort_key))
    return f"{header}\n\n" + "\n\n".join(blocks) + "\n"
