"""Tests for the Phase 2 dataset CLI commands (spec, build, validate, export, run)."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest

from data_fetcher.phase2 import cli

EXPORT_FILES = (
    "data.jsonl",
    "manifest.json",
    "statistics.json",
    "rejected.jsonl",
    "provenance.jsonl",
    "validation_report.json",
)

VALID_SPEC = {
    "dataset": {"name": "cli-test", "version": 1},
    "source": {"allowed_formats": ["html", "plain_text", "text"]},
    "content": {"minimum_characters": 10, "maximum_characters": 50000},
    "quality": {"minimum_score": 0.5},
    "deduplication": {"mode": "normalized", "similarity_threshold": 0.85},
    "selection": {"maximum_records": 100},
    "output": {"format": "jsonl"},
}


def write_spec(tmp_path: Path, spec: dict, filename: str = "spec.json") -> str:
    path = tmp_path / filename
    path.write_text(json.dumps(spec), encoding="utf-8")
    return str(path)


class TestTakeOption:
    """_take_option extracts flag values without disturbing positionals."""

    def test_extracts_value_and_keeps_positionals(self):
        value, rest = cli._take_option(["name", "--output", "dir"], "--output", "-o")
        assert value == "dir"
        assert rest == ["name"]

    def test_accepts_short_alias(self):
        value, rest = cli._take_option(["-o", "dir", "name"], "--output", "-o")
        assert value == "dir"
        assert rest == ["name"]

    def test_missing_value_raises(self):
        with pytest.raises(ValueError):
            cli._take_option(["name", "--output"], "--output", "-o")

    def test_absent_option_returns_none(self):
        value, rest = cli._take_option(["name", "2"], "--output", "-o")
        assert value is None
        assert rest == ["name", "2"]


class TestArgumentValidation:
    """Commands reject bad invocations before touching the database."""

    def test_spec_requires_action(self, capsys):
        assert cli.cmd_spec([]) == 2
        assert "spec action required" in capsys.readouterr().err

    def test_spec_rejects_unknown_action(self, capsys):
        assert cli.cmd_spec(["destroy"]) == 2
        assert "unknown spec action" in capsys.readouterr().err

    def test_spec_create_requires_name(self, tmp_path, capsys):
        spec_file = write_spec(tmp_path, VALID_SPEC)
        assert cli.cmd_spec(["create", "--file", spec_file]) == 2
        assert "name is required" in capsys.readouterr().err

    def test_spec_create_requires_file(self, capsys):
        assert cli.cmd_spec(["create", "some-name"]) == 2
        assert "--file" in capsys.readouterr().err

    def test_spec_create_rejects_unreadable_file(self, tmp_path, capsys):
        missing = str(tmp_path / "nope.json")
        assert cli.cmd_spec(["create", "n", "--file", missing]) == 1
        assert "cannot read" in capsys.readouterr().err

    def test_spec_create_rejects_malformed_json(self, tmp_path, capsys):
        path = tmp_path / "bad.json"
        path.write_text("{not json", encoding="utf-8")
        assert cli.cmd_spec(["create", "n", "--file", str(path)]) == 1
        assert "not valid JSON" in capsys.readouterr().err

    def test_spec_create_reports_validation_errors(self, tmp_path, capsys):
        spec_file = write_spec(tmp_path, {"dataset": {"name": "", "version": 0}})
        assert cli.cmd_spec(["create", "n", "--file", spec_file]) == 1
        err = capsys.readouterr().err
        assert "validation failed" in err
        assert "dataset.name" in err

    def test_build_requires_spec_name(self, capsys):
        assert cli.cmd_build([]) == 2
        assert "name is required" in capsys.readouterr().err

    def test_build_rejects_non_integer_version(self, capsys):
        assert cli.cmd_build(["some-spec", "latest"]) == 2
        assert "version must be an integer" in capsys.readouterr().err

    def test_validate_requires_build_id(self, capsys):
        assert cli.cmd_validate([]) == 2
        assert "build id is required" in capsys.readouterr().err

    def test_export_requires_build_id(self, capsys):
        assert cli.cmd_export(["--output", "out"]) == 2
        assert "build id is required" in capsys.readouterr().err

    def test_export_requires_output(self, capsys):
        assert cli.cmd_export(["some-build-id"]) == 2
        assert "--output" in capsys.readouterr().err

    def test_run_requires_output(self, capsys):
        assert cli.cmd_run(["some-spec"]) == 2
        assert "--output" in capsys.readouterr().err

    def test_run_requires_spec_name(self, capsys):
        assert cli.cmd_run(["--output", "out"]) == 2
        assert "name is required" in capsys.readouterr().err


class TestDispatcher:
    """run_phase2 advertises and routes the dataset subcommands."""

    def test_no_subcommand_lists_dataset_commands(self, capsys):
        assert cli.run_phase2([]) == 2
        err = capsys.readouterr().err
        for name in ("spec", "build", "validate", "export", "run"):
            assert name in err

    def test_unknown_subcommand_lists_dataset_commands(self, capsys):
        assert cli.run_phase2(["frobnicate"]) == 2
        err = capsys.readouterr().err
        assert "unknown subcommand" in err
        for name in ("spec", "build", "validate", "export", "run"):
            assert name in err

    @pytest.mark.parametrize(
        "argv",
        [
            ["build"],
            ["validate"],
            ["export", "--output", "out"],
            ["run", "--output", "out"],
            ["spec"],
        ],
    )
    def test_routes_to_command_argument_validation(self, argv, capsys):
        assert cli.run_phase2(argv) == 2
        capsys.readouterr()


def _build_id_from(stdout: str) -> str:
    for line in stdout.splitlines():
        if line.strip().startswith("build_id:"):
            return line.split(":", 1)[1].strip()
    raise AssertionError(f"no build_id in output:\n{stdout}")


@pytest.fixture
def cli_spec(tmp_path, capsys):
    """Create a specification through the CLI and return its name."""
    name = f"cli-cmd-spec-{uuid.uuid4().hex[:8]}"
    spec_file = write_spec(tmp_path, VALID_SPEC)
    assert cli.cmd_spec(["create", name, "--file", spec_file]) == 0
    out = capsys.readouterr().out
    assert "SPECIFICATION CREATED" in out
    return name


class TestDatasetPipelineCommands:
    """Integration tests over a live database."""

    def test_spec_list_and_show(self, cli_spec, capsys):
        assert cli.cmd_spec(["list"]) == 0
        assert cli_spec in capsys.readouterr().out

        assert cli.cmd_spec(["show", cli_spec]) == 0
        out = capsys.readouterr().out
        assert cli_spec in out
        assert "Canonical specification" in out
        assert '"minimum_characters": 10' in out

    def test_spec_show_reports_missing(self, capsys):
        assert cli.cmd_spec(["show", f"absent-{uuid.uuid4().hex[:8]}"]) == 1
        assert "not found" in capsys.readouterr().err

    def test_build_reports_missing_specification(self, capsys):
        assert cli.cmd_build([f"absent-{uuid.uuid4().hex[:8]}"]) == 1
        assert "not found" in capsys.readouterr().err

    def test_validate_reports_missing_build(self, capsys):
        assert cli.cmd_validate(["00000000-0000-0000-0000-000000000000"]) == 1
        assert "Build not found" in capsys.readouterr().err

    def test_export_reports_missing_build(self, tmp_path, capsys):
        argv = ["00000000-0000-0000-0000-000000000000", "--output", str(tmp_path / "out")]
        assert cli.cmd_export(argv) == 1
        assert "Build not found" in capsys.readouterr().err

    def test_build_validate_export_sequence(self, cli_spec, tmp_path, capsys):
        assert cli.cmd_build([cli_spec]) == 0
        build_out = capsys.readouterr().out
        assert "DATASET BUILD" in build_out
        build_id = _build_id_from(build_out)

        assert cli.cmd_validate([build_id]) in (0, 1)
        validate_out = capsys.readouterr().out
        assert "VALIDATION REPORT" in validate_out
        for check in ("schema_validity", "record_counts", "rejection_accounting"):
            assert check in validate_out

        out_dir = tmp_path / "discrete"
        assert cli.cmd_export([build_id, "--output", str(out_dir)]) == 0
        export_out = capsys.readouterr().out
        assert "EXPORT COMPLETE" in export_out
        for filename in EXPORT_FILES:
            assert (out_dir / filename).is_file(), filename

    def test_export_picks_up_persisted_validation_report(self, cli_spec, tmp_path, capsys):
        assert cli.cmd_build([cli_spec]) == 0
        build_id = _build_id_from(capsys.readouterr().out)
        cli.cmd_validate([build_id])
        capsys.readouterr()

        out_dir = tmp_path / "validated"
        assert cli.cmd_export([build_id, "--output", str(out_dir)]) == 0
        capsys.readouterr()
        report = json.loads((out_dir / "validation_report.json").read_text(encoding="utf-8"))
        assert report["status"] != "not_validated"
        assert len(report["checks"]) == 10

    def test_export_warns_when_build_was_not_validated(self, cli_spec, tmp_path, capsys):
        assert cli.cmd_build([cli_spec]) == 0
        build_id = _build_id_from(capsys.readouterr().out)

        out_dir = tmp_path / "unvalidated"
        assert cli.cmd_export([build_id, "--output", str(out_dir)]) == 0
        assert "no validation report found" in capsys.readouterr().err
        report = json.loads((out_dir / "validation_report.json").read_text(encoding="utf-8"))
        assert report["status"] == "not_validated"

    def test_run_chains_all_stages(self, cli_spec, tmp_path, capsys):
        out_dir = tmp_path / "chained"
        assert cli.cmd_run([cli_spec, "--output", str(out_dir), "--allow-invalid"]) == 0
        out = capsys.readouterr().out
        for stage in ("STAGE 1/4", "STAGE 2/4", "STAGE 3/4", "STAGE 4/4"):
            assert stage in out
        for filename in EXPORT_FILES:
            assert (out_dir / filename).is_file(), filename

    def test_run_can_skip_feasibility(self, cli_spec, tmp_path, capsys):
        out_dir = tmp_path / "skipped"
        argv = [cli_spec, "--output", str(out_dir), "--skip-feasibility", "--allow-invalid"]
        assert cli.cmd_run(argv) == 0
        out = capsys.readouterr().out
        assert "STAGE 1/4" not in out
        assert "STAGE 4/4" in out
        assert (out_dir / "data.jsonl").is_file()

    @pytest.mark.parametrize("verdict", ["fail", "blocked"])
    def test_run_aborts_on_infeasible_specification(
        self, cli_spec, tmp_path, capsys, monkeypatch, verdict
    ):
        """A non-passing feasibility verdict stops the run before building."""
        from data_fetcher.phase2 import feasibility as feasibility_module

        real_analyze = feasibility_module.FeasibilityEngine.analyze

        def analyze(self, specification):
            report = real_analyze(self, specification)
            report.feasibility = verdict
            report.blockers = ["synthetic blocker"]
            return report

        monkeypatch.setattr(feasibility_module.FeasibilityEngine, "analyze", analyze)

        out_dir = tmp_path / "infeasible"
        assert cli.cmd_run([cli_spec, "--output", str(out_dir)]) == 1
        captured = capsys.readouterr()
        assert "not feasible" in captured.err
        assert "STAGE 2/4" not in captured.out
        assert not out_dir.exists()

    def test_run_allow_invalid_overrides_feasibility_gate(
        self, cli_spec, tmp_path, capsys, monkeypatch
    ):
        from data_fetcher.phase2 import feasibility as feasibility_module

        real_analyze = feasibility_module.FeasibilityEngine.analyze

        def analyze(self, specification):
            report = real_analyze(self, specification)
            report.feasibility = "fail"
            return report

        monkeypatch.setattr(feasibility_module.FeasibilityEngine, "analyze", analyze)

        out_dir = tmp_path / "forced"
        argv = [cli_spec, "--output", str(out_dir), "--allow-invalid"]
        assert cli.cmd_run(argv) == 0
        assert "STAGE 4/4" in capsys.readouterr().out
        assert (out_dir / "data.jsonl").is_file()


