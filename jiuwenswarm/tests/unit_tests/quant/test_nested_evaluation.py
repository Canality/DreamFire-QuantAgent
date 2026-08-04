from __future__ import annotations

import hashlib
import json
import subprocess
from copy import deepcopy
from dataclasses import asdict, replace
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest

from jiuwenswarm.quant.nested_evaluation import (
    NestedEvaluationPlan,
    OuterResultAccessError,
    PairingError,
    build_git_binding,
    evaluate_nested_promotion,
)


BASELINE = "baseline"
CANDIDATE = "challenger"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_hash(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _git_binding(tmp_path: Path, *, dirty: bool = False) -> dict[str, Any]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "WP1-B Test")
    (repo / "seed.txt").write_text("frozen\n", encoding="utf-8")
    _git(repo, "add", "seed.txt")
    _git(repo, "commit", "-qm", "frozen test state")
    if dirty:
        (repo / "dirty.txt").write_text("uncommitted\n", encoding="utf-8")
    return build_git_binding(repo)


def _snapshot_binding(
    tmp_path: Path,
    *,
    verified: bool = True,
) -> dict[str, Any]:
    snapshot_dir = tmp_path / "snapshot"
    snapshot_dir.mkdir()
    manifest: dict[str, Any] = {
        "snapshot_id": "snap-1",
        "source": "fixture",
        "adjustment": "verified",
        "n_stocks": 49,
        "n_sectors": 6,
    }
    verified_reports = None
    wp1a = None
    if verified:
        consistency = snapshot_dir / "consistency.json"
        regime = snapshot_dir / "regime.json"
        consistency.write_text('{"status":"VERIFIED"}\n', encoding="utf-8")
        regime.write_text('{"status":"VERIFIED"}\n', encoding="utf-8")
        wp1a = {
            "status": "VERIFIED",
            "consistency_report_path": consistency.name,
            "consistency_report_sha256": _sha256(consistency),
            "regime_report_path": regime.name,
            "regime_report_sha256": _sha256(regime),
        }
        manifest["wp1a_binding"] = wp1a
        verified_reports = {
            "consistency_report": {
                "path": str(consistency.resolve()),
                "sha256": _sha256(consistency),
            },
            "regime_report": {
                "path": str(regime.resolve()),
                "sha256": _sha256(regime),
            },
        }
    manifest_path = snapshot_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    return {
        "snapshot_id": manifest["snapshot_id"],
        "manifest_path": str(manifest_path.resolve()),
        "manifest_sha256": _sha256(manifest_path),
        "manifest": manifest,
        "verified_wp1a": verified,
        "wp1a_binding": wp1a,
        "verified_reports": verified_reports,
    }


def _config_binding(plan: NestedEvaluationPlan) -> dict[str, Any]:
    payload = {
        "preregistration": {
            "protocol": plan.protocol,
            "candidate_set": [CANDIDATE],
        },
        "plan": asdict(plan),
        "strategies": {
            BASELINE: {"version": "frozen"},
            CANDIDATE: {"version": "frozen"},
        },
    }
    return {"sha256": _canonical_hash(payload), "payload": payload}


def _rows(*, return_delta: float = 0.01, drawdown_delta: float = 0.0):
    baseline_rows = []
    candidate_rows = []
    first = date(2025, 1, 1)
    for idx in range(20):
        decision = first + timedelta(days=idx * 30)
        embargo = decision + timedelta(days=1)
        valuations = [
            (decision + timedelta(days=offset)).isoformat()
            for offset in range(2, 22)
        ]
        common = {
            "idx": idx,
            "decision_date": decision.isoformat(),
            "embargo_date": embargo.isoformat(),
            "entry_date": valuations[0],
            "valuation_dates": valuations,
            "exit_date": valuations[-1],
            "regime": "bull" if idx % 2 == 0 else "bear",
            "n_stocks_covered": 49,
            "n_sectors_covered": 6,
            "n_forward_closes": 20,
        }
        baseline_rows.append({
            **common,
            "official": {"total_return": 0.0, "max_drawdown": 0.02},
        })
        candidate_rows.append({
            **common,
            "official": {
                "total_return": return_delta,
                "max_drawdown": 0.02 + drawdown_delta,
            },
        })
    return {BASELINE: baseline_rows, CANDIDATE: candidate_rows}


def _evaluate(
    tmp_path: Path,
    *,
    details=None,
    plan: NestedEvaluationPlan | None = None,
    dirty: bool = False,
    verified: bool = True,
    selection_metric: str = "median_return_delta",
):
    frozen_plan = plan or NestedEvaluationPlan()
    return evaluate_nested_promotion(
        details=details or _rows(),
        baseline_name=BASELINE,
        candidate_names=[CANDIDATE],
        git_state=_git_binding(tmp_path, dirty=dirty),
        snapshot_binding=_snapshot_binding(tmp_path, verified=verified),
        config_binding=_config_binding(frozen_plan),
        plan=frozen_plan,
        selection_metric=selection_metric,
    )


def test_clean_verified_strong_candidate_is_promotion_eligible(
    tmp_path: Path,
) -> None:
    result = _evaluate(tmp_path)
    assert result["status"] == "PROMOTION_ELIGIBLE"
    assert result["promotion_eligible"] is True
    assert result["checks"]["preregistered_plan"] is True
    assert result["split"] == {
        "inner_indices": list(range(10)),
        "outer_indices": list(range(10, 20)),
    }


def test_dirty_run_cannot_promote_even_when_statistics_pass(tmp_path: Path) -> None:
    result = _evaluate(tmp_path, dirty=True)
    assert result["statistical_qualified"] is True
    assert result["checks"]["clean_git"] is False
    assert result["status"] == "RESEARCH_ONLY"


def test_unverified_snapshot_cannot_promote(tmp_path: Path) -> None:
    result = _evaluate(tmp_path, verified=False)
    assert result["statistical_qualified"] is True
    assert result["checks"]["verified_wp1a_snapshot"] is False
    assert result["status"] == "RESEARCH_ONLY"


def test_p10_noninferiority_failure_blocks_candidate(tmp_path: Path) -> None:
    details = _rows()
    for row in details[CANDIDATE][10:]:
        row["official"]["total_return"] = 0.01
    details[CANDIDATE][10]["official"]["total_return"] = -0.20
    result = _evaluate(tmp_path, details=details)
    assert result["checks"]["p10_return_noninferiority"] is False
    assert result["status"] == "DOES_NOT_QUALIFY"


def test_mismatched_window_identity_fails_closed(tmp_path: Path) -> None:
    details = _rows()
    details[CANDIDATE][4]["entry_date"] = "2099-01-01"
    with pytest.raises(PairingError, match="entry/exit|identity"):
        _evaluate(tmp_path, details=details)


def test_outer_selection_metric_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(OuterResultAccessError, match="outer"):
        _evaluate(tmp_path, selection_metric="outer_return")


def test_identical_inputs_have_identical_evaluation_hash(tmp_path: Path) -> None:
    git_state = _git_binding(tmp_path)
    snapshot = _snapshot_binding(tmp_path)
    plan = NestedEvaluationPlan()
    kwargs = {
        "details": _rows(),
        "baseline_name": BASELINE,
        "candidate_names": [CANDIDATE],
        "git_state": git_state,
        "snapshot_binding": snapshot,
        "config_binding": _config_binding(plan),
        "plan": plan,
    }
    first = evaluate_nested_promotion(**kwargs)
    second = evaluate_nested_promotion(**kwargs)
    assert first["evaluation_hash"] == second["evaluation_hash"]
    assert first["bootstrap"] == second["bootstrap"]


def test_changed_candidate_inputs_change_evaluation_hash(tmp_path: Path) -> None:
    details = _rows()
    first = _evaluate(tmp_path, details=details)
    changed = deepcopy(details)
    changed[CANDIDATE][19]["official"]["total_return"] = 0.02
    git_state = first["git"]
    snapshot = first["snapshot_binding"]
    plan = NestedEvaluationPlan()
    second = evaluate_nested_promotion(
        details=changed,
        baseline_name=BASELINE,
        candidate_names=[CANDIDATE],
        git_state=git_state,
        snapshot_binding=snapshot,
        config_binding=_config_binding(plan),
        plan=plan,
    )
    assert first["evaluation_hash"] != second["evaluation_hash"]


def test_missing_valuation_date_fails_closed(tmp_path: Path) -> None:
    details = _rows()
    details[CANDIDATE][0]["valuation_dates"].pop()
    with pytest.raises(PairingError, match="exact 20"):
        _evaluate(tmp_path, details=details)


def test_config_payload_tampering_is_rejected(tmp_path: Path) -> None:
    plan = NestedEvaluationPlan()
    binding = _config_binding(plan)
    binding["payload"]["plan"]["seed"] = 1
    with pytest.raises(ValueError, match="config binding SHA-256 mismatch"):
        evaluate_nested_promotion(
            details=_rows(),
            baseline_name=BASELINE,
            candidate_names=[CANDIDATE],
            git_state=_git_binding(tmp_path),
            snapshot_binding=_snapshot_binding(tmp_path),
            config_binding=binding,
            plan=plan,
        )


def test_self_hashed_wrong_strategy_set_is_rejected(tmp_path: Path) -> None:
    plan = NestedEvaluationPlan()
    binding = _config_binding(plan)
    binding["payload"]["strategies"].pop(CANDIDATE)
    binding["sha256"] = _canonical_hash(binding["payload"])
    with pytest.raises(ValueError, match="exact strategy set"):
        evaluate_nested_promotion(
            details=_rows(),
            baseline_name=BASELINE,
            candidate_names=[CANDIDATE],
            git_state=_git_binding(tmp_path),
            snapshot_binding=_snapshot_binding(tmp_path),
            config_binding=binding,
            plan=plan,
        )


def test_snapshot_manifest_tampering_is_rejected(tmp_path: Path) -> None:
    snapshot = _snapshot_binding(tmp_path)
    Path(snapshot["manifest_path"]).write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="snapshot manifest SHA-256 mismatch"):
        evaluate_nested_promotion(
            details=_rows(),
            baseline_name=BASELINE,
            candidate_names=[CANDIDATE],
            git_state=_git_binding(tmp_path),
            snapshot_binding=snapshot,
            config_binding=_config_binding(NestedEvaluationPlan()),
        )


def test_forged_wp1a_flag_without_manifest_binding_is_rejected(
    tmp_path: Path,
) -> None:
    snapshot = _snapshot_binding(tmp_path, verified=False)
    snapshot["verified_wp1a"] = True
    snapshot["verified_reports"] = {
        "consistency_report": {
            "path": snapshot["manifest_path"],
            "sha256": snapshot["manifest_sha256"],
        },
        "regime_report": {
            "path": snapshot["manifest_path"],
            "sha256": snapshot["manifest_sha256"],
        },
    }
    with pytest.raises(ValueError, match="manifest is not WP1-A VERIFIED"):
        evaluate_nested_promotion(
            details=_rows(),
            baseline_name=BASELINE,
            candidate_names=[CANDIDATE],
            git_state=_git_binding(tmp_path),
            snapshot_binding=snapshot,
            config_binding=_config_binding(NestedEvaluationPlan()),
        )


def test_wp1a_report_tampering_is_rejected(tmp_path: Path) -> None:
    snapshot = _snapshot_binding(tmp_path)
    report = Path(snapshot["verified_reports"]["consistency_report"]["path"])
    report.write_text("tampered\n", encoding="utf-8")
    with pytest.raises(ValueError, match="consistency_report SHA-256 mismatch"):
        evaluate_nested_promotion(
            details=_rows(),
            baseline_name=BASELINE,
            candidate_names=[CANDIDATE],
            git_state=_git_binding(tmp_path),
            snapshot_binding=snapshot,
            config_binding=_config_binding(NestedEvaluationPlan()),
        )


def test_hash_bound_failed_wp1a_report_is_rejected(tmp_path: Path) -> None:
    snapshot = _snapshot_binding(tmp_path)
    manifest_path = Path(snapshot["manifest_path"])
    report = Path(snapshot["verified_reports"]["consistency_report"]["path"])
    report.write_text('{"status":"FAILED"}\n', encoding="utf-8")
    failed_hash = _sha256(report)
    snapshot["verified_reports"]["consistency_report"]["sha256"] = failed_hash
    snapshot["wp1a_binding"]["consistency_report_sha256"] = failed_hash
    snapshot["manifest"]["wp1a_binding"][
        "consistency_report_sha256"
    ] = failed_hash
    manifest_path.write_text(
        json.dumps(snapshot["manifest"], ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    snapshot["manifest_sha256"] = _sha256(manifest_path)
    with pytest.raises(ValueError, match="does not have VERIFIED status"):
        evaluate_nested_promotion(
            details=_rows(),
            baseline_name=BASELINE,
            candidate_names=[CANDIDATE],
            git_state=_git_binding(tmp_path),
            snapshot_binding=snapshot,
            config_binding=_config_binding(NestedEvaluationPlan()),
        )


def test_changed_git_state_is_rejected(tmp_path: Path) -> None:
    git_state = _git_binding(tmp_path)
    Path(git_state["repo_root"], "after.txt").write_text("changed\n", encoding="utf-8")
    with pytest.raises(ValueError, match="differs from current repository state"):
        evaluate_nested_promotion(
            details=_rows(),
            baseline_name=BASELINE,
            candidate_names=[CANDIDATE],
            git_state=git_state,
            snapshot_binding=_snapshot_binding(tmp_path),
            config_binding=_config_binding(NestedEvaluationPlan()),
        )


def test_nondefault_plan_is_research_only(tmp_path: Path) -> None:
    plan = replace(NestedEvaluationPlan(), bootstrap_iterations=20)
    result = _evaluate(tmp_path, plan=plan)
    assert result["statistical_qualified"] is True
    assert result["checks"]["preregistered_plan"] is False
    assert result["status"] == "RESEARCH_ONLY"
