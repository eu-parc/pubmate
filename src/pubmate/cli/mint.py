import sys
import click
import logging
import yaml

from pubmate import IdentifierGenerator

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


@click.command()
@click.option(
    "--data", "-d", "data_path", required=True, type=click.Path(exists=True), help="Path to the YAML data file."
)
@click.option("--target", "-t", "target_name", required=True, help="Name of the target entity list in the data file.")
@click.option("--namespace", required=True, help="Namespace prefix used to create identifiers.")
@click.option("--id-key", default="id", help="Field name containing the identifier.")
@click.option("--method", default="hash", type=click.Choice(["uuid", "hash"]), help="ID generation method.")
@click.option(
    "--output", "output_path", default=None, help="Optional output path. Defaults to overwriting the input file."
)
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging.")
@click.option("--dry-run", is_flag=True, help="Show changes without writing files.")
@click.option("--force", is_flag=True, help="Force regeneration of identifiers even when one already exists.")
@click.option("--preflabel", required=False, default="name")
def cli(
    data_path: str,
    target_name: str,
    namespace: str,
    id_key: str,
    method: str,
    output_path: str,
    verbose: bool,
    dry_run: bool,
    force: bool,
    preflabel: str,
):
    """Generate identifiers for all vocabulary terms and update the YAML file."""
    if verbose:
        logger.setLevel(logging.DEBUG)

    try:
        logger.info(f"Loading data from: {data_path}")
        with open(data_path, "r", encoding="utf-8") as f:
            yaml_root = yaml.safe_load(f)

        if target_name not in yaml_root:
            raise ValueError(f"Target '{target_name}' not found. " f"Available keys: {list(yaml_root.keys())}")

        entities = yaml_root[target_name]
        if not isinstance(entities, list):
            raise ValueError(f"Target '{target_name}' must be a list.")

        logger.info(f"Found {len(entities)} entities in '{target_name}'")
        id_generator = IdentifierGenerator(namespace=namespace)

        new_ids = 0
        updated = 0

        for i, entity in enumerate(entities):
            if not isinstance(entity, dict):
                raise ValueError(f"Entity at index {i} is not a dict: {entity}")

            current_id = entity.get(id_key)
            label_value = entity.get(preflabel)

            if not label_value:
                raise ValueError(f"Entity at index {i} has no '{preflabel}' value: {entity}")

            # Keep existing valid IDs unless forced
            if current_id and not force:
                if id_generator.is_valid_id(current_id, method=method):
                    id_generator.register_id(current_id)
                    logger.debug(f"Keeping existing ID: {current_id}")
                    continue

            # Generate new ID
            new_id = id_generator.generate_id(entity, method=method, preflabel=preflabel)
            entity[id_key] = new_id

            logger.debug(f"Generated new ID for '{label_value}': {new_id}")
            new_ids += 1
            updated += 1

        logger.info("Processing complete:")
        logger.info(f"  - Total entities: {len(entities)}")
        logger.info(f"  - New IDs generated: {new_ids}")
        logger.info(f"  - Entities updated: {updated}")

        if dry_run:
            logger.info("Dry run: no files written.")
            yaml.safe_dump(yaml_root, sys.stdout, default_flow_style=False, allow_unicode=True, sort_keys=False)
            return

        output_path = output_path or data_path
        logger.info(f"Writing updated data to: {output_path}")

        with open(output_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(yaml_root, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

        logger.info("Successfully wrote updated YAML file.")

    except Exception as e:
        logger.error(f"Error: {e}")
        if verbose:
            import traceback

            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    cli()
