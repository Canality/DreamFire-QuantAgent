from __future__ import annotations

import importlib.util
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from jiuwenswarm.quant.challenger_mechanisms import (
    CHALLENGER_IDS,
    SECTOR_CANDIDATE,
    TAIL_CANDIDATE,
    TREND_CANDIDATE,
)
from jiuwenswarm.quant.challenger_registry import build_registry
from jiuwenswarm.quant.stock_pool import ALL_STOCKS, SECTOR_MAP


REPO_ROOT = Path(__file__).resolve().parents[4]


def _load_module():
    path = REPO_ROOT / "jiuwenswarm/evaluation/challenger_round.py"
    spec = importlib.util.spec_from_file_location("challenger_round_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _row(
    idx: int,
    *,
    candidate_id: str | None,
    total_return: float,
    max_drawdown: float,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "idx": idx,
        "official": {
            "total_return": total_return,
            "max_drawdown": max_drawdown,
        },
    }
    if candidate_id is None:
        return row
    forward = {
        ticker: 0.001 + position * 0.0001
        for position, ticker in enumerate(ALL_STOCKS)
    }
    if candidate_id == TREND_CANDIDATE:
        diagnostics = {
            "trend_consistency": {
                ticker: float(position)
                for position, ticker in enumerate(ALL_STOCKS)
            }
        }
    elif candidate_id == SECTOR_CANDIDATE:
        sectors = sorted(set(SECTOR_MAP.values()))
        leadership = {
            sector: 0.1 + position * 0.1
            for position, sector in enumerate(sectors)
        }
        forward = {
            ticker: leadership[SECTOR_MAP[ticker]]
            for ticker in ALL_STOCKS
        }
        diagnostics = {
            "sector_leadership_score": leadership,
            "top2_leaders": sectors[-2:],
        }
    else:
        diagnostics = {"tail_severity": {ticker: 0.0 for ticker in ALL_STOCKS}}
    row["challenger"] = {
        "candidate_id": candidate_id,
        "diagnostics": diagnostics,
        "forward_returns": forward,
    }
    return row


def _details() -> dict[str, list[dict[str, Any]]]:
    module = _load_module()
    details = {
        module.BASE_STRATEGY_ID: [
            _row(idx, candidate_id=None, total_return=0.0, max_drawdown=0.02)
            for idx in range(20)
        ],
        TREND_CANDIDATE: [
            _row(
                idx,
                candidate_id=TREND_CANDIDATE,
                total_return=0.01,
                max_drawdown=0.02,
            )
            for idx in range(20)
        ],
        SECTOR_CANDIDATE: [
            _row(
                idx,
                candidate_id=SECTOR_CANDIDATE,
                total_return=0.01,
                max_drawdown=0.02,
            )
            for idx in range(20)
        ],
        TAIL_CANDIDATE: [
            _row(
                idx,
                candidate_id=TAIL_CANDIDATE,
                total_return=-0.001,
                max_drawdown=0.018,
            )
            for idx in range(20)
        ],
    }
    return details


def _registry():
    return build_registry(
        task_path=REPO_ROOT / "coordination/active/WP1B-EVALUATION-0804.md",
        review_path=(
            REPO_ROOT
            / "output/agent_handoffs/WP1B-EVALUATION-0804/review.json"
        ),
    )


def test_exact_three_inner_prescreens_pass_fixed_thresholds() -> None:
    module = _load_module()
    result = module.evaluate_inner_prescreens(_details())
    assert list(result) == list(CHALLENGER_IDS)
    assert all(item["passed"] for item in result.values())
    assert all(item["inner_indices"] == list(range(10)) for item in result.values())


def test_outer_rows_cannot_change_inner_prescreen() -> None:
    module = _load_module()
    details = _details()
    expected = module.evaluate_inner_prescreens(details)
    for candidate_id in CHALLENGER_IDS:
        for row in details[candidate_id][10:]:
            row["official"]["total_return"] = -99.0
            row["official"]["max_drawdown"] = 99.0
            row["challenger"]["forward_returns"] = {
                ticker: -99.0 for ticker in ALL_STOCKS
            }
    assert module.evaluate_inner_prescreens(details) == expected


def test_untradable_forward_target_is_excluded_and_coverage_recorded() -> None:
    module = _load_module()
    details = _details()
    missing = ALL_STOCKS[-1]
    for candidate_id in CHALLENGER_IDS:
        for row in details[candidate_id]:
            row["challenger"]["forward_returns"].pop(missing)
    result = module.evaluate_inner_prescreens(details)
    assert result[TREND_CANDIDATE]["evidence"][
        "min_forward_target_coverage"
    ] == 48
    assert result[SECTOR_CANDIDATE]["evidence"][
        "min_forward_target_coverage"
    ] == 48


def test_failed_inner_candidate_is_retained_and_never_sent_outer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_module()
    details = _details()
    for row in details[TREND_CANDIDATE][:10]:
        row["official"]["total_return"] = -0.01
    calls: list[str] = []

    def fake_nested(**kwargs):
        candidate = kwargs["candidate_names"][0]
        calls.append(candidate)
        return {
            "status": "RESEARCH_ONLY",
            "promotion_eligible": False,
            "evaluation_hash": f"hash-{candidate}",
            "checks": {"clean_git": False},
        }

    monkeypatch.setattr(module, "evaluate_nested_promotion", fake_nested)
    result = module.evaluate_round(
        details=details,
        registry=_registry(),
        git_state={"dirty": True},
        snapshot_binding={"manifest_sha256": "a" * 64},
    )
    assert TREND_CANDIDATE not in calls
    assert set(calls) == {SECTOR_CANDIDATE, TAIL_CANDIDATE}
    assert result["failures"][TREND_CANDIDATE]["stage"] == "INNER_PRESCREEN"
    assert result["production_pointer_updated"] is False
    assert result["status"] == "RESEARCH_ONLY"


def test_construction_failure_is_retained_while_other_candidates_continue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_module()
    details = _details()
    details.pop(TAIL_CANDIDATE)
    calls: list[str] = []

    def fake_nested(**kwargs):
        candidate = kwargs["candidate_names"][0]
        calls.append(candidate)
        return {
            "status": "RESEARCH_ONLY",
            "promotion_eligible": False,
            "evaluation_hash": f"hash-{candidate}",
            "checks": {"clean_git": False},
        }

    monkeypatch.setattr(module, "evaluate_nested_promotion", fake_nested)
    result = module.evaluate_round(
        details=details,
        registry=_registry(),
        git_state={"dirty": True},
        snapshot_binding={"manifest_sha256": "a" * 64},
        construction_failures={
            TAIL_CANDIDATE: {
                "stage": "CONSTRUCTION",
                "error_type": "ValueError",
                "message": "missing open history",
            }
        },
    )
    assert set(calls) == {TREND_CANDIDATE, SECTOR_CANDIDATE}
    assert result["failures"][TAIL_CANDIDATE]["stage"] == "CONSTRUCTION"
    assert result["inner"][TAIL_CANDIDATE]["passed"] is False


def test_each_passing_candidate_gets_exactly_one_outer_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_module()
    calls: list[str] = []

    def fake_nested(**kwargs):
        candidate = kwargs["candidate_names"][0]
        calls.append(candidate)
        return {
            "status": "RESEARCH_ONLY",
            "promotion_eligible": False,
            "evaluation_hash": f"hash-{candidate}",
            "checks": {"clean_git": False},
        }

    monkeypatch.setattr(module, "evaluate_nested_promotion", fake_nested)
    result = module.evaluate_round(
        details=_details(),
        registry=_registry(),
        git_state={"dirty": True},
        snapshot_binding={"manifest_sha256": "b" * 64},
    )
    assert calls == list(CHALLENGER_IDS)
    assert len(calls) == len(set(calls)) == 3
    assert result["promotion_eligible_candidates"] == []


def test_round_hash_is_deterministic_and_changes_with_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_module()

    def fake_nested(**kwargs):
        candidate = kwargs["candidate_names"][0]
        return {
            "status": "RESEARCH_ONLY",
            "promotion_eligible": False,
            "evaluation_hash": f"hash-{candidate}",
            "checks": {"clean_git": False},
        }

    monkeypatch.setattr(module, "evaluate_nested_promotion", fake_nested)
    kwargs = {
        "registry": _registry(),
        "git_state": {"commit": "c" * 40, "dirty": True},
        "snapshot_binding": {"manifest_sha256": "d" * 64},
    }
    details = _details()
    first = module.evaluate_round(details=details, **kwargs)
    second = module.evaluate_round(details=deepcopy(details), **kwargs)
    assert first["round_hash"] == second["round_hash"]
    changed = deepcopy(details)
    changed[TREND_CANDIDATE][19]["official"]["total_return"] = 0.02
    third = module.evaluate_round(details=changed, **kwargs)
    assert third["round_hash"] != first["round_hash"]


def test_create_once_evidence_tree_has_manifest_and_no_latest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_module()

    def fake_nested(**kwargs):
        candidate = kwargs["candidate_names"][0]
        return {
            "status": "RESEARCH_ONLY",
            "promotion_eligible": False,
            "evaluation_hash": f"hash-{candidate}",
            "checks": {"clean_git": False},
        }

    monkeypatch.setattr(module, "evaluate_nested_promotion", fake_nested)
    registry = _registry()
    details = _details()
    result = module.evaluate_round(
        details=details,
        registry=registry,
        git_state={"commit": "e" * 40, "dirty": True},
        snapshot_binding={"manifest_sha256": "f" * 64},
    )
    run_dir = module.write_round_artifacts(
        run_id="wp1c-test",
        registry=registry,
        details=details,
        result=result,
        snapshot_binding={"manifest_sha256": "f" * 64},
        git_state={"commit": "e" * 40, "dirty": True},
        output_root=tmp_path,
    )
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["round_hash"] == result["round_hash"]
    assert manifest["production_pointer_updated"] is False
    assert manifest["legacy_latest_files_modified"] is False
    assert not any("latest" in path.name.lower() for path in run_dir.rglob("*"))
    verification = module.verify_round_artifacts(run_dir)
    assert verification["passed"] is True

    detail_path = run_dir / "details" / f"{TREND_CANDIDATE}.json"
    original_detail = detail_path.read_text(encoding="utf-8")
    tampered_detail = json.loads(original_detail)
    tampered_detail[0]["official"]["total_return"] = 99.0
    detail_path.write_text(
        json.dumps(tampered_detail, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    relative_detail = detail_path.relative_to(run_dir).as_posix()
    manifest["files"][relative_detail] = module.file_sha256(detail_path)
    (run_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="detail hash mismatch"):
        module.verify_round_artifacts(run_dir)

    detail_path.write_text(original_detail, encoding="utf-8")
    manifest["files"][relative_detail] = module.file_sha256(detail_path)
    (run_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    assert module.verify_round_artifacts(run_dir)["passed"] is True
    with pytest.raises(FileExistsError):
        module.write_round_artifacts(
            run_id="wp1c-test",
            registry=registry,
            details=details,
            result=result,
            snapshot_binding={"manifest_sha256": "f" * 64},
            git_state={"commit": "e" * 40, "dirty": True},
            output_root=tmp_path,
        )
    decision = run_dir / "promotion_decision.json"
    decision.write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        module.verify_round_artifacts(run_dir)
