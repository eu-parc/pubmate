"""Builder for nanopubs that update a term's definition.

An update re-states a term against its already-minted, fixed URI (its trusty
artifact-code URI), not the placeholder. When the nanopub is signed, only its
*own* artifact code is computed; the fixed URIs of this and other terms are
preserved.

Every update carries ``npx:introduces`` for the term: the vocabulary queries only
count nanopubs that introduce the class, so an update without it hides the term
(eu-parc/pubmate#17). It links to the definition it replaces in one of two ways:

* **supersede** -- ``npx:supersedes`` the previous nanopub. This invalidates it,
  but only takes effect when both are signed with the same key.
* **override** -- ``prov:wasDerivedFrom`` the previous nanopub, in the pubinfo.
  For a previous definition signed with another key (another bot, an edit in
  Nanodash): the newer definition wins in the vocabulary queries, as with
  Nanodash's own overrides.

This is offline friendly: it does not fetch or key-check the previous nanopub
(unlike ``nanopub.NanopubUpdate``); the caller decides which link applies (see
:mod:`pubmate.current`).
"""

from __future__ import annotations

from typing import Optional, Sequence

import nanopub
import rdflib

from nanopub.namespaces import NPX
from rdflib.namespace import PROV

from pubmate._nanopub_build import (
    UNSET as _UNSET,
    add_label_and_license,
    add_pubinfo_tags,
    build_conf,
    ephemeral_profile,
    relabel_blank_nodes,
)
from pubmate.defining import DEFAULT_LICENSE


class SupersessionBuilder:
    """Build an unsigned nanopub that updates (supersedes or overrides) a definition.

    Configure once with a signing ``profile`` (omit it to build keyless for
    validation, like the defining builder), then call :meth:`build` per update.
    The assertion must use the term's fixed URIs; pass the term it introduces
    and the URI of the nanopub being superseded or overridden.
    """

    def __init__(
        self,
        *,
        profile: Optional[nanopub.Profile] = None,
        license: Optional[str] = DEFAULT_LICENSE,
        test_server: bool = False,
        add_prov_generated_time: bool = True,
        nanopub_types: Optional[Sequence[str]] = None,
        template: Optional[str] = None,
    ):
        self.license = license
        self.test_server = test_server
        self.add_prov_generated_time = add_prov_generated_time
        #: ``npx:hasNanopubType`` value(s) tagged on every nanopub's pubinfo.
        self.nanopub_types = tuple(nanopub_types) if nanopub_types else ()
        #: ``nt:wasCreatedFromTemplate`` value tagged on every nanopub's pubinfo.
        self.template = template

        self._keyless = profile is None
        self.profile = profile if profile is not None else ephemeral_profile()

    def build(
        self,
        assertion: rdflib.Graph,
        *,
        introduces: str,
        supersedes_np_uri: Optional[str] = None,
        overrides_np_uri: Optional[str] = None,
        suggester_orcid: Optional[str] = None,
        label: Optional[str] = None,
        license: Optional[str] = _UNSET,
        derived_from: Optional[str] = None,
    ) -> nanopub.Nanopub:
        """Wrap an updated ``assertion`` into an unsigned updating nanopub.

        Args:
            assertion: the term's updated graph, written against its fixed URI.
            introduces: the term's URI, for pubinfo ``npx:introduces``.
            supersedes_np_uri: the nanopub this one supersedes (same key).
            overrides_np_uri: the nanopub this one overrides (another key),
                linked with pubinfo ``prov:wasDerivedFrom``. Give exactly one of
                the two.
            suggester_orcid: ORCID the assertion is attributed to.
            label: optional ``rdfs:label`` for the nanopub.
            license: pubinfo ``dct:license``; defaults to the builder's license,
                pass ``None`` to omit.
            derived_from: optional ``prov:wasDerivedFrom`` source of the
                assertion (provenance).
        """
        if len(assertion) == 0:
            raise ValueError("assertion graph is empty; an update needs at least one triple.")
        if not introduces:
            raise ValueError("introduces is required: an update must introduce the term (pubmate#17).")
        if bool(supersedes_np_uri) == bool(overrides_np_uri):
            raise ValueError("give exactly one of supersedes_np_uri (same key) and overrides_np_uri (another key).")

        conf = build_conf(
            profile=self.profile,
            keyless=self._keyless,
            test_server=self.test_server,
            add_prov_generated_time=self.add_prov_generated_time,
            suggester_orcid=suggester_orcid,
            derived_from=derived_from,
        )

        np = nanopub.Nanopub(conf=conf, assertion=relabel_blank_nodes(assertion))
        np_ref = np.metadata.namespace[""]

        if supersedes_np_uri:
            np.pubinfo.add((np_ref, NPX.supersedes, rdflib.URIRef(supersedes_np_uri)))
        else:
            np.pubinfo.add((np_ref, PROV.wasDerivedFrom, rdflib.URIRef(overrides_np_uri)))
        np.pubinfo.add((np_ref, NPX.introduces, rdflib.URIRef(introduces)))

        effective_license = self.license if license is _UNSET else license
        add_label_and_license(np, np_ref=np_ref, label=label, license=effective_license)
        add_pubinfo_tags(np, np_ref=np_ref, nanopub_types=self.nanopub_types, template=self.template)

        return np
