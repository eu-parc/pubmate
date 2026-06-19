import logging
import pathlib

import click

from pubmate import utils

logging.basicConfig(level=logging.INFO, format="::%(levelname)s:: %(message)s")
logger = logging.getLogger(__name__)


@click.command()
@click.option(
    "--nanopub-folder",
    required=True,
    type=click.Path(exists=True, file_okay=False, path_type=pathlib.Path),
    help="Folder of signed nanopublication .trig files.",
)
@click.option(
    "--out",
    "out_folder",
    required=True,
    type=click.Path(file_okay=False, path_type=pathlib.Path),
    help="Output folder for the extracted plain-Turtle assertions.",
)
@click.option(
    "--glob",
    "pattern",
    default="*.trig",
    show_default=True,
    help="Glob for nanopub files within --nanopub-folder.",
)
def cli(nanopub_folder: pathlib.Path, out_folder: pathlib.Path, pattern: str) -> None:
    """Extract each nanopublication's assertion graph into a plain .ttl file.

    For every ``--nanopub-folder/<name>.trig`` this writes ``--out/<name>.ttl``
    containing only the assertion graph, for consumers that read assertions and
    cannot parse a four-graph nanopublication (e.g. the vocabulary-browser site).
    """
    out_folder.mkdir(parents=True, exist_ok=True)

    files = sorted(nanopub_folder.glob(pattern))
    if not files:
        logger.info("No nanopubs matching %s in %s. Nothing to extract.", pattern, nanopub_folder)
        return

    count = 0
    for path in files:
        assertion = utils.load_nanopub_assertion(path)
        dest = out_folder / f"{path.stem}.ttl"
        dest.write_text(assertion.serialize(format="turtle"), encoding="utf-8")
        logger.info("Extracted assertion %s -> %s", path.name, dest)
        count += 1

    logger.info("Extracted %d assertion(s) -> %s", count, out_folder)


if __name__ == "__main__":
    cli()
