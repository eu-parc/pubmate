"""Incremental mint/update publishing.

Re-runnable publishing of defining nanopubs. Each term is one of:

* **new** -- neither in the id-map nor given as a minted (trusty) URI: mint a
  defining nanopub, record its thing/nanopub URIs and fingerprint.
* **unchanged** -- skip, and carry its id-map row forward.
* **changed** -- publish an *update*: re-state the assertion against the term's
  **existing fixed thing URI** (so the term keeps its identity), with every
  inter-term reference resolved to its thing URI via the id-map
  (:func:`pubmate.references.resolve_references`). The update always carries
  ``npx:introduces`` for the term, which the vocabulary queries require
  (eu-parc/pubmate#17). The id-map's ``np_uri``/``fingerprint`` move to the new
  version.

A term is matched against the id-map by **either identifier**: the old id the map
is keyed by, or the minted thing URI it resolved to (:meth:`pubmate.idmap.IdMap.resolve`).
Whichever form was submitted, the id-map row stays keyed by the original old id.
References inside a re-submitted assertion may likewise use either form.

**With current definitions** (``current``, see :mod:`pubmate.current`), the
network decides, not the id-map:

* unchanged means the resolved assertion equals the assertion of the term's
  current definition; the id-map row is then re-pointed at that definition, and
  its fingerprint becomes the verified baseline. So rows without a fingerprint
  are compared properly instead of being assumed unchanged.
* the update supersedes the current definition when it was signed with the same
  key, and overrides it (``prov:wasDerivedFrom``) otherwise -- e.g. after an edit
  in Nanodash or another bot's override.
* a term in the id-map that has no current definition (withdrawn, or not
  approved) counts as changed, and the update overrides the definition the
  id-map recorded.
* a minted URI that is not in the id-map but has a current definition is updated
  like any other term, instead of getting a second, unlinked definition.

**Without them** (offline), changes are detected with the id-map fingerprint and
updates supersede the recorded nanopub; the caller must make sure it was signed
with the same key. A row without a fingerprint is assumed unchanged and its
fingerprint is backfilled (with a warning): without the network there is no
baseline to compare against.

I/O (reading assertions, writing trig/id-map) is left to the caller/CLI, mirroring
:func:`pubmate.migrate.migrate_terms`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List, Optional, Sequence

import rdflib

from pubmate._nanopub_build import UNSET as _UNSET, preferred_label
from pubmate.current import CurrentDefinitions, normalize_key
from pubmate.fingerprint import fingerprint_term
from pubmate.idmap import IdMap, IdMapEntry
from pubmate.migrate import MintedSupersession
from pubmate.minting import MintBatch, MintedTerm, SequentialMinter, TermInput, is_trusty_thing_uri
from pubmate.rdf2nanopub import sign_and_publish
from pubmate.references import resolve_references
from pubmate.supersede import SupersessionBuilder

logger = logging.getLogger(__name__)


@dataclass
class IncrementalResult:
    """The outcome of an incremental publish run."""

    minted: MintBatch = field(default_factory=MintBatch)
    #: updates of changed terms (supersessions and overrides).
    superseded: List[MintedSupersession] = field(default_factory=list)
    #: term_ids that were unchanged and skipped (includes backfilled legacy rows).
    skipped: List[str] = field(default_factory=list)
    id_map: IdMap = field(default_factory=IdMap)


def publish_incremental(
    terms: Sequence[TermInput],
    *,
    minter: SequentialMinter,
    supersession_builder: SupersessionBuilder,
    existing: Optional[IdMap] = None,
    dry_run: bool = True,
    current: Optional[CurrentDefinitions] = None,
) -> IncrementalResult:
    """Mint new terms, skip unchanged ones, and publish updates for changed ones.

    Args:
        terms: the terms to publish (assertions keyed on the builder's placeholder
            thing URI, e.g. from ``term_input_from_assertion``).
        minter: a :class:`~pubmate.minting.SequentialMinter` carrying the defining
            builder + signing profile.
        supersession_builder: a :class:`~pubmate.supersede.SupersessionBuilder`
            configured with the *same* signing profile/wrapper, used for updates.
        existing: id-map from previous runs (fingerprints included where known).
        dry_run: sign only (offline), do not publish.
        current: the terms' current definitions on the network (see the module
            docstring). Omit only for offline use.

    Returns an :class:`IncrementalResult` whose ``id_map`` is the complete,
    updated map (existing entries carried forward, plus new/updated/backfilled).
    """
    result = IncrementalResult(id_map=IdMap(list(existing or [])))
    placeholder = minter.builder.thing_uri
    namespace = minter.builder.namespace
    default_suggester = minter.default_suggester_orcid
    own_key = normalize_key(supersession_builder.profile.public_key)

    for term in terms:
        entry = result.id_map.resolve(term.term_id)
        already_trusty = is_trusty_thing_uri(term.term_id, namespace=namespace)
        fingerprint_introduces = (
            term.term_id
            if (entry is None and already_trusty)
            or (
                entry is not None
                and entry.old_id == entry.thing_uri
                and is_trusty_thing_uri(entry.thing_uri, namespace=namespace)
            )
            else _UNSET
        )
        current_fp = fingerprint_term(
            term,
            minter.builder,
            default_suggester=default_suggester,
            introduces=fingerprint_introduces,
        )

        if entry is None and not already_trusty:
            minted = minter.mint(term, dry_run=dry_run)
            result.id_map.add(IdMapEntry(term.term_id, minted.thing_uri, minted.np_uri, current_fp), overwrite=True)
            result.minted.terms.append(minted)
            continue

        if entry is not None and entry.old_id != term.term_id:
            logger.info(
                "Resolved submitted id %s to existing term %s via its thing URI.",
                term.term_id,
                entry.old_id,
            )
        old_id = entry.old_id if entry is not None else term.term_id
        thing = entry.thing_uri if entry is not None else term.term_id
        fixed = rdflib.URIRef(thing)
        full = resolve_references(
            term.assertion,
            namespace=namespace,
            subject=placeholder,
            new_subject=fixed,
            thing_uris=result.id_map.resolution_map,
        )
        label = term.label or preferred_label(full, fixed)
        suggester = term.suggester_orcid or default_suggester

        definition = current.get(thing) if current is not None else None
        previous_np = definition.np_uri if definition is not None else (entry.np_uri if entry is not None else None)

        if previous_np is None:
            # A minted URI with no id-map row and no current definition: publish
            # its (first) defining nanopub as given, without re-minting the URI.
            np = minter.builder.build(
                full,
                suggester_orcid=suggester,
                label=label,
                derived_from=term.derived_from,
                introduces=thing,
            )
            np_uri = sign_and_publish(np, dry_run=dry_run)
            logger.info("Published already-minted term %s -> %s", thing, np_uri)
            result.id_map.add(IdMapEntry(thing, thing, np_uri, current_fp), overwrite=True)
            result.minted.terms.append(MintedTerm(term_id=thing, thing_uri=thing, np_uri=np_uri, nanopub=np))
            continue

        if definition is not None:
            unchanged = definition.same_content(full)
        elif current is not None:
            logger.info("Term %s has no current definition (withdrawn or not approved); re-publishing it.", old_id)
            unchanged = False
        elif entry.fingerprint == "":
            logger.warning(
                "Backfilling baseline fingerprint for legacy term (no prior fingerprint "
                "to compare against and no current definitions given; adopting current "
                "build as baseline): %s",
                old_id,
            )
            unchanged = True
        else:
            unchanged = entry.fingerprint == current_fp

        if unchanged:
            logger.info("Skipping unchanged term: %s", old_id)
            result.id_map.add(IdMapEntry(old_id, thing, previous_np, current_fp), overwrite=True)
            result.skipped.append(old_id)
            continue

        if definition is not None:
            dropped = set(definition.assertion.predicates(fixed)) - set(full.predicates(fixed))
            if dropped:
                logger.warning(
                    "The update of %s drops all of its %s statements, which the submission does not state.",
                    old_id,
                    ", ".join(sorted(map(str, dropped))),
                )

        # Supersede only what our own key signed (or, offline, what the id-map
        # recorded); override anything else.
        supersede = current is None or (definition is not None and bool(own_key) and definition.public_key == own_key)
        link = {"supersedes_np_uri": previous_np} if supersede else {"overrides_np_uri": previous_np}
        sup_np = supersession_builder.build(
            full,
            introduces=thing,
            label=label,
            suggester_orcid=suggester,
            derived_from=term.derived_from,
            **link,
        )
        sup_uri = sign_and_publish(sup_np, dry_run=dry_run)
        kind = "supersede" if supersede else "override"
        logger.info("Updated term %s (%s %s) -> %s", old_id, kind, previous_np, sup_uri)
        result.id_map.add(IdMapEntry(old_id, thing, sup_uri, current_fp), overwrite=True)
        result.superseded.append(
            MintedSupersession(
                term_id=old_id,
                supersedes_np_uri=previous_np,
                np_uri=sup_uri,
                nanopub=sup_np,
                kind=kind,
            )
        )

    return result
