#!/usr/bin/env python3
"""Causal, fixed-share comparison of the three preregistered baselines.

This evaluator deliberately does not create or inspect a historical holdout.
All currently observed history is development data; the competition period (or
future data not yet observed) is the only honest final holdout.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import requests

from jiuwenswarm.quant.backtest_engine import BacktestEngine
from jiuwenswarm.quant.factors import FactorCalculator, PositionSizer
from jiuwenswarm.quant.regime_fusion import RegimeFusion
from jiuwenswarm.quant.stock_pool import ALL_STOCKS, SECTOR_MAP
from jiuwenswarm.quant.strategy_configs import STRATEGY_SPECS, get_strategy_spec


EVALUATION_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = EVALUATION_DIR.parent
SNAPSHOT_ROOT = EVALUATION_DIR / "data_snapshots"
HORIZON = 20
MIN_HISTORY = 80
BASELINES = (
    "production_six_factor",
    "two_factor_ic_ratio",
    "momentum20_only",
)
FACTOR_COLUMNS = (
    "momentum_20_z",
    "momentum_60_z",
    "max_drawdown_z",
    "reversal_5_z",
    "volume_corr_z",
    "volume_trend_z",
)

PREREGISTRATION = {
    "hypothesis": (
        "On identical causal windows and an official-style first-open, fixed-share "
        "valuation, determine whether either simplified factor model improves on "
        "the current six-factor production model."
    ),
    "data_policy": {
        "coverage": "49/49 exact tickers and 6/6 exact sectors or fail closed",
        "source": "one uniform Sina daily K-line source; raw/unadjusted OHLCV",
        "snapshot": "immutable CSV files plus SHA-256 manifest",
        "missing_close": "forward-fill only for valuation during suspension",
        "missing_entry_open": "fail closed if a selected stock cannot be bought",
    },
    "window_policy": {
        "history": "expanding history ending at prior trading-day close",
        "entry": "first forward trading-day open",
        "exit": "20th forward trading-day close",
        "portfolio": "buy once at entry; fixed shares; no daily rebalance",
        "overlap": 0,
        "historical_holdout": "none; all observed history is development data",
    },
    "shared_strategy_rules": {
        "selection": "positive composite, naked top 15",
        "max_single_stock": 0.10,
        "max_single_sector": 0.25,
        "max_total_weight": 0.95,
        "official_transaction_cost": 0.0,
        "cost_aware_transaction_cost": 0.0003,
    },
    "candidate_acceptance": {
        "median_return_delta_min": 0.003,
        "paired_utility_win_rate_min": 0.60,
        "recent_four_utility_wins_min": 3,
        "median_drawdown_worsening_max": 0.003,
        "worst_return_worsening_max": 0.005,
        "utility_definition": "0.70 * total_return - 0.30 * max_drawdown",
    },
}


def _git_state() -> dict[str, Any]:
    def run(*args: str) -> str:
        result = subprocess.run(
            ["git", *args], cwd=PROJECT_ROOT, capture_output=True, text=True,
            check=False,
        )
        return result.stdout.strip()

    return {
        "commit": run("rev-parse", "HEAD") or "unknown",
        "dirty": bool(run("status", "--porcelain")),
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sina_symbol(ticker: str) -> str:
    code, exchange = ticker.split(".")
    return f"{'sh' if exchange == 'SH' else 'sz'}{code}"


def _fetch_sina_symbol(label: str, symbol: str, datalen: int) -> tuple[str, pd.DataFrame]:
    url = (
        "https://quotes.sina.cn/cn/api/json_v2.php/"
        "CN_MarketDataService.getKLineData"
    )
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            response = requests.get(
                url,
                params={"symbol": symbol, "scale": "240", "ma": "no", "datalen": datalen},
                timeout=25,
            )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, list) or not payload:
                raise ValueError(f"empty or invalid payload: {str(payload)[:120]}")
            frame = pd.DataFrame(payload)
            required = {"day", "open", "high", "low", "close", "volume"}
            if not required.issubset(frame.columns):
                raise ValueError(f"missing fields: {sorted(required - set(frame.columns))}")
            frame["day"] = pd.to_datetime(frame["day"], errors="raise")
            frame = frame.set_index("day").sort_index()
            for column in ("open", "high", "low", "close", "volume"):
                frame[column] = pd.to_numeric(frame[column], errors="coerce")
            frame = frame[~frame.index.duplicated(keep="last")]
            if len(frame) < MIN_HISTORY + HORIZON:
                raise ValueError(f"only {len(frame)} rows")
            return label, frame
        except Exception as exc:  # noqa: BLE001 - preserve provider detail
            last_error = exc
            if attempt < 2:
                time.sleep(0.5 * (attempt + 1))
    raise RuntimeError(f"Sina fetch failed for {label}/{symbol}: {last_error}")


def create_snapshot(datalen: int = 500) -> Path:
    """Fetch one uniform OHLCV snapshot and save immutable source files."""
    run_id = datetime.now().strftime("sina_%Y%m%d_%H%M%S")
    snapshot_dir = SNAPSHOT_ROOT / run_id
    snapshot_dir.mkdir(parents=True, exist_ok=False)

    requests_to_make = [(ticker, _sina_symbol(ticker)) for ticker in ALL_STOCKS]
    requests_to_make.append(("CSI300", "sh000300"))
    frames: dict[str, pd.DataFrame] = {}
    errors: list[str] = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {
            pool.submit(_fetch_sina_symbol, label, symbol, datalen): label
            for label, symbol in requests_to_make
        }
        for future in as_completed(futures):
            label = futures[future]
            try:
                result_label, frame = future.result()
                frames[result_label] = frame
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{label}: {exc}")

    missing = sorted(set(ALL_STOCKS) - set(frames))
    if errors or missing or "CSI300" not in frames:
        error_path = snapshot_dir / "FAILED.json"
        error_path.write_text(
            json.dumps({"missing": missing, "errors": errors}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        raise RuntimeError(
            f"Snapshot coverage failed; missing={missing}, errors={errors[:5]}; "
            f"evidence={error_path}"
        )

    field_frames: dict[str, pd.DataFrame] = {}
    for field in ("open", "high", "low", "close", "volume"):
        field_frames[field] = pd.DataFrame(
            {ticker: frames[ticker][field] for ticker in ALL_STOCKS}
        ).sort_index().reindex(columns=ALL_STOCKS)
    index_frame = frames["CSI300"][["open", "high", "low", "close", "volume"]]

    files: dict[str, dict[str, Any]] = {}
    for field, frame in field_frames.items():
        path = snapshot_dir / f"stocks_{field}.csv.gz"
        frame.to_csv(path, encoding="utf-8", compression="gzip", date_format="%Y-%m-%d")
        files[path.name] = {"sha256": _sha256(path), "rows": len(frame), "columns": len(frame.columns)}
    index_path = snapshot_dir / "csi300_ohlcv.csv.gz"
    index_frame.to_csv(index_path, encoding="utf-8", compression="gzip", date_format="%Y-%m-%d")
    files[index_path.name] = {"sha256": _sha256(index_path), "rows": len(index_frame), "columns": 5}

    manifest = {
        "snapshot_id": run_id,
        "created_at": datetime.now().astimezone().isoformat(),
        "source": "Sina CN_MarketDataService.getKLineData",
        "adjustment": "raw/unadjusted",
        "requested_rows": datalen,
        "tickers": list(ALL_STOCKS),
        "n_stocks": len(ALL_STOCKS),
        "n_sectors": len({SECTOR_MAP[ticker] for ticker in ALL_STOCKS}),
        "files": files,
    }
    manifest_path = snapshot_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return snapshot_dir


def load_snapshot(snapshot_dir: Path) -> dict[str, Any]:
    manifest_path = snapshot_dir / "manifest.json"
    if not manifest_path.exists():
        raise ValueError(f"Snapshot manifest missing: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("tickers") != list(ALL_STOCKS):
        raise ValueError("Snapshot ticker order does not exactly match the competition pool")
    if manifest.get("n_stocks") != 49 or manifest.get("n_sectors") != 6:
        raise ValueError("Snapshot does not contain exact 49/49 and 6/6 coverage")

    loaded: dict[str, Any] = {"manifest": manifest, "snapshot_dir": snapshot_dir}
    for filename, info in manifest["files"].items():
        path = snapshot_dir / filename
        if not path.exists() or _sha256(path) != info["sha256"]:
            raise ValueError(f"Snapshot checksum mismatch: {path}")
    for field in ("open", "high", "low", "close", "volume"):
        frame = pd.read_csv(
            snapshot_dir / f"stocks_{field}.csv.gz", index_col=0, parse_dates=True
        )
        frame = frame.reindex(columns=ALL_STOCKS)
        if list(frame.columns) != list(ALL_STOCKS):
            raise ValueError(f"{field} columns do not exactly match the stock pool")
        loaded[field] = frame
    loaded["index"] = pd.read_csv(
        snapshot_dir / "csi300_ohlcv.csv.gz", index_col=0, parse_dates=True
    )
    return loaded


def build_schedule(n_days: int, min_history: int = MIN_HISTORY, horizon: int = HORIZON) -> list[int]:
    starts = list(range(min_history, n_days - horizon + 1, horizon))
    if not starts:
        raise ValueError(f"Insufficient data: {n_days} days for {min_history}+{horizon}")
    return starts


def _prepare_frames(snapshot: dict[str, Any]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.Series]:
    calendar = snapshot["index"].index
    closes = snapshot["close"].reindex(calendar).ffill()
    opens = snapshot["open"].reindex(calendar)
    volumes = snapshot["volume"].reindex(calendar).fillna(0.0)
    index_close = pd.to_numeric(snapshot["index"]["close"], errors="coerce").reindex(calendar).ffill()
    if closes.shape[1] != 49 or len({SECTOR_MAP[ticker] for ticker in closes.columns}) != 6:
        raise ValueError("Prepared data lost 49/49 or 6/6 coverage")
    if closes.iloc[MIN_HISTORY - 1:].isna().any().any():
        bad = closes.columns[closes.iloc[MIN_HISTORY - 1:].isna().any()].tolist()
        raise ValueError(f"Close coverage incomplete after minimum history: {bad}")
    return opens, closes, volumes, index_close


def _factor_contributions(scores: pd.DataFrame, selected: list[str], factor_config, regime: str) -> dict[str, float]:
    weights = factor_config.get_regime_weights(regime)
    result: dict[str, float] = {}
    for column in FACTOR_COLUMNS:
        weight = float(weights.get(column, 0.0))
        if column in scores and weight != 0:
            result[column] = round(float((scores.loc[selected, column].fillna(0) * weight).mean()), 6)
        else:
            result[column] = 0.0
    return result


def evaluate_strategy(
    strategy_name: str,
    opens: pd.DataFrame,
    closes: pd.DataFrame,
    volumes: pd.DataFrame,
    index_close: pd.Series,
    starts: list[int],
) -> list[dict[str, Any]]:
    spec = get_strategy_spec(strategy_name)
    results: list[dict[str, Any]] = []
    for idx, start in enumerate(starts):
        history = closes.iloc[:start]
        history_volume = volumes.iloc[:start]
        decision_date = history.index[-1]
        regime = RegimeFusion.detect(
            history,
            index_prices=index_close[index_close.index <= decision_date],
        )
        factor_config = spec.factor_config()
        calculator = FactorCalculator(factor_config)
        calculator.regime = regime
        factors = calculator.compute_factors(history, history_volume)
        scores = calculator.filter_high_volatility(calculator.compute_scores(factors))
        selected = [
            ticker for ticker in scores.index
            if float(scores.loc[ticker, "composite"]) > 0
        ][:spec.top_n]
        if len(selected) != spec.top_n:
            raise RuntimeError(
                f"{strategy_name} window {idx}: selected {len(selected)}/{spec.top_n}"
            )

        weights = PositionSizer(spec.position_config()).allocate(
            scores.loc[selected], history[selected]
        )
        if set(weights) != set(selected):
            raise RuntimeError(f"{strategy_name} window {idx}: selection/allocation mismatch")

        test_closes = closes.iloc[start:start + HORIZON]
        entry_open = opens.iloc[start]
        if len(test_closes) != HORIZON:
            raise RuntimeError(f"{strategy_name} window {idx}: incomplete forward window")
        official = BacktestEngine(transaction_cost=0.0).run_open_to_close(
            entry_open, test_closes, weights
        )
        cost_aware = BacktestEngine(transaction_cost=0.0003).run_open_to_close(
            entry_open, test_closes, weights
        )

        sector_weights: dict[str, float] = {}
        for ticker, weight in weights.items():
            sector = SECTOR_MAP[ticker]
            sector_weights[sector] = sector_weights.get(sector, 0.0) + float(weight)
        total_weight = float(sum(weights.values()))
        max_stock = float(max(weights.values()))
        max_sector = float(max(sector_weights.values()))
        if max_stock > spec.max_single_stock + 1e-9:
            raise RuntimeError(f"{strategy_name} window {idx}: stock cap {max_stock}")
        if max_sector > spec.max_single_sector + 1e-9:
            raise RuntimeError(f"{strategy_name} window {idx}: sector cap {max_sector}")
        if total_weight > spec.max_total_weight + 1e-9:
            raise RuntimeError(f"{strategy_name} window {idx}: total weight {total_weight}")

        results.append({
            "idx": idx,
            "decision_date": str(decision_date.date()),
            "test_start": str(test_closes.index[0].date()),
            "test_end": str(test_closes.index[-1].date()),
            "regime": regime,
            "n_history_days": len(history),
            "n_forward_closes": len(test_closes),
            "selected_tickers": selected,
            "n_selected": len(selected),
            "n_selected_sectors": len({SECTOR_MAP[ticker] for ticker in selected}),
            "weights": {ticker: round(float(weight), 8) for ticker, weight in weights.items()},
            "sector_weights": {sector: round(value, 8) for sector, value in sector_weights.items()},
            "total_weight": round(total_weight, 8),
            "cash": round(1.0 - total_weight, 8),
            "max_stock_weight": round(max_stock, 8),
            "max_sector_weight": round(max_sector, 8),
            "official": official.metrics,
            "cost_aware": cost_aware.metrics,
            "factor_contributions": _factor_contributions(
                scores, selected, factor_config, regime
            ),
        })
    return results


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    returns = np.array([row["official"]["total_return"] for row in results], dtype=float)
    drawdowns = np.array([row["official"]["max_drawdown"] for row in results], dtype=float)
    annualized = np.array([row["official"]["annualized_return"] for row in results], dtype=float)
    volatility = np.array([row["official"]["annualized_volatility"] for row in results], dtype=float)
    sharpes = np.array([row["official"]["sharpe_ratio"] for row in results], dtype=float)
    calmars = annualized / np.maximum(drawdowns, 1e-10)
    factor_names = results[0]["factor_contributions"]
    return {
        "n_windows": len(results),
        "median_return": round(float(np.median(returns)), 6),
        "mean_return": round(float(np.mean(returns)), 6),
        "worst_return": round(float(np.min(returns)), 6),
        "positive_windows": int((returns > 0).sum()),
        "median_drawdown": round(float(np.median(drawdowns)), 6),
        "worst_drawdown": round(float(np.max(drawdowns)), 6),
        "median_annualized_return": round(float(np.median(annualized)), 6),
        "median_annualized_volatility": round(float(np.median(volatility)), 6),
        "median_sharpe": round(float(np.median(sharpes)), 4),
        "median_calmar": round(float(np.median(calmars)), 4),
        "median_invested": round(float(np.median([row["total_weight"] for row in results])), 6),
        "max_stock_weight": round(float(max(row["max_stock_weight"] for row in results)), 6),
        "max_sector_weight": round(float(max(row["max_sector_weight"] for row in results)), 6),
        "mean_factor_contributions": {
            factor: round(float(np.mean([
                row["factor_contributions"][factor] for row in results
            ])), 6)
            for factor in factor_names
        },
    }


def compare_to_production(
    candidate: list[dict[str, Any]],
    production: list[dict[str, Any]],
) -> dict[str, Any]:
    if len(candidate) != len(production):
        raise ValueError("Candidate and production windows differ")
    return_delta = np.array([
        cand["official"]["total_return"] - base["official"]["total_return"]
        for cand, base in zip(candidate, production)
    ])
    dd_delta = np.array([
        cand["official"]["max_drawdown"] - base["official"]["max_drawdown"]
        for cand, base in zip(candidate, production)
    ])
    utilities = np.array([
        0.70 * cand["official"]["total_return"] - 0.30 * cand["official"]["max_drawdown"]
        - (0.70 * base["official"]["total_return"] - 0.30 * base["official"]["max_drawdown"])
        for cand, base in zip(candidate, production)
    ])
    recent_wins = int((utilities[-4:] > 0).sum()) if len(utilities) >= 4 else int((utilities > 0).sum())
    candidate_worst = min(row["official"]["total_return"] for row in candidate)
    production_worst = min(row["official"]["total_return"] for row in production)
    thresholds = PREREGISTRATION["candidate_acceptance"]
    checks = {
        "median_return_delta": float(np.median(return_delta)) >= thresholds["median_return_delta_min"],
        "utility_win_rate": float((utilities > 0).mean()) >= thresholds["paired_utility_win_rate_min"],
        "recent_four_wins": recent_wins >= thresholds["recent_four_utility_wins_min"],
        "median_drawdown_worsening": float(np.median(dd_delta)) <= thresholds["median_drawdown_worsening_max"],
        "worst_return_worsening": candidate_worst >= production_worst - thresholds["worst_return_worsening_max"],
    }
    return {
        "median_return_delta": round(float(np.median(return_delta)), 6),
        "mean_return_delta": round(float(np.mean(return_delta)), 6),
        "median_drawdown_delta": round(float(np.median(dd_delta)), 6),
        "utility_wins": int((utilities > 0).sum()),
        "utility_win_rate": round(float((utilities > 0).mean()), 4),
        "recent_four_utility_wins": recent_wins,
        "worst_return_delta": round(float(candidate_worst - production_worst), 6),
        "acceptance_checks": checks,
        "verdict": "QUALIFIES" if all(checks.values()) else "DOES_NOT_QUALIFY",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", type=Path, help="Reuse an immutable snapshot directory")
    parser.add_argument("--datalen", type=int, default=500)
    args = parser.parse_args()

    started = time.time()
    print("=" * 78)
    print("Phase A: unified official-style three-baseline evaluation")
    print(json.dumps(PREREGISTRATION, ensure_ascii=False, indent=2))
    print("=" * 78)

    snapshot_dir = args.snapshot.resolve() if args.snapshot else create_snapshot(args.datalen)
    snapshot = load_snapshot(snapshot_dir)
    opens, closes, volumes, index_close = _prepare_frames(snapshot)
    starts = build_schedule(len(index_close))
    print(
        f"Snapshot {snapshot_dir.name}: 49/49 stocks, 6/6 sectors, "
        f"{len(index_close)} index trading days, {len(starts)} non-overlapping windows"
    )

    details: dict[str, list[dict[str, Any]]] = {}
    summaries: dict[str, dict[str, Any]] = {}
    for strategy_name in BASELINES:
        print(f"[Run] {strategy_name}: {STRATEGY_SPECS[strategy_name].description}")
        rows = evaluate_strategy(strategy_name, opens, closes, volumes, index_close, starts)
        details[strategy_name] = rows
        summaries[strategy_name] = summarize(rows)

    comparisons = {
        name: compare_to_production(rows, details["production_six_factor"])
        for name, rows in details.items()
        if name != "production_six_factor"
    }
    run_id = datetime.now().strftime("unified_baselines_%Y%m%d_%H%M%S")
    report = {
        "run_id": run_id,
        "created_at": datetime.now().astimezone().isoformat(),
        "git": _git_state(),
        "preregistration": PREREGISTRATION,
        "snapshot": {
            "path": str(snapshot_dir),
            "id": snapshot["manifest"]["snapshot_id"],
            "source": snapshot["manifest"]["source"],
            "adjustment": snapshot["manifest"]["adjustment"],
            "n_stocks": 49,
            "n_sectors": 6,
            "calendar_days": len(index_close),
            "date_start": str(index_close.index[0].date()),
            "date_end": str(index_close.index[-1].date()),
        },
        "protocol": {
            "min_history": MIN_HISTORY,
            "horizon": HORIZON,
            "n_windows": len(starts),
            "windows": [
                {
                    "decision_date": str(index_close.index[start - 1].date()),
                    "test_start": str(index_close.index[start].date()),
                    "test_end": str(index_close.index[start + HORIZON - 1].date()),
                }
                for start in starts
            ],
        },
        "summaries": summaries,
        "comparisons_to_production": comparisons,
        "details": details,
        "elapsed_seconds": round(time.time() - started, 2),
    }
    immutable_path = EVALUATION_DIR / f"{run_id}.json"
    latest_path = EVALUATION_DIR / "unified_baselines_latest.json"
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    immutable_path.write_text(payload, encoding="utf-8")
    latest_path.write_text(payload, encoding="utf-8")
    print(json.dumps({"summaries": summaries, "comparisons": comparisons}, ensure_ascii=False, indent=2))
    print(f"Saved immutable result: {immutable_path}")
    print(f"Updated latest result:  {latest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
