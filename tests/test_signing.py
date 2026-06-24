"""Regression tests for resolve_signing key-file handling."""
import nanopub

from pubmate.cli._signing import resolve_signing


def test_resolve_signing_reads_key_files(tmp_path):
    # Real key files on disk: resolve_signing must read them (pass Path to Profile),
    # not treat the path string as the key material.
    nanopub.generate_keyfiles(tmp_path)
    priv, pub = tmp_path / "id_rsa", tmp_path / "id_rsa.pub"

    signing = resolve_signing(
        orcid_id="https://orcid.org/0000-0002-1825-0097", name="Test",
        private_key=str(priv), public_key=str(pub), intro_nanopub_uri=None,
        use_testsuite_keys=False, testsuite_key="rsa-key1", testsuite_ref="main",
        test_server=False, dry_run=True,
    )
    # the profile holds the key *content*, not the path string
    assert signing.profile is not None
    assert signing.profile.private_key == priv.read_text().strip()
    assert "id_rsa" not in signing.profile.private_key
