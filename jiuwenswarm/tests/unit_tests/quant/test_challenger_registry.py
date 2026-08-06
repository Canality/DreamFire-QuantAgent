from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

import jiuwenswarm.quant.challenger_registry as registry_module
from jiuwenswarm.quant.challenger_mechanisms import CHALLENGER_IDS
from jiuwenswarm.quant.challenger_registry import (
    ACCEPTED_WP1B_EVALUATION_HASH,
    ACCEPTED_WP1B_REVIEW_SHA256,
    BASE_STRATEGY_ID,
    FROZEN_REGISTRY_HASH,
    WP1B_REVIEW_EVIDENCE_RELATIVE_PATH,
    build_registry,
    canonical_hash,
    validate_registry,
)


REPO_ROOT = Path(__file__).resolve().parents[4]
TASK_PATH = REPO_ROOT / "coordination/active/WP1B-EVALUATION-0804.md"
REVIEW_PATH = REPO_ROOT / WP1B_REVIEW_EVIDENCE_RELATIVE_PATH


def _registry():
    return build_registry(task_path=TASK_PATH, review_path=REVIEW_PATH)


def test_registry_binds_exact_accepted_wp1b_evidence() -> None:
    registry = _registry()
    assert registry["wp1b_status"] == "CLOSED"
    assert registry["wp1b_review_sha256"] == ACCEPTED_WP1B_REVIEW_SHA256
    assert registry["wp1b_evidence_hash"] == ACCEPTED_WP1B_EVALUATION_HASH
    assert registry["registry_hash"] == FROZEN_REGISTRY_HASH
    assert registry["registry_hash"] == canonical_hash({
        key: value for key, value in registry.items() if key != "registry_hash"
    })


def test_registry_contains_exact_three_single_mechanism_candidates() -> None:
    registry = _registry()
    assert registry["candidate_ids"] == list(CHALLENGER_IDS)
    assert len(registry["candidates"]) == 3
    mechanisms = {
        item["only_changed_mechanism"] for item in registry["candidates"]
    }
    assert len(mechanisms) == 3
    assert all(item["regime_route"] == "all" for item in registry["candidates"])


def test_registry_freezes_t2_base_constraints_and_production_pointer() -> None:
    registry = _registry()
    assert registry["base_strategy_id"] == BASE_STRATEGY_ID
    assert registry["base_strategy"]["factor_weights"] == [
        0.71, 0.0, 0.0, 0.0, 0.0, 0.29
    ]
    assert registry["base_strategy"]["score_tilt"] == 0.20
    assert registry["constraints"] == {
        "max_single_stock": 0.10,
        "max_single_sector": 0.25,
        "min_cash": 0.05,
    }
    assert registry["production_pointer"] == "production_six_factor"
    assert registry["production_pointer_unchanged"] is True


def test_registry_is_deterministic_and_tamper_fails() -> None:
    first = _registry()
    second = _registry()
    assert first == second
    tampered = deepcopy(first)
    tampered["candidates"][0]["parameters"]["overlay_coefficient"] = 0.16
    with pytest.raises(ValueError, match="differs from frozen"):
        validate_registry(tampered, task_path=TASK_PATH, review_path=REVIEW_PATH)


def test_nonverified_wp1b_task_fails_closed(tmp_path: Path) -> None:
    task = tmp_path / "task.md"
    task.write_text("---\nstatus: IMPLEMENTED\n---\n", encoding="utf-8")
    with pytest.raises(ValueError, match="not VERIFIED or CLOSED"):
        build_registry(task_path=task, review_path=REVIEW_PATH)


def test_review_hash_mismatch_fails_closed(tmp_path: Path) -> None:
    review = tmp_path / "review.json"
    review.write_text(REVIEW_PATH.read_text(encoding="utf-8") + " ", encoding="utf-8")
    with pytest.raises(ValueError, match="review SHA-256"):
        build_registry(task_path=TASK_PATH, review_path=review)


def test_missing_tracked_review_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="review artifact is missing"):
        build_registry(task_path=TASK_PATH, review_path=tmp_path / "missing.json")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("task_id", "WRONG-TASK"),
        ("verdict", "REJECT"),
        ("blocking_findings_count", 1),
    ],
)
def test_semantic_repin_cannot_replace_accepted_review(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    value: object,
) -> None:
    payload = json.loads(REVIEW_PATH.read_text(encoding="utf-8"))
    payload[field] = value
    review = tmp_path / "review.json"
    review.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    digest = hashlib.sha256(review.read_bytes()).hexdigest()
    monkeypatch.setattr(registry_module, "ACCEPTED_WP1B_REVIEW_SHA256", digest)

    with pytest.raises(ValueError, match="not an unblocked ACCEPT"):
        build_registry(task_path=TASK_PATH, review_path=review)


def test_semantic_repin_cannot_remove_evaluation_binding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = REVIEW_PATH.read_text(encoding="utf-8")
    review = tmp_path / "review.json"
    review.write_text(
        original.replace(ACCEPTED_WP1B_EVALUATION_HASH, "0" * 64),
        encoding="utf-8",
    )
    digest = hashlib.sha256(review.read_bytes()).hexdigest()
    monkeypatch.setattr(registry_module, "ACCEPTED_WP1B_REVIEW_SHA256", digest)

    with pytest.raises(ValueError, match="does not bind"):
        build_registry(task_path=TASK_PATH, review_path=review)
