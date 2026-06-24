"""CLI: bootstrap a publishing bot's cryptographic identity.

Generates (or reuses) an RSA keypair and builds a **self-signed introduction**
nanopublication that declares the bot agent and binds it to that key. By default
it stops at signing — it does **not** publish and does **not** touch any secret
store. That is deliberate: the private key is the bot's identity, so generating
it locally/offline and reviewing the introduction before anything goes out (then
adding the key as a CI secret by hand, once) is far safer than minting an
identity inside automation.

Typical flow::

    pubmate-bootstrap-identity \\
        --bot-name "Biochementity bot" --bot-id biochementity-bot \\
        --owner-orcid https://orcid.org/0000-0002-1267-0234 --owner-name "Tobias Kuhn" \\
        --generate-keys --output-dir ./bot-identity

Review ``bot-identity/introduction.trig``; if it looks right, publish it once
(``--publish``) and add ``bot-identity/id_rsa`` as the repo's signing secret.
"""

import logging
import pathlib
import stat

import click

from nanopub import generate_keyfiles
from pubmate.introduction import build_introduction
from pubmate.utils import serialize_nanopub

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def _code(np_uri: str) -> str:
    return np_uri.rstrip("/").rsplit("/", 1)[-1]


@click.command()
@click.option("--bot-name", required=True, help="foaf:name for the agent, e.g. \"Biochementity bot\".")
@click.option("--owner-orcid", required=True, help="ORCID URI of the human owner (frbr:owner + attribution).")
@click.option("--bot-id", default="bot", show_default=True, help="Local URI segment for the agent (…/RA<code>/<bot-id>).")
@click.option("--owner-name", help="Optional foaf:name for the owner ORCID.")
@click.option("--output-dir", required=True, type=click.Path(file_okay=False, path_type=pathlib.Path))
@click.option("--generate-keys", is_flag=True, help="Generate a fresh RSA keypair into --output-dir (id_rsa / id_rsa.pub).")
@click.option("--private-key", type=click.Path(exists=True, dir_okay=False), help="Existing private key (instead of --generate-keys).")
@click.option("--public-key", type=click.Path(exists=True, dir_okay=False), help="Existing public key (with --private-key).")
@click.option("--license", "license_", default=None, help="Override pubinfo license URI (default CC BY 4.0).")
@click.option("--test-server", is_flag=True, help="Mark the introduction for the nanopub test server.")
@click.option("--publish", is_flag=True, help="Publish the signed introduction to the network (default: sign only).")
def cli(
    bot_name: str,
    owner_orcid: str,
    bot_id: str,
    owner_name: str | None,
    output_dir: pathlib.Path,
    generate_keys: bool,
    private_key: str | None,
    public_key: str | None,
    license_: str | None,
    test_server: bool,
    publish: bool,
) -> None:
    """Generate a bot keypair + self-signed introduction nanopublication.

    Signs offline by default and writes everything under --output-dir; nothing is
    published or stored as a secret unless you ask (--publish), so you can review
    the introduction first.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    if generate_keys:
        if private_key or public_key:
            raise click.UsageError("Pass either --generate-keys or --private-key/--public-key, not both.")
        priv_path = output_dir / "id_rsa"
        if priv_path.exists():
            raise click.UsageError(f"{priv_path} already exists; refusing to overwrite an identity key.")
        generate_keyfiles(output_dir)
        priv_path.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 0600
        priv, pub = priv_path, output_dir / "id_rsa.pub"
        logger.info("Generated keypair: %s (private, chmod 600) / %s", priv, pub)
    elif private_key and public_key:
        priv, pub = pathlib.Path(private_key), pathlib.Path(public_key)
    else:
        raise click.UsageError("Provide --generate-keys, or both --private-key and --public-key.")

    kwargs = {} if license_ is None else {"license": license_}
    np = build_introduction(
        private_key=priv, public_key=pub, bot_name=bot_name,
        owner_orcid=owner_orcid, bot_local_name=bot_id, owner_name=owner_name,
        test_server=test_server, **kwargs,
    )
    np.sign()
    agent_uri = f"{np.metadata.np_uri}/{bot_id}"
    intro_path = output_dir / "introduction.trig"
    intro_path.write_text(serialize_nanopub(np), encoding="utf-8")

    if publish:
        np.publish()
        logger.info("Published introduction: %s", np.metadata.np_uri)
    logger.info("Wrote introduction -> %s (artifact code %s)", intro_path, _code(np.metadata.np_uri))
    click.echo(f"\nBot agent URI : {agent_uri}")
    click.echo(f"Introduction  : {np.metadata.np_uri}")
    click.echo(f"is_valid      : {np.is_valid}")
    if not publish:
        click.echo(
            "\nNot published. Next: review introduction.trig, then publish it once "
            "(--publish) and add id_rsa as your signing secret (e.g. gh secret set …)."
        )


if __name__ == "__main__":
    cli()
