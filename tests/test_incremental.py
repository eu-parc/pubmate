import rdflib
from rdflib import Literal
from rdflib.namespace import PROV, RDF, RDFS

from nanopub.namespaces import NPX
from pubmate._nanopub_build import ephemeral_profile
from pubmate.current import StaticDefinitions, definition_from_trig
from pubmate.defining import DefiningNanopubBuilder
from pubmate.idmap import IdMap, IdMapEntry
from pubmate.incremental import publish_incremental
from pubmate.minting import SequentialMinter, TermInput
from pubmate.supersede import SupersessionBuilder
from pubmate.utils import serialize_nanopub

NAMESPACE = "https://example.org/terms/"
TPL_OLD = "https://w3id.org/np/RAtemplateOld"
TPL_NEW = "https://w3id.org/np/RAtemplateNew"
REL = rdflib.URIRef("https://example.org/rel/isMetaboliteOf")


def _minter() -> SequentialMinter:
    return SequentialMinter(DefiningNanopubBuilder(NAMESPACE))


def _sup() -> SupersessionBuilder:
    return SupersessionBuilder()


def _wrapped(template):
    builder = DefiningNanopubBuilder(NAMESPACE, template=template)
    return SequentialMinter(builder), SupersessionBuilder(template=template)


def _term(term_id: str, label: str) -> TermInput:
    builder = DefiningNanopubBuilder(NAMESPACE)
    assertion = builder.make_assertion([(RDF.type, RDFS.Class), (RDFS.label, Literal(label))])
    return TermInput(term_id=term_id, assertion=assertion, label=label)


def _term_ref(term_uri: str, label: str, ref_uri: str | None = None) -> TermInput:
    builder = DefiningNanopubBuilder(NAMESPACE)
    stmts = [(RDF.type, RDFS.Class), (RDFS.label, Literal(label))]
    if ref_uri:
        stmts.append((REL, rdflib.URIRef(ref_uri)))
    return TermInput(term_id=term_uri, assertion=builder.make_assertion(stmts), label=label)


def _run(terms, existing=None):
    return publish_incremental(
        terms,
        minter=_minter(),
        supersession_builder=_sup(),
        existing=existing or IdMap(),
        dry_run=True,
    )


def test_new_term_is_minted_and_records_fingerprint():
    result = _run([_term("alpha", "Alpha")])
    assert [m.term_id for m in result.minted.terms] == ["alpha"]
    assert result.superseded == []
    entry = result.id_map["alpha"]
    assert entry.thing_uri.startswith(f"{NAMESPACE}RA")
    assert entry.np_uri.startswith("https://w3id.org/np/RA")
    assert entry.fingerprint != ""


def test_new_trusty_term_is_published_without_reminting_thing_uri():
    thing = f"{NAMESPACE}RA" + ("a" * 41)

    result = _run([_term(thing, "Alpha")])

    assert result.superseded == []
    assert [m.term_id for m in result.minted.terms] == [thing]
    minted = result.minted.terms[0]
    assert minted.thing_uri == thing
    assert minted.np_uri.startswith("https://w3id.org/np/RA")
    assert rdflib.URIRef(thing) in set(minted.nanopub.assertion.subjects())
    assert rdflib.URIRef(f"{NAMESPACE}RA") not in set(minted.nanopub.assertion.subjects())

    entry = result.id_map[thing]
    assert entry.thing_uri == thing
    assert entry.np_uri == minted.np_uri
    assert entry.fingerprint != ""


def test_new_trusty_term_rerun_is_skipped():
    thing = f"{NAMESPACE}RA" + ("a" * 41)
    first = _run([_term(thing, "Alpha")])

    again = _run([_term(thing, "Alpha")], existing=first.id_map)

    assert again.minted.terms == []
    assert again.superseded == []
    assert again.skipped == [thing]
    assert again.id_map[thing] == first.id_map[thing]


def test_unchanged_term_is_skipped():
    first = _run([_term("alpha", "Alpha")])
    again = _run([_term("alpha", "Alpha")], existing=first.id_map)
    assert again.minted.terms == []
    assert again.superseded == []
    assert again.skipped == ["alpha"]
    # id-map entry carried forward untouched.
    assert again.id_map["alpha"] == first.id_map["alpha"]


def test_drifted_term_is_superseded_keeping_thing_uri():
    first = _run([_term("alpha", "Alpha")])
    before = first.id_map["alpha"]

    drifted = _run([_term("alpha", "Alpha (edited)")], existing=first.id_map)

    assert drifted.minted.terms == []
    assert [s.term_id for s in drifted.superseded] == ["alpha"]
    sup = drifted.superseded[0]
    # The new nanopub supersedes the recorded one...
    assert sup.supersedes_np_uri == before.np_uri
    assert (None, NPX.supersedes, rdflib.URIRef(before.np_uri)) in sup.nanopub.pubinfo
    # ...introduces the term, so the vocabulary queries keep listing it (#17)...
    assert (None, NPX.introduces, rdflib.URIRef(before.thing_uri)) in sup.nanopub.pubinfo
    assert sup.kind == "supersede"
    # ...and is written against the term's fixed, unchanged thing URI.
    assert rdflib.URIRef(before.thing_uri) in set(sup.nanopub.assertion.subjects())

    after = drifted.id_map["alpha"]
    assert after.thing_uri == before.thing_uri  # identity preserved
    assert after.np_uri == sup.np_uri != before.np_uri  # version advanced
    assert after.fingerprint != before.fingerprint  # fingerprint updated


def test_legacy_entry_without_fingerprint_is_backfilled_not_superseded():
    legacy = IdMap([IdMapEntry("alpha", f"{NAMESPACE}RAseed", "https://w3id.org/np/RAseed", "")])
    result = _run([_term("alpha", "Alpha")], existing=legacy)
    assert result.minted.terms == []
    assert result.superseded == []
    assert result.skipped == ["alpha"]
    entry = result.id_map["alpha"]
    # URIs untouched (no re-issue), fingerprint adopted as baseline.
    assert entry.thing_uri == f"{NAMESPACE}RAseed"
    assert entry.np_uri == "https://w3id.org/np/RAseed"
    assert entry.fingerprint != ""


def test_supersede_resolves_interterm_reference_to_new_thing_uri():
    A, B = NAMESPACE + "a", NAMESPACE + "b"
    minter1, sup1 = _wrapped(TPL_OLD)
    first = publish_incremental(
        [_term_ref(A, "Alpha", ref_uri=B), _term_ref(B, "Beta")],
        minter=minter1,
        supersession_builder=sup1,
        existing=IdMap(),
        dry_run=True,
    )
    thing_a = first.id_map[A].thing_uri
    thing_b = first.id_map[B].thing_uri

    # Change the template -> both drift -> both superseded.
    minter2, sup2 = _wrapped(TPL_NEW)
    result = publish_incremental(
        [_term_ref(A, "Alpha", ref_uri=B), _term_ref(B, "Beta")],
        minter=minter2,
        supersession_builder=sup2,
        existing=first.id_map,
        dry_run=True,
    )
    sup_a = next(s for s in result.superseded if s.term_id == A)
    objs = set(sup_a.nanopub.assertion.objects(rdflib.URIRef(thing_a), REL))
    # The reference now points at b's NEW thing URI, not the old-id.
    assert objs == {rdflib.URIRef(thing_b)}
    assert rdflib.URIRef(B) not in set(sup_a.nanopub.assertion.objects())


def test_resubmission_under_thing_uri_unchanged_is_skipped():
    first = _run([_term("alpha", "Alpha")])
    thing = first.id_map["alpha"].thing_uri

    again = _run([_term(thing, "Alpha")], existing=first.id_map)

    assert again.minted.terms == []
    assert again.superseded == []
    assert again.skipped == ["alpha"]
    # Still a single row, keyed by the original old id, untouched.
    assert len(again.id_map) == 1
    assert again.id_map["alpha"] == first.id_map["alpha"]


def test_resubmission_under_thing_uri_drifted_is_superseded_not_reminted():
    first = _run([_term("alpha", "Alpha")])
    before = first.id_map["alpha"]

    drifted = _run([_term(before.thing_uri, "Alpha (edited)")], existing=first.id_map)

    # The issue-#10 scenario: no duplicate term, a superseding nanopub instead.
    assert drifted.minted.terms == []
    assert [s.term_id for s in drifted.superseded] == ["alpha"]
    sup = drifted.superseded[0]
    assert sup.supersedes_np_uri == before.np_uri
    assert (None, NPX.supersedes, rdflib.URIRef(before.np_uri)) in sup.nanopub.pubinfo
    assert rdflib.URIRef(before.thing_uri) in set(sup.nanopub.assertion.subjects())
    # Single row, keyed by the original old id; identity kept, version advanced.
    assert len(drifted.id_map) == 1
    after = drifted.id_map["alpha"]
    assert after.thing_uri == before.thing_uri
    assert after.np_uri == sup.np_uri != before.np_uri


def test_supersede_keeps_references_already_given_as_thing_uris():
    A, B = NAMESPACE + "a", NAMESPACE + "b"
    first = _run([_term_ref(A, "Alpha", ref_uri=B), _term_ref(B, "Beta")])
    thing_a = first.id_map[A].thing_uri
    thing_b = first.id_map[B].thing_uri

    # Re-submit a drifted alpha under its thing URI, referencing beta by *its*
    # thing URI -- neither reference form may be dropped as dangling.
    result = _run(
        [_term_ref(thing_a, "Alpha (edited)", ref_uri=thing_b)],
        existing=first.id_map,
    )
    assert [s.term_id for s in result.superseded] == [A]
    objs = set(result.superseded[0].nanopub.assertion.objects(rdflib.URIRef(thing_a), REL))
    assert objs == {rdflib.URIRef(thing_b)}


def test_mixed_batch_mints_skips_and_supersedes():
    first = _run([_term("keep", "Keep"), _term("edit", "Edit")])
    batch = [
        _term("keep", "Keep"),  # unchanged
        _term("edit", "Edit (edited)"),  # drifted
        _term("new", "New"),  # new
    ]
    result = _run(batch, existing=first.id_map)
    assert [m.term_id for m in result.minted.terms] == ["new"]
    assert [s.term_id for s in result.superseded] == ["edit"]
    assert result.skipped == ["keep"]
    assert set(result.id_map.fingerprint_map) == {"keep", "edit", "new"}


# -- with current definitions from the network --------------------------------


def _current(*nanopubs_by_thing):
    """StaticDefinitions from (thing_uri, np_uri, nanopub) triples, read back from TriG."""
    return StaticDefinitions(
        {
            thing: definition_from_trig(serialize_nanopub(np), thing_uri=thing, np_uri=np_uri)
            for thing, np_uri, np in nanopubs_by_thing
        }
    )


def _published(term_id="alpha", label="Alpha", minter=None):
    """Mint a term (dry run) as it would be on the network; return (row, current)."""
    result = publish_incremental(
        [_term(term_id, label)],
        minter=minter or _minter(),
        supersession_builder=_sup(),
        existing=IdMap(),
        dry_run=True,
    )
    minted = result.minted.terms[0]
    return result.id_map[term_id], _current((minted.thing_uri, minted.np_uri, minted.nanopub))


def _run_current(terms, existing, current, minter=None, sup=None):
    return publish_incremental(
        terms,
        minter=minter or _minter(),
        supersession_builder=sup or _sup(),
        existing=existing,
        dry_run=True,
        current=current,
    )


def test_row_without_fingerprint_unchanged_is_skipped_and_baseline_verified():
    row, current = _published()
    legacy = IdMap([IdMapEntry(row.old_id, row.thing_uri, row.np_uri, "")])

    result = _run_current([_term("alpha", "Alpha")], legacy, current)

    assert result.minted.terms == [] and result.superseded == []
    assert result.skipped == ["alpha"]
    assert result.id_map["alpha"].fingerprint == row.fingerprint


def test_row_without_fingerprint_changed_is_updated_not_dropped():
    # #54, first gap: a changed submission for a row without fingerprint used to
    # be recorded as published without being published.
    row, current = _published()
    legacy = IdMap([IdMapEntry(row.old_id, row.thing_uri, row.np_uri, "")])

    result = _run_current([_term("alpha", "Alpha (edited)")], legacy, current)

    assert [s.term_id for s in result.superseded] == ["alpha"]
    sup = result.superseded[0].nanopub
    assert (None, RDFS.label, Literal("Alpha (edited)")) in sup.assertion
    assert (None, NPX.introduces, rdflib.URIRef(row.thing_uri)) in sup.pubinfo
    assert result.id_map["alpha"].np_uri == result.superseded[0].np_uri


def test_update_overrides_current_definition_signed_with_another_key():
    row, current = _published()
    # The id-map is stale: the network has a newer definition (here: the same one,
    # under its real URI) than the row records.
    stale = IdMap([IdMapEntry(row.old_id, row.thing_uri, "https://w3id.org/np/RAstale", row.fingerprint)])

    result = _run_current([_term("alpha", "Alpha (edited)")], stale, current)

    (sup,) = result.superseded
    assert sup.kind == "override"
    assert sup.supersedes_np_uri == row.np_uri  # the current definition, not the stale row
    assert (None, PROV.wasDerivedFrom, rdflib.URIRef(row.np_uri)) in sup.nanopub.pubinfo
    assert (None, NPX.supersedes, None) not in sup.nanopub.pubinfo
    assert (None, NPX.introduces, rdflib.URIRef(row.thing_uri)) in sup.nanopub.pubinfo


def test_update_supersedes_current_definition_signed_with_the_same_key():
    profile = ephemeral_profile()
    minter = SequentialMinter(DefiningNanopubBuilder(NAMESPACE, profile=profile))
    sup_builder = SupersessionBuilder(profile=profile)
    row, current = _published(minter=minter)

    result = _run_current([_term("alpha", "Alpha (edited)")], IdMap([row]), current, minter=minter, sup=sup_builder)

    (sup,) = result.superseded
    assert sup.kind == "supersede"
    assert (None, NPX.supersedes, rdflib.URIRef(row.np_uri)) in sup.nanopub.pubinfo
    assert (None, NPX.introduces, rdflib.URIRef(row.thing_uri)) in sup.nanopub.pubinfo


def test_minted_uri_without_row_updates_its_current_definition():
    # #54, second gap: a term submitted under its minted URI with no id-map row
    # got a second, unlinked definition.
    row, current = _published()

    same = _run_current([_term(row.thing_uri, "Alpha")], IdMap(), current)
    changed = _run_current([_term(row.thing_uri, "Alpha (edited)")], IdMap(), current)

    assert same.minted.terms == [] and same.superseded == []
    assert same.skipped == [row.thing_uri]
    assert same.id_map[row.thing_uri].np_uri == row.np_uri
    assert changed.minted.terms == []
    (sup,) = changed.superseded
    assert (None, PROV.wasDerivedFrom, rdflib.URIRef(row.np_uri)) in sup.nanopub.pubinfo


def test_term_without_current_definition_is_republished():
    # E.g. withdrawn in the meantime: re-submitting it publishes it again.
    row, _ = _published()

    result = _run_current([_term("alpha", "Alpha")], IdMap([row]), StaticDefinitions())

    (sup,) = result.superseded
    assert sup.kind == "override"
    assert (None, PROV.wasDerivedFrom, rdflib.URIRef(row.np_uri)) in sup.nanopub.pubinfo
    assert (None, NPX.introduces, rdflib.URIRef(row.thing_uri)) in sup.nanopub.pubinfo


def test_blank_nodes_in_the_current_definition_compare_equal():
    builder = DefiningNanopubBuilder(NAMESPACE)

    def term():
        alias = rdflib.BNode()
        g = builder.make_assertion([(RDF.type, RDFS.Class), (RDFS.label, Literal("Alpha")), (REL, alias)])
        g.add((alias, RDFS.label, Literal("a")))
        return TermInput(term_id="alpha", assertion=g, label="Alpha")

    first = publish_incremental([term()], minter=_minter(), supersession_builder=_sup(), existing=IdMap())
    minted = first.minted.terms[0]
    current = _current((minted.thing_uri, minted.np_uri, minted.nanopub))

    result = _run_current([term()], first.id_map, current)

    assert result.superseded == [] and result.skipped == ["alpha"]


def test_update_warns_when_it_drops_a_property_entirely(caplog):
    row, current = _published()
    builder = DefiningNanopubBuilder(NAMESPACE)
    # The resubmission has no rdf:type at all (e.g. a lossy export was edited).
    only_label = builder.make_assertion([(RDFS.label, Literal("Alpha (edited)"))])

    with caplog.at_level("WARNING", logger="pubmate.incremental"):
        result = _run_current([TermInput(term_id="alpha", assertion=only_label)], IdMap([row]), current)

    assert len(result.superseded) == 1
    assert any("drops all of its" in r.message and str(RDF.type) in r.message for r in caplog.records)
