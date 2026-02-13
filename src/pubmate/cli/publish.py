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
@click.option("--orcid-id", required=True, help="ORCID identifier of the nanopub author.")
@click.option("--name", required=True, help="Full name of the nanopub author.")
@click.option(
    "--private-key", required=True, type=click.Path(exists=True, dir_okay=False), help="Path to the private key file."
)
@click.option(
    "--public-key", required=True, type=click.Path(exists=True, dir_okay=False), help="Path to the public key file."
)
@click.option("--intro-nanopub-uri", required=True, help="URI of the introduction nanopublication.")
@click.option("--dry-run", is_flag=True, help="Run without publishing to the Nanopub network.")
def cli(
    assertion_folder: str,
    orcid_id: str,
    name: str,
    private_key: str,
    public_key: str,
    intro_nanopub_uri: str,
    dry_run: bool,
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
