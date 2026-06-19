import logging
import pathlib

import click
import nanopub
import rdflib

from pubmate import NanopubGenerator
from pubmate.defining import DefiningNanopubBuilder
from pubmate.idmap import IdMap
from pubmate.minting import SequentialMinter, term_input_from_assertion
from pubmate.utils import serialize_nanopub

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def _build_builder(
    namespace: str,
    *,
    orcid_id: str | None,
    name: str | None,
    private_key: str | None,
    public_key: str | None,
    intro_nanopub_uri: str | None,
    use_testsuite_keys: bool,
    testsuite_key: str,
    testsuite_ref: str,
    test_server: bool,
    dry_run: bool,
) -> DefiningNanopubBuilder:
    """Resolve signing material into a configured defining-nanopub builder."""
    if use_testsuite_keys:
        generator = NanopubGenerator.from_testsuite_connector(
            key_name=testsuite_key,
            suite_ref=testsuite_ref,
            intro_nanopub_uri=intro_nanopub_uri,
            test_server=True,
        )
        return DefiningNanopubBuilder(namespace, profile=generator.profile, test_server=True)

    if private_key and public_key:
        profile = nanopub.Profile(
            orcid_id=orcid_id,
            name=name,
            private_key=private_key,
            public_key=public_key,
            introduction_nanopub_uri=intro_nanopub_uri,
        )
        return DefiningNanopubBuilder(namespace, profile=profile, test_server=test_server)

    if not dry_run:
        raise click.UsageError(
            "No signing keys provided. Pass --private-key/--public-key or --use-testsuite-keys, "
            "or use --dry-run for an offline preview with throwaway (ephemeral) keys."
        )
    # Ephemeral keyless builder: signs offline with a throwaway key. The artifact
    # codes are NOT authoritative (they depend on the key) -- preview/testing only.
    logger.warning("No keys given; minting with an ephemeral key (--dry-run). Artifact codes are throwaway.")
    return DefiningNanopubBuilder(namespace, test_server=test_server)


@click.command()
@click.option("--assertion-folder", "-a", required=True, type=click.Path(exists=True, file_okay=False, path_type=pathlib.Path))
@click.option("--namespace", default="https://w3id.org/peh/biochementities/", show_default=True)
@click.option("--output-dir", required=True, type=click.Path(file_okay=False, path_type=pathlib.Path), help="Where to write the minted .trig nanopubs.")
@click.option("--id-map-file", type=click.Path(dir_okay=False, path_type=pathlib.Path), help="TSV id-map to write/merge (old_id -> thing_uri, np_uri).")
@click.option("--default-suggester", help="Fallback suggester ORCID for terms without their own.")
@click.option("--orcid-id")
@click.option("--name")
@click.option("--private-key", type=click.Path(exists=True, dir_okay=False))
@click.option("--public-key", type=click.Path(exists=True, dir_okay=False))
@click.option("--intro-nanopub-uri")
@click.option("--test-server", is_flag=True, help="Publish to the nanopub test server (with --private-key).")
@click.option("--use-testsuite-keys", is_flag=True, help="Sign with nanopub-testsuite-connector key material (test server).")
@click.option("--testsuite-key", default="rsa-key1", show_default=True, hidden=True)
@click.option("--testsuite-ref", default="main", show_default=True, hidden=True)
@click.option("--dry-run", is_flag=True, help="Sign only (offline); do not publish to the network.")
@click.option("--glob", "pattern", default="*.ttl", show_default=True)
def cli(
    assertion_folder: pathlib.Path,
    namespace: str,
    output_dir: pathlib.Path,
    id_map_file: pathlib.Path | None,
    default_suggester: str | None,
    orcid_id: str | None,
    name: str | None,
    private_key: str | None,
    public_key: str | None,
    intro_nanopub_uri: str | None,
    test_server: bool,
    use_testsuite_keys: bool,
    testsuite_key: str,
    testsuite_ref: str,
    dry_run: bool,
    pattern: str,
) -> None:
    """Sequentially mint defining nanopubs from per-term assertions and publish them.

    Each assertion is re-keyed onto the artifact-code placeholder, signed (which
    lands the code on the term's thing URI), and -- unless --dry-run -- published.
    Minted nanopubs are written to --output-dir as <old_id-stem>.trig and the
    old_id -> thing_uri/np_uri mapping is written/merged into --id-map-file.

    Inter-term links (forward refs/cycles) are intentionally left to a later
    superseding pass (see the migration tooling); this mints the assertions as
    given.
    """
    builder = _build_builder(
        namespace,
        orcid_id=orcid_id,
        name=name,
        private_key=private_key,
        public_key=public_key,
        intro_nanopub_uri=intro_nanopub_uri,
        use_testsuite_keys=use_testsuite_keys,
        testsuite_key=testsuite_key,
        testsuite_ref=testsuite_ref,
        test_server=test_server,
        dry_run=dry_run,
    )

    files = sorted(assertion_folder.glob(pattern))
    if not files:
        logger.info("No assertions matching %s in %s. Nothing to mint.", pattern, assertion_folder)
        return

    terms = []
    for path in files:
        graph = rdflib.Graph()
        graph.parse(path, format="turtle")
        terms.append(
            term_input_from_assertion(
                graph,
                namespace=namespace,
                thing_uri=builder.thing_uri,
                default_suggester=default_suggester,
            )
        )

    existing = IdMap.from_tsv(id_map_file.read_text(encoding="utf-8")) if id_map_file and id_map_file.exists() else IdMap()

    minter = SequentialMinter(builder, default_suggester_orcid=default_suggester)
    batch = minter.mint_all(
        terms,
        dry_run=dry_run,
        already_minted=existing.np_uri_map,
    )

    # Write each nanopub as <artifact-code>.trig (the thing/np code under scheme A).
    output_dir.mkdir(parents=True, exist_ok=True)
    for minted in batch.terms:
        code = minted.thing_uri.removeprefix(namespace)
        (output_dir / f"{code}.trig").write_text(serialize_nanopub(minted.nanopub), encoding="utf-8")

    if id_map_file is not None:
        merged = IdMap(list(existing))
        merged.merge(IdMap.from_batch(batch), overwrite=True)
        id_map_file.parent.mkdir(parents=True, exist_ok=True)
        merged.write_tsv(id_map_file)
        logger.info("Wrote id-map (%d entries) -> %s", len(merged), id_map_file)

    logger.info("Minted %d new term(s)%s -> %s", len(batch.terms), " (dry-run)" if dry_run else "", output_dir)


if __name__ == "__main__":
    cli()
