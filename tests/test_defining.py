import re

import rdflib
import pytest
from rdflib.namespace import DCTERMS, RDF, RDFS

from nanopub.definitions import ARTIFACTCODE_PLACEHOLDER
from nanopub.namespaces import NPX
from pubmate.defining import DEFAULT_LICENSE, DefiningNanopubBuilder

NAMESPACE = "https://w3id.org/peh/biochementities/"
PROV = rdflib.Namespace("http://www.w3.org/ns/prov#")
SKOS = rdflib.Namespace("http://www.w3.org/2004/02/skos/core#")
SUGGESTER = "https://orcid.org/0000-0002-1825-0097"


def _builder() -> DefiningNanopubBuilder:
    # Keyless: ephemeral in-memory profile, no network, no key files.
    return DefiningNanopubBuilder(NAMESPACE)


def _assertion(builder: DefiningNanopubBuilder) -> rdflib.Graph:
    return builder.make_assertion(
        [
            (RDF.type, SKOS.Concept),
            (RDFS.label, rdflib.Literal("Example term")),
        ]
    )


def test_thing_uri_carries_placeholder() -> None:
    builder = _builder()
    assert str(builder.thing_uri) == f"{NAMESPACE}{ARTIFACTCODE_PLACEHOLDER}"


def test_make_assertion_keys_on_thing_uri() -> None:
    builder = _builder()
    graph = _assertion(builder)
    subjects = set(graph.subjects())
    assert subjects == {builder.thing_uri}


def test_make_assertion_rejects_non_term_object() -> None:
    builder = _builder()
    with pytest.raises(TypeError):
        builder.make_assertion([(RDFS.label, "plain string is not a term")])


def test_build_rejects_empty_assertion() -> None:
    builder = _builder()
    with pytest.raises(ValueError, match="assertion graph is empty"):
        builder.build(rdflib.Graph())


def test_build_adds_pubinfo_and_attribution() -> None:
    builder = _builder()
    np = builder.build(
        _assertion(builder),
        suggester_orcid=SUGGESTER,
        label="Example term",
    )

    np_ref = np.metadata.namespace[""]

    # Default introduces points at the placeholder thing URI.
    assert (np_ref, NPX.introduces, builder.thing_uri) in np.pubinfo
    assert (np_ref, RDFS.label, rdflib.Literal("Example term")) in np.pubinfo
    assert (np_ref, DCTERMS.license, rdflib.URIRef(DEFAULT_LICENSE)) in np.pubinfo

    # Assertion attributed to the suggester (not the signer/profile).
    assert (None, PROV.wasAttributedTo, rdflib.URIRef(SUGGESTER)) in np.provenance


def test_build_can_suppress_license_and_introduces() -> None:
    builder = _builder()
    np = builder.build(_assertion(builder), license=None, introduces=None)

    assert (None, NPX.introduces, None) not in np.pubinfo
    assert (None, DCTERMS.license, None) not in np.pubinfo


NTEMPLATE = rdflib.Namespace("https://w3id.org/np/o/ntemplate/")
TYPE_URI = "https://w3id.org/peh/terms/BioChemEntity"
TEMPLATE_URI = "https://w3id.org/np/RAhSlIuuw5YqmMoyyvmy5GL3qIhs7sp14i6x2y3DCOhXM"


def test_build_tags_nanopub_type_and_template() -> None:
    builder = DefiningNanopubBuilder(NAMESPACE, nanopub_types=[TYPE_URI], template=TEMPLATE_URI)
    np = builder.build(_assertion(builder))
    np_ref = np.metadata.namespace[""]

    assert (np_ref, NPX.hasNanopubType, rdflib.URIRef(TYPE_URI)) in np.pubinfo
    assert (np_ref, NTEMPLATE.wasCreatedFromTemplate, rdflib.URIRef(TEMPLATE_URI)) in np.pubinfo


def test_build_omits_tags_by_default() -> None:
    np = _builder().build(_assertion(_builder()))

    assert (None, NPX.hasNanopubType, None) not in np.pubinfo
    assert (None, NTEMPLATE.wasCreatedFromTemplate, None) not in np.pubinfo


def test_sign_substitutes_placeholder_with_artifact_code() -> None:
    # The ephemeral profile holds in-memory RSA keys, so signing works offline.
    builder = _builder()
    np = builder.build(_assertion(builder), suggester_orcid=SUGGESTER, label="Example term")
    np.sign()

    np_uri = str(np.metadata.np_uri)
    code_match = re.search(r"RA[A-Za-z0-9_\-]{40,}", np_uri)
    assert code_match, f"no artifact code in signed nanopub URI: {np_uri}"
    code = code_match.group(0)

    serialized = np.rdf.serialize(format="trig")
    assert ARTIFACTCODE_PLACEHOLDER not in serialized

    # Artifact code lands on the thing URI in our namespace (scheme A).
    expected_thing_uri = rdflib.URIRef(f"{NAMESPACE}{code}")
    assert (expected_thing_uri, None, None) in np.assertion
    assert (None, NPX.introduces, expected_thing_uri) in np.pubinfo


def test_blank_nodes_get_short_deterministic_labels():
    """Blank nodes serialize as sub:_b1/_b2, not the source's long random ids."""
    builder = _builder()
    schema = rdflib.Namespace("http://schema.org/")
    g = builder.make_assertion([(RDFS.label, rdflib.Literal("x"))])
    subj = builder.thing_uri
    ctx = rdflib.BNode("ndf301ab1d6704b938f61a317a7631d20b1")  # long source-style id
    g.add((subj, NPX.declaredBy, ctx))  # any predicate -> bnode object
    g.add((ctx, schema.identifier, rdflib.Literal("short_name")))
    np = builder.build(g)
    np.sign()
    trig = np.rdf.serialize(format="trig")
    assert "ndf301ab1d6704b938f61a317a7631d20b1" not in trig
    assert "_b1" in trig


def test_blank_node_relabel_is_isomorphic_and_stable():
    """Differently-labeled isomorphic graphs relabel to the same b1 graph."""
    from pubmate._nanopub_build import relabel_blank_nodes

    schema = rdflib.Namespace("http://schema.org/")
    subj = rdflib.URIRef(NAMESPACE + "x")

    def make(bid):
        g = rdflib.Graph()
        b = rdflib.BNode(bid)
        g.add((subj, NPX.declaredBy, b))
        g.add((b, schema.identifier, rdflib.Literal("short_name")))
        return g

    r1, r2 = relabel_blank_nodes(make("nAAA")), relabel_blank_nodes(make("nBBB"))
    # the source bnode id no longer matters -> identical (isomorphic) graphs
    assert set(r1) == set(r2)
    assert {str(n) for t in r1 for n in t if isinstance(n, rdflib.BNode)} == {"b1"}
