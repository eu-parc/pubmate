import re

import pytest
import rdflib
from rdflib import Literal
from rdflib.namespace import RDF, RDFS

from nanopub.namespaces import NPX
from pubmate.defining import DEFAULT_LICENSE, DefiningNanopubBuilder
from pubmate.minting import SequentialMinter, TermInput
from pubmate.supersede import SupersessionBuilder

NAMESPACE = "https://example.org/terms/"
PROV = rdflib.Namespace("http://www.w3.org/ns/prov#")
PEH = rdflib.Namespace("https://example.org/pred/")
SUGGESTER = "https://orcid.org/0000-0002-1825-0097"
CODE_RE = re.compile(r"RA[A-Za-z0-9_\-]{40,}")


def _mint_two():
    """Mint two defining terms and return (minter outputs, builder)."""
    builder = DefiningNanopubBuilder(NAMESPACE)
    minter = SequentialMinter(builder)

    def term(tid, label):
        a = builder.make_assertion([(RDF.type, RDFS.Class), (RDFS.label, Literal(label))])
        return TermInput(term_id=tid, assertion=a, label=label)

    batch = minter.mint_all([term("a", "A"), term("b", "B")], dry_run=True)
    return batch


def test_build_requires_supersedes_uri():
    builder = SupersessionBuilder()
    g = rdflib.Graph()
    g.add((rdflib.URIRef(f"{NAMESPACE}RAxxx"), RDFS.label, Literal("x")))
    with pytest.raises(ValueError, match="supersedes_np_uri is required"):
        builder.build(g, supersedes_np_uri="")


def test_supersedes_triple_and_pubinfo():
    builder = SupersessionBuilder()
    thing = rdflib.URIRef(f"{NAMESPACE}RAexample")
    g = rdflib.Graph()
    g.add((thing, RDFS.label, Literal("A")))
    np = builder.build(
        g,
        supersedes_np_uri="https://w3id.org/np/RAoldnp",
        suggester_orcid=SUGGESTER,
        label="Updated A",
    )
    np_ref = np.metadata.namespace[""]
    assert (np_ref, NPX.supersedes, rdflib.URIRef("https://w3id.org/np/RAoldnp")) in np.pubinfo
    assert (np_ref, RDFS.label, Literal("Updated A")) in np.pubinfo
    assert (np_ref, rdflib.URIRef("http://purl.org/dc/terms/license"), rdflib.URIRef(DEFAULT_LICENSE)) in np.pubinfo
    assert (None, PROV.wasAttributedTo, rdflib.URIRef(SUGGESTER)) in np.provenance
    # No introduces by default for a supersession.
    assert (None, NPX.introduces, None) not in np.pubinfo


def test_supersession_tags_nanopub_type_and_template():
    ntemplate = rdflib.Namespace("https://w3id.org/np/o/ntemplate/")
    type_uri = "https://w3id.org/peh/terms/BioChemEntity"
    template_uri = "https://w3id.org/np/RAhSlIuuw5YqmMoyyvmy5GL3qIhs7sp14i6x2y3DCOhXM"
    builder = SupersessionBuilder(nanopub_types=[type_uri], template=template_uri)
    g = rdflib.Graph()
    g.add((rdflib.URIRef(f"{NAMESPACE}RAexample"), RDFS.label, Literal("A")))
    np = builder.build(g, supersedes_np_uri="https://w3id.org/np/RAoldnp")
    np_ref = np.metadata.namespace[""]
    assert (np_ref, NPX.hasNanopubType, rdflib.URIRef(type_uri)) in np.pubinfo
    assert (np_ref, ntemplate.wasCreatedFromTemplate, rdflib.URIRef(template_uri)) in np.pubinfo


def test_supersession_preserves_fixed_uris_when_signed():
    # Mint two real terms first, then supersede term A to add a link to term B.
    batch = _mint_two()
    a = batch.thing_uri_map["a"]
    b = batch.thing_uri_map["b"]
    a_np = batch.np_uri_map["a"]

    a_uri = rdflib.URIRef(a)
    b_uri = rdflib.URIRef(b)
    updated = rdflib.Graph()
    updated.add((a_uri, RDF.type, RDFS.Class))
    updated.add((a_uri, RDFS.label, Literal("A")))
    updated.add((a_uri, PEH.relatedTo, b_uri))  # the new cross-term link

    builder = SupersessionBuilder()  # keyless -> offline signing
    np = builder.build(updated, supersedes_np_uri=a_np, suggester_orcid=SUGGESTER)
    np.sign()

    serialized = np.rdf.serialize(format="trig")
    new_code = np.metadata.np_uri.rstrip("/").split("/")[-1]

    # Both fixed term URIs survive signing unchanged (only this nanopub's own
    # code is freshly minted, and it differs from the terms' codes).
    assert (a_uri, PEH.relatedTo, b_uri) in np.assertion
    assert a in serialized and b in serialized
    assert new_code not in (a.split("/")[-1], b.split("/")[-1])
    # The supersedes link points at term A's defining nanopub.
    assert (None, NPX.supersedes, rdflib.URIRef(a_np)) in np.pubinfo
