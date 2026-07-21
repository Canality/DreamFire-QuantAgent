#!/usr/bin/env python3
"""Phase B: 2×2 mechanism experiment — factor weight shrinkage × score-tilted allocation.

Pre-registered before run. No threshold adjustments after seeing results.
"""

from __future__ import annotations

import argparse, json, time
from datetime import datetime
from pathlib import Path

import numpy as np

from jiuwenswarm.quant.strategy_configs import STRATEGY_SPECS

_EVAL_DIR = Path(__file__).resolve().parent
import importlib.util as _iu
_UE_SPEC = _iu.spec_from_file_location(
    "unified_baseline_evaluation",
    _EVAL_DIR / "unified_baseline_evaluation.py",
)
_UE = _iu.module_from_spec(_UE_SPEC)
assert _UE_SPEC.loader is not None
_UE_SPEC.loader.exec_module(_UE)

# ---- Pre-registration (frozen before run) ----
PHASE_B_BASELINES = (
    "production_six_factor",
    "phase_b_t0_control",
    "phase_b_t1_shrink",
    "phase_b_t2_score_alloc",
    "phase_b_t3_joint",
)

PREREGISTRATION = {
    "hypothesis": (
        "1. Shrinking volume_trend from 0.29 to 0.15 reduces recent decay. "
        "2. Mild score-tilted allocation (inv-vol × exp(0.20×clip(z,-2,2))) "
        "converts selection advantage into higher realized returns."
    ),
    "design": "2×2: factor weights (0.71/0.29 vs 0.85/0.15) × allocation (pure inv-vol vs score-tilted)",
    "fixed_constraints": {
        "selection": "positive composite, naked top 15",
        "max_single_stock": 0.10,
        "max_single_sector": 0.25,
        "max_total_weight": 0.95,
    },
    "success_criteria": {
        "goal": (
            "Preserve ~+0.77pp pairwise return advantage over production while "
            "keeping median DD worsening ≤ +0.30pp and ≥ 2/3 consecutive "
            "7-window time blocks with positive composite utility."
        ),
        "utility": "0.70 × total_return - 0.30 × max_drawdown",
    },
}


def paired_compare(candidate_rows, baseline_rows):
    """Per-window paired comparison of candidate vs baseline."""
    n = len(candidate_rows)
    ret_deltas = np.array([
        c["official"]["total_return"] - b["official"]["total_return"]
        for c, b in zip(candidate_rows, baseline_rows)
    ])
    dd_deltas = np.array([
        c["official"]["max_drawdown"] - b["official"]["max_drawdown"]
        for c, b in zip(candidate_rows, baseline_rows)
    ])
    utility = 0.70 * ret_deltas - 0.30 * dd_deltas
    wins = int((utility > 0).sum())
    recent4 = int((utility[-4:] > 0).sum()) if n >= 4 else wins
    # time-block: 3 consecutive 7-window blocks
    block_wins = []
    for start in range(0, n - 6, 7):
        block = utility[start:start + 7]
        block_wins.append(int((block > 0).sum()))
    blocks_positive = sum(1 for bw in block_wins if bw >= 4)

    return {
        "median_return_delta_pp": round(float(np.median(ret_deltas)) * 100, 4),
        "mean_return_delta_pp": round(float(np.mean(ret_deltas)) * 100, 4),
        "median_dd_delta_pp": round(float(np.median(dd_deltas)) * 100, 4),
        "utility_wins": f"{wins}/{n}",
        "utility_win_rate": round(wins / n, 4),
        "recent4_wins": f"{recent4}/4",
        "block_7w_positive": f"{blocks_positive}/{len(block_wins)}",
        "worst_return_delta_pp": round(
            float(min(c["official"]["total_return"] for c in candidate_rows)
                  - min(b["official"]["total_return"] for b in baseline_rows)) * 100, 4
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--datalen", type=int, default=500)
    args = parser.parse_args()

    started = time.time()
    print("=" * 78)
    print("Phase B: 2×2 mechanism experiment")
    print(json.dumps(PREREGISTRATION, ensure_ascii=False, indent=2))
    print("=" * 78)

    # Load or create snapshot (shared with Phase A)
    snapshot_dir = args.snapshot.resolve() if args.snapshot else _UE.create_snapshot(args.datalen)
    snapshot = _UE.load_snapshot(snapshot_dir)
    opens, closes, volumes, index_close = _UE._prepare_frames(snapshot)
    starts = _UE.build_schedule(len(index_close))
    print(
        f"Snapshot {snapshot_dir.name}: {len(index_close)} index days, "
        f"{len(starts)} non-overlapping windows"
    )

    # Run all baselines
    details: dict[str, list] = {}
    summaries: dict[str, dict] = {}
    for name in PHASE_B_BASELINES:
        spec = STRATEGY_SPECS[name]
        print(f"[Run] {name}: {spec.description}")
        rows = _UE.evaluate_strategy(name, opens, closes, volumes, index_close, starts)
        details[name] = rows
        summaries[name] = _UE.summarize(rows)

    # Pairwise comparisons vs production
    prod_rows = details["production_six_factor"]
    comparisons = {}
    for name in PHASE_B_BASELINES:
        if name == "production_six_factor":
            continue
        comparisons[name] = paired_compare(details[name], prod_rows)

    # Print results
    print("\n" + "=" * 78)
    print("  Phase B Results")
    print("=" * 78)
    print(f"{'Strategy':<28s} {'MedRet%':>8s} {'Worst%':>8s} {'MedDD%':>7s} "
          f"{'PosWin':>6s} {'vsProd_Δpp':>9s} {'UtilWins':>9s} {'Rec4':>5s} {'Blk7':>6s}")
    print("-" * 78)
    for name in PHASE_B_BASELINES:
        s = summaries[name]
        ret_pct = s["median_return"] * 100
        worst_pct = s["worst_return"] * 100
        dd_pct = s["median_drawdown"] * 100
        pos = f"{s['positive_windows']}/{s['n_windows']}"
        if name == "production_six_factor":
            print(f"{name:<28s} {ret_pct:>7.2f}% {worst_pct:>7.2f}% "
                  f"{dd_pct:>6.2f}% {pos:>6s} {'(baseline)':>9s}")
        else:
            c = comparisons[name]
            print(f"{name:<28s} {ret_pct:>7.2f}% {worst_pct:>7.2f}% "
                  f"{dd_pct:>6.2f}% {pos:>6s} "
                  f"{c['median_return_delta_pp']:>+8.2f} "
                  f"{c['utility_wins']:>9s} {c['recent4_wins']:>5s} {c['block_7w_positive']:>6s}")

    # Save
    run_id = datetime.now().strftime("phase_b_%Y%m%d_%H%M%S")
    report = {
        "run_id": run_id,
        "created_at": datetime.now().astimezone().isoformat(),
        "git": _UE._git_state(),
        "preregistration": PREREGISTRATION,
        "snapshot_id": snapshot["manifest"]["snapshot_id"],
        "summaries": summaries,
        "comparisons": comparisons,
    }
    out_path = _EVAL_DIR / f"{run_id}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False, default=str)
    latest = _EVAL_DIR / "phase_b_latest.json"
    with open(latest, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False, default=str)
    print(f"\nSaved to {out_path}  ({time.time() - started:.0f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
