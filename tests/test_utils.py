import rdflib
from rdflib import Literal
from rdflib.namespace import RDF, RDFS

from pubmate.defining import DefiningNanopubBuilder
from pubmate.utils import serialize_nanopub

NAMESPACE = "https://w3id.org/peh/biochementities/"
SUGGESTER = "https://orcid.org/0000-0002-1825-0097"
CANONICAL_ORDER = ["head", "assertion", "provenance", "pubinfo"]


def _nanopub():
    builder = DefiningNanopubBuilder(NAMESPACE)
    assertion = builder.make_assertion(
        [(RDF.type, RDFS.Class), (RDFS.label, Literal("Caffeine"))]
    )
    return builder.build(assertion, suggester_orcid=SUGGESTER, label="Definition of Caffeine")


def _graph_block_order(trig: str) -> list[str]:
    order = []
    for line in trig.splitlines():
        stripped = line.strip()
        if not stripped.endswith("{"):
            continue
        # Graph label, e.g. "<http://purl.org/nanopub/temp/np/Head> {" or "sub:Head {".
        label = stripped[:-1].strip().strip("<>").rstrip("/").lower()
        for name in CANONICAL_ORDER:
            if label.endswith(name):
                order.append(name)
                break
    return order


def test_graphs_in_canonical_order():
    trig = serialize_nanopub(_nanopub())
    assert _graph_block_order(trig) == list(CANONICAL_ORDER)


def test_only_used_prefixes_emitted():
    trig = serialize_nanopub(_nanopub())
    # rdflib binds dozens of default prefixes; the pruned output must not carry
    # ones the nanopub never uses.
    assert "@prefix brick:" not in trig
    assert "@prefix foaf:" not in trig
    # ...but must declare the ones it does use.
    assert "@prefix npx:" in trig
    assert "@prefix prov:" in trig


def test_roundtrips_to_same_graph():
    np = _nanopub()
    ordered = serialize_nanopub(np)
    reparsed = rdflib.Dataset()
    reparsed.parse(data=ordered, format="trig")
    # Same set of quads as the original dataset (order is non-semantic).
    assert set(reparsed.quads()) == set(np.rdf.quads())


def test_works_after_signing():
    np = _nanopub()
    np.sign()
    trig = serialize_nanopub(np)
    assert _graph_block_order(trig) == list(CANONICAL_ORDER)
    assert "~~~ARTIFACTCODE~~~" not in trig
