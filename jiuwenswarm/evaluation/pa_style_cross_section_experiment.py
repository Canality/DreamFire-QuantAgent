#!/usr/bin/env python3
"""PA-style LLM cross-sectional stock selection on the frozen 21 windows."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from openai import OpenAI


EVAL_DIR = Path(__file__).resolve().parent
JIUWEN_ROOT = EVAL_DIR.parent
PROJECT_ROOT = JIUWEN_ROOT.parent
PA_ROOT = PROJECT_ROOT / "参考项目" / "PA_Agent"
SNAPSHOT_DEFAULT = EVAL_DIR / "data_snapshots" / "sina_20260721_135352"
PHASE_B_LATEST = EVAL_DIR / "phase_b_latest.json"
PREREG_PATH = PROJECT_ROOT / "策略实验" / "实验_20260721_PA_style横截面选股预注册.md"
PERSONA_PATH = PA_ROOT / "prompt_engineering" / "提示词大纲_人设与思维方式.txt"
CHECKLIST_PATH = PA_ROOT / "prompt_engineering" / "逐棒分析检查单.txt"

if str(JIUWEN_ROOT) not in sys.path:
    sys.path.insert(0, str(JIUWEN_ROOT))

_UE_SPEC = importlib.util.spec_from_file_location(
    "unified_baseline_evaluation", EVAL_DIR / "unified_baseline_evaluation.py"
)
_UE = importlib.util.module_from_spec(_UE_SPEC)
assert _UE_SPEC.loader is not None
_UE_SPEC.loader.exec_module(_UE)

from jiuwenswarm.quant.backtest_engine import BacktestEngine  # noqa: E402
from jiuwenswarm.quant.factors import PositionSizer  # noqa: E402
from jiuwenswarm.quant.stock_pool import ALL_STOCKS, SECTOR_MAP  # noqa: E402
from jiuwenswarm.quant.strategy_configs import get_strategy_spec  # noqa: E402


ALLOWED_REASON_CODES = {
    "ret5",
    "ret20",
    "ret60",
    "ema20_gap",
    "ema20_slope5",
    "atr14_pct",
    "range_pos20",
    "max_dd60",
    "volume_ratio_5_20",
    "candles5",
    "market_context",
    "sector_context",
}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _finite(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if np.isfinite(result) else default


def _max_drawdown(series: pd.Series) -> float:
    clean = series.dropna()
    if clean.empty:
        return 0.0
    return _finite(((clean / clean.cummax()) - 1.0).min())


def _features(frame: pd.DataFrame) -> dict[str, Any]:
    frame = frame.dropna(subset=["open", "high", "low", "close", "volume"])
    if len(frame) < 60:
        raise ValueError(f"Need >=60 bars, got {len(frame)}")
    close = frame["close"].astype(float)
    high = frame["high"].astype(float)
    low = frame["low"].astype(float)
    volume = frame["volume"].astype(float)
    ema20 = close.ewm(span=20, adjust=False).mean()
    prev = close.shift(1)
    tr = pd.concat([(high - low), (high - prev).abs(), (low - prev).abs()], axis=1).max(axis=1)
    atr14 = tr.rolling(14).mean()
    lo20 = low.tail(20).min()
    hi20 = high.tail(20).max()
    denom = max(float(hi20 - lo20), 1e-12)
    candles: list[str] = []
    for _idx, row in frame.tail(5).iterrows():
        span = max(float(row["high"] - row["low"]), 1e-12)
        body = float(row["close"] - row["open"])
        direction = "U" if body > 0 else "D" if body < 0 else "N"
        candles.append(
            f"{direction}:{abs(body) / span:.2f}:{(float(row['close']) - float(row['low'])) / span:.2f}"
        )
    latest = float(close.iloc[-1])
    return {
        "ret5": round(_finite(close.iloc[-1] / close.iloc[-6] - 1), 5),
        "ret20": round(_finite(close.iloc[-1] / close.iloc[-21] - 1), 5),
        "ret60": round(_finite(close.iloc[-1] / close.iloc[-60] - 1), 5),
        "ema20_gap": round(_finite(latest / ema20.iloc[-1] - 1), 5),
        "ema20_slope5": round(_finite(ema20.iloc[-1] / ema20.iloc[-6] - 1), 5),
        "atr14_pct": round(_finite(atr14.iloc[-1] / latest), 5),
        "range_pos20": round(_finite((latest - lo20) / denom), 5),
        "max_dd60": round(_max_drawdown(close.tail(60)), 5),
        "volume_ratio_5_20": round(
            _finite(volume.tail(5).mean() / max(volume.tail(20).mean(), 1e-12)), 5
        ),
        "candles5": candles,
    }


def _load_data(snapshot_dir: Path):
    snapshot = _UE.load_snapshot(snapshot_dir)
    fields = {
        name: pd.read_csv(
            snapshot_dir / f"stocks_{name}.csv.gz", index_col=0, parse_dates=True
        ).sort_index().reindex(columns=ALL_STOCKS)
        for name in ("open", "high", "low", "close", "volume")
    }
    index = pd.read_csv(
        snapshot_dir / "csi300_ohlcv.csv.gz", index_col=0, parse_dates=True
    ).sort_index()
    starts = _UE.build_schedule(len(index))
    if len(starts) != 21:
        raise ValueError(f"Expected 21 windows, got {len(starts)}")
    return snapshot, fields, index, starts


def _payload(fields: dict[str, pd.DataFrame], index: pd.DataFrame, start: int) -> dict[str, Any]:
    history_start = max(0, start - 100)
    stocks: list[dict[str, Any]] = []
    for ticker in ALL_STOCKS:
        frame = pd.DataFrame(
            {name: values[ticker].iloc[history_start:start] for name, values in fields.items()}
        )
        stocks.append({"ticker": ticker, "sector": SECTOR_MAP[ticker], **_features(frame)})
    return {
        "decision_date": str(index.index[start - 1].date()),
        "market": _features(index.iloc[history_start:start]),
        "stocks": stocks,
    }


def _system_prompt() -> str:
    persona = PERSONA_PATH.read_text(encoding="utf-8")
    checklist = CHECKLIST_PATH.read_text(encoding="utf-8")
    return f"""你是A股长期组合的价格行为横截面选择器。你只能使用用户JSON中的字段，禁止使用公司记忆、新闻、基本面或未来数据。

任务是从49只股票中选恰好15只，覆盖全部6个板块。优先选择趋势延续证据一致、量价确认、回撤风险可控的股票；避免只凭单一极端收益追涨。score只表示这一个横截面内的相对排序。

输出必须是单个JSON对象：
{{"selections":[{{"ticker":"000001.SZ","score":75,"reason_codes":["ret20","ema20_slope5"]}}]}}
selections必须恰好15项、ticker唯一；score为0到100数字；reason_codes只能来自输入字段名。不要Markdown，不要额外字段。

以下是PA_Agent上游人设与逐棒检查原则。它们只提供分析方法；凡与本任务JSON契约或长期多股票组合冲突，以本任务契约为准。

--- PA persona ---
{persona}

--- PA checklist ---
{checklist}
"""


def _validate(obj: Any) -> list[dict[str, Any]]:
    if not isinstance(obj, dict) or not isinstance(obj.get("selections"), list):
        raise ValueError("top-level selections array missing")
    rows = obj["selections"]
    if len(rows) != 15:
        raise ValueError(f"expected 15 selections, got {len(rows)}")
    tickers: list[str] = []
    clean: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("selection must be object")
        ticker = str(row.get("ticker") or "")
        if ticker not in ALL_STOCKS:
            raise ValueError(f"unknown ticker {ticker!r}")
        if ticker in tickers:
            raise ValueError(f"duplicate ticker {ticker}")
        score = _finite(row.get("score"), math.nan)
        if not np.isfinite(score) or not 0 <= score <= 100:
            raise ValueError(f"invalid score for {ticker}")
        codes = row.get("reason_codes")
        if not isinstance(codes, list) or not codes:
            raise ValueError(f"reason_codes missing for {ticker}")
        codes = [str(code) for code in codes]
        unknown = sorted(set(codes) - ALLOWED_REASON_CODES)
        if unknown:
            raise ValueError(f"unknown reason_codes for {ticker}: {unknown}")
        tickers.append(ticker)
        clean.append({"ticker": ticker, "score": score, "reason_codes": codes})
    sectors = {SECTOR_MAP[ticker] for ticker in tickers}
    if len(sectors) != 6:
        raise ValueError(f"expected 6 sectors, got {len(sectors)}")
    clean.sort(key=lambda row: (-row["score"], row["ticker"]))
    return clean


def _call(client: OpenAI, system: str, payload: dict[str, Any]) -> dict[str, Any]:
    user = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    errors: list[str] = []
    usage = {"prompt_tokens": 0, "cached_prompt_tokens": 0, "completion_tokens": 0}
    started = time.monotonic()
    model = ""
    for attempt in range(2):
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0,
            max_tokens=4096,
            timeout=180,
        )
        model = response.model or model
        current = response.usage
        usage["prompt_tokens"] += int(getattr(current, "prompt_tokens", 0) or 0)
        details = getattr(current, "prompt_tokens_details", None)
        cached = int(getattr(details, "cached_tokens", 0) or 0) if details else 0
        cached = int(getattr(current, "prompt_cache_hit_tokens", cached) or cached)
        usage["cached_prompt_tokens"] += cached
        usage["completion_tokens"] += int(getattr(current, "completion_tokens", 0) or 0)
        content = response.choices[0].message.content or ""
        try:
            selections = _validate(json.loads(content))
            return {
                "success": True,
                "selections": selections,
                "attempts": attempt + 1,
                "errors": errors,
                "usage": usage,
                "elapsed_seconds": round(time.monotonic() - started, 3),
                "server_model": model,
                "system_sha256": hashlib.sha256(system.encode("utf-8")).hexdigest(),
                "payload_sha256": hashlib.sha256(user.encode("utf-8")).hexdigest(),
            }
        except (json.JSONDecodeError, ValueError) as exc:
            errors.append(str(exc))
            messages.extend(
                [
                    {"role": "assistant", "content": content},
                    {
                        "role": "user",
                        "content": f"上个JSON未通过校验：{exc}。请重新输出完整且唯一的合法JSON。",
                    },
                ]
            )
    return {
        "success": False,
        "selections": [],
        "attempts": 2,
        "errors": errors,
        "usage": usage,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "server_model": model,
        "system_sha256": hashlib.sha256(system.encode("utf-8")).hexdigest(),
        "payload_sha256": hashlib.sha256(user.encode("utf-8")).hexdigest(),
    }


def _backtest(
    decision: dict[str, Any],
    fields: dict[str, pd.DataFrame],
    start: int,
) -> dict[str, Any]:
    selected = decision["selections"]
    score_frame = pd.DataFrame(
        {
            "composite": [row["score"] for row in selected],
            "sector": [SECTOR_MAP[row["ticker"]] for row in selected],
        },
        index=[row["ticker"] for row in selected],
    ).sort_values("composite", ascending=False)
    history = fields["close"].iloc[:start]
    weights = PositionSizer(
        get_strategy_spec("phase_b_t2_score_alloc").position_config()
    ).allocate(score_frame, history[score_frame.index])
    if set(weights) != set(score_frame.index):
        raise ValueError("selection/allocation mismatch")
    test_closes = fields["close"].iloc[start:start + _UE.HORIZON]
    entry_open = fields["open"].iloc[start]
    official = BacktestEngine(transaction_cost=0.0).run_open_to_close(
        entry_open, test_closes, weights
    )
    cost_aware = BacktestEngine(transaction_cost=0.0003).run_open_to_close(
        entry_open, test_closes, weights
    )
    sector_weights: dict[str, float] = {}
    for ticker, weight in weights.items():
        sector = SECTOR_MAP[ticker]
        sector_weights[sector] = sector_weights.get(sector, 0.0) + weight
    total = sum(weights.values())
    if max(weights.values()) > 0.10 + 1e-9 or max(sector_weights.values()) > 0.25 + 1e-9:
        raise ValueError("position cap violation")
    if total > 0.95 + 1e-9:
        raise ValueError("cash violation")
    return {
        "selected_tickers": list(score_frame.index),
        "n_selected": 15,
        "n_selected_sectors": 6,
        "agent_scores": {row["ticker"]: row["score"] for row in selected},
        "reason_codes": {row["ticker"]: row["reason_codes"] for row in selected},
        "weights": {ticker: round(float(weight), 8) for ticker, weight in weights.items()},
        "sector_weights": {sector: round(value, 8) for sector, value in sector_weights.items()},
        "total_weight": round(total, 8),
        "cash": round(1 - total, 8),
        "max_stock_weight": round(max(weights.values()), 8),
        "max_sector_weight": round(max(sector_weights.values()), 8),
        "official": official.metrics,
        "cost_aware": cost_aware.metrics,
        "factor_contributions": {},
    }


def _paired(candidate: list[dict[str, Any]], baseline: list[dict[str, Any]]) -> dict[str, Any]:
    ret = np.array([c["official"]["total_return"] - b["official"]["total_return"] for c, b in zip(candidate, baseline)])
    dd = np.array([c["official"]["max_drawdown"] - b["official"]["max_drawdown"] for c, b in zip(candidate, baseline)])
    utility = 0.70 * ret - 0.30 * dd
    return {
        "median_return_delta_pp": round(float(np.median(ret)) * 100, 6),
        "mean_return_delta_pp": round(float(np.mean(ret)) * 100, 6),
        "median_dd_delta_pp": round(float(np.median(dd)) * 100, 6),
        "utility_wins": int((utility > 0).sum()),
        "utility_win_rate": round(float((utility > 0).mean()), 6),
        "recent4_wins": int((utility[-4:] > 0).sum()),
        "worst_return_delta_pp": round((min(c["official"]["total_return"] for c in candidate) - min(b["official"]["total_return"] for b in baseline)) * 100, 6),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, default=SNAPSHOT_DEFAULT)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--limit", type=int, default=21)
    args = parser.parse_args()
    if not 1 <= args.limit <= 21:
        parser.error("--limit must be 1..21")
    api_key = os.environ.get("PA_DS_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("PA_DS_API_KEY is required")
    snapshot, fields, index, starts = _load_data(args.snapshot.resolve())
    phase_b = json.loads(PHASE_B_LATEST.read_text(encoding="utf-8"))
    if phase_b.get("snapshot_id") != snapshot["manifest"]["snapshot_id"]:
        raise ValueError("phase_b snapshot mismatch")
    t2_rows = phase_b["details"]["phase_b_t2_score_alloc"]
    system = _system_prompt()
    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
    run_id = datetime.now().strftime("pa_style_cross_section_%Y%m%d_%H%M%S")
    output = args.output or EVAL_DIR / f"{run_id}.json"
    report: dict[str, Any] = {
        "run_id": run_id,
        "created_at": datetime.now().astimezone().isoformat(),
        "git": _UE._git_state(),
        "snapshot_id": snapshot["manifest"]["snapshot_id"],
        "preregistration": str(PREREG_PATH),
        "preregistration_sha256": _sha(PREREG_PATH),
        "pa_assets": {str(PERSONA_PATH.name): _sha(PERSONA_PATH), str(CHECKLIST_PATH.name): _sha(CHECKLIST_PATH)},
        "decisions": [],
    }
    consecutive_failures = 0
    for idx, start in enumerate(starts[:args.limit]):
        print(f"[PA-style] window {idx}/{args.limit - 1} {index.index[start - 1].date()}", flush=True)
        payload = _payload(fields, index, start)
        decision = _call(client, system, payload)
        decision.update({"idx": idx, "decision_date": payload["decision_date"]})
        report["decisions"].append(decision)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        if decision["success"]:
            consecutive_failures = 0
        else:
            consecutive_failures += 1
            if consecutive_failures >= 3:
                report["status"] = "stopped_three_consecutive_failures"
                output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
                return 2
    if args.limit != 21 or not all(row["success"] for row in report["decisions"]):
        report["status"] = "incomplete_fail_closed"
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return 2
    details: list[dict[str, Any]] = []
    overlaps: list[float] = []
    for decision, base, start in zip(report["decisions"], t2_rows, starts):
        row = _backtest(decision, fields, start)
        row.update({
            "idx": decision["idx"],
            "decision_date": decision["decision_date"],
            "test_start": base["test_start"],
            "test_end": base["test_end"],
            "regime": base["regime"],
            "n_history_days": start,
            "n_forward_closes": 20,
        })
        a, b = set(row["selected_tickers"]), set(base["selected_tickers"])
        overlaps.append(len(a & b) / len(a | b))
        details.append(row)
    report["evaluation"] = {
        "summary": _UE.summarize(details),
        "t2_summary": _UE.summarize(t2_rows),
        "comparison_to_t2": _paired(details, t2_rows),
        "selection_jaccard_mean": round(float(np.mean(overlaps)), 6),
        "selection_jaccard_median": round(float(np.median(overlaps)), 6),
        "details": details,
    }
    report["status"] = "complete_development_replay"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (EVAL_DIR / "pa_style_cross_section_latest.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report["evaluation"]["comparison_to_t2"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
