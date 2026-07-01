import logging
import pathlib

import click
import rdflib

from pubmate.defining import DefiningNanopubBuilder
from pubmate.utils import materialize_nanopub

logging.basicConfig(level=logging.INFO, format="::%(levelname)s:: %(message)s")
logger = logging.getLogger(__name__)


@click.command()
@click.option(
    "--assertion-folder",
    required=True,
    type=click.Path(exists=True, file_okay=False, path_type=pathlib.Path),
    help="Folder of per-term assertion .ttl files to validate.",
)
@click.option(
    "--namespace",
    default="https://w3id.org/peh/biochementities/",
    show_default=True,
    help="Term namespace used when building the defining nanopub.",
)
@click.option(
    "--glob",
    "pattern",
    default="*.ttl",
    show_default=True,
    help="Glob for assertion files within --assertion-folder.",
)
def cli(assertion_folder: pathlib.Path, namespace: str, pattern: str) -> None:
    """Validate that each assertion builds into a valid, signable defining nanopub.

    Keyless and offline: every assertion is wrapped into an unsigned defining
    nanopublication and signed with an *ephemeral, in-memory* key (no repo
    secrets, no network), then checked for structural validity (valid trusty
    code + valid signature). Intended as a pull-request gate — it proves each
    proposed term can become a well-formed nanopub, without minting final
    artifact-code URIs or publishing (those need the real bot key; see B4).

    Exits non-zero if any term fails.
    """
    files = sorted(assertion_folder.glob(pattern))
    if not files:
        logger.info("No assertions matching %s in %s. Nothing to validate.", pattern, assertion_folder)
        return

    failures: list[tuple[str, str]] = []
    for path in files:
        try:
            assertion = rdflib.Graph()
            assertion.parse(path, format="turtle")
            if len(assertion) == 0:
                raise ValueError("empty assertion graph")

            # If the assertion has a single subject, introduce that term; otherwise
            # let the builder fall back to its default introduces.
            subjects = set(assertion.subjects())
            introduces = str(next(iter(subjects))) if len(subjects) == 1 else None

            np = DefiningNanopubBuilder(namespace).build(assertion, introduces=introduces)
            materialize_nanopub(np)  # signs and validates the exact serialized artifact
        except Exception as exc:  # noqa: BLE001 - report any failure per file
            failures.append((path.name, str(exc)))
            logger.error("INVALID %s: %s", path.name, exc)
        else:
            logger.info("OK %s", path.name)

    logger.info("Validated %d assertion(s); %d failure(s).", len(files), len(failures))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    cli()
