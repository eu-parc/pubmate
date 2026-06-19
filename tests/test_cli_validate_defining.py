import rdflib
from click.testing import CliRunner

from pubmate.cli.validate_defining import cli

TERM = "https://w3id.org/peh/biochementities/01KRB098ND0MXJ7J2ZSF49KSFN"


def _write_assertion(path) -> None:
    g = rdflib.Graph()
    s = rdflib.URIRef(TERM)
    g.add((s, rdflib.RDF.type, rdflib.URIRef("http://www.w3.org/2004/02/skos/core#Concept")))
    g.add((s, rdflib.RDFS.label, rdflib.Literal("Example term")))
    g.serialize(destination=path, format="turtle")


def test_valid_assertions_pass(tmp_path) -> None:
    folder = tmp_path / "assertions"
    folder.mkdir()
    _write_assertion(folder / "term-a.ttl")
    _write_assertion(folder / "term-b.ttl")

    result = CliRunner().invoke(cli, ["--assertion-folder", str(folder)])

    assert result.exit_code == 0, result.output


def test_empty_assertion_fails(tmp_path) -> None:
    folder = tmp_path / "assertions"
    folder.mkdir()
    _write_assertion(folder / "good.ttl")
    (folder / "empty.ttl").write_text("", encoding="utf-8")

    result = CliRunner().invoke(cli, ["--assertion-folder", str(folder)])

    assert result.exit_code == 1, result.output


def test_no_assertions_is_noop(tmp_path) -> None:
    folder = tmp_path / "assertions"
    folder.mkdir()

    result = CliRunner().invoke(cli, ["--assertion-folder", str(folder)])

    assert result.exit_code == 0, result.output
