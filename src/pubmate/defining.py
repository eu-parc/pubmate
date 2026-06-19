"""Defining-nanopub builder.

Build an *unsigned* nanopublication that defines a single term, with the term's
"thing" URI carrying the trusty artifact-code placeholder
(``~~~ARTIFACTCODE~~~``). When the nanopub is signed, nanopub-py substitutes the
computed artifact code for the placeholder wherever it appears, so the code
lands on the thing URI in a caller-chosen namespace while the nanopub URI keeps
the default ``w3id.org/np`` form.

Keep the defining assertion to a term's *intrinsic* properties. References to
other terms that may not be minted yet (or that form cycles) are best added
afterwards by superseding, once every referenced term has a stable URI.
"""

from __future__ import annotations

from typing import Any, Iterable, Optional, Tuple

import nanopub
import rdflib
from rdflib.namespace import DCTERMS, RDFS

from nanopub.definitions import ARTIFACTCODE_PLACEHOLDER
from nanopub.namespaces import NPX

# A sensible default license for openly published nanopubs (CC BY 4.0). Override
# per project via the ``license`` argument, or pass ``None`` to omit it.
DEFAULT_LICENSE = "https://creativecommons.org/licenses/by/4.0/"

# Sentinel distinguishing "argument not given" (fall back to builder/default
# behaviour) from "explicitly given None" (suppress that piece of pubinfo).
_UNSET: Any = object()


class DefiningNanopubBuilder:
    """Turn a term assertion into an unsigned defining nanopublication.

    The builder is configured with the *thing namespace* (e.g.
    ``https://example.org/terms/``); the term subject is always
    :attr:`thing_uri`, the namespace concatenated with the artifact-code
    placeholder. Build the assertion against that subject (use
    :meth:`make_assertion` or :attr:`thing_uri` directly), then :meth:`build`
    wraps it into a nanopub.

    A real :class:`nanopub.Profile` (e.g. a signing keypair) is only needed to
    *sign* at publish time. Omit ``profile`` to build for validation only: the
    builder uses an ephemeral in-memory profile whose generated keys are never
    written to disk, and does not attribute publication to it.
    """

    def __init__(
        self,
        namespace: str,
        *,
        profile: Optional[nanopub.Profile] = None,
        license: Optional[str] = DEFAULT_LICENSE,
        test_server: bool = False,
        add_prov_generated_time: bool = True,
    ):
        if not namespace:
            raise ValueError(
                "namespace is required (e.g. 'https://example.org/terms/')."
            )
        self.namespace = namespace
        self.license = license
        self.test_server = test_server
        self.add_prov_generated_time = add_prov_generated_time

        self._keyless = profile is None
        self.profile = profile if profile is not None else nanopub.Profile(
            orcid_id="https://orcid.org/0000-0000-0000-0000",
            name="pubmate unsigned builder",
        )

    @property
    def thing_uri(self) -> rdflib.URIRef:
        """Placeholder thing URI used as the defining assertion's subject."""
        return rdflib.URIRef(f"{self.namespace}{ARTIFACTCODE_PLACEHOLDER}")

    def make_assertion(self, statements: Iterable[Tuple[Any, Any]]) -> rdflib.Graph:
        """Build an assertion graph keyed on :attr:`thing_uri`.

        ``statements`` is an iterable of ``(predicate, object)`` pairs; the
        subject is always the thing URI. String predicates are coerced to
        ``URIRef``; objects must already be rdflib terms (``URIRef``/``Literal``/
        ``BNode``) so that IRI-vs-literal intent stays explicit. Pass only the
        term's *intrinsic* properties here.
        """
        graph = rdflib.Graph()
        subject = self.thing_uri
        for predicate, obj in statements:
            pred = predicate if isinstance(predicate, rdflib.term.Identifier) else rdflib.URIRef(predicate)
            if not isinstance(obj, rdflib.term.Identifier):
                raise TypeError(
                    f"Object for predicate {pred} must be an rdflib term "
                    f"(URIRef/Literal/BNode), got {type(obj).__name__}."
                )
            graph.add((subject, pred, obj))
        return graph

    def build(
        self,
        assertion: rdflib.Graph,
        *,
        suggester_orcid: Optional[str] = None,
        label: Optional[str] = None,
        license: Optional[str] = _UNSET,
        derived_from: Optional[str] = None,
        introduces: Optional[str] = _UNSET,
    ) -> nanopub.Nanopub:
        """Wrap a defining ``assertion`` into an unsigned nanopublication.

        Args:
            assertion: the term's intrinsic-property graph (subject = thing URI).
            suggester_orcid: ORCID the assertion is attributed to via
                ``prov:wasAttributedTo`` (the suggester, never the signer).
            label: optional ``rdfs:label`` for the nanopub in pubinfo.
            license: pubinfo ``dct:license``; defaults to the builder's license,
                pass ``None`` to omit.
            derived_from: optional ``prov:wasDerivedFrom`` source.
            introduces: pubinfo ``npx:introduces``; defaults to the thing URI,
                pass ``None`` to omit.
        """
        if len(assertion) == 0:
            raise ValueError("assertion graph is empty; a defining nanopub needs at least one triple.")

        conf = nanopub.NanopubConf(
            profile=self.profile,
            use_test_server=self.test_server,
            add_prov_generated_time=self.add_prov_generated_time,
            add_pubinfo_generated_time=True,
            # Attribute the assertion to the suggester, never to the signer/profile;
            # passing both would raise MalformedNanopubError.
            assertion_attributed_to=suggester_orcid,
            attribute_assertion_to_profile=False,
            # Publication is attributed to the real signer at publish time; keep it
            # off for keyless validation builds so the ephemeral profile is not embedded.
            attribute_publication_to_profile=not self._keyless,
            derived_from=derived_from,
        )

        np = nanopub.Nanopub(conf=conf, assertion=assertion)
        np_ref = np.metadata.namespace[""]

        if introduces is _UNSET:
            introduces = self.thing_uri
        if introduces is not None:
            np.pubinfo.add((np_ref, NPX.introduces, rdflib.URIRef(introduces)))

        if label:
            np.pubinfo.add((np_ref, RDFS.label, rdflib.Literal(label)))

        effective_license = self.license if license is _UNSET else license
        if effective_license:
            np.pubinfo.add((np_ref, DCTERMS.license, rdflib.URIRef(effective_license)))

        return np
