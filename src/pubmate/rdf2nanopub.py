import logging
from pathlib import Path

import nanopub
import rdflib

from typing import Optional


# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class NanopubGenerator:
    def __init__(
        self,
        orcid_id: str,
        name: str,
        private_key: str | Path,
        public_key: str | Path,
        test_server: bool,
        intro_nanopub_uri: str | None = None,
    ):
        self.profile = nanopub.Profile(
            orcid_id=orcid_id,
            name=name,
            private_key=private_key,
            public_key=public_key,
            introduction_nanopub_uri=intro_nanopub_uri,
        )

        self.np_conf = nanopub.NanopubConf(
            profile=self.profile,
            use_test_server=test_server,
            add_prov_generated_time=True,
            attribute_publication_to_profile=True,
        )
        self.test_server = test_server
        self.client = None

    @classmethod
    def from_testsuite_connector(
        cls,
        key_name: str = "rsa-key1",
        suite_ref: str = "main",
        orcid_id: str = "https://orcid.org/0000-0002-1825-0097",
        name: str = "Pubmate Test Publisher",
        intro_nanopub_uri: str | None = None,
        test_server: bool = True,
    ) -> "NanopubGenerator":
        """
        Construct a NanopubGenerator from a keypair managed by nanopub-testsuite-connector.
        This avoids requiring repository-specific secrets for test-server publishing.
        """
        try:
            from nanopub_testsuite_connector import NanopubTestSuite
        except ImportError as exc:
            raise ImportError(
                "nanopub-testsuite-connector is required for from_testsuite_connector(). "
                "Install it in your test/development environment."
            ) from exc

        suite: NanopubTestSuite
        if suite_ref == "main":
            suite = NanopubTestSuite.get_latest()
        else:
            suite = NanopubTestSuite.get_at_commit(suite_ref)

        keypair = suite.get_signing_key(key_name)
        return cls(
            orcid_id=orcid_id,
            name=name,
            private_key=keypair.private_key,
            public_key=keypair.public_key,
            intro_nanopub_uri=intro_nanopub_uri,
            test_server=test_server,
        )

    def get_client(self):
        if self.client is None:
            self.client = nanopub.NanopubClient(use_test_server=self.test_server)
        return self.client

    def create_nanopub(self, assertion: rdflib.Graph) -> nanopub.Nanopub:
        return nanopub.Nanopub(conf=self.np_conf, assertion=assertion)

    def update_nanopub(self, np_uri: str, assertion: rdflib.Graph) -> nanopub.Nanopub:
        new_np = nanopub.NanopubUpdate(
            uri=np_uri,
            conf=self.np_conf,
            assertion=assertion,
        )
        new_np.sign()
        return new_np

    @classmethod
    def check_prefix(cls, key: str):
        allowed_prefixes = [
            "http://purl.org",
            "https://purl.org",
            "http://w3id.org",
            "https://w3id.org",
        ]
        for prefix in allowed_prefixes:
            if key.startswith(prefix):
                return True
        return False

    def check_nanopub_existence(self, uri: str) -> bool:
        # TODO: do real check where nanopub is fetched
        try:
            if self.test_server:
                return self.check_prefix(uri)
            else:
                client = self.get_client()
                ret = client.find_nanopubs_with_pattern(
                    obj=uri,
                )
                first = next(ret, None)
                return first is not None
        except Exception as e:
            logger.error(f"Error in check_nanopub_existence: {e}")
            return False

    def publish_single(
        self,
        to_publish: rdflib.Graph,
        supersedes: Optional[str] = None,
        dry_run: bool = True,
    ) -> str:
        try:
            if supersedes is None:
                np = self.create_nanopub(assertion=to_publish)
                np.sign()
                np_uri = np.metadata.np_uri
                if np_uri is None:
                    raise ValueError("no URI returned by nanpub server.")
                if not dry_run:
                    publication_info = np.publish()
                    logger.info(f"Nanopub published: {publication_info}")
            else:
                raise NotImplementedError

            return np_uri

        except Exception as e:
            logger.error(f"Error in publish_single: {e}")
            raise

    def publish_sequence(
        self,
        to_publish: list[rdflib.Graph],
        supersedes: list[str] | None = None,
        dry_run: bool = True,
    ) -> list:
        try:
            np_uris = []
            if supersedes is None:
                supersedes = [None] * len(to_publish)
            elif len(supersedes) != len(to_publish):
                raise ValueError("Length mismatch: 'supersedes' must match the number of assertion graphs.")

            for statement, supersedes_uri in zip(to_publish, supersedes):
                np_uri = self.publish_single(statement, supersedes_uri, dry_run=dry_run)
                np_uris.append(np_uri)

            return np_uris

        except Exception as e:
            logger.error(f"Error in publish_sequence: {e}")
            raise
