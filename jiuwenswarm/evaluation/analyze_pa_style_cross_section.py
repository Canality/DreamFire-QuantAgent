#!/usr/bin/env python3
"""Descriptive paired analysis of valid windows from a failed-closed PA-style run."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

import numpy as np

import pa_style_cross_section_experiment as experiment


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run = json.loads(args.run.read_text(encoding="utf-8"))
    decisions = list(run.get("decisions") or [])
    valid = [row for row in decisions if row.get("success")]
    invalid = [row for row in decisions if not row.get("success")]

    snapshot, fields, _index, starts = experiment._load_data(experiment.SNAPSHOT_DEFAULT)
    phase_b = json.loads(experiment.PHASE_B_LATEST.read_text(encoding="utf-8"))
    t2_all = phase_b["details"]["phase_b_t2_score_alloc"]
    rows = []
    t2_rows = []
    backtest_failures = []
    jaccards = []
    reason_counts: Counter[str] = Counter()
    ticker_counts: Counter[str] = Counter()
    for decision in valid:
        idx = int(decision["idx"])
        base = t2_all[idx]
        try:
            row = experiment._backtest(decision, fields, starts[idx])
        except ValueError as exc:
            backtest_failures.append({"idx": idx, "error": str(exc)})
            continue
        row.update({
            "idx": idx,
            "decision_date": decision["decision_date"],
            "test_start": base["test_start"],
            "test_end": base["test_end"],
            "regime": base["regime"],
            "n_history_days": starts[idx],
            "n_forward_closes": 20,
        })
        a, b = set(row["selected_tickers"]), set(base["selected_tickers"])
        jaccards.append(len(a & b) / len(a | b))
        for selection in decision["selections"]:
            ticker_counts[selection["ticker"]] += 1
            reason_counts.update(selection["reason_codes"])
        rows.append(row)
        t2_rows.append(base)

    paired = experiment._paired(rows, t2_rows)
    ret_delta_pp = np.array([
        (candidate["official"]["total_return"] - baseline["official"]["total_return"]) * 100
        for candidate, baseline in zip(rows, t2_rows)
    ])
    rng = np.random.default_rng(20260721)
    boot = np.array([
        np.median(rng.choice(ret_delta_pp, size=len(ret_delta_pp), replace=True))
        for _ in range(10_000)
    ])
    paired["median_return_delta_pp_bootstrap_95pct_ci"] = [
        round(float(x), 6) for x in np.quantile(boot, [0.025, 0.975])
    ]

    prompt = sum(int(row["usage"]["prompt_tokens"]) for row in decisions)
    cached = sum(int(row["usage"]["cached_prompt_tokens"]) for row in decisions)
    completion = sum(int(row["usage"]["completion_tokens"]) for row in decisions)
    miss = prompt - cached
    cost = cached / 1e6 * 0.0028 + miss / 1e6 * 0.14 + completion / 1e6 * 0.28

    report = {
        "created_at": datetime.now().astimezone().isoformat(),
        "source_run": str(args.run.resolve()),
        "source_status": run.get("status"),
        "validity": {
            "attempted": len(decisions),
            "valid": len(valid),
            "invalid": len(invalid),
            "valid_rate": round(len(valid) / len(decisions), 6),
            "invalid_indices": [row["idx"] for row in invalid],
            "invalid_errors": {str(row["idx"]): row["errors"] for row in invalid},
            "backtest_valid": len(rows),
            "backtest_invalid": len(backtest_failures),
            "backtest_failures": backtest_failures,
        },
        "valid_window_subset_only": {
            "warning": "Contract-failed and backtest-failed windows are excluded; this is not a 21-window strategy score.",
            "summary": experiment._UE.summarize(rows),
            "t2_same_windows_summary": experiment._UE.summarize(t2_rows),
            "comparison_to_t2_same_windows": paired,
            "selection_jaccard_mean": round(float(np.mean(jaccards)), 6),
            "selection_jaccard_median": round(float(np.median(jaccards)), 6),
            "top_selected_tickers": ticker_counts.most_common(15),
            "reason_code_counts": dict(reason_counts.most_common()),
            "details": rows,
        },
        "resources": {
            "prompt_tokens": prompt,
            "cached_prompt_tokens": cached,
            "cache_miss_tokens": miss,
            "completion_tokens": completion,
            "total_tokens": prompt + completion,
            "elapsed_seconds": round(sum(float(row["elapsed_seconds"]) for row in decisions), 3),
            "estimated_cost_usd": round(cost, 6),
        },
        "conclusion_guard": "The full strategy failed closed at 17/21. Subset returns may only motivate or reject a new preregistered contract repair.",
    }
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "validity": report["validity"],
        "paired_subset": paired,
        "jaccard_mean": report["valid_window_subset_only"]["selection_jaccard_mean"],
        "resources": report["resources"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
