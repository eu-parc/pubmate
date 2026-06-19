"""Utility helpers for pubmate."""

from __future__ import annotations

import pathlib

import nanopub
import rdflib


def load_nanopub_assertion(path: str | pathlib.Path) -> rdflib.Graph:
    """Load a nanopublication ``.trig`` file and return its assertion graph.

    Thin wrapper over nanopub-py: ``Nanopub(rdf=...).assertion`` is the assertion
    named graph as an :class:`rdflib.Graph`, which serializes to plain Turtle
    (with the right prefixes) on its own. Useful for downstream consumers that
    read assertions only — e.g. the vocabulary-browser site, which cannot parse
    the four-graph ``.trig`` itself.
    """
    return nanopub.Nanopub(rdf=pathlib.Path(path)).assertion


def serialize_nanopub(np: nanopub.Nanopub) -> str:
    """Serialize a nanopub to TriG with graphs in canonical order.

    rdflib's TriG serializer emits named graphs in arbitrary store-iteration
    order. The nanopublication convention (and the Java tooling) presents the
    four graphs as Head, assertion, provenance, pubinfo. This produces that
    order with a single deduplicated, sorted prefix block and only the prefixes
    actually used — for human-readable, diff-friendly ``.trig`` output.

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

    prefixes: set[str] = set()
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
                prefixes.add(stripped)
            elif stripped:
                body.append("    " + line.rstrip())

        blocks.append(f"{graph_id.n3(namespace_manager)} {{\n" + "\n".join(body) + "\n}")

    header = "\n".join(sorted(prefixes))
    return f"{header}\n\n" + "\n\n".join(blocks) + "\n"
