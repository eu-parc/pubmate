"""Build a self-signed agent **introduction** (key-declaration) nanopublication.

An introduction declares a software agent (a publishing *bot*) and binds it to
the RSA key it signs with, so consumers can verify that later nanopubs
``npx:signedBy`` that agent really come from it. The agent is a fresh URI minted
*inside* the introduction itself (``…/np/RA<code>/<bot>``), typed ``npx:Bot`` /
``npx:SoftwareAgent`` and ``frbr:owner``ed by a human ORCID; the introduction is
**self-signed** by the agent's own key. This mirrors the nanopub-community
``declaredBy`` pattern (e.g. the ai-in-edu-bot introduction).

The agent URI only exists once the artifact code is computed at signing time, so
— exactly like scheme A on a thing URI — the URI is written with the
``~~~ARTIFACTCODE~~~`` placeholder (including in the signing profile's identity,
so ``npx:signedBy`` resolves to the agent). nanopub-py substitutes the real code
into every occurrence when :meth:`nanopub.Nanopub.sign` runs.

The builder is identity-agnostic: pass the bot name, the owner ORCID, and the
bot's keypair. It returns an *unsigned* nanopub — the caller signs (and decides
whether to publish).
"""

from __future__ import annotations

import pathlib
from typing import Iterable, Optional, Union

import nanopub
import rdflib
from rdflib.namespace import DCTERMS, RDF

from nanopub.definitions import ARTIFACTCODE_PLACEHOLDER
from nanopub.namespaces import NPX

from pubmate.defining import DEFAULT_LICENSE

#: The nanopub URI namespace; the introduced agent is a sub-URI under the
#: introduction's own (placeholder) artifact code.
NP_NAMESPACE = "https://w3id.org/np/"

FOAF = rdflib.Namespace("http://xmlns.com/foaf/0.1/")
FRBR = rdflib.Namespace("http://purl.org/vocab/frbr/core#")
NTEMPLATE = rdflib.Namespace("https://w3id.org/np/o/ntemplate/")

#: Default RDF types for the introduced publishing agent.
DEFAULT_AGENT_TYPES = (NPX.Bot, NPX.SoftwareAgent)

#: The community "declare a key / introduce an agent" assertion template. Tools
#: like Nanodash use ``nt:wasCreatedFromTemplate`` to render the nanopub with the
#: right form/labels, so we tag the introduction with it by default.
DEFAULT_INTRO_TEMPLATE = "https://w3id.org/np/RAbn04KkfbV5PK2UDGkp-j7RUghs_y75DL4qWl_8zQQ3w"


def _agent_uri(local_name: str) -> rdflib.URIRef:
    """A self-URI under the introduction's (placeholder) artifact code."""
    return rdflib.URIRef(f"{NP_NAMESPACE}{ARTIFACTCODE_PLACEHOLDER}/{local_name}")


def build_introduction(
    *,
    private_key: Union[str, pathlib.Path],
    public_key: Union[str, pathlib.Path],
    bot_name: str,
    owner_orcid: str,
    bot_local_name: str = "bot",
    owner_name: Optional[str] = None,
    agent_types: Iterable[rdflib.URIRef] = DEFAULT_AGENT_TYPES,
    license: Optional[str] = DEFAULT_LICENSE,
    keydecl_local_name: str = "keydecl",
    template: Optional[str] = DEFAULT_INTRO_TEMPLATE,
    test_server: bool = False,
) -> nanopub.Nanopub:
    """Build an unsigned, self-signing agent-introduction nanopublication.

    Args:
        private_key: the bot's base64 RSA private key (PEM/DER string or path).
        public_key: the matching base64 RSA public key (string or path); also
            embedded in the key declaration (``npx:hasPublicKey``).
        bot_name: the agent's ``foaf:name`` (e.g. ``"Biochementity bot"``).
        owner_orcid: ORCID URI of the human who owns/attributes the agent
            (``frbr:owner`` + provenance ``prov:wasAttributedTo``).
        bot_local_name: the agent URI's local segment (``…/RA<code>/<here>``).
        owner_name: optional ``foaf:name`` for the owner ORCID, added to pubinfo.
        agent_types: RDF types for the agent (default ``npx:Bot`` /
            ``npx:SoftwareAgent``).
        license: pubinfo ``dcterms:license`` (default CC BY 4.0); ``None`` omits.
        keydecl_local_name: local segment for the key-declaration node.
        template: ``nt:wasCreatedFromTemplate`` value (the introduction template,
            so Nanodash & co. render the nanopub nicely); ``None`` omits it.
        test_server: target the nanopub test server when later published.

    Returns:
        an unsigned :class:`nanopub.Nanopub`. Call ``.sign()`` (the artifact code
        replaces the placeholder everywhere, including ``npx:signedBy``), then
        optionally ``.publish()``.
    """
    agent = _agent_uri(bot_local_name)
    keydecl = _agent_uri(keydecl_local_name)
    owner = rdflib.URIRef(owner_orcid)

    # The agent signs its own introduction: the signing identity *is* the agent
    # URI (placeholder form), so npx:signedBy resolves to it after signing.
    profile = nanopub.Profile(
        orcid_id=str(agent), name=bot_name, private_key=private_key, public_key=public_key
    )
    conf = nanopub.NanopubConf(
        profile=profile,
        use_test_server=test_server,
        add_prov_generated_time=False,
        add_pubinfo_generated_time=True,
        assertion_attributed_to=owner_orcid,
        attribute_assertion_to_profile=False,
        attribute_publication_to_profile=False,
    )

    assertion = rdflib.Graph()
    for t in agent_types:
        assertion.add((agent, RDF.type, t))
    assertion.add((agent, FRBR.owner, owner))
    assertion.add((agent, FOAF.name, rdflib.Literal(bot_name)))
    assertion.add((keydecl, NPX.declaredBy, agent))
    assertion.add((keydecl, NPX.hasAlgorithm, rdflib.Literal("RSA")))
    assertion.add((keydecl, NPX.hasPublicKey, rdflib.Literal(profile.public_key)))

    np = nanopub.Nanopub(conf=conf, assertion=assertion)
    np_ref = np.metadata.namespace[""]
    np.pubinfo.add((np_ref, NPX.introduces, agent))
    np.pubinfo.add((np_ref, DCTERMS.creator, agent))
    np.pubinfo.add((np_ref, NPX.hasNanopubType, NPX.declaredBy))
    if template is not None:
        np.pubinfo.add((np_ref, NTEMPLATE.wasCreatedFromTemplate, rdflib.URIRef(template)))
    if license is not None:
        np.pubinfo.add((np_ref, DCTERMS.license, rdflib.URIRef(license)))
    if owner_name:
        np.pubinfo.add((owner, FOAF.name, rdflib.Literal(owner_name)))

    return np
