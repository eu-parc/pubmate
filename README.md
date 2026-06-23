# Pubmate CLI Guide

`pubmate` helps you go from vocabulary/source data to publishable nanopublications.

This README focuses on real publishing workflows:
- prepare and normalize vocabulary data
- create per-term assertion graphs
- dry-run sign/publish checks
- publish to nanopub servers

## Install

From this repository:

```bash
uv sync
```

CLI entrypoints provided by this project:
- `pubmate-yamlconcat`
- `pubmate-mint`
- `pubmate-cleanrdf`
- `pubmate-extract-assertions`
- `pubmate-validate-defining`
- `pubmate-mint-publish`

## Typical End-to-End Workflow

### 1) Merge multiple YAML term files (optional)

Use this when your terms are spread across files and you want one container.

```bash
pubmate-yamlconcat combined.yaml terms1.yaml terms2.yaml --target vocabulary_terms
```

### 2) Mint stable IDs for terms

Generate IDs into the `id` field (or another field via `--id-key`).

Preview only:

```bash
pubmate-mint \
  --data combined.yaml \
  --target vocabulary_terms \
  --namespace https://w3id.org/yourspace/term/ \
  --dry-run
```

Write changes:

```bash
pubmate-mint \
  --data combined.yaml \
  --target vocabulary_terms \
  --namespace https://w3id.org/yourspace/term/
```

Notes:
- default method is `hash` (recommended for deterministic IDs)
- use `--force` to regenerate existing IDs

### 3) Convert ontology graph to per-term assertion TTL files

`pubmate-cleanrdf` loads your ontology RDF, normalizes translation blocks into language-tagged literals, and writes one assertion file per subclass of the parent class(es).

```bash
pubmate-cleanrdf \
  --input-ontology-path ontology.ttl \
  --base-namespace https://w3id.org/yourspace/ \
  --term-output-path assertions \
  --term-parent-class your:VocabularyTerm \
  --parent-subclasses your:AdditionalParent
```

Output: `assertions/<term_id>.ttl` files.

### 4) Validate that each assertion forms a defining nanopub (keyless)

`pubmate-validate-defining` wraps each assertion into a defining nanopub and
signs it with an ephemeral in-memory key (no secrets, no network) — a good PR gate.

```bash
pubmate-validate-defining \
  --assertion-folder assertions \
  --namespace https://w3id.org/yourspace/term/
```

### 5) Mint and publish defining nanopubs

`pubmate-mint-publish` re-keys each assertion onto the `~~~ARTIFACTCODE~~~`
placeholder, signs it (which lands the artifact code on the term's thing URI),
and — unless `--dry-run` — publishes it. Minted `.trig` nanopubs go to
`--output-dir`, and the old-id → thing/np-URI mapping is merged into `--id-map-file`.

Dry-run (sign only, offline, ephemeral key):

```bash
pubmate-mint-publish \
  --assertion-folder assertions \
  --namespace https://w3id.org/yourspace/term/ \
  --output-dir published \
  --id-map-file id-map.tsv \
  --dry-run
```

Publish to the nanopub test server with testsuite keys (no personal secrets):

```bash
pubmate-mint-publish \
  --assertion-folder assertions \
  --namespace https://w3id.org/yourspace/term/ \
  --output-dir published \
  --id-map-file id-map.tsv \
  --use-testsuite-keys
```

Real publication uses the bot/personal key instead of `--use-testsuite-keys`:

```bash
pubmate-mint-publish \
  --assertion-folder assertions \
  --namespace https://w3id.org/yourspace/term/ \
  --output-dir published \
  --id-map-file id-map.tsv \
  --orcid-id https://orcid.org/0000-0000-0000-0000 \
  --name "Your Name" \
  --private-key /path/to/id_rsa \
  --public-key /path/to/id_rsa.pub \
  --intro-nanopub-uri https://w3id.org/np/RA...
```

## Real-Life Publishing Checklist

Before real publish:
1. Run `pubmate-mint --dry-run` and inspect ID changes.
2. Generate assertion files and manually inspect a few `.ttl` outputs.
3. Run `pubmate-validate-defining`, then `pubmate-mint-publish --dry-run`.
4. Publish a small subset first (e.g., a temporary small assertion folder).
5. Then publish the full batch.

## Troubleshooting

- `Missing required options in manual-key mode`:
  - pass the full manual key/profile options, or use `--dry-run --use-testsuite-keys`.
- No files published:
  - verify assertion folder contains `.ttl` files.
- URI prefix differences:
  - published nanopub URIs may use `purl.org` or `w3id.org` prefixes depending on server behavior.
