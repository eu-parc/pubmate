import rdflib
from click.testing import CliRunner
from rdflib.namespace import RDF, RDFS

from nanopub.namespaces import NPX
from pubmate.cli.extract_assertions import cli
from pubmate.defining import DefiningNanopubBuilder
from pubmate.utils import serialize_nanopub

NAMESPACE = "https://w3id.org/peh/biochementities/"
SKOS = rdflib.Namespace("http://www.w3.org/2004/02/skos/core#")
PROV = rdflib.Namespace("http://www.w3.org/ns/prov#")
SUGGESTER = "https://orcid.org/0000-0002-1825-0097"


def _write_nanopub(path) -> rdflib.URIRef:
    """Write a signed defining nanopub to ``path`` and return its thing URI."""
    builder = DefiningNanopubBuilder(NAMESPACE)
    assertion = builder.make_assertion(
        [
            (RDF.type, SKOS.Concept),
            (RDFS.label, rdflib.Literal("Example term")),
        ]
    )
    np = builder.build(assertion, suggester_orcid=SUGGESTER, label="Example term")
    np.sign()
    path.write_text(serialize_nanopub(np), encoding="utf-8")
    return np.metadata.np_uri


def test_extract_writes_one_ttl_per_nanopub(tmp_path) -> None:
    nanopubs = tmp_path / "published"
    nanopubs.mkdir()
    out = tmp_path / "assertions"
    _write_nanopub(nanopubs / "term-a.trig")
    _write_nanopub(nanopubs / "term-b.trig")

    result = CliRunner().invoke(cli, ["--nanopub-folder", str(nanopubs), "--out", str(out)])

    assert result.exit_code == 0, result.output
    assert {p.name for p in out.glob("*.ttl")} == {"term-a.ttl", "term-b.ttl"}


def test_extract_keeps_assertion_only(tmp_path) -> None:
    nanopubs = tmp_path / "published"
    nanopubs.mkdir()
    out = tmp_path / "assertions"
    _write_nanopub(nanopubs / "term.trig")

    result = CliRunner().invoke(cli, ["--nanopub-folder", str(nanopubs), "--out", str(out)])
    assert result.exit_code == 0, result.output

    graph = rdflib.Graph()
    graph.parse(out / "term.ttl", format="turtle")

    # Assertion triples are present...
    assert (None, RDFS.label, rdflib.Literal("Example term")) in graph
    assert (None, RDF.type, SKOS.Concept) in graph
    # ...but provenance/pubinfo triples are not.
    assert (None, PROV.wasAttributedTo, rdflib.URIRef(SUGGESTER)) not in graph
    assert (None, NPX.introduces, None) not in graph


def test_extract_no_nanopubs_is_noop(tmp_path) -> None:
    nanopubs = tmp_path / "published"
    nanopubs.mkdir()
    out = tmp_path / "assertions"

    result = CliRunner().invoke(cli, ["--nanopub-folder", str(nanopubs), "--out", str(out)])

    assert result.exit_code == 0, result.output
    assert list(out.glob("*.ttl")) == []
