import click
import logging
import pathlib
import rdflib

from pubmate import NanopubGenerator

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


@click.command()
@click.option(
    "--assertion-folder",
    "-a",
    required=True,
    type=click.Path(exists=True, file_okay=False),
    help="Folder containing .ttl assertion files.",
)
@click.option("--orcid-id", required=False, help="ORCID identifier of the nanopub author.")
@click.option("--name", required=False, help="Full name of the nanopub author.")
@click.option(
    "--private-key", required=False, type=click.Path(exists=True, dir_okay=False), help="Path to the private key file."
)
@click.option(
    "--public-key", required=False, type=click.Path(exists=True, dir_okay=False), help="Path to the public key file."
)
@click.option("--intro-nanopub-uri", required=False, help="URI of the introduction nanopublication.")
@click.option("--dry-run", is_flag=True, help="Run without publishing to the Nanopub network.")
@click.option(
    "--use-testsuite-keys",
    is_flag=True,
    help="Use nanopub-testsuite-connector key material instead of personal key files (dry-run only).",
)
@click.option(
    "--testsuite-key",
    default="rsa-key1",
    show_default=True,
    hidden=True,
    help="Advanced override: testsuite key alias.",
)
@click.option(
    "--testsuite-ref",
    default="main",
    show_default=True,
    hidden=True,
    help="Advanced override: testsuite git ref or commit SHA.",
)
def cli(
    assertion_folder: str,
    orcid_id: str | None,
    name: str | None,
    private_key: str | None,
    public_key: str | None,
    intro_nanopub_uri: str | None,
    dry_run: bool,
    use_testsuite_keys: bool,
    testsuite_key: str,
    testsuite_ref: str,
):
    """Publish a sequence of assertion nanopublications."""

    folder = pathlib.Path(assertion_folder)
    ttl_files = sorted(folder.glob("*.ttl"))

    if not ttl_files:
        logger.warning(f"No .ttl files found in {assertion_folder}")
        return

    logger.info(f"Loading {len(ttl_files)} assertion graphs from: {assertion_folder}")

    loaded_assertions = []
    for ttl_file in ttl_files:
        g = rdflib.Graph()
        g.parse(ttl_file, format="turtle")
        loaded_assertions.append(g)
        logger.debug(f"Loaded graph from {ttl_file}")

    if use_testsuite_keys:
        if not dry_run:
            raise click.ClickException("--use-testsuite-keys is only supported with --dry-run.")
        nanopub_generator = NanopubGenerator.from_testsuite_connector(
            key_name=testsuite_key,
            suite_ref=testsuite_ref,
            test_server=True,
        )
    else:
        required_values = {
            "--orcid-id": orcid_id,
            "--name": name,
            "--private-key": private_key,
            "--public-key": public_key,
            "--intro-nanopub-uri": intro_nanopub_uri,
        }
        missing = [flag for flag, value in required_values.items() if not value]
        if missing:
            raise click.ClickException(
                "Missing required options in manual-key mode: " + ", ".join(missing)
            )

        nanopub_generator = NanopubGenerator(
            orcid_id=orcid_id,
            name=name,
            private_key=private_key,
            public_key=public_key,
            intro_nanopub_uri=intro_nanopub_uri,
            test_server=dry_run,
        )

    nanopub_generator.publish_sequence(
        loaded_assertions,
        dry_run=dry_run,
    )

    logger.info("Publishing complete")


if __name__ == "__main__":
    cli()
