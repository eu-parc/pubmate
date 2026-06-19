"""Supersession-nanopub builder.

Build a nanopublication that *supersedes* an earlier one, used to add links a
term's defining nanopub deliberately left out — forward references to terms that
were not minted yet, or cyclic references between terms.

The superseded term keeps its identity: the assertion here is written against
the term's already-minted, fixed URI (its trusty artifact-code URI), not the
placeholder. When this nanopub is signed, only its *own* artifact code is
computed; the fixed URIs of this and other terms are preserved.

This adds an ``npx:supersedes`` triple to a plain nanopub, which is offline
friendly. It does not fetch or key-check the superseded nanopub over the network
(unlike ``nanopub.NanopubUpdate``); the caller is responsible for superseding
only nanopubs signed with a matching key.
"""

from __future__ import annotations

from typing import Optional

import nanopub
import rdflib

from nanopub.namespaces import NPX

from pubmate._nanopub_build import (
    UNSET as _UNSET,
    add_label_and_license,
    build_conf,
    ephemeral_profile,
)
from pubmate.defining import DEFAULT_LICENSE


class SupersessionBuilder:
    """Build an unsigned nanopub that supersedes an existing one.

    Configure once with a signing ``profile`` (omit it to build keyless for
    validation, like the defining builder), then call :meth:`build` per
    supersession. The assertion must use the term's fixed URIs; pass the URI of
    the nanopub being superseded.
    """

    def __init__(
        self,
        *,
        profile: Optional[nanopub.Profile] = None,
        license: Optional[str] = DEFAULT_LICENSE,
        test_server: bool = False,
        add_prov_generated_time: bool = True,
    ):
        self.license = license
        self.test_server = test_server
        self.add_prov_generated_time = add_prov_generated_time

        self._keyless = profile is None
        self.profile = profile if profile is not None else ephemeral_profile()

    def build(
        self,
        assertion: rdflib.Graph,
        *,
        supersedes_np_uri: str,
        suggester_orcid: Optional[str] = None,
        label: Optional[str] = None,
        license: Optional[str] = _UNSET,
        derived_from: Optional[str] = None,
        introduces: Optional[str] = None,
    ) -> nanopub.Nanopub:
        """Wrap an updated ``assertion`` into an unsigned superseding nanopub.

        Args:
            assertion: the term's updated graph, written against its fixed URI
                (typically the original intrinsic properties plus the new links).
            supersedes_np_uri: URI of the nanopub this one supersedes.
            suggester_orcid: ORCID the assertion is attributed to.
            label: optional ``rdfs:label`` for the nanopub.
            license: pubinfo ``dct:license``; defaults to the builder's license,
                pass ``None`` to omit.
            derived_from: optional ``prov:wasDerivedFrom`` source.
            introduces: pubinfo ``npx:introduces``; omitted by default since the
                concept was already introduced by the superseded nanopub.
        """
        if len(assertion) == 0:
            raise ValueError("assertion graph is empty; a supersession needs at least one triple.")
        if not supersedes_np_uri:
            raise ValueError("supersedes_np_uri is required.")

        conf = build_conf(
            profile=self.profile,
            keyless=self._keyless,
            test_server=self.test_server,
            add_prov_generated_time=self.add_prov_generated_time,
            suggester_orcid=suggester_orcid,
            derived_from=derived_from,
        )

        np = nanopub.Nanopub(conf=conf, assertion=assertion)
        np_ref = np.metadata.namespace[""]

        np.pubinfo.add((np_ref, NPX.supersedes, rdflib.URIRef(supersedes_np_uri)))
        if introduces is not None:
            np.pubinfo.add((np_ref, NPX.introduces, rdflib.URIRef(introduces)))

        effective_license = self.license if license is _UNSET else license
        add_label_and_license(np, np_ref=np_ref, label=label, license=effective_license)

        return np
