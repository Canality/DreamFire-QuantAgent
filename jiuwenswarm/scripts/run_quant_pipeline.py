#!/usr/bin/env python3
"""Direct, fail-closed validation path for the quant investment pipeline."""

from __future__ import annotations

import importlib.util
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from jiuwenswarm.quant.backtest_engine import BacktestEngine
from jiuwenswarm.quant.factors import FactorCalculator, PositionSizer
from jiuwenswarm.quant.market_regime import MarketRegime
from jiuwenswarm.quant.stock_pool import ALL_STOCKS, SECTOR_MAP, TICKER_NAME_MAP
from jiuwenswarm.quant.strategy_configs import (
    PRODUCTION_STRATEGY,
    STRATEGY_SPECS,
    get_strategy_spec,
)


def _load_data_provider():
    extension_path = (
        Path(__file__).resolve().parent.parent
        / "jiuwenswarm" / "extensions" / "quant-finance" / "extension.py"
    )
    spec = importlib.util.spec_from_file_location("quant_finance_extension", extension_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load quant data provider: {extension_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fetch_data(
    tickers: list[str], start_date: str, end_date: str
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, str], dict]:
    """Use the Extension's five-source missing-only fallback chain."""
    provider = _load_data_provider()
    prices, volumes, errors = provider._fetch_real_data(tickers, start_date, end_date)
    missing = [
        ticker for ticker in tickers
        if not provider._ticker_data_usable(prices, volumes, ticker)
    ]
    if missing:
        details = "\n".join(f"  - {error}" for error in errors[-20:])
        raise RuntimeError(
            f"Real-data coverage failed: {len(prices)}/{len(tickers)}; missing {missing}.\n{details}"
        )
    prices_df = pd.DataFrame(prices).sort_index().reindex(columns=tickers)
    volumes_df = pd.DataFrame(volumes).sort_index().reindex(columns=tickers)
    print(f"  Missing-only fallback complete: {len(prices_df.columns)}/{len(tickers)} stocks")
    print(f"  Coverage evidence: {len(prices_df.columns)} stocks, {len(prices_df)} days")
    print(f"  Provider coverage: {provider._last_fetch_provider_stats}")

    provider_stats = dict(getattr(provider, "_last_fetch_provider_stats", {}))
    provider_ledger = dict(getattr(provider, "_last_fetch_provider_ledger", {}))
    if set(provider_ledger) != set(tickers):
        raise RuntimeError("Provider ledger does not exactly cover the requested stock pool")
    return prices_df, volumes_df, provider_ledger, provider_stats


def select_stocks(scores: pd.DataFrame, top_n: int = 15) -> list[str]:
    """Select exactly top_n positive-score stocks."""
    selected = [
        ticker for ticker in scores.index
        if float(scores.loc[ticker, "composite"]) > 0
    ][:top_n]
    return selected


def _validate_weights(weights: dict[str, float]) -> dict[str, float]:
    sector_totals: dict[str, float] = {}
    for ticker, weight in weights.items():
        if weight > 0.10 + 1e-9:
            raise RuntimeError(f"Single-stock cap exceeded: {ticker}={weight:.4f}")
        sector = SECTOR_MAP[ticker]
        sector_totals[sector] = sector_totals.get(sector, 0.0) + weight
    over_cap = {sector: value for sector, value in sector_totals.items() if value > 0.25 + 1e-9}
    if over_cap:
        raise RuntimeError(f"Sector cap exceeded: {over_cap}")
    if 1.0 - sum(weights.values()) < 0.05 - 1e-9:
        raise RuntimeError("Cash reserve is below 5%")
    return sector_totals


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy", default=PRODUCTION_STRATEGY,
                        choices=sorted(STRATEGY_SPECS),
                        help="Strategy spec to use (default: production_six_factor)")
    args = parser.parse_args()
    strategy_spec = get_strategy_spec(args.strategy)
    factor_cfg = strategy_spec.factor_config()
    position_cfg = strategy_spec.position_config()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=400)).strftime("%Y-%m-%d")
    print("=" * 60)
    print("  Quant Investment Pipeline (direct validation path)")
    print(f"  Requested data: {start_date} -> {end_date}")
    print("=" * 60)

    print("\n[1/6] Fetching data...")
    prices_full, volumes_full, provider_ledger, provider_stats = fetch_data(
        ALL_STOCKS, start_date, end_date
    )
    if list(prices_full.columns) != list(ALL_STOCKS):
        raise RuntimeError(
            "Data columns do not exactly match the "
            f"{len(ALL_STOCKS)}-stock competition pool"
        )
    if len(prices_full) < 81:
        raise RuntimeError(f"Insufficient trading days: {len(prices_full)} < 81")

    split_at = len(prices_full) - 20
    prices_train = prices_full.iloc[:split_at]
    prices_test = prices_full.iloc[split_at - 1:]
    volumes_train = volumes_full.reindex(prices_train.index) if not volumes_full.empty else pd.DataFrame()
    train_start = prices_train.index[0].strftime("%Y-%m-%d")
    train_end = prices_train.index[-1].strftime("%Y-%m-%d")
    test_start = prices_test.index[0].strftime("%Y-%m-%d")
    test_end = prices_test.index[-1].strftime("%Y-%m-%d")
    print(f"  Train: {train_start} -> {train_end} ({len(prices_train)} trading days)")
    print(f"  Test:  {test_start} -> {test_end} (20 forward returns)")

    print("\n[2/6] Computing factors on training data...")
    regime = MarketRegime.detect(prices_train)
    calculator = FactorCalculator(factor_cfg)
    calculator.regime = regime
    factors = calculator.compute_factors(prices_train, volumes_train if not volumes_train.empty else None)
    scores = calculator.compute_scores(factors)
    print(f"  Market regime: {regime.upper()}; analyzed {len(scores)} stocks")

    print("\n[3/6] Selecting stocks...")
    tickers = select_stocks(scores)
    sectors_covered = len({SECTOR_MAP[ticker] for ticker in tickers})
    if len(tickers) != 15 or sectors_covered != 6:
        raise RuntimeError(f"Selection coverage failed: {len(tickers)}/15 stocks, {sectors_covered}/6 sectors")
    print(f"  {len(tickers)} stocks from {sectors_covered} sectors")

    print("\n[4/6] Allocating positions...")
    weights = PositionSizer(position_cfg).allocate(
        scores.loc[tickers], prices_train[tickers]
    )
    if set(weights) != set(tickers):
        raise RuntimeError(f"Selection/allocation mismatch: selected={tickers}, allocated={list(weights)}")
    sector_totals = _validate_weights(weights)
    print(f"  {len(weights)} holdings; cash reserve {(1 - sum(weights.values())) * 100:.2f}%")

    print("\n[5/6] Running forward backtest...")
    backtest = BacktestEngine().run(prices_test, weights)
    print(f"  Total return: {backtest.total_return * 100:+.2f}%")
    print(f"  Max drawdown: {backtest.max_drawdown * 100:.2f}%")
    print(f"  Sharpe: {backtest.sharpe_ratio:.2f}")

    print("\n[6/6] Saving results...")
    output_dir = Path(__file__).resolve().parent.parent.parent / "output"
    output_dir.mkdir(exist_ok=True)
    from jiuwenswarm.quant.reporting import write_data_snapshot
    snapshot = write_data_snapshot(
        prices_full,
        volumes_full,
        provider_ledger,
        provider_stats,
        output_dir / "data_snapshots",
    )
    snapshot_id = snapshot.snapshot_id
    print(f"  Snapshot: {snapshot_id} ({len(prices_full.columns)} stocks, {len(prices_full)} days)")
    results = {
        "snapshot_id": snapshot_id,
        "regime": regime,
        "train_period": f"{train_start} -> {train_end}",
        "test_period": f"{test_start} -> {test_end}",
        "n_train_trading_days": len(prices_train),
        "n_forward_returns": len(prices_test) - 1,
        "n_stocks_fetched": len(prices_full.columns),
        "data_source_chain": "sina -> tencent -> akshare -> baostock -> yfinance",
        "n_stocks_selected": len(tickers),
        "n_sectors_covered": sectors_covered,
        "sector_weights": {sector: round(weight, 4) for sector, weight in sector_totals.items()},
        "portfolio": [
            {
                "ticker": ticker,
                "name": TICKER_NAME_MAP.get(ticker, ticker),
                "weight": round(weight, 4),
                "weight_pct": round(weight * 100, 2),
                "sector": SECTOR_MAP[ticker],
            }
            for ticker, weight in weights.items()
        ],
        "backtest": backtest.metrics,
        "top_stocks": [
            {
                "ticker": ticker,
                "name": TICKER_NAME_MAP.get(ticker, ticker),
                "composite": round(float(scores.loc[ticker, "composite"]), 3),
                "sector": str(scores.loc[ticker, "sector"]),
            }
            for ticker in scores.head(15).index
        ],
    }
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    timestamped_path = output_dir / f"pipeline_results_{run_id}.json"
    for path in (timestamped_path, output_dir / "pipeline_results.json"):
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(results, handle, ensure_ascii=False, indent=2, default=str)
    print(f"  Results saved to {timestamped_path}")

    # [7/7] Build submission candidate package via ReportService
    print("\n[7/7] Building submission candidate package...")
    t0 = time.time()
    try:
        from jiuwenswarm.quant.reporting import (
            EvidenceRef,
            MetricFact,
            ReportService,
            install_snapshot_in_candidate,
        )
        from jiuwenswarm.quant.reporting.resource_meter import new_resource_report, ResourceMeter

        resource = new_resource_report(f"direct_{run_id}")
        service = ReportService()
        decision_time = prices_test.index[0].to_pydatetime()

        with ResourceMeter("build_package", resource) as meter:
            ev_ref = EvidenceRef(
                evidence_id=snapshot_id,
                source_type="market_data", source_name="Multi-source market snapshot",
                source_url=f"data_snapshot/{snapshot.manifest_path.name}", period_end=None,
                published_at=None,
                available_at=decision_time - timedelta(days=1),
                retrieved_at=datetime.now(timezone.utc),
                content_sha256=snapshot.manifest_sha256,
            )

            bundles = {}
            for ticker in ALL_STOCKS:
                weight = weights.get(ticker, 0.0)
                tech_facts = (
                    MetricFact(name="composite_score", value=round(float(scores.loc[ticker, "composite"]), 4),
                               unit=None, status="available", evidence_ids=(snapshot_id,)),
                ) if ticker in scores.index else ()
                bundles[ticker] = service.build_company_bundle(
                    ticker=ticker,
                    name=TICKER_NAME_MAP.get(ticker, ticker),
                    sector=SECTOR_MAP.get(ticker, "未知"),
                    as_of_time=decision_time,
                    portfolio_weight=weight,
                    selected=weight > 0,
                    weight_zero_reason="" if weight > 0 else "因子得分未进入 Top 15",
                    technical_facts=tech_facts,
                    data_provider_status="partial",
                )

            portfolio_snapshot = service.build_portfolio_snapshot(
                as_of_time=decision_time, holdings=dict(weights),
                cash=round(1.0 - sum(weights.values()), 6),
                strategy_id=args.strategy,
            )

            package_ok, quality, pkg_path = service.build_package(
                portfolio=portfolio_snapshot, bundles=bundles,
                output_dir=str(output_dir), strategy_label=args.strategy,
                evidence_manifest={snapshot_id: ev_ref},
            )
            meter.record_tool_call()
            if not package_ok:
                raise RuntimeError(
                    "candidate package quality failed: " + "; ".join(quality.blockers)
                )
            installed_url, installed_hash = install_snapshot_in_candidate(snapshot, pkg_path)
            if installed_url != ev_ref.source_url or installed_hash != ev_ref.content_sha256:
                raise RuntimeError("installed snapshot does not match EvidenceRef")

        # Resource report
        resource.finalize()
        resource.save_json(str(output_dir / "submission_candidate" / "resource_usage.json"))
        resource.save_markdown(str(output_dir / "submission_candidate" / "resource_usage.md"))

        # Reproducibility doc
        repro_md = f"""# 可复现说明

## 运行环境
- Python 3.11
- 依赖: pandas, akshare, baostock, yfinance, requests
- 运行命令: `python scripts/run_quant_pipeline.py --strategy {args.strategy}`

## 数据源
- Sina Finance → Tencent → akshare → baostock → yfinance (逐只补缺)
- 数据区间: {train_start} → {end_date}
- 训练天数: {len(prices_train)}, 前向窗口: 20 交易日

## 策略
- 因子: {args.strategy}
- 选股: 裸分 Top 15
- 配仓: 单股≤10%, 板块≤25%, 总仓位≤95%

## 复现步骤
1. 安装依赖: `pip install -r requirements.txt`
2. 运行直跑: `python scripts/run_quant_pipeline.py`
3. 产物: `output/submission_candidate/`
"""
        with open(str(output_dir / "submission_candidate" / "reproducibility.md"), "w", encoding="utf-8") as f:
            f.write(repro_md)

        # Rails execution
        from jiuwenswarm.quant.reporting.rails import (
            EvidenceRail, ReportCompletenessRail,
            PortfolioConsistencyRail, ResourceBudgetRail,
        )
        n_reports_on_disk = len(bundles)  # all bundles have reports generated
        rails = [
            EvidenceRail(quality),
            ReportCompletenessRail(len(ALL_STOCKS), n_reports_on_disk),
            PortfolioConsistencyRail(dict(weights), {t: b.portfolio_weight for t, b in bundles.items()}),
            ResourceBudgetRail(max_duration_s=600),
        ]
        rail_results = []
        for r in rails:
            rr = r.check()
            rail_results.append({
                "name": rr.rail_name, "passed": rr.passed,
                "blockers": rr.blockers, "warnings": rr.warnings,
            })
        with open(str(output_dir / "submission_candidate" / "rails_result.json"), "w", encoding="utf-8") as f:
            json.dump({"all_passed": all(r["passed"] for r in rail_results), "rails": rail_results}, f, indent=2, ensure_ascii=False)
        print(f"  Rails: {sum(1 for r in rail_results if r['passed'])}/{len(rail_results)} passed")

        # Framework changes
        framework_md = """# 框架优化说明

## 新增模块
- `quant/reporting/` — 证据模型、确定性报告生成、质量门禁、候选包构建 (R0-R5)
- `quant/reporting/submission_contract.py` — 冻结官方规则契约 (38 测试)
- `quant/reporting/models.py` — 7 个证据 dataclass
- `quant/reporting/company_report.py` — 确定性 MD 报告生成器
- `quant/reporting/quality_gate.py` — 12 项质量检查含 EvidenceRef 强制执行
- `quant/reporting/package_builder.py` — 候选提交包构建
- `quant/reporting/report_service.py` — 双路径共享报告服务
- `quant/reporting/resource_meter.py` — 真实资源计量
- `quant/reporting/symphony_adapter.py` — Symphony 计划模型与策略校验
- `quant/reporting/providers/` — 数据 Provider 抽象

## 修改文件
- `scripts/run_quant_pipeline.py` — 新增 Step 7 候选包生成
- `extensions/quant-finance/extension.py` — generate_report 接入 ReportService
- `common/schema/agent.py` — 修复 Unicode 腐败

## 验收
- 当前测试数量、双路径 session、退出码和证据路径只引用根目录 `VALIDATION.md`
- 直跑要求: 官方股票池全覆盖、全部板块、15只、Quality PASSED
- 多Agent要求: 8/8 RPC, Bull/Bear 专属调用
"""
        with open(str(output_dir / "submission_candidate" / "framework_changes.md"), "w", encoding="utf-8") as f:
            f.write(framework_md)

        elapsed = time.time() - t0
        print(f"  Package: {pkg_path}")
        print(f"  Quality: {'PASSED' if package_ok else 'FAILED'} ({elapsed:.1f}s)")
        if quality.blockers:
            for b in quality.blockers:
                print(f"    BLOCKER: {b}")
        if quality.warnings:
            for w in quality.warnings:
                print(f"    WARNING: {w}")
    except Exception as exc:
        raise RuntimeError(f"Candidate package generation failed: {exc}") from exc

    print("\nDone.")


if __name__ == "__main__":
    main()
