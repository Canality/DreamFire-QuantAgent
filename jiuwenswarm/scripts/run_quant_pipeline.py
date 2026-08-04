#!/usr/bin/env python3
"""Direct, fail-closed validation path for the quant investment pipeline."""

from __future__ import annotations

import json
import sys
import time
from dataclasses import replace
from datetime import datetime, timedelta
from datetime import time as datetime_time
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
from jiuwenswarm.quant.backtest_engine import BacktestEngine
from jiuwenswarm.quant.factors import FactorCalculator, PositionSizer
from jiuwenswarm.quant.market_data_provider import fetch_market_data_bundle
from jiuwenswarm.quant.market_data_service import (
    MarketDataBundle,
    MarketDiagnostics,
    diagnose_market_data,
    require_diagnostics_passed,
)
from jiuwenswarm.quant.market_regime import MarketRegime
from jiuwenswarm.quant.stock_pool import ALL_STOCKS, SECTOR_MAP, TICKER_NAME_MAP
from jiuwenswarm.quant.strategy_configs import (
    PRODUCTION_STRATEGY,
    STRATEGY_SPECS,
    get_strategy_spec,
)

_SHANGHAI = ZoneInfo("Asia/Shanghai")
_MIN_TRAIN_DAYS = 61
_FORWARD_TEST_DAYS = 20


def _market_as_of_time(end_date: str, *, now: datetime | None = None) -> datetime:
    """Return the latest lawful evidence time for a requested market date."""

    local_now = now or datetime.now(_SHANGHAI)
    if local_now.tzinfo is None or local_now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    local_now = local_now.astimezone(_SHANGHAI)
    end_day = pd.Timestamp(end_date).date()
    if end_day > local_now.date():
        raise ValueError("market-data end_date cannot be in the future")
    if end_day == local_now.date():
        return local_now
    return datetime.combine(
        end_day,
        datetime_time(16, 0),
        tzinfo=_SHANGHAI,
    )


def _default_end_date(*, now: datetime | None = None) -> str:
    """Avoid requesting an incomplete current A-share session by default."""

    local_now = (now or datetime.now(_SHANGHAI)).astimezone(_SHANGHAI)
    end_day = local_now.date()
    if local_now.time() < datetime_time(15, 30):
        end_day -= timedelta(days=1)
    return end_day.isoformat()


def _decision_evidence_bundle(
    bundle: MarketDataBundle,
    decision_index: pd.Timestamp,
) -> MarketDataBundle:
    """Remove forward-test rows before persisting factor evidence."""

    decision_timestamp = pd.Timestamp(decision_index)
    decision_time = datetime.combine(
        decision_timestamp.date(),
        datetime_time(16, 0),
        tzinfo=_SHANGHAI,
    )
    return replace(
        bundle,
        opens=bundle.opens.loc[:decision_timestamp].copy(),
        highs=bundle.highs.loc[:decision_timestamp].copy(),
        lows=bundle.lows.loc[:decision_timestamp].copy(),
        closes=bundle.closes.loc[:decision_timestamp].copy(),
        volumes=bundle.volumes.loc[:decision_timestamp].copy(),
        secondary_closes=bundle.secondary_closes.loc[:decision_timestamp].copy(),
        benchmark_closes=bundle.benchmark_closes.loc[:decision_timestamp].copy(),
        as_of_time=decision_time,
    )


def fetch_data(
    tickers: list[str],
    start_date: str,
    end_date: str,
    *,
    as_of_time: datetime | None = None,
) -> tuple[MarketDataBundle, MarketDiagnostics]:
    """Fetch and validate the shared five-source canonical market bundle."""

    if tickers != list(ALL_STOCKS):
        raise RuntimeError("Direct data request must exactly match the official 49-stock pool")
    bundle = fetch_market_data_bundle(
        tickers,
        start_date,
        end_date,
        as_of_time=as_of_time or _market_as_of_time(end_date),
    )
    diagnostics = require_diagnostics_passed(
        diagnose_market_data(bundle, tickers)
    )
    print(f"  Shared provider complete: {len(bundle.closes.columns)}/{len(tickers)} stocks")
    print(f"  Coverage evidence: {len(bundle.closes.columns)} stocks, {len(bundle.closes)} days")
    print(f"  Provider coverage: {bundle.provider_stats}")
    return bundle, diagnostics


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


def main(argv: list[str] | None = None) -> None:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy", default=PRODUCTION_STRATEGY,
                        choices=sorted(STRATEGY_SPECS),
                        help="Strategy spec to use (default: production_six_factor)")
    parser.add_argument("--start-date", help="Inclusive market-data start date")
    parser.add_argument("--end-date", help="Inclusive market-data end date")
    args = parser.parse_args(argv)
    strategy_spec = get_strategy_spec(args.strategy)
    factor_cfg = strategy_spec.factor_config()
    position_cfg = strategy_spec.position_config()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    local_now = datetime.now(_SHANGHAI)
    end_date = args.end_date or _default_end_date(now=local_now)
    end_as_of = _market_as_of_time(end_date, now=local_now)
    start_date = args.start_date or (
        pd.Timestamp(end_date) - pd.Timedelta(days=400)
    ).strftime("%Y-%m-%d")
    print("=" * 60)
    print("  Quant Investment Pipeline (direct validation path)")
    print(f"  Requested data: {start_date} -> {end_date}")
    print("=" * 60)

    print("\n[1/7] Fetching data...")
    market_bundle, market_diagnostics = fetch_data(
        list(ALL_STOCKS),
        start_date,
        end_date,
        as_of_time=end_as_of,
    )
    prices_full = market_bundle.closes
    volumes_full = market_bundle.volumes
    if list(prices_full.columns) != list(ALL_STOCKS):
        raise RuntimeError(
            "Data columns do not exactly match the "
            f"{len(ALL_STOCKS)}-stock competition pool"
        )
    minimum_total_rows = _MIN_TRAIN_DAYS + _FORWARD_TEST_DAYS
    if len(prices_full) < minimum_total_rows:
        raise RuntimeError(
            f"Insufficient trading days: {len(prices_full)} < {minimum_total_rows}"
        )

    split_at = len(prices_full) - _FORWARD_TEST_DAYS
    prices_train = prices_full.iloc[:split_at]
    prices_test = prices_full.iloc[split_at - 1:]
    volumes_train = volumes_full.reindex(prices_train.index) if not volumes_full.empty else pd.DataFrame()
    train_start = prices_train.index[0].strftime("%Y-%m-%d")
    train_end = prices_train.index[-1].strftime("%Y-%m-%d")
    test_start = prices_test.index[0].strftime("%Y-%m-%d")
    test_end = prices_test.index[-1].strftime("%Y-%m-%d")
    print(f"  Train: {train_start} -> {train_end} ({len(prices_train)} trading days)")
    print(f"  Test:  {test_start} -> {test_end} (20 forward returns)")

    print("\n[2/7] Computing factors on training data...")
    regime = MarketRegime.detect(prices_train)
    calculator = FactorCalculator(factor_cfg)
    calculator.regime = regime
    factors = calculator.compute_factors(prices_train, volumes_train if not volumes_train.empty else None)
    scores = calculator.compute_scores(factors)
    print(f"  Market regime: {regime.upper()}; analyzed {len(scores)} stocks")

    print("\n[3/7] Selecting stocks...")
    tickers = select_stocks(scores)
    sectors_covered = len({SECTOR_MAP[ticker] for ticker in tickers})
    if len(tickers) != 15 or sectors_covered != 6:
        raise RuntimeError(f"Selection coverage failed: {len(tickers)}/15 stocks, {sectors_covered}/6 sectors")
    print(f"  {len(tickers)} stocks from {sectors_covered} sectors")

    print("\n[4/7] Allocating positions...")
    weights = PositionSizer(position_cfg).allocate(
        scores.loc[tickers], prices_train[tickers]
    )
    if set(weights) != set(tickers):
        raise RuntimeError(f"Selection/allocation mismatch: selected={tickers}, allocated={list(weights)}")
    sector_totals = _validate_weights(weights)
    print(f"  {len(weights)} holdings; cash reserve {(1 - sum(weights.values())) * 100:.2f}%")

    print("\n[5/7] Running forward backtest...")
    backtest = BacktestEngine().run(prices_test, weights)
    print(f"  Total return: {backtest.total_return * 100:+.2f}%")
    print(f"  Max drawdown: {backtest.max_drawdown * 100:.2f}%")
    print(f"  Sharpe: {backtest.sharpe_ratio:.2f}")

    print("\n[6/7] Saving results...")
    output_dir = Path(__file__).resolve().parent.parent.parent / "output"
    output_dir.mkdir(exist_ok=True)
    from jiuwenswarm.quant.reporting import write_market_data_snapshot

    evidence_bundle = _decision_evidence_bundle(
        market_bundle,
        prices_train.index[-1],
    )
    evidence_diagnostics = require_diagnostics_passed(
        diagnose_market_data(
            evidence_bundle,
            list(ALL_STOCKS),
            minimum_rows=_MIN_TRAIN_DAYS,
        )
    )
    snapshot = write_market_data_snapshot(
        evidence_bundle,
        evidence_diagnostics,
        output_dir / "data_snapshots",
        minimum_rows=_MIN_TRAIN_DAYS,
    )
    snapshot_id = snapshot.snapshot_id
    print(
        f"  Snapshot: {snapshot_id} "
        f"({len(evidence_bundle.closes.columns)} stocks, "
        f"{len(evidence_bundle.closes)} decision-time days)"
    )
    results = {
        "snapshot_id": snapshot_id,
        "snapshot_manifest_sha256": snapshot.manifest_sha256,
        "market_diagnostics": market_diagnostics.to_dict(),
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
    run_id = local_now.strftime("%Y%m%d_%H%M%S")
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
            install_market_data_snapshot_in_candidate,
            run_announcement_service,
        )
        from jiuwenswarm.quant.reporting.providers.archive import EvidenceArchive
        from jiuwenswarm.quant.reporting.resource_meter import (
            ResourceMeter,
            new_resource_report,
        )

        resource = new_resource_report(f"direct_{run_id}")
        service = ReportService()
        decision_time = evidence_bundle.as_of_time

        with ResourceMeter("build_package", resource) as meter:
            ev_ref = EvidenceRef(
                evidence_id=snapshot_id,
                source_type="market_data", source_name="Multi-source market snapshot",
                source_url=f"data_snapshot/{snapshot.manifest_path.name}",
                period_end=decision_time,
                published_at=decision_time,
                available_at=decision_time,
                retrieved_at=evidence_bundle.retrieved_at,
                content_sha256=snapshot.manifest_sha256,
            )
            archive_root = output_dir / "evidence_archive"
            announcement_result = run_announcement_service(
                list(ALL_STOCKS),
                decision_time,
                archive_root,
            )
            announcement_archive = EvidenceArchive(archive_root)
            evidence_manifest = {
                snapshot_id: ev_ref,
                **announcement_result.manifest,
            }
            results["announcement_evidence"] = {
                "as_of_time": decision_time.isoformat(),
                "total_facts": announcement_result.total_facts,
                "tickers_with_events": announcement_result.tickers_with_events,
                "manifest_count": len(announcement_result.manifest),
                "status_counts": {
                    status.value: sum(
                        item == status
                        for item in announcement_result.statuses.values()
                    )
                    for status in set(announcement_result.statuses.values())
                },
            }
            for path in (timestamped_path, output_dir / "pipeline_results.json"):
                with open(path, "w", encoding="utf-8") as handle:
                    json.dump(results, handle, ensure_ascii=False, indent=2, default=str)
            print(
                "  Announcement evidence: "
                f"{announcement_result.total_facts} facts for "
                f"{announcement_result.tickers_with_events}/{len(ALL_STOCKS)} tickers"
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
                    event_facts=tuple(
                        announcement_result.facts_by_ticker.get(ticker, ())
                    ),
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
                evidence_manifest=evidence_manifest,
                evidence_archive=announcement_archive,
            )
            meter.record_tool_call()
            if not package_ok:
                raise RuntimeError(
                    "candidate package quality failed: " + "; ".join(quality.blockers)
                )
            installed_url, installed_hash = install_market_data_snapshot_in_candidate(
                snapshot,
                pkg_path,
            )
            if installed_url != ev_ref.source_url or installed_hash != ev_ref.content_sha256:
                raise RuntimeError("installed snapshot does not match EvidenceRef")
            results["candidate_package"] = {
                "path": str(pkg_path),
                "quality_passed": package_ok,
                "snapshot_id": snapshot_id,
                "snapshot_manifest_sha256": installed_hash,
                "reports": len(bundles),
                "blockers": list(quality.blockers),
                "warnings": list(quality.warnings),
            }
            for path in (timestamped_path, output_dir / "pipeline_results.json"):
                with open(path, "w", encoding="utf-8") as handle:
                    json.dump(results, handle, ensure_ascii=False, indent=2, default=str)

        # Resource report
        resource.finalize()
        resource.save_json(str(output_dir / "submission_candidate" / "resource_usage.json"))
        resource.save_markdown(str(output_dir / "submission_candidate" / "resource_usage.md"))

        # Reproducibility doc
        repro_md = f"""# 可复现说明

## 运行环境
- Python 3.11
- 依赖: pandas, akshare, baostock, yfinance, requests
- 运行命令: `python scripts/run_quant_pipeline.py --strategy {args.strategy} --start-date {start_date} --end-date {end_date}`

## 数据源
- Sina Finance → Tencent → akshare → baostock → yfinance (逐只补缺)
- 独立逐股复核: 每只股票必须有第二来源重叠验证
- 数据区间: {market_bundle.closes.index[0].date()} → {market_bundle.closes.index[-1].date()}
- 训练天数: {len(prices_train)}, 前向窗口: 20 交易日
- 决策证据截止: {decision_time.isoformat()}
- 行情 manifest SHA-256: `{snapshot.manifest_sha256}`

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
            EvidenceRail,
            PortfolioConsistencyRail,
            ReportCompletenessRail,
            ResourceBudgetRail,
        )
        n_reports_on_disk = len(
            list((Path(pkg_path) / "company_reports").glob("*.md"))
        )
        rails = [
            EvidenceRail(quality),
            ReportCompletenessRail(len(ALL_STOCKS), n_reports_on_disk),
            PortfolioConsistencyRail(dict(weights), {t: b.portfolio_weight for t, b in bundles.items()}),
            ResourceBudgetRail(max_duration_s=600),
        ]
        rail_results = []
        elapsed = time.time() - t0
        for rail in rails:
            rr = (
                rail.check(duration_s=elapsed)
                if isinstance(rail, ResourceBudgetRail)
                else rail.check()
            )
            rail_results.append({
                "name": rr.rail_name, "passed": rr.passed,
                "blockers": rr.blockers, "warnings": rr.warnings,
            })
        all_rails_passed = all(item["passed"] for item in rail_results)
        with open(str(output_dir / "submission_candidate" / "rails_result.json"), "w", encoding="utf-8") as f:
            json.dump({"all_passed": all_rails_passed, "rails": rail_results}, f, indent=2, ensure_ascii=False)
        print(f"  Rails: {sum(1 for r in rail_results if r['passed'])}/{len(rail_results)} passed")
        if not all_rails_passed:
            blockers = [
                blocker
                for item in rail_results
                for blocker in item["blockers"]
            ]
            raise RuntimeError("runtime rails failed: " + "; ".join(blockers))

        # Framework changes
        framework_md = """# 框架实现说明

## 当前模块
- `quant/reporting/` — 证据模型、确定性报告生成、质量门禁、候选包构建 (R0-R5)
- `quant/reporting/submission_contract.py` — 赛事提交契约
- `quant/reporting/models.py` — 7 个证据 dataclass
- `quant/reporting/company_report.py` — 确定性 MD 报告生成器
- `quant/reporting/quality_gate.py` — 12 项质量检查含 EvidenceRef 强制执行
- `quant/reporting/package_builder.py` — 候选提交包构建
- `quant/reporting/report_service.py` — 双路径共享报告服务
- `quant/reporting/resource_meter.py` — 真实资源计量
- `quant/reporting/symphony_adapter.py` — Symphony 计划模型与策略校验
- `quant/reporting/providers/` — 数据 Provider 抽象
- `quant/market_data_provider.py` — 五源逐股补缺与第二来源复核
- `quant/market_data_service.py` — 共享 OHLCV、时序、覆盖与诊断契约

## 入口
- `scripts/run_quant_pipeline.py` — 研发旁路
- `evaluation/run_multi_agent.py` — JiuwenSwarm 正式路径
- 两条入口必须复用共享行情、选股、配仓、回测和报告服务

## 验收
- 当前测试数量、双路径 session、退出码和证据路径只引用根目录 `VALIDATION.md`
- 直跑要求: 官方股票池全覆盖、全部板块、15只、Quality PASSED
- 多Agent要求: 8/8 RPC, Alpha/Risk & Evidence 各自调用专属工具
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
