"""Shared internals for building nanopublications (defining and superseding).

Private module: not part of the public API. Holds the construction bits common
to the defining-nanopub builder and the supersession builder so they stay in one
place.
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

import nanopub
import rdflib
from rdflib.namespace import DCTERMS, RDFS

from nanopub.namespaces import NPX

#: The nanopub-template ontology; ``nt:wasCreatedFromTemplate`` lets tools like
#: Nanodash render a nanopub with the form/labels of the template it follows.
NTEMPLATE = rdflib.Namespace("https://w3id.org/np/o/ntemplate/")

# Sentinel distinguishing "argument not given" (fall back to a default) from
# "explicitly given None" (suppress that piece of pubinfo).
UNSET: Any = object()

# ORCID used for the throwaway in-memory profile (see ephemeral_profile).
EPHEMERAL_ORCID = "https://orcid.org/0000-0000-0000-0000"


def _bnode_sort_key(graph: rdflib.Graph, bnode: rdflib.BNode) -> tuple:
    """A content-based key for a blank node, so relabeling is order-stable.

    Keys on the bnode's outgoing ``(predicate, object)`` pairs (nested blank
    objects contribute only their predicate), so the ordering does not depend on
    the source's random bnode ids. Bnodes with identical content sort equal —
    which is fine, since swapping their labels yields an isomorphic graph.
    """
    items = [
        (str(p), "" if isinstance(o, rdflib.BNode) else str(o))
        for p, o in graph.predicate_objects(bnode)
    ]
    return tuple(sorted(items))


def relabel_blank_nodes(graph: rdflib.Graph, *, prefix: str = "b") -> rdflib.Graph:
    """Rename blank nodes to short, deterministic labels (``b1``, ``b2``, …).

    nanopub-py turns each blank node into a ``sub:_<label>`` URI. With the
    source's long, per-parse-random anonymous-node ids that yields unreadable and
    non-reproducible suffixes (e.g. ``sub:_ndf301ab1d67…b1``). Relabeling to short
    content-ordered labels makes them ``sub:_b1`` / ``sub:_b2`` — readable and
    stable across runs. Returns the graph unchanged if it has no blank nodes.
    """
    bnodes = {n for triple in graph for n in triple if isinstance(n, rdflib.BNode)}
    if not bnodes:
        return graph
    ordered = sorted(bnodes, key=lambda b: _bnode_sort_key(graph, b))
    mapping: dict = {b: rdflib.BNode(f"{prefix}{i + 1}") for i, b in enumerate(ordered)}
    out = rdflib.Graph()
    for s, p, o in graph:
        out.add((mapping.get(s, s), p, mapping.get(o, o)))
    return out


def preferred_label(
    graph: rdflib.Graph,
    subject: rdflib.term.Node,
    predicate: rdflib.URIRef = RDFS.label,
) -> Optional[str]:
    """Pick the "regular" label for a term among several language variants.

    A term often carries an untagged label plus localized ones (e.g. ``"Lead"``
    and ``"Lood"@nl-be``). For the nanopub's own ``rdfs:label`` we want the
    canonical one, so prefer an **untagged** literal, then English, then any
    other (ties broken by text for determinism). Returns ``None`` if there is no
    literal label.
    """
    labels = [o for o in graph.objects(subject, predicate) if isinstance(o, rdflib.Literal)]
    if not labels:
        return None

    def rank(lit: rdflib.Literal) -> int:
        lang = (lit.language or "").lower()
        if not lang:
            return 0
        if lang == "en" or lang.startswith("en-"):
            return 1
        return 2

    return str(min(labels, key=lambda lit: (rank(lit), str(lit))))


def ephemeral_profile() -> nanopub.Profile:
    """An in-memory profile whose generated keys are never written to disk.

    Use it to build nanopubs for validation when no real signing key is on hand.
    """
    return nanopub.Profile(orcid_id=EPHEMERAL_ORCID, name="pubmate unsigned builder")


def build_conf(
    *,
    profile: nanopub.Profile,
    keyless: bool,
    test_server: bool,
    add_prov_generated_time: bool,
    suggester_orcid: Optional[str],
    derived_from: Optional[str],
) -> nanopub.NanopubConf:
    """Build a NanopubConf shared by the defining and supersession builders.

    The assertion is attributed to ``suggester_orcid`` (never the signer; passing
    both would raise). Publication is attributed to the profile only when a real
    profile was supplied, so an ephemeral keyless profile is not embedded.
    """
    return nanopub.NanopubConf(
        profile=profile,
        use_test_server=test_server,
        add_prov_generated_time=add_prov_generated_time,
        add_pubinfo_generated_time=True,
        assertion_attributed_to=suggester_orcid,
        attribute_assertion_to_profile=False,
        attribute_publication_to_profile=not keyless,
        derived_from=derived_from,
    )


def add_label_and_license(
    np: nanopub.Nanopub,
    *,
    np_ref: rdflib.term.Identifier,
    label: Optional[str],
    license: Optional[str],
) -> None:
    """Add optional ``rdfs:label`` and ``dct:license`` triples to pubinfo."""
    if label:
        np.pubinfo.add((np_ref, RDFS.label, rdflib.Literal(label)))
    if license:
        np.pubinfo.add((np_ref, DCTERMS.license, rdflib.URIRef(license)))


def add_pubinfo_tags(
    np: nanopub.Nanopub,
    *,
    np_ref: rdflib.term.Identifier,
    nanopub_types: Optional[Iterable[str]] = None,
    template: Optional[str] = None,
) -> None:
    """Add optional ``npx:hasNanopubType`` and ``nt:wasCreatedFromTemplate`` tags.

    Both are pubinfo hints consumers use to categorize and render the nanopub:
    ``hasNanopubType`` declares the kind(s) of thing it asserts (e.g. a
    ``BioChemEntity``); ``wasCreatedFromTemplate`` points at the assertion
    template it follows so Nanodash shows it with the matching form.
    """
    if nanopub_types:
        for nanopub_type in nanopub_types:
            np.pubinfo.add((np_ref, NPX.hasNanopubType, rdflib.URIRef(nanopub_type)))
    if template:
        np.pubinfo.add((np_ref, NTEMPLATE.wasCreatedFromTemplate, rdflib.URIRef(template)))
