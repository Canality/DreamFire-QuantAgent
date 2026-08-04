from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


def _load_module():
    path = Path(__file__).resolve().parents[3] / "evaluation" / "phase_b_experiment.py"
    spec = importlib.util.spec_from_file_location("phase_b_experiment_wp1b", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_preregistration_deprecates_legacy_phase_b_conclusion() -> None:
    module = _load_module()
    assert module.PREREGISTRATION["protocol"] == "competition_nested_v1"
    assert module.PREREGISTRATION["legacy_next_day_entry"] == "RESEARCH_ONLY"
    assert module.PREREGISTRATION["outer_results_may_select_candidate"] is False


def test_write_artifact_is_create_once_and_has_no_latest_pointer(tmp_path: Path) -> None:
    module = _load_module()
    report = {"run_id": "wp1b-test", "status": "RESEARCH_ONLY"}
    path = module.write_research_artifact(report, tmp_path)
    assert path.name == "wp1b-test.json"
    assert json.loads(path.read_text(encoding="utf-8")) == report
    assert not any("latest" in item.name.lower() for item in tmp_path.iterdir())
    with pytest.raises(FileExistsError):
        module.write_research_artifact(report, tmp_path)


def test_raw_snapshot_binding_is_not_wp1a_verified(tmp_path: Path) -> None:
    module = _load_module()
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps({
            "snapshot_id": "raw-sina",
            "source": "Sina",
            "adjustment": "raw/unadjusted",
        }),
        encoding="utf-8",
    )
    binding = module.build_snapshot_binding(tmp_path, {"manifest": {
        "snapshot_id": "raw-sina",
        "source": "Sina",
        "adjustment": "raw/unadjusted",
    }})
    assert binding["verified_wp1a"] is False
    assert len(binding["manifest_sha256"]) == 64
