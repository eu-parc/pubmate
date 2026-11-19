import json

import pytest
import rdflib
from rdflib import Literal
from rdflib.namespace import RDF, RDFS

from pubmate.current import QueryDefinitions, definition_from_trig, normalize_key
from pubmate.defining import DefiningNanopubBuilder
from pubmate.minting import SequentialMinter, TermInput
from pubmate.utils import serialize_nanopub

NAMESPACE = "https://example.org/terms/"
EX = rdflib.Namespace("https://example.org/pred/")


def _minted_with_blank_node():
    builder = DefiningNanopubBuilder(NAMESPACE)
    alias = rdflib.BNode()
    assertion = builder.make_assertion([(RDF.type, RDFS.Class), (RDFS.label, Literal("Alpha")), (EX.alias, alias)])
    assertion.add((alias, EX.name, Literal("a")))
    minted = SequentialMinter(builder).mint(TermInput(term_id="alpha", assertion=assertion), dry_run=True)
    return builder, minted


def test_definition_from_trig_reads_assertion_and_key():
    builder, minted = _minted_with_blank_node()
    trig = serialize_nanopub(minted.nanopub)

    definition = definition_from_trig(trig, thing_uri=minted.thing_uri, np_uri=minted.np_uri)

    assert definition.np_uri == minted.np_uri
    assert definition.public_key == normalize_key(builder.profile.public_key) != ""
    thing = rdflib.URIRef(minted.thing_uri)
    assert (thing, RDFS.label, Literal("Alpha")) in definition.assertion
    # The nanopub's <np>/_b1 URI is a blank node again...
    (alias,) = definition.assertion.objects(thing, EX.alias)
    assert isinstance(alias, rdflib.BNode)
    # ...so the same content, freshly built with a blank node, compares equal.
    fresh = rdflib.Graph()
    fresh_alias = rdflib.BNode()
    fresh += [
        (thing, RDF.type, RDFS.Class),
        (thing, RDFS.label, Literal("Alpha")),
        (thing, EX.alias, fresh_alias),
        (fresh_alias, EX.name, Literal("a")),
    ]
    assert definition.same_content(fresh)
    fresh.add((thing, RDFS.comment, Literal("changed")))
    assert not definition.same_content(fresh)


def test_normalize_key_strips_pem_and_whitespace():
    assert normalize_key("-----BEGIN PUBLIC KEY-----\nAB\nCD\n-----END PUBLIC KEY-----\n") == "ABCD"
    assert normalize_key(None) == ""


class _FakeNetwork:
    def __init__(self, rows, trigs):
        self.rows = rows
        self.trigs = trigs
        self.calls = []

    def __call__(self, url, *, accept, timeout, retries):
        self.calls.append(url)
        if url.endswith(".trig"):
            return self.trigs[url[: -len(".trig")]].encode("utf-8")
        return json.dumps({"results": {"bindings": self.rows}}).encode("utf-8")


def _row(thing, np_uri):
    return {"class": {"type": "uri", "value": thing}, "np": {"type": "uri", "value": np_uri}}


def test_query_definitions_runs_query_once_and_fetches_lazily():
    _, minted = _minted_with_blank_node()
    network = _FakeNetwork(
        rows=[_row(minted.thing_uri, minted.np_uri), _row(f"{NAMESPACE}RAother", "https://w3id.org/np/RAother")],
        trigs={minted.np_uri: serialize_nanopub(minted.nanopub)},
    )
    current = QueryDefinitions("https://query.example/api/vocab", fetch=network)

    first = current.get(minted.thing_uri)
    again = current.get(minted.thing_uri)
    missing = current.get(f"{NAMESPACE}RAnotthere")

    assert first is again and first.np_uri == minted.np_uri
    assert missing is None
    # One query, one nanopub download; the other term is never fetched.
    assert network.calls == ["https://query.example/api/vocab", f"{minted.np_uri}.trig"]


def test_query_definitions_rejects_conflicting_or_empty_results():
    thing = f"{NAMESPACE}RAx"
    conflicting = _FakeNetwork(
        rows=[_row(thing, "https://w3id.org/np/RA1"), _row(thing, "https://w3id.org/np/RA2")], trigs={}
    )
    with pytest.raises(RuntimeError, match="two current definitions"):
        QueryDefinitions("https://query.example/api/vocab", fetch=conflicting).get(thing)
    with pytest.raises(RuntimeError, match="no terms"):
        QueryDefinitions("https://query.example/api/vocab", fetch=_FakeNetwork(rows=[], trigs={})).get(thing)
