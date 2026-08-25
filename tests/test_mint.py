import pytest

from pubmate.mint import IdentifierGenerator


def test_generate_id_defaults_to_full_ulid() -> None:
    generator = IdentifierGenerator(namespace="https://example.org/")

    identifier = generator.generate_id({"name": "Alpha"})
    ulid_part = identifier.removeprefix("https://example.org/")

    assert generator.is_valid_id(identifier, method="ulid")
    assert len(ulid_part) == 26


def test_generate_id_hash_retries_with_salt_when_collision() -> None:
    generator = IdentifierGenerator(namespace="https://example.org/")
    entity = {"name": "Alpha"}

    first = generator.generate_id(entity, method="hash")
    second = generator.generate_id(entity, method="hash")

    assert first != second
    assert first.startswith("https://example.org/")
    assert second.startswith("https://example.org/")


def test_is_valid_uri_accepts_absolute_uris_without_requiring_minting_pattern() -> None:
    generator = IdentifierGenerator(namespace="https://example.org/terms/")

    assert generator.is_valid_uri("https://example.org/terms/alpha")
    assert not generator.is_valid_id("https://example.org/terms/alpha", method="ulid")


def test_is_valid_id_accepts_trusty_artifact_code_in_namespace() -> None:
    generator = IdentifierGenerator(namespace="https://example.org/terms/")
    artifact = "RA" + ("a" * 41)

    assert generator.is_valid_id(f"https://example.org/terms/{artifact}", method="trusty")
    assert not generator.is_valid_id(f"https://other.example/terms/{artifact}", method="trusty")
    assert not generator.is_valid_id(f"https://example.org/terms/{artifact}/extra", method="trusty")


def test_is_valid_id_accepts_type_prefixed_trusty_artifact_code() -> None:
    generator = IdentifierGenerator(namespace="https://example.org/terms/", type_prefix="chem")
    artifact = "RA" + ("a" * 41)

    assert generator.is_valid_id(f"https://example.org/terms/chem-{artifact}", method="trusty")
    assert not generator.is_valid_id(f"https://example.org/terms/{artifact}", method="trusty")


def test_is_valid_uri_rejects_relative_or_malformed_values() -> None:
    generator = IdentifierGenerator(namespace="https://example.org/terms/")

    assert not generator.is_valid_uri("alpha")
    assert not generator.is_valid_uri("https://")
    assert not generator.is_valid_uri("https://example.org/terms/has space")


def test_generate_id_raises_runtimeerror_when_attempts_exhausted() -> None:
    generator = IdentifierGenerator(namespace="https://example.org/")

    with pytest.raises(RuntimeError, match="Could not generate a unique identifier for 'Alpha' after 0 attempts"):
        generator.generate_id({"name": "Alpha"}, method="hash", max_attempts=0)


def test_generate_id_rejects_trusty_method() -> None:
    generator = IdentifierGenerator(namespace="https://example.org/")

    with pytest.raises(ValueError, match="Cannot generate a trusty artifact-code identifier"):
        generator.generate_id({"name": "Alpha"}, method="trusty")
