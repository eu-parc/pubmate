import pytest
import rdflib

from pubmate.rdf2nanopub import NanopubGenerator


def test_publish_sequence_uses_none_supersedes_by_default() -> None:
    generator = object.__new__(NanopubGenerator)
    calls: list[tuple[rdflib.Graph, str | None, bool]] = []

    def fake_publish_single(statement: rdflib.Graph, supersedes: str | None = None, dry_run: bool = True) -> str:
        calls.append((statement, supersedes, dry_run))
        return f"uri-{len(calls)}"

    generator.publish_single = fake_publish_single  # type: ignore[method-assign]

    assertions = [rdflib.Graph(), rdflib.Graph()]
    uris = generator.publish_sequence(assertions, dry_run=True)

    assert uris == ["uri-1", "uri-2"]
    assert [supersedes for _, supersedes, _ in calls] == [None, None]
    assert [dry_run for _, _, dry_run in calls] == [True, True]


def test_publish_sequence_raises_when_supersedes_length_mismatch() -> None:
    generator = object.__new__(NanopubGenerator)
    generator.publish_single = lambda *_args, **_kwargs: "uri"  # type: ignore[method-assign]

    with pytest.raises(ValueError, match="Length mismatch: 'supersedes' must match the number of assertion graphs."):
        generator.publish_sequence([rdflib.Graph(), rdflib.Graph()], supersedes=["one"], dry_run=True)


def test_from_testsuite_connector_uses_keypair_without_network(monkeypatch: pytest.MonkeyPatch) -> None:
    from nanopub_testsuite_connector import NanopubTestSuite

    class DummyKeyPair:
        private_key = "/tmp/dummy_private"
        public_key = "/tmp/dummy_public"

    class DummySuite:
        def get_signing_key(self, key_name: str) -> DummyKeyPair:
            assert key_name == "rsa-key1"
            return DummyKeyPair()

    monkeypatch.setattr(NanopubTestSuite, "get_latest", staticmethod(lambda: DummySuite()))

    generator = NanopubGenerator.from_testsuite_connector(key_name="rsa-key1")

    assert generator.test_server is True
    assert str(generator.profile.private_key) == "/tmp/dummy_private"
    assert str(generator.profile.public_key) == "/tmp/dummy_public"


def test_check_nanopub_existence_queries_client_with_obj_keyword() -> None:
    generator = object.__new__(NanopubGenerator)
    generator.test_server = False
    generator.client = None

    class DummyClient:
        def __init__(self):
            self.called_obj = None

        def find_nanopubs_with_pattern(self, subj=None, pred=None, obj=None, filter_retracted=True, pubkey=None):
            self.called_obj = obj
            return iter(["np-uri"])

    dummy_client = DummyClient()
    generator.get_client = lambda: dummy_client  # type: ignore[method-assign]

    assert generator.check_nanopub_existence("https://example.org/some-uri") is True
    assert dummy_client.called_obj == "https://example.org/some-uri"
