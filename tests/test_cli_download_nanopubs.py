import json

from click.testing import CliRunner

from pubmate.cli.download_nanopubs import cli


def _trig(code: str) -> bytes:
    return f"""
@prefix np: <http://www.nanopub.org/nschema#> .
@prefix this: <https://w3id.org/np/{code}#> .

this:Head {{
    <https://w3id.org/np/{code}> a np:Nanopublication .
}}
""".encode()


def test_download_nanopubs_cli_writes_trig_and_manifest(tmp_path, monkeypatch) -> None:
    calls: list[tuple[str, str]] = []
    query_payload = {
        "results": {
            "bindings": [
                {"np": {"type": "uri", "value": "https://w3id.org/np/RAone"}},
                {"np": {"type": "uri", "value": "https://w3id.org/np/RAtwo"}},
            ]
        }
    }

    def fake_fetch_url(url: str, *, accept: str, timeout: int, retries: int) -> bytes:
        calls.append((url, accept))
        if accept == "application/sparql-results+json":
            assert timeout == 5
            assert retries == 1
            assert url == "https://query.example/api/run?ontology=https%3A%2F%2Fexample.org%2Fvocab&limit=2"
            return json.dumps(query_payload).encode()
        code = url.removesuffix(".trig").rsplit("/", 1)[-1]
        return _trig(code)

    monkeypatch.setattr("pubmate.download.fetch_url", fake_fetch_url)
    out = tmp_path / "published"
    manifest = tmp_path / "build" / "manifest.tsv"

    result = CliRunner().invoke(
        cli,
        [
            "https://query.example/api/run",
            "--query-param",
            "ontology=https://example.org/vocab",
            "--query-param",
            "limit=2",
            "--output-dir",
            str(out),
            "--manifest",
            str(manifest),
            "--timeout",
            "5",
            "--retries",
            "1",
        ],
    )

    assert result.exit_code == 0, result.output
    assert sorted(path.name for path in out.glob("*.trig")) == ["RAone.trig", "RAtwo.trig"]
    assert manifest.read_text(encoding="utf-8").splitlines() == [
        "artifact_code\tnp_uri\tpath",
        f"RAone\thttps://w3id.org/np/RAone\t{out / 'RAone.trig'}",
        f"RAtwo\thttps://w3id.org/np/RAtwo\t{out / 'RAtwo.trig'}",
    ]
    assert calls == [
        (
            "https://query.example/api/run?ontology=https%3A%2F%2Fexample.org%2Fvocab&limit=2",
            "application/sparql-results+json",
        ),
        ("https://w3id.org/np/RAone.trig", "application/trig"),
        ("https://w3id.org/np/RAtwo.trig", "application/trig"),
    ]


def test_download_nanopubs_cli_replace_removes_stale_trig(tmp_path, monkeypatch) -> None:
    query_payload = {
        "results": {
            "bindings": [
                {"np": {"type": "uri", "value": "https://w3id.org/np/RAfresh"}},
            ]
        }
    }

    def fake_fetch_url(url: str, *, accept: str, timeout: int, retries: int) -> bytes:
        if accept == "application/sparql-results+json":
            return json.dumps(query_payload).encode()
        return _trig("RAfresh")

    monkeypatch.setattr("pubmate.download.fetch_url", fake_fetch_url)
    out = tmp_path / "published"
    out.mkdir()
    (out / "RAstale.trig").write_text("stale", encoding="utf-8")
    (out / "keep.ttl").write_text("keep", encoding="utf-8")

    result = CliRunner().invoke(cli, ["https://query.example/api/run", "--output-dir", str(out), "--replace"])

    assert result.exit_code == 0, result.output
    assert sorted(path.name for path in out.iterdir()) == ["RAfresh.trig", "keep.ttl"]


def test_download_nanopubs_cli_honors_min_count(tmp_path, monkeypatch) -> None:
    def fake_fetch_url(url: str, *, accept: str, timeout: int, retries: int) -> bytes:
        return json.dumps(
            {"results": {"bindings": [{"np": {"type": "uri", "value": "https://w3id.org/np/RAone"}}]}}
        ).encode()

    monkeypatch.setattr("pubmate.download.fetch_url", fake_fetch_url)

    result = CliRunner().invoke(
        cli,
        ["https://query.example/api/run", "--output-dir", str(tmp_path / "published"), "--min-count", "2"],
    )

    assert result.exit_code != 0
    assert "Expected at least 2 nanopub" in result.output
