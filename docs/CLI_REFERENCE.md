# CLI Reference

Every command is invoked as `python -m data_fetcher.demo ...` (or `data-fetcher ...`
after `pip install -e .`). All commands read connection settings from `.env`, the
environment, or `docker-compose.yml` defaults, in that order.

Exit codes: `0` success, `1` runtime failure (not found, database error, validation
failure), `2` bad invocation.

## Acquisition

```bash
python -m data_fetcher.demo http://127.0.0.1:8000/ok
```

Runs a controlled fetch and prints the provenance record as JSON. `fetch <url>` is
the explicit form of the same operation.

## Corpus inspection

| Command | Purpose |
|---|---|
| `phase2 inventory` | Data inventory and profiling across all raw artifacts |
| `phase2 inspect <artifact-id>` | Inspect a single artifact |
| `phase2 extract <artifact-id>` | Extract the canonical representation |
| `phase2 quality <artifact-id>` | Report quality signals for a canonical document |
| `phase2 deduplicate [--threshold N]` | Detect duplicate groups across normalized documents (default threshold `0.85`) |

`deduplicate` clears previously stored duplicate data so re-runs are idempotent.

## Dataset construction

The dataset flow is: define a specification, check feasibility, build, validate,
export. `phase2 run` chains the last four stages.

### `phase2 spec create <name> --file <spec.json> [--description <text>]`

Validates the JSON against the specification schema and stores it as version 1.
Fails with exit `1` if a specification of that name and version already exists.
See [`examples/dataset_spec.example.json`](../examples/dataset_spec.example.json)
for a complete specification.

```bash
python -m data_fetcher.demo phase2 spec create my-dataset \
  --file examples/dataset_spec.example.json \
  --description "First cut"
```

### `phase2 spec list [--status <status>]`

Lists stored specifications with name, version, status, and hash prefix.

### `phase2 spec show <name> [version]`

Prints the specification metadata and its canonical body. Version defaults to `1`.

### `phase2 feasibility <spec-name> [version]`

Runs stage-by-stage eligibility analysis (format, language, length, quality,
deduplication) against the current corpus and persists the report. Reports
`pass`, `fail`, or `blocked` (the latter when there are no normalized documents at
all) along with blockers, warnings, and distributions. Does not build anything.

### `phase2 build <spec-name> [version]`

Constructs the dataset: applies the specification rules, selects deduplication
representatives, and records an accept/reject decision with reason codes and
threshold values for every candidate. Prints the build id needed by the following
two commands.

### `phase2 validate <build-id>`

Runs the ten pre-export checks (schema, required fields, counts, duplicate
leakage, language, quality, content length, provenance, specification compliance,
rejection accounting) and persists the report. Exits `1` when
`overall_status` is `invalid`; warnings alone still exit `0`.

### `phase2 export <build-id> --output <dir>`

Writes the JSONL package. Reuses the most recent persisted validation report for
the build; if none exists it warns on stderr and records `not_validated` in
`validation_report.json`.

Produces six files in `<dir>`:

| File | Contents |
|---|---|
| `data.jsonl` | Accepted records |
| `rejected.jsonl` | Rejected candidates with reason codes, actual values, thresholds |
| `provenance.jsonl` | Per-record lineage back to the source URL |
| `manifest.json` | Specification hash, source snapshot, counts, validation status, record checksums |
| `statistics.json` | Counts, rejection reason breakdown, acceptance rate |
| `validation_report.json` | Full validation report |

### `phase2 run <spec-name> [version] --output <dir> [--skip-feasibility] [--allow-invalid]`

Runs feasibility, build, validate, and export in one pass, printing each stage.
Aborts before building if feasibility is `fail` or `blocked`, and before exporting
if validation is `invalid`. `--allow-invalid` overrides both gates;
`--skip-feasibility` omits the first stage.

```bash
python -m data_fetcher.demo phase2 run my-dataset --output output/my-dataset
```

## Worked example

```bash
docker compose up -d
python -m data_fetcher.demo phase2 spec create demo-001 --file examples/dataset_spec.example.json
python -m data_fetcher.demo phase2 run demo-001 --output output/demo-001
```

The discrete equivalent, when you want to inspect each stage:

```bash
python -m data_fetcher.demo phase2 feasibility demo-001
python -m data_fetcher.demo phase2 build demo-001          # prints <build-id>
python -m data_fetcher.demo phase2 validate <build-id>
python -m data_fetcher.demo phase2 export <build-id> --output output/demo-001
```

Both paths produce the same accepted records and rejection reasons; only the
build id, record ids, and timestamps differ.


