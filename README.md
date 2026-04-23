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
- `pubmate-publish`

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

### 4) Dry-run publication flow (safe first pass)

This signs and builds nanopubs but does not publish (`--dry-run`).

```bash
pubmate-publish \
  --assertion-folder assertions \
  --orcid-id https://orcid.org/0000-0000-0000-0000 \
  --name "Your Name" \
  --private-key /path/to/id_rsa \
  --public-key /path/to/id_rsa.pub \
  --intro-nanopub-uri https://w3id.org/np/RA... \
  --dry-run
```

### 5) Publish to nanopub server (real publication)

Same command, without `--dry-run`:

```bash
pubmate-publish \
  --assertion-folder assertions \
  --orcid-id https://orcid.org/0000-0000-0000-0000 \
  --name "Your Name" \
  --private-key /path/to/id_rsa \
  --public-key /path/to/id_rsa.pub \
  --intro-nanopub-uri https://w3id.org/np/RA...
```

## Using Testsuite Keys (No Personal Secrets)

For local/CI dry-run checks, you can use nanopub testsuite keys:

```bash
pubmate-publish \
  --assertion-folder assertions \
  --dry-run \
  --use-testsuite-keys
```

This avoids passing personal key files.

Advanced overrides exist for testsuite key/ref (hidden from normal help):
- `--testsuite-key` (default `rsa-key1`)
- `--testsuite-ref` (default `main`)

## Real-Life Publishing Checklist

Before real publish:
1. Run `pubmate-mint --dry-run` and inspect ID changes.
2. Generate assertion files and manually inspect a few `.ttl` outputs.
3. Run `pubmate-publish --dry-run` first.
4. Publish a small subset first (e.g., a temporary small assertion folder).
5. Then publish the full batch.

## Troubleshooting

- `Missing required options in manual-key mode`:
  - pass the full manual key/profile options, or use `--dry-run --use-testsuite-keys`.
- No files published:
  - verify assertion folder contains `.ttl` files.
- URI prefix differences:
  - published nanopub URIs may use `purl.org` or `w3id.org` prefixes depending on server behavior.
