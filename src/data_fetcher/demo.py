from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from uuid import UUID

from data_fetcher.runner import run_controlled_fetch
from data_fetcher.phase2.cli import run_phase2, cmd_feasibility


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    if not argv:
        parser = argparse.ArgumentParser(prog="python -m data_fetcher.demo")
        parser.add_argument("url", nargs="?", help="URL to fetch")
        parser.add_argument("phase2", nargs="?", help="Phase 2 subcommands")
        parser.add_argument("fetch", nargs="?", help="Fetch a URL")
        parser.print_usage(sys.stderr)
        print("error: the following arguments are required: url", file=sys.stderr)
        return 2
    # Top-level help only. When a command is named, let argparse render the
    # help for that command's own subparser instead.
    if argv[0] not in ("phase2", "fetch") and ("--help" in argv or "-h" in argv):
        parser = argparse.ArgumentParser(
            description="Data Fetcher Ubuntu - acquisition and dataset construction CLI"
        )
        parser.add_argument("url", nargs="?", help="URL to fetch")
        parser.add_argument("phase2", nargs="?", help="Phase 2 subcommands")
        parser.add_argument("fetch", nargs="?", help="Fetch a URL")
        parser.print_help(sys.stderr)
        return 0
    if argv[0] not in ("phase2", "fetch"):
        provenance = run_controlled_fetch(argv[0])
        normalized = {}
        for key, value in provenance.items():
            if isinstance(value, datetime):
                normalized[key] = value.isoformat()
            elif isinstance(value, UUID):
                normalized[key] = str(value)
            else:
                normalized[key] = value
        print(json.dumps(normalized, indent=2, sort_keys=True))
        return 0

    parser = argparse.ArgumentParser(
        description="Data Fetcher Ubuntu - acquisition and dataset construction CLI"
    )
    subparsers = parser.add_subparsers(dest="command")

    # phase2 subcommands
    phase2_parser = subparsers.add_parser("phase2", help="Phase 2 dataset construction commands")
    phase2_subparsers = phase2_parser.add_subparsers(dest="phase2_command")

    # data-fetcher phase2 inventory
    inventory_parser = phase2_subparsers.add_parser("inventory", help="Run data inventory and profiling")

    # data-fetcher phase2 inspect <artifact-id>
    inspect_parser = phase2_subparsers.add_parser("inspect", help="Inspect a single artifact")
    inspect_parser.add_argument("artifact_id", help="Artifact UUID to inspect")

    # data-fetcher phase2 extract <artifact-id>
    extract_parser = phase2_subparsers.add_parser("extract", help="Extract canonical representation of an artifact")
    extract_parser.add_argument("artifact_id", help="Artifact UUID to extract")

    # data-fetcher phase2 quality <artifact-id>
    quality_parser = phase2_subparsers.add_parser("quality", help="Analyze quality signals of a canonical document")
    quality_parser.add_argument("artifact_id", help="Artifact UUID to analyze")

    # data-fetcher phase2 deduplicate
    deduplicate_parser = phase2_subparsers.add_parser("deduplicate", help="Run duplicate detection on normalized documents")
    deduplicate_parser.add_argument("--threshold", type=float, default=0.85, help="Similarity threshold for near-duplicate detection (default: 0.85)")

    # data-fetcher phase2 spec <create|list|show>
    spec_parser = phase2_subparsers.add_parser("spec", help="Manage dataset specifications")
    spec_subparsers = spec_parser.add_subparsers(dest="spec_command")
    spec_create = spec_subparsers.add_parser("create", help="Create a specification from a JSON file")
    spec_create.add_argument("name", help="Specification name")
    spec_create.add_argument("--file", "-f", required=True, help="Path to specification JSON")
    spec_create.add_argument("--description", help="Human-readable description")
    spec_list = spec_subparsers.add_parser("list", help="List stored specifications")
    spec_list.add_argument("--status", help="Filter by status")
    spec_show = spec_subparsers.add_parser("show", help="Show a specification and its canonical body")
    spec_show.add_argument("name", help="Specification name")
    spec_show.add_argument("version", nargs="?", type=int, default=1, help="Specification version (default: 1)")

    # data-fetcher phase2 feasibility <spec-name> [version]
    feasibility_parser = phase2_subparsers.add_parser("feasibility", help="Run feasibility analysis for a dataset specification")
    feasibility_parser.add_argument("spec_name", help="Specification name to analyze")
    feasibility_parser.add_argument("version", nargs="?", type=int, default=1, help="Specification version (default: 1)")

    # data-fetcher phase2 build <spec-name> [version]
    build_parser = phase2_subparsers.add_parser("build", help="Build a governed dataset from a specification")
    build_parser.add_argument("spec_name", help="Specification name to build")
    build_parser.add_argument("version", nargs="?", type=int, default=1, help="Specification version (default: 1)")

    # data-fetcher phase2 validate <build-id>
    validate_parser = phase2_subparsers.add_parser("validate", help="Validate a dataset build before export")
    validate_parser.add_argument("build_id", help="Dataset build UUID to validate")

    # data-fetcher phase2 export <build-id> --output <dir>
    export_parser = phase2_subparsers.add_parser("export", help="Export a dataset build to a JSONL package")
    export_parser.add_argument("build_id", help="Dataset build UUID to export")
    export_parser.add_argument("--output", "-o", required=True, help="Output directory for the export package")

    # data-fetcher phase2 run <spec-name> [version] --output <dir>
    run_parser = phase2_subparsers.add_parser("run", help="Run feasibility, build, validate and export in one pass")
    run_parser.add_argument("spec_name", help="Specification name to run")
    run_parser.add_argument("version", nargs="?", type=int, default=1, help="Specification version (default: 1)")
    run_parser.add_argument("--output", "-o", required=True, help="Output directory for the export package")
    run_parser.add_argument("--skip-feasibility", action="store_true", help="Skip the feasibility stage")
    run_parser.add_argument("--allow-invalid", action="store_true", help="Export even if feasibility or validation fails")

    # Default: controlled fetch
    fetch_parser = subparsers.add_parser("fetch", help="Run a controlled fetch")
    fetch_parser.add_argument("url", nargs="?", help="URL to fetch")

    args = parser.parse_args(argv)

    if args.command == "phase2":
        if not args.phase2_command:
            phase2_parser.print_help(sys.stderr)
            return 2
        # argparse has already validated the grammar; cli.py owns the argument
        # parsing for each subcommand, so forward the original tokens verbatim.
        return run_phase2(argv[1:])

    if args.command == "fetch":
        if not args.url:
            fetch_parser.print_usage(sys.stderr)
            print("error: the following arguments are required: url", file=sys.stderr)
            return 2
        provenance = run_controlled_fetch(args.url)
        normalized = {}
        for key, value in provenance.items():
            if isinstance(value, datetime):
                normalized[key] = value.isoformat()
            elif isinstance(value, UUID):
                normalized[key] = str(value)
            else:
                normalized[key] = value
        print(json.dumps(normalized, indent=2, sort_keys=True))
        return 0

    parser.print_help(sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
