#!/usr/bin/env python3
"""PA_Agent native two-stage CSI300 diagnosis as a T2 exposure overlay.

This is a development-set experiment, not holdout validation.  PA_Agent is
kept in its native single-symbol role: it diagnoses CSI300 and may only scale
the total exposure of the already-frozen T2 portfolio.  It never sees forward
bars and never changes selected tickers or their relative weights.

Run this module with PA_Agent's locked virtual environment because the native
orchestrator imports its GUI/runtime dependencies::

    ..\..\参考项目\PA_Agent\.venv\Scripts\python.exe \
      evaluation\pa_native_regime_experiment.py --dry-run

The DeepSeek key is read only from ``PA_DS_API_KEY``.  It is never persisted.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


EVAL_DIR = Path(__file__).resolve().parent
JIUWEN_ROOT = EVAL_DIR.parent
PROJECT_ROOT = JIUWEN_ROOT.parent
PA_ROOT = PROJECT_ROOT / "参考项目" / "PA_Agent"
SNAPSHOT_DEFAULT = EVAL_DIR / "data_snapshots" / "sina_20260721_135352"
PHASE_B_LATEST = EVAL_DIR / "phase_b_latest.json"
PROMPT_VERSION = "pa_native_upstream_71fbade_failclosed_wrapper_v1"
SENTINEL_WINDOWS = (0, 10, 20)

for path in (JIUWEN_ROOT, PA_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

_UE_SPEC = importlib.util.spec_from_file_location(
    "unified_baseline_evaluation", EVAL_DIR / "unified_baseline_evaluation.py"
)
_UE = importlib.util.module_from_spec(_UE_SPEC)
assert _UE_SPEC.loader is not None
_UE_SPEC.loader.exec_module(_UE)

from jiuwenswarm.quant.backtest_engine import BacktestEngine  # noqa: E402
from jiuwenswarm.quant.stock_pool import SECTOR_MAP  # noqa: E402

from pa_agent.ai.deepseek_client import DeepSeekClient  # noqa: E402
from pa_agent.ai.json_validator import JsonValidator, ValidationError  # noqa: E402
from pa_agent.ai.prompt_assembler import PromptAssembler  # noqa: E402
from pa_agent.ai.router import route_strategy_files  # noqa: E402
from pa_agent.config.paths import PROMPT_DIR  # noqa: E402
from pa_agent.config.settings import (  # noqa: E402
    AIProviderSettings,
    GeneralSettings,
    PromptSettings,
    Settings,
    ValidationSettings,
)
from pa_agent.data.base import KlineBar, KlineFrame  # noqa: E402
from pa_agent.data.snapshot import compute_indicators  # noqa: E402
from pa_agent.orchestrator.two_stage import TwoStageOrchestrator  # noqa: E402
from pa_agent.records.experience_reader import ExperienceReader  # noqa: E402
from pa_agent.records.pending_writer import PendingWriter  # noqa: E402
from pa_agent.util.event_bus import EventBus  # noqa: E402
from pa_agent.util.threading import CancelToken  # noqa: E402


PREREGISTRATION_PATH = PROJECT_ROOT / "策略实验" / "实验_20260721_PA_Agent原生判市预注册.md"


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _git_state() -> dict[str, Any]:
    return _UE._git_state()


def _strip_fences(text: str) -> str:
    stripped = (text or "").strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines:
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    return stripped


class FailClosedJsonValidator(JsonValidator):
    """Reject dangerous raw contradictions before PA's normalizers repair them."""

    def validate(self, stage: str, raw_text: str, **kwargs: Any):  # type: ignore[override]
        stripped = _strip_fences(raw_text)
        try:
            raw = json.loads(stripped)
        except json.JSONDecodeError as exc:
            return ValidationError(
                category="a",
                stage=stage,
                raw_text=raw_text,
                parse_position=f"{exc.lineno}:{exc.colno}",
                message=f"Fail-closed raw JSON syntax error: {exc.msg}",
            )
        if not isinstance(raw, dict):
            return ValidationError(
                category="a",
                stage=stage,
                raw_text=raw_text,
                message="Fail-closed top-level JSON must be an object",
            )
        if stage == "stage2":
            decision = raw.get("decision")
            if isinstance(decision, dict):
                order_type = decision.get("order_type")
                price_fields = (
                    "entry_price",
                    "take_profit_price",
                    "take_profit_price_2",
                    "stop_loss_price",
                )
                if order_type == "不下单" and any(
                    decision.get(field) is not None for field in price_fields
                ):
                    return ValidationError(
                        category="c",
                        stage=stage,
                        raw_text=raw_text,
                        invalid_fields=["decision.no_order_price_fields"],
                        message="Fail-closed: no-order decision contains prices",
                    )
                if order_type == "突破单" and not (
                    decision.get("entry_basis_bar")
                    and decision.get("entry_basis_extreme")
                ):
                    return ValidationError(
                        category="c",
                        stage=stage,
                        raw_text=raw_text,
                        invalid_fields=["decision.breakout_basis"],
                        message="Fail-closed: breakout order lacks explicit basis",
                    )
        return super().validate(stage, raw_text, **kwargs)


def _settings(api_key: str) -> Settings:
    validation = ValidationSettings(
        normalization_mode="strict",
        stage1_coherence_checks=True,
        stage2_coherence_checks=True,
        trace_semantic_checks=True,
        strict_bar_by_bar_features=True,
        disable_truncation_repair=True,
        retry_enabled=True,
        retry_max=1,
        retry_max_semantic=0,
        retry_stage2=True,
    )
    return Settings(
        provider=AIProviderSettings(
            model="deepseek-chat",
            base_url="https://api.deepseek.com",
            api_key=api_key,
            thinking=False,
            reasoning_effort="low",
            context_window=128_000,
        ),
        general=GeneralSettings(
            analysis_bar_count=100,
            last_symbol="CSI300",
            last_timeframe="1d",
            decision_stance="balanced",
            enable_next_bar_prediction=False,
        ),
        prompt=PromptSettings(
            stage2_load_full_strategy_library=False,
            experience_max_entries=0,
            experience_max_chars_per_entry=400,
            stage1_inject_pattern_briefs=True,
        ),
        validation=validation,
    )


def _load_market(snapshot_dir: Path) -> tuple[dict[str, Any], pd.DataFrame, list[int]]:
    snapshot = _UE.load_snapshot(snapshot_dir)
    index_ohlcv = pd.read_csv(
        snapshot_dir / "csi300_ohlcv.csv.gz", index_col=0, parse_dates=True
    ).sort_index()
    required = ["open", "high", "low", "close", "volume"]
    if list(index_ohlcv.columns) != required:
        index_ohlcv = index_ohlcv.reindex(columns=required)
    if index_ohlcv[required].isna().any().any():
        raise ValueError("CSI300 OHLCV contains missing values")
    starts = _UE.build_schedule(len(index_ohlcv))
    if len(starts) != 21:
        raise ValueError(f"Expected 21 portfolio windows, got {len(starts)}")
    return snapshot, index_ohlcv, starts


def _to_frame(index_ohlcv: pd.DataFrame, start: int, max_bars: int = 100) -> KlineFrame:
    history = index_ohlcv.iloc[max(0, start - max_bars):start]
    if len(history) < 80:
        raise ValueError(f"PA history requires at least 80 bars, got {len(history)}")
    bars: list[KlineBar] = []
    for seq, (timestamp, row) in enumerate(history.iloc[::-1].iterrows(), start=1):
        ts = pd.Timestamp(timestamp)
        if ts.tzinfo is None:
            ts = ts.tz_localize("Asia/Shanghai")
        bars.append(
            KlineBar(
                seq=seq,
                ts_open=int(ts.timestamp() * 1000),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row["volume"]),
                closed=True,
            )
        )
    return KlineFrame(
        symbol="CSI300",
        timeframe="1d",
        bars=tuple(bars),
        indicators=compute_indicators(bars),
        snapshot_ts_local_ms=int(pd.Timestamp(history.index[-1]).timestamp() * 1000),
    )


def _make_components(api_key: str, runtime_dir: Path):
    settings = _settings(api_key)
    experience_dir = runtime_dir / "empty_experience"
    pending_dir = runtime_dir / "pending"
    experience_dir.mkdir(parents=True, exist_ok=True)
    pending_dir.mkdir(parents=True, exist_ok=True)
    exp_reader = ExperienceReader(experience_dir=experience_dir)
    assembler = PromptAssembler(
        prompt_dir=PROMPT_DIR,
        experience_reader=exp_reader,
        prompt_settings=settings.prompt,
    )
    validator = FailClosedJsonValidator(settings.validation)
    event_bus = EventBus()
    writer = PendingWriter(
        pending_dir=pending_dir,
        event_bus=event_bus,
        api_key=api_key,
    )
    orchestrator = TwoStageOrchestrator(
        client=DeepSeekClient(settings.provider),
        assembler=assembler,
        router=route_strategy_files,
        validator=validator,
        pending_writer=writer,
        exp_reader=exp_reader,
        settings=settings,
    )
    return settings, assembler, orchestrator


def _prompt_stats(messages: list[dict[str, Any]]) -> dict[str, Any]:
    contents = [str(message.get("content") or "") for message in messages]
    joined = "\n\n".join(contents)
    try:
        import tiktoken

        tokens = len(tiktoken.get_encoding("cl100k_base").encode(joined))
    except Exception:
        tokens = None
    return {
        "messages": len(messages),
        "characters": len(joined),
        "estimated_tokens_cl100k": tokens,
        "sha256": _sha256_text(joined),
    }


def _record_window(
    window_idx: int,
    start: int,
    index_ohlcv: pd.DataFrame,
    orchestrator: TwoStageOrchestrator,
    assembler: PromptAssembler,
) -> dict[str, Any]:
    frame = _to_frame(index_ohlcv, start)
    stage1_messages = assembler.build_stage1(frame, analysis_mode="original")
    prompt_stats = _prompt_stats(stage1_messages)
    events: list[str] = []
    started = time.monotonic()
    record = orchestrator.submit(
        frame=frame,
        cancel_token=CancelToken(),
        on_event=lambda event: events.append(event.name),
    )
    elapsed = time.monotonic() - started
    stage1 = record.stage1_diagnosis
    stage2 = record.stage2_decision
    decision = stage2.get("decision", {}) if isinstance(stage2, dict) else {}
    order_type = decision.get("order_type")
    order_direction = decision.get("order_direction")
    if order_type == "不下单" or not order_type:
        normalized_direction = "neutral"
    elif order_direction == "做多":
        normalized_direction = "bullish"
    elif order_direction == "做空":
        normalized_direction = "bearish"
    else:
        normalized_direction = "neutral"
    confidence = decision.get("trade_confidence")
    if confidence is None and isinstance(stage1, dict):
        confidence = stage1.get("diagnosis_confidence")
    usage = dict(record.usage_total or {})
    return {
        "idx": window_idx,
        "decision_date": str(index_ohlcv.index[start - 1].date()),
        "history_start": str(index_ohlcv.index[max(0, start - 100)].date()),
        "history_bars": len(frame.bars),
        "prompt_version": PROMPT_VERSION,
        "stage1_prompt": prompt_stats,
        "events": events,
        "elapsed_seconds": round(elapsed, 3),
        "stage1": stage1,
        "strategy_files_used": list(record.strategy_files_used or []),
        "stage2": stage2,
        "normalized_direction": normalized_direction,
        "confidence": float(confidence or 0),
        "usage": usage,
        "exception": record.exception,
        "success": bool(stage1) and bool(stage2) and not record.exception,
    }


def _target_exposure(decision: dict[str, Any], mapping: str) -> float:
    direction = decision["normalized_direction"]
    confidence = float(decision.get("confidence") or 0)
    if mapping == "pa_m1":
        if direction == "bullish":
            return 0.95 if confidence >= 60 else 0.85
        if direction == "bearish":
            return 0.55
        return 0.75
    if mapping == "pa_m2":
        if direction == "bearish" and confidence >= 60:
            return 0.70
        return 0.95
    raise ValueError(mapping)


def _scale_t2_rows(
    decisions: list[dict[str, Any]],
    t2_rows: list[dict[str, Any]],
    opens: pd.DataFrame,
    closes: pd.DataFrame,
    starts: list[int],
    mapping: str,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for decision, base, start in zip(decisions, t2_rows, starts):
        if decision["idx"] != base["idx"] or decision["decision_date"] != base["decision_date"]:
            raise ValueError("PA and T2 windows are not aligned")
        target = _target_exposure(decision, mapping)
        base_weights = {ticker: float(value) for ticker, value in base["weights"].items()}
        base_total = sum(base_weights.values())
        scale = min(1.0, target / base_total)
        weights = {ticker: value * scale for ticker, value in base_weights.items()}
        entry_open = opens.iloc[start]
        test_closes = closes.iloc[start:start + _UE.HORIZON]
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
        if max(weights.values()) > 0.10 + 1e-9:
            raise ValueError("Scaled portfolio violates stock cap")
        if max(sector_weights.values()) > 0.25 + 1e-9:
            raise ValueError("Scaled portfolio violates sector cap")
        if total > 0.95 + 1e-9:
            raise ValueError("Scaled portfolio violates total exposure cap")
        row = dict(base)
        row.update(
            {
                "strategy": mapping,
                "pa_direction": decision["normalized_direction"],
                "pa_confidence": decision["confidence"],
                "target_exposure": target,
                "weights": {k: round(v, 8) for k, v in weights.items()},
                "sector_weights": {k: round(v, 8) for k, v in sector_weights.items()},
                "total_weight": round(total, 8),
                "cash": round(1.0 - total, 8),
                "max_stock_weight": round(max(weights.values()), 8),
                "max_sector_weight": round(max(sector_weights.values()), 8),
                "official": official.metrics,
                "cost_aware": cost_aware.metrics,
            }
        )
        results.append(row)
    return results


def _paired(candidate: list[dict[str, Any]], baseline: list[dict[str, Any]]) -> dict[str, Any]:
    returns = np.array(
        [c["official"]["total_return"] - b["official"]["total_return"]
         for c, b in zip(candidate, baseline)],
        dtype=float,
    )
    drawdowns = np.array(
        [c["official"]["max_drawdown"] - b["official"]["max_drawdown"]
         for c, b in zip(candidate, baseline)],
        dtype=float,
    )
    utility = 0.70 * returns - 0.30 * drawdowns
    return {
        "median_return_delta_pp": round(float(np.median(returns)) * 100, 6),
        "mean_return_delta_pp": round(float(np.mean(returns)) * 100, 6),
        "median_dd_delta_pp": round(float(np.median(drawdowns)) * 100, 6),
        "utility_wins": int((utility > 0).sum()),
        "utility_win_rate": round(float((utility > 0).mean()), 6),
        "recent4_wins": int((utility[-4:] > 0).sum()),
        "worst_return_delta_pp": round(
            (min(row["official"]["total_return"] for row in candidate)
             - min(row["official"]["total_return"] for row in baseline)) * 100,
            6,
        ),
    }


def _evaluate(
    decisions: list[dict[str, Any]],
    snapshot: dict[str, Any],
    starts: list[int],
) -> dict[str, Any]:
    phase_b = json.loads(PHASE_B_LATEST.read_text(encoding="utf-8"))
    if phase_b.get("snapshot_id") != snapshot["manifest"]["snapshot_id"]:
        raise ValueError("phase_b_latest snapshot does not match PA experiment snapshot")
    t2_rows = phase_b["details"]["phase_b_t2_score_alloc"]
    if len(t2_rows) != 21:
        raise ValueError("T2 baseline must contain 21 windows")
    opens, closes, _volumes, _index_close = _UE._prepare_frames(snapshot)
    details: dict[str, list[dict[str, Any]]] = {
        "phase_b_t2_score_alloc": t2_rows,
    }
    for mapping in ("pa_m1", "pa_m2"):
        details[mapping] = _scale_t2_rows(
            decisions, t2_rows, opens, closes, starts, mapping
        )
    return {
        "summaries": {name: _UE.summarize(rows) for name, rows in details.items()},
        "comparisons_to_t2": {
            name: _paired(rows, t2_rows)
            for name, rows in details.items()
            if name != "phase_b_t2_score_alloc"
        },
        "details": details,
    }


def _save(report: dict[str, Any], path: Path) -> None:
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, default=SNAPSHOT_DEFAULT)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--window-index", type=int)
    parser.add_argument("--full-run", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.window_index is not None and not 0 <= args.window_index < 21:
        parser.error("--window-index must be between 0 and 20")
    if not (args.dry_run or args.full_run or args.window_index is not None):
        parser.error("choose --dry-run, --window-index, or --full-run")

    snapshot_dir = args.snapshot.resolve()
    snapshot, index_ohlcv, starts = _load_market(snapshot_dir)
    api_key = os.environ.get("PA_DS_API_KEY", "").strip()
    if not args.dry_run and not api_key:
        raise SystemExit("PA_DS_API_KEY is required for live runs")

    run_id = datetime.now().strftime("pa_native_regime_%Y%m%d_%H%M%S")
    output = args.output or (EVAL_DIR / f"{run_id}.json")
    prereg_sha = hashlib.sha256(PREREGISTRATION_PATH.read_bytes()).hexdigest()
    report: dict[str, Any] = {
        "run_id": run_id,
        "created_at": datetime.now().astimezone().isoformat(),
        "git": _git_state(),
        "reference_pa_commit": "71fbade",
        "prompt_version": PROMPT_VERSION,
        "preregistration_path": str(PREREGISTRATION_PATH),
        "preregistration_sha256": prereg_sha,
        "snapshot_id": snapshot["manifest"]["snapshot_id"],
        "window_count": len(starts),
        "mode": "dry_run" if args.dry_run else "live",
        "decisions": [],
    }

    with tempfile.TemporaryDirectory(prefix="pa_native_regime_") as temp:
        settings, assembler, orchestrator = _make_components(api_key or "dry-run", Path(temp))
        if args.dry_run:
            indices = [args.window_index if args.window_index is not None else 0]
            for idx in indices:
                frame = _to_frame(index_ohlcv, starts[idx])
                messages = assembler.build_stage1(frame, analysis_mode="original")
                report["decisions"].append(
                    {
                        "idx": idx,
                        "decision_date": str(index_ohlcv.index[starts[idx] - 1].date()),
                        "history_bars": len(frame.bars),
                        "stage1_prompt": _prompt_stats(messages),
                    }
                )
            _save(report, output)
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 0

        indices = list(range(21)) if args.full_run else [int(args.window_index)]
        consecutive_failures = 0
        for idx in indices:
            print(f"[PA] window {idx}/20 decision={index_ohlcv.index[starts[idx] - 1].date()}", flush=True)
            decision = _record_window(
                idx, starts[idx], index_ohlcv, orchestrator, assembler
            )
            report["decisions"].append(decision)
            _save(report, output)
            if decision["success"]:
                consecutive_failures = 0
            else:
                consecutive_failures += 1
                if consecutive_failures >= 3:
                    report["stopped_reason"] = "three_consecutive_failures"
                    _save(report, output)
                    return 2

    if args.full_run:
        if len(report["decisions"]) != 21 or not all(
            row["success"] for row in report["decisions"]
        ):
            report["evaluation_status"] = "fail_closed_incomplete_decisions"
            _save(report, output)
            return 2
        report["evaluation"] = _evaluate(report["decisions"], snapshot, starts)
        report["evaluation_status"] = "complete_development_replay"
        latest = EVAL_DIR / "pa_native_regime_latest.json"
        _save(report, latest)
    _save(report, output)
    print(f"Saved: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
