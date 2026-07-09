import json

import pytest

from pubmate.download import artifact_code, endpoint_url_with_params, nanopub_uris_from_query


def test_endpoint_url_with_params_preserves_existing_filters() -> None:
    url = endpoint_url_with_params(
        "https://query.example/api/run?ontology=https%3A%2F%2Fexample.org%2Fvocab",
        ("space=https://example.org/space", "limit=10"),
    )

    assert url == (
        "https://query.example/api/run?"
        "ontology=https%3A%2F%2Fexample.org%2Fvocab&"
        "space=https%3A%2F%2Fexample.org%2Fspace&limit=10"
    )


def test_endpoint_url_with_params_requires_key_value() -> None:
    with pytest.raises(ValueError, match="key=value"):
        endpoint_url_with_params("https://query.example/api/run", ("ontology",))


def test_nanopub_uris_from_query_extracts_sorted_unique_column(monkeypatch) -> None:
    payload = {
        "results": {
            "bindings": [
                {"np": {"type": "uri", "value": "https://w3id.org/np/RAb"}},
                {"np": {"type": "uri", "value": "https://w3id.org/np/RAa"}},
                {"np": {"type": "uri", "value": "https://w3id.org/np/RAb"}},
                {"label": {"type": "literal", "value": "ignored"}},
            ]
        }
    }

    def fake_fetch_url(url: str, *, accept: str, timeout: int, retries: int) -> bytes:
        assert url == "https://query.example/api/run"
        assert accept == "application/sparql-results+json"
        assert timeout == 10
        assert retries == 2
        return json.dumps(payload).encode()

    monkeypatch.setattr("pubmate.download.fetch_url", fake_fetch_url)

    assert nanopub_uris_from_query("https://query.example/api/run", timeout=10, retries=2) == [
        "https://w3id.org/np/RAa",
        "https://w3id.org/np/RAb",
    ]


def test_artifact_code_rejects_non_trusty_uri() -> None:
    with pytest.raises(ValueError, match="without RA artifact code"):
        artifact_code("https://example.org/not-a-nanopub")
