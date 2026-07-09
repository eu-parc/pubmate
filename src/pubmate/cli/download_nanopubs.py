import logging
import pathlib

import click

from pubmate.download import (
    download_nanopubs,
    endpoint_url_with_params,
    nanopub_uris_from_query,
    sync_nanopubs,
    write_manifest,
)

logging.basicConfig(level=logging.INFO, format="::%(levelname)s:: %(message)s")
logger = logging.getLogger(__name__)


@click.command()
@click.argument("endpoint_url")
@click.option(
    "--query-param",
    "query_params",
    multiple=True,
    help="Additional endpoint query parameter as key=value. Repeatable.",
)
@click.option(
    "--output-dir",
    required=True,
    type=click.Path(file_okay=False, path_type=pathlib.Path),
    help="Where to write downloaded .trig nanopublications.",
)
@click.option(
    "--manifest",
    type=click.Path(dir_okay=False, path_type=pathlib.Path),
    help="Optional TSV manifest to write.",
)
@click.option("--np-column", default="np", show_default=True, help="SPARQL JSON result column containing nanopub URIs.")
@click.option("--timeout", default=60, show_default=True, type=int, help="HTTP timeout in seconds.")
@click.option("--retries", default=3, show_default=True, type=int, help="Number of retries per HTTP request.")
@click.option(
    "--min-count",
    default=1,
    show_default=True,
    type=int,
    help="Fail if the endpoint returns fewer nanopublications than this.",
)
@click.option(
    "--replace/--no-replace",
    default=False,
    show_default=True,
    help="Replace existing .trig files in --output-dir with exactly the endpoint result set.",
)
@click.option(
    "--validate/--no-validate",
    default=True,
    show_default=True,
    help="Parse each downloaded TriG file and require it to declare an np:Nanopublication.",
)
def cli(
    endpoint_url: str,
    query_params: tuple[str, ...],
    output_dir: pathlib.Path,
    manifest: pathlib.Path | None,
    np_column: str,
    timeout: int,
    retries: int,
    min_count: int,
    replace: bool,
    validate: bool,
) -> None:
    """Download nanopublication .trig files listed by a query endpoint.

    ENDPOINT_URL is expected to return SPARQL results JSON. Pubmate reads
    nanopublication URIs from the ``np`` binding by default, then downloads each
    URI as ``<URI>.trig`` into ``--output-dir``.
    """
    try:
        query_url = endpoint_url_with_params(endpoint_url, query_params)
    except ValueError as error:
        raise click.ClickException(str(error)) from error
    np_uris = nanopub_uris_from_query(query_url, np_column=np_column, timeout=timeout, retries=retries)
    if len(np_uris) < min_count:
        raise click.ClickException(f"Expected at least {min_count} nanopub(s), got {len(np_uris)}.")

    downloader = sync_nanopubs if replace else download_nanopubs
    downloaded = downloader(
        np_uris,
        output_dir=output_dir,
        timeout=timeout,
        retries=retries,
        validate=validate,
    )

    if manifest is not None:
        write_manifest(manifest, downloaded)
        logger.info("Wrote manifest (%d entries) -> %s", len(downloaded), manifest)

    logger.info("Downloaded %d nanopublication(s) -> %s", len(downloaded), output_dir)


if __name__ == "__main__":
    cli()
