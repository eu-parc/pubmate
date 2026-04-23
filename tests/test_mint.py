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


def test_generate_id_raises_runtimeerror_when_attempts_exhausted() -> None:
    generator = IdentifierGenerator(namespace="https://example.org/")

    with pytest.raises(RuntimeError, match="Could not generate a unique identifier for 'Alpha' after 0 attempts"):
        generator.generate_id({"name": "Alpha"}, method="hash", max_attempts=0)
