import nanopub
import rdflib

from nanopub.namespaces import NPX
from pubmate._nanopub_build import ephemeral_profile
from pubmate.introduction import DEFAULT_INTRO_TEMPLATE, FOAF, FRBR, NTEMPLATE, build_introduction

OWNER = "https://orcid.org/0000-0002-1267-0234"


def _keys():
    p = ephemeral_profile()  # generates a throwaway RSA keypair in memory
    return p.private_key, p.public_key


def _build(**over):
    priv, pub = _keys()
    kwargs = dict(
        private_key=priv, public_key=pub, bot_name="Biochementity bot",
        owner_orcid=OWNER, bot_local_name="biochementity-bot", owner_name="Tobias Kuhn",
    )
    kwargs.update(over)
    return build_introduction(**kwargs)


def test_introduction_signs_and_is_valid():
    np = _build()
    np.sign()
    assert np.is_valid
    # the artifact-code placeholder must be fully resolved
    assert "~~~ARTIFACTCODE~~~" not in np.rdf.serialize(format="trig")


def test_agent_is_self_signed_and_introduced():
    np = _build()
    np.sign()
    agent = rdflib.URIRef(f"{np.metadata.np_uri}/biochementity-bot")
    np_ref = rdflib.URIRef(np.metadata.np_uri)
    # the introduction introduces the agent and is signed *by* it (self-signed)
    assert (np_ref, NPX.introduces, agent) in np.pubinfo
    assert agent in set(np.pubinfo.objects(None, NPX.signedBy))


def test_agent_typed_owned_and_named():
    np = _build()
    np.sign()
    agent = rdflib.URIRef(f"{np.metadata.np_uri}/biochementity-bot")
    assert (agent, rdflib.RDF.type, NPX.Bot) in np.assertion
    assert (agent, rdflib.RDF.type, NPX.SoftwareAgent) in np.assertion
    assert (agent, FRBR.owner, rdflib.URIRef(OWNER)) in np.assertion
    assert (agent, FOAF.name, rdflib.Literal("Biochementity bot")) in np.assertion


def test_key_declaration_carries_public_key():
    np = _build()
    np.sign()
    decls = list(np.assertion.subject_objects(NPX.hasPublicKey))
    assert len(decls) == 1
    keydecl, pubkey = decls[0]
    assert (keydecl, NPX.hasAlgorithm, rdflib.Literal("RSA")) in np.assertion
    # the declared key matches the key the nanopub is signed with
    assert str(pubkey) in np.rdf.serialize(format="trig")


def test_pubinfo_tags_introduction_template():
    np = _build()
    np.sign()
    np_ref = rdflib.URIRef(np.metadata.np_uri)
    assert (np_ref, NTEMPLATE.wasCreatedFromTemplate, rdflib.URIRef(DEFAULT_INTRO_TEMPLATE)) in np.pubinfo
    # opt-out
    np2 = _build(template=None)
    np2.sign()
    assert not list(np2.pubinfo.objects(None, NTEMPLATE.wasCreatedFromTemplate))


def test_assertion_attributed_to_owner_not_signer():
    np = _build()
    np.sign()
    prov = rdflib.URIRef("http://www.w3.org/ns/prov#wasAttributedTo")
    attributed = set(np.provenance.objects(None, prov))
    assert rdflib.URIRef(OWNER) in attributed
