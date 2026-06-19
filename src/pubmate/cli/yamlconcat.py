from pathlib import Path
import yaml
import click


@click.command()
@click.argument(
    "output",
    type=click.Path(path_type=Path, dir_okay=False),
)
@click.argument(
    "inputs",
    nargs=-1,
    type=click.Path(exists=True, path_type=Path),
)
@click.option(
    "--target",
    required=True,
)
@click.option(
    "--inherit",
    "inherit_keys",
    multiple=True,
    help=(
        "Top-level key whose value is applied as a default to every entry in the "
        "same file that does not set it. May be given multiple times (e.g. --inherit suggester)."
    ),
)
def cli(output: Path, inputs: tuple[Path, ...], target: str, inherit_keys: tuple[str, ...]):
    """
    Aggregate multiple YAML vocabulary files into a single container.

    OUTPUT: combined YAML file
    INPUTS: one or more YAML files from dropbox/
    """

    if not inputs:
        raise click.ClickException("No input YAML files provided.")

    combined: dict = {target: []}
    container_id = None

    # deterministic ordering
    for path in sorted(inputs):
        click.echo(f"Processing {path}", err=True)

        try:
            data = yaml.safe_load(path.read_text()) or {}
        except Exception as e:
            raise click.ClickException(f"Failed parsing {path}: {e}")

        if not isinstance(data, dict):
            raise click.ClickException(f"{path} must contain a YAML mapping at top level.")

        # container id handling
        file_id = data.get("id")
        if container_id is None and file_id:
            container_id = file_id
        elif file_id and file_id != container_id:
            raise click.ClickException(f"Conflicting container ids: '{container_id}' vs '{file_id}' in {path}")

        subclasses = data.get(target, [])
        if not isinstance(subclasses, list):
            raise click.ClickException(f"target must be a list in {path}")

        # Apply file-level defaults (e.g. suggester) to entries that omit them.
        defaults = {key: data[key] for key in inherit_keys if key in data}
        if defaults:
            for entry in subclasses:
                if not isinstance(entry, dict):
                    continue
                for key, value in defaults.items():
                    entry.setdefault(key, value)

        combined[target].extend(subclasses)

    if container_id:
        combined["id"] = container_id

    # ensure output directory exists
    output.parent.mkdir(parents=True, exist_ok=True)

    yaml.safe_dump(
        combined,
        output.open("w"),
        sort_keys=False,
        allow_unicode=True,
    )

    click.echo(
        f"Wrote {len(combined[target])} terms → {output}",
        err=True,
    )


if __name__ == "__main__":
    cli()
