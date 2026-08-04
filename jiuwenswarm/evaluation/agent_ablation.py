#!/usr/bin/env python3
"""A0/A1/A2 Agent ablation experiment (WP0-B research acceptance).

Compares three configurations on the same snapshot, base scores, embargo
and position constraints:

  A0 — No Agent:  raw composite scores → select → allocate → backtest
  A1 — Alpha only: composite + Alpha proposals → select → allocate → backtest
  A2 — Dual Agent: composite + Alpha + Risk & Evidence proposals →
                    DecisionAssembler → select → allocate → backtest

Produces ablation_results_<timestamp>.json with per-variant returns,
MDD, P10, utility, position overlap and DecisionTrace.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# ---- Load extension ----
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_EXT_PATH = (
    _PROJECT_ROOT / "jiuwenswarm" / "extensions"
    / "quant-finance" / "extension.py"
)


def _load_extension():
    spec = importlib.util.spec_from_file_location("quant_ablation_ext", _EXT_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _pp_pct(value: float) -> str:
    return f"{value:+.4%}"


def _score(prices_df, weights: dict[str, float]) -> dict:
    """Compute realised return and MDD from price DataFrame and fixed weights."""
    import numpy as np

    rets = prices_df.pct_change().dropna(how="all")
    if rets.empty:
        return {"total_return": 0.0, "max_drawdown": 0.0,
                "p10_return": 0.0, "sharpe": 0.0}

    # Daily portfolio return
    port_rets = rets.multiply(pd.Series(weights)).sum(axis=1)
    port_rets = port_rets.fillna(0.0)

    total_ret = float((1.0 + port_rets).prod() - 1.0)
    cum = (1.0 + port_rets).cumprod()
    running_max = cum.expanding().max()
    drawdown = (cum / running_max - 1.0)
    max_dd = float(drawdown.min())

    # P10 daily return
    daily_sorted = sorted(port_rets.dropna())
    n = len(daily_sorted)
    p10_idx = max(0, int(n * 0.10))
    p10 = float(np.mean(daily_sorted[:p10_idx])) if p10_idx > 0 else 0.0

    # Sharpe (simple, no risk-free)
    mean_daily = float(port_rets.mean())
    std_daily = float(port_rets.std())
    sharpe = (mean_daily / std_daily * (252 ** 0.5)) if std_daily > 0 else 0.0

    return {
        "total_return": round(total_ret, 6),
        "max_drawdown": round(max_dd, 6),
        "p10_daily_return": round(p10, 6),
        "sharpe_ratio": round(sharpe, 4),
    }


def _position_overlap(a_weights: dict[str, float],
                      b_weights: dict[str, float]) -> dict:
    a_set = set(a_weights)
    b_set = set(b_weights)
    common = a_set & b_set
    only_a = a_set - b_set
    only_b = b_set - a_set
    return {
        "n_common": len(common),
        "n_only_a": len(only_a),
        "n_only_b": len(only_b),
        "common_tickers": sorted(common),
        "only_a_tickers": sorted(only_a),
        "only_b_tickers": sorted(only_b),
    }


def _utility(total_return: float, max_drawdown: float,
             penalty: float = 1.0) -> float:
    """Simple risk-adjusted utility: return − λ × |MDD|."""
    return round(total_return - penalty * abs(max_drawdown), 6)


# ---- Main ----
def main() -> int:
    ext = _load_extension()
    ext._data_cache.clear()
    ext._phase_results.clear()

    # Fetch data (same as direct pipeline)
    print("[1/6] Fetching data...")
    instance = ext.QuantFinanceExtension()
    fetched = asyncio.run(instance.fetch_data({}))
    if not fetched.get("success"):
        print(f"Fetch failed: {fetched.get('detail')}")
        return 1
    print(f"  {fetched['n_stocks']} stocks, {fetched['n_days']} days, "
          f"coverage={fetched['coverage_complete']}")

    # Compute factors
    print("[2/6] Computing factors...")
    factors = asyncio.run(instance.compute_factors({}))
    if not factors.get("success"):
        print(f"Factors failed: {factors.get('detail')}")
        return 1
    base_scores = factors["all_composite"]
    print(f"  Regime={factors['regime']}, "
          f"decision_date={factors['decision_date']}")

    # A0: No Agent — raw composite scores
    print("[3/6] A0: No Agent...")
    a0_selection = asyncio.run(instance.select_stocks({}))
    a0_alloc = asyncio.run(
        instance.allocate_positions({"tickers": a0_selection["tickers"]})
    )
    a0_backtest = asyncio.run(
        instance.run_backtest({"weights": a0_alloc["weights"]})
    )

    # A1: Alpha-only overlay
    print("[4/6] A1: Alpha only...")
    alpha_view = asyncio.run(instance.alpha_view({}))
    from jiuwenswarm.quant.agent_decision import AgentProposal, DecisionAssembler

    alpha_proposals = []
    for item in alpha_view.get("alpha_stocks", [])[:12]:
        ascore = item.get("alpha_score", 0)
        if ascore >= 7:
            alpha_proposals.append(AgentProposal(
                role="alpha", ticker=item["ticker"], action="include",
                adjustment=2, confidence="high",
                evidence=tuple(item.get("signals", [])[:2]),
                rationale=item.get("signals", [""])[0] if item.get("signals") else "",
            ))
        elif ascore >= 5:
            alpha_proposals.append(AgentProposal(
                role="alpha", ticker=item["ticker"], action="include",
                adjustment=1, confidence="medium",
                evidence=tuple(item.get("signals", [])[:1]),
                rationale=item.get("signals", [""])[0] if item.get("signals") else "",
            ))

    a1_trace = DecisionAssembler.assemble(dict(base_scores), alpha_proposals)
    # Override select cache to use A1 adjusted scores
    ext._update_cached_data(_scores_df=ext._get_cached_data()["_scores_df"].copy(),
                            _alpha_result=alpha_view)
    # Manually run selection with adjusted scores
    a1_sorted = sorted(a1_trace.adjusted_scores.items(), key=lambda x: x[1], reverse=True)
    from jiuwenswarm.quant.stock_pool import STOCK_POOL
    a1_selected = []
    sel_set = set()
    for sector in STOCK_POOL:
        for ticker, score in a1_sorted:
            if ticker in STOCK_POOL[sector] and ticker not in sel_set and score > -0.5:
                a1_selected.append(ticker)
                sel_set.add(ticker)
                break
    for ticker, score in a1_sorted:
        if len(a1_selected) >= 15:
            break
        if ticker not in sel_set and score > -0.5:
            a1_selected.append(ticker)
            sel_set.add(ticker)
    # Re-run allocate/backtest with A1 tickers
    ext._phase_results.pop("allocate_positions", None)
    ext._phase_results.pop("run_backtest", None)
    a1_alloc = asyncio.run(instance.allocate_positions({"tickers": a1_selected}))
    a1_backtest = asyncio.run(instance.run_backtest({"weights": a1_alloc["weights"]}))

    # A2: Dual Agent (Alpha + Risk & Evidence)
    print("[5/6] A2: Alpha + Risk & Evidence...")
    risk_view = asyncio.run(instance.risk_evidence_view({}))

    risk_proposals = []
    for item in risk_view.get("risky_stocks", [])[:12]:
        rscore = item.get("risk_score", 0)
        if rscore >= 8:
            risk_proposals.append(AgentProposal(
                role="risk_evidence", ticker=item["ticker"], action="exclude",
                adjustment=-3, confidence="high",
                evidence=tuple(item.get("warnings", [])[:2]),
                rationale=item.get("warnings", [""])[0] if item.get("warnings") else "",
            ))
        elif rscore >= 5:
            risk_proposals.append(AgentProposal(
                role="risk_evidence", ticker=item["ticker"], action="reduce",
                adjustment=-1, confidence="medium",
                evidence=tuple(item.get("warnings", [])[:2]),
                rationale=item.get("warnings", [""])[0] if item.get("warnings") else "",
            ))

    a2_trace = DecisionAssembler.assemble(dict(base_scores),
                                           alpha_proposals + risk_proposals)
    a2_sorted = sorted(a2_trace.adjusted_scores.items(), key=lambda x: x[1], reverse=True)
    a2_selected = []
    sel_set2 = set()
    for sector in STOCK_POOL:
        for ticker, score in a2_sorted:
            if ticker in STOCK_POOL[sector] and ticker not in sel_set2 and score > -0.5:
                a2_selected.append(ticker)
                sel_set2.add(ticker)
                break
    for ticker, score in a2_sorted:
        if len(a2_selected) >= 15:
            break
        if ticker not in sel_set2 and score > -0.5:
            a2_selected.append(ticker)
            sel_set2.add(ticker)
    ext._phase_results.pop("allocate_positions", None)
    ext._phase_results.pop("run_backtest", None)
    a2_alloc = asyncio.run(instance.allocate_positions({"tickers": a2_selected}))
    a2_backtest = asyncio.run(instance.run_backtest({"weights": a2_alloc["weights"]}))

    # ---- Compare ----
    print("[6/6] Comparing...")
    a0_metrics = {
        "total_return": a0_backtest.get("total_return", 0.0),
        "max_drawdown": a0_backtest.get("max_drawdown", 0.0),
    }
    a1_metrics = {
        "total_return": a1_backtest.get("total_return", 0.0),
        "max_drawdown": a1_backtest.get("max_drawdown", 0.0),
    }
    a2_metrics = {
        "total_return": a2_backtest.get("total_return", 0.0),
        "max_drawdown": a2_backtest.get("max_drawdown", 0.0),
    }

    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "regime": factors["regime"],
        "decision_date": factors["decision_date"],
        "n_base_stocks": len(base_scores),
        "A0_no_agent": {
            "description": "Raw composite scores, no Agent overlay",
            "tickers": a0_selection["tickers"],
            "weights": dict(a0_alloc["weights"]),
            "backtest": a0_metrics,
            "utility": _utility(a0_metrics["total_return"], a0_metrics["max_drawdown"]),
        },
        "A1_alpha_only": {
            "description": "Composite + Alpha Analyst proposals",
            "n_alpha_proposals": len(alpha_proposals),
            "n_accepted": len(a1_trace.accepted),
            "n_rejected": len(a1_trace.rejected),
            "tickers": a1_selected,
            "weights": dict(a1_alloc["weights"]),
            "backtest": a1_metrics,
            "utility": _utility(a1_metrics["total_return"], a1_metrics["max_drawdown"]),
            "vs_A0": {
                "return_delta_pp": round((a1_metrics["total_return"] - a0_metrics["total_return"]) * 100, 4),
                "mdd_delta_pp": round((a1_metrics["max_drawdown"] - a0_metrics["max_drawdown"]) * 100, 4),
                "utility_delta": round(
                    _utility(a1_metrics["total_return"], a1_metrics["max_drawdown"])
                    - _utility(a0_metrics["total_return"], a0_metrics["max_drawdown"]), 6),
            },
            "overlap_vs_A0": _position_overlap(dict(a1_alloc["weights"]), dict(a0_alloc["weights"])),
        },
        "A2_dual_agent": {
            "description": "Composite + Alpha + Risk & Evidence proposals",
            "n_alpha_proposals": len(alpha_proposals),
            "n_risk_proposals": len(risk_proposals),
            "n_total_accepted": len(a2_trace.accepted),
            "n_rejected": len(a2_trace.rejected),
            "n_excluded": sum(1 for p in a2_trace.accepted if p.action == "exclude"),
            "tickers": a2_selected,
            "weights": dict(a2_alloc["weights"]),
            "backtest": a2_metrics,
            "utility": _utility(a2_metrics["total_return"], a2_metrics["max_drawdown"]),
            "vs_A0": {
                "return_delta_pp": round((a2_metrics["total_return"] - a0_metrics["total_return"]) * 100, 4),
                "mdd_delta_pp": round((a2_metrics["max_drawdown"] - a0_metrics["max_drawdown"]) * 100, 4),
                "utility_delta": round(
                    _utility(a2_metrics["total_return"], a2_metrics["max_drawdown"])
                    - _utility(a0_metrics["total_return"], a0_metrics["max_drawdown"]), 6),
            },
            "vs_A1": {
                "return_delta_pp": round((a2_metrics["total_return"] - a1_metrics["total_return"]) * 100, 4),
                "mdd_delta_pp": round((a2_metrics["max_drawdown"] - a1_metrics["max_drawdown"]) * 100, 4),
            },
            "overlap_vs_A0": _position_overlap(dict(a2_alloc["weights"]), dict(a0_alloc["weights"])),
        },
        "decision_trace_A1": {
            "n_accepted": len(a1_trace.accepted),
            "n_rejected": len(a1_trace.rejected),
        },
        "decision_trace_A2": {
            "n_accepted": len(a2_trace.accepted),
            "n_rejected": len(a2_trace.rejected),
            "reject_reasons": dict(a2_trace.reject_reasons),
        },
    }

    # Print summary
    print(f"\n{'='*60}")
    print("ABLATION RESULTS")
    print(f"{'='*60}")
    for label, key in [("A0  No Agent       ", "A0_no_agent"),
                        ("A1  Alpha only     ", "A1_alpha_only"),
                        ("A2  Dual Agent     ", "A2_dual_agent")]:
        v = result[key]
        bt = v["backtest"]
        print(f"  {label}: return={_pp_pct(bt['total_return'])}, "
              f"MDD={_pp_pct(bt['max_drawdown'])}, "
              f"utility={v['utility']:.6f}")

    print(f"\n  A1 vs A0: return {result['A1_alpha_only']['vs_A0']['return_delta_pp']:+.4f}pp, "
          f"MDD {result['A1_alpha_only']['vs_A0']['mdd_delta_pp']:+.4f}pp")
    print(f"  A2 vs A0: return {result['A2_dual_agent']['vs_A0']['return_delta_pp']:+.4f}pp, "
          f"MDD {result['A2_dual_agent']['vs_A0']['mdd_delta_pp']:+.4f}pp")
    print(f"  Position overlap (A0 vs A1): {result['A1_alpha_only']['overlap_vs_A0']['n_common']}/15")
    print(f"  Position overlap (A0 vs A2): {result['A2_dual_agent']['overlap_vs_A0']['n_common']}/15")

    # Agent causal verdict
    a1_delta = result["A1_alpha_only"]["vs_A0"]["return_delta_pp"]
    a2_delta = result["A2_dual_agent"]["vs_A0"]["return_delta_pp"]
    if abs(a1_delta) < 0.01 and abs(a2_delta) < 0.01:
        result["agent_causal_verdict"] = "NO_SIGNIFICANT_EFFECT"
        print("\n  VERDICT: Agent overlay has no significant effect on returns.")
        print("  AGENT_OVERLAY_ENABLED should remain False.")
    elif a2_delta >= a1_delta >= 0:
        result["agent_causal_verdict"] = "POSITIVE_INCREMENTAL"
    else:
        result["agent_causal_verdict"] = "MIXED_OR_NEGATIVE"
        print("\n  VERDICT: Agent overlay does not show clear positive increment.")
        print("  AGENT_OVERLAY_ENABLED should remain False until outer evidence.")

    out_path = _PROJECT_ROOT.parent / "output" / \
        f"ablation_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"\n  Results saved to {out_path}")
    return 0


if __name__ == "__main__":
    import pandas as pd  # noqa: E402
    sys.exit(main())
