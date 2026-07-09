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
- `pubmate-download-nanopubs`
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

### 6) Download published nanopubs from a query endpoint

Use `pubmate-download-nanopubs` when a query endpoint returns the nanopublication
URIs you want to mirror locally. The endpoint should return SPARQL results JSON;
by default Pubmate reads nanopub URIs from the `np` binding and downloads each one
as `<nanopub-uri>.trig`.

You can pass a complete endpoint URL:

```bash
pubmate-download-nanopubs \
  "https://query.knowledgepixels.com/api/RA.../your-query?ontology=https%3A%2F%2Fw3id.org%2Fyourspace%2Fvocabulary" \
  --output-dir published \
  --manifest build/nanopub-network-published.tsv
```

Or split filters into repeatable query parameters:

```bash
pubmate-download-nanopubs \
  "https://query.knowledgepixels.com/api/RA.../your-query" \
  --query-param "ontology=https://w3id.org/yourspace/vocabulary" \
  --query-param "ontologyNamespace=https://w3id.org/yourspace/vocabulary" \
  --output-dir published \
  --manifest build/nanopub-network-published.tsv
```

Useful options:
- `--np-column`: read nanopub URIs from a binding other than `np`.
- `--min-count`: fail if the endpoint returns fewer nanopubs than expected.
- `--replace`: replace existing `.trig` files in `--output-dir` with exactly the endpoint result set.
- `--no-validate`: skip parsing each downloaded TriG file as a nanopublication.

## Real-Life Publishing Checklist

Before real publish:
1. Run `pubmate-mint --dry-run` and inspect ID changes.
2. Generate assertion files and manually inspect a few `.ttl` outputs.
3. Run `pubmate-validate-defining`, then `pubmate-mint-publish --dry-run`.
4. Publish a small subset first (e.g., a temporary small assertion folder).
5. Then publish the full batch.
6. Use `pubmate-download-nanopubs --replace` to rebuild the local `published` folder from the network when needed.

## Troubleshooting

- `Missing required options in manual-key mode`:
  - pass the full manual key/profile options, or use `--dry-run --use-testsuite-keys`.
- No files published:
  - verify assertion folder contains `.ttl` files.
- URI prefix differences:
  - published nanopub URIs may use `purl.org` or `w3id.org` prefixes depending on server behavior.
- Download endpoint returns no nanopubs:
  - verify the endpoint returns SPARQL results JSON and that nanopub URIs are in the binding named by `--np-column` (`np` by default).
