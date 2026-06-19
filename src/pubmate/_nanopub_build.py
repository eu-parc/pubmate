"""Shared internals for building nanopublications (defining and superseding).

Private module: not part of the public API. Holds the construction bits common
to the defining-nanopub builder and the supersession builder so they stay in one
place.
"""

from __future__ import annotations

from typing import Any, Optional

import nanopub
import rdflib
from rdflib.namespace import DCTERMS, RDFS

# Sentinel distinguishing "argument not given" (fall back to a default) from
# "explicitly given None" (suppress that piece of pubinfo).
UNSET: Any = object()

# ORCID used for the throwaway in-memory profile (see ephemeral_profile).
EPHEMERAL_ORCID = "https://orcid.org/0000-0000-0000-0000"


def ephemeral_profile() -> nanopub.Profile:
    """An in-memory profile whose generated keys are never written to disk.

    Use it to build nanopubs for validation when no real signing key is on hand.
    """
    return nanopub.Profile(orcid_id=EPHEMERAL_ORCID, name="pubmate unsigned builder")


def build_conf(
    *,
    profile: nanopub.Profile,
    keyless: bool,
    test_server: bool,
    add_prov_generated_time: bool,
    suggester_orcid: Optional[str],
    derived_from: Optional[str],
) -> nanopub.NanopubConf:
    """Build a NanopubConf shared by the defining and supersession builders.

    The assertion is attributed to ``suggester_orcid`` (never the signer; passing
    both would raise). Publication is attributed to the profile only when a real
    profile was supplied, so an ephemeral keyless profile is not embedded.
    """
    return nanopub.NanopubConf(
        profile=profile,
        use_test_server=test_server,
        add_prov_generated_time=add_prov_generated_time,
        add_pubinfo_generated_time=True,
        assertion_attributed_to=suggester_orcid,
        attribute_assertion_to_profile=False,
        attribute_publication_to_profile=not keyless,
        derived_from=derived_from,
    )


def add_label_and_license(
    np: nanopub.Nanopub,
    *,
    np_ref: rdflib.term.Identifier,
    label: Optional[str],
    license: Optional[str],
) -> None:
    """Add optional ``rdfs:label`` and ``dct:license`` triples to pubinfo."""
    if label:
        np.pubinfo.add((np_ref, RDFS.label, rdflib.Literal(label)))
    if license:
        np.pubinfo.add((np_ref, DCTERMS.license, rdflib.URIRef(license)))
