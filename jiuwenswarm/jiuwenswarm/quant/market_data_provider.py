"""Shared real-market provider layer for deterministic quant inputs.

The provider layer owns network parsing, per-ticker fallback, unit conversion,
independent secondary evidence, and benchmark provenance.  It deliberately
does not own either production entry point; adapters are migrated only after
this module passes isolated review.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from typing import Any, Protocol

import numpy as np
import pandas as pd
import requests

from jiuwenswarm.quant.market_data_service import MarketDataBundle, ProviderEvidence

_OHLCV = ("open", "high", "low", "close", "volume")
_PRICE_COLUMNS = ("open", "high", "low", "close")
_ADJUSTMENT_POLICY = "raw_unadjusted"
_CALENDAR_ID = "SSE_SZSE_observed_sessions"
_MARKET_CLOSE = time(15, 30)


class MarketDataFetchError(RuntimeError):
    """Raised when real evidence cannot satisfy the frozen market contract."""


@dataclass(frozen=True)
class ProviderPayload:
    """Raw per-ticker provider frames plus bounded error evidence."""

    frames: Mapping[str, pd.DataFrame]
    errors: tuple[str, ...] = ()


class ProviderFetcher(Protocol):
    def __call__(
        self,
        tickers: Sequence[str],
        start_date: str,
        end_date: str,
    ) -> ProviderPayload: ...


@dataclass(frozen=True)
class ProviderSpec:
    """One source adapter and the economic conventions it declares."""

    name: str
    fetcher: ProviderFetcher
    evidence: ProviderEvidence


@dataclass(frozen=True)
class BenchmarkPayload:
    """CSI300 close evidence with an explicit source identity."""

    closes: pd.Series
    provider: str
    source_endpoint: str
    errors: tuple[str, ...] = ()


BenchmarkFetcher = Callable[[str, str], BenchmarkPayload]


def _http_symbol(ticker: str) -> str:
    code, exchange = ticker.split(".")
    if exchange not in {"SH", "SZ"}:
        raise ValueError(f"unsupported A-share exchange: {ticker}")
    return f"{'sh' if exchange == 'SH' else 'sz'}{code}"


def _yf_ticker(ticker: str) -> str:
    return ticker.replace(".SH", ".SS")


def _baostock_symbol(ticker: str) -> str:
    code, exchange = ticker.split(".")
    if exchange not in {"SH", "SZ"}:
        raise ValueError(f"unsupported A-share exchange: {ticker}")
    return f"{exchange.lower()}.{code}"


def _normalize_frame(
    frame: Any,
    start_date: str,
    end_date: str,
    *,
    volume_multiplier: float,
) -> pd.DataFrame:
    """Return sorted canonical OHLCV in CNY/share and shares."""

    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.DataFrame(columns=_OHLCV)
    normalized = frame.copy()
    normalized.columns = [str(column).strip().lower() for column in normalized.columns]
    if not set(_OHLCV).issubset(normalized.columns):
        return pd.DataFrame(columns=_OHLCV)
    index = pd.to_datetime(normalized.index, errors="coerce")
    valid_index = ~index.isna()
    normalized = normalized.loc[valid_index, list(_OHLCV)]
    index = pd.DatetimeIndex(index[valid_index])
    if index.tz is not None:
        index = index.tz_convert("Asia/Shanghai").tz_localize(None)
    normalized.index = index.normalize()
    normalized = normalized[~normalized.index.duplicated(keep="last")].sort_index()
    normalized = normalized.loc[pd.Timestamp(start_date) : pd.Timestamp(end_date)]
    for column in _OHLCV:
        normalized[column] = pd.to_numeric(normalized[column], errors="coerce")
    normalized["volume"] *= float(volume_multiplier)
    normalized = normalized.replace([np.inf, -np.inf], np.nan).dropna(how="any")
    return normalized.astype(float)


def _frame_usable(frame: pd.DataFrame, minimum_rows: int) -> bool:
    if len(frame) < minimum_rows or list(frame.columns) != list(_OHLCV):
        return False
    if frame.index.has_duplicates or not frame.index.is_monotonic_increasing:
        return False
    if bool((frame[list(_PRICE_COLUMNS)] <= 0).any().any()):
        return False
    if bool((frame["volume"] < 0).any()):
        return False
    high_floor = frame[["open", "close"]].max(axis=1)
    low_ceiling = frame[["open", "close"]].min(axis=1)
    return not bool(
        (
            (frame["high"] < high_floor)
            | (frame["low"] > low_ceiling)
            | (frame["high"] < frame["low"])
        ).any()
    )


def _numeric_ohlcv(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.loc[:, list(_OHLCV)].copy()
    for column in _OHLCV:
        result[column] = pd.to_numeric(result[column], errors="coerce")
    return result.dropna(how="any")


def _parallel_http_fetch(
    tickers: Sequence[str],
    worker: Callable[[str], pd.DataFrame],
    provider_name: str,
) -> ProviderPayload:
    frames: dict[str, pd.DataFrame] = {}
    errors: list[str] = []
    with ThreadPoolExecutor(max_workers=min(8, max(1, len(tickers)))) as pool:
        futures = {pool.submit(worker, ticker): ticker for ticker in tickers}
        for future in as_completed(futures):
            ticker = futures[future]
            try:
                frame = future.result()
                if frame.empty:
                    raise ValueError("empty OHLCV payload")
                frames[ticker] = frame
            except Exception as exc:  # noqa: BLE001 - retained as provider evidence
                errors.append(f"{provider_name}:{ticker}: {exc}")
    return ProviderPayload(frames=frames, errors=tuple(errors))


def fetch_sina(
    tickers: Sequence[str],
    start_date: str,
    end_date: str,
    *,
    http: Any = requests,
) -> ProviderPayload:
    """Fetch raw, unadjusted OHLCV from Sina's daily K-line endpoint."""

    url = (
        "https://quotes.sina.cn/cn/api/json_v2.php/"
        "CN_MarketDataService.getKLineData"
    )
    start = pd.Timestamp(start_date)
    datalen = min(1023, max(120, (pd.Timestamp.now().normalize() - start).days + 30))

    def worker(ticker: str) -> pd.DataFrame:
        response = http.get(
            url,
            params={
                "symbol": _http_symbol(ticker),
                "scale": "240",
                "ma": "no",
                "datalen": datalen,
            },
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=12,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list) or not payload:
            raise ValueError(f"invalid payload: {str(payload)[:100]}")
        frame = pd.DataFrame(payload)
        if not {"day", *_OHLCV}.issubset(frame.columns):
            raise ValueError(f"missing fields: {list(frame.columns)}")
        frame["day"] = pd.to_datetime(frame["day"], errors="raise")
        return _numeric_ohlcv(
            frame.set_index("day").sort_index().loc[start_date:end_date]
        )

    return _parallel_http_fetch(tickers, worker, "sina")


def fetch_tencent(
    tickers: Sequence[str],
    start_date: str,
    end_date: str,
    *,
    http: Any = requests,
) -> ProviderPayload:
    """Fetch raw, unadjusted OHLCV from Tencent's daily K-line endpoint."""

    url = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"

    def worker(ticker: str) -> pd.DataFrame:
        symbol = _http_symbol(ticker)
        response = http.get(
            url,
            params={"param": f"{symbol},day,{start_date},{end_date},1023,none"},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=12,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("code") != 0:
            raise ValueError(f"provider code={payload.get('code')}: {payload.get('msg')}")
        rows = payload.get("data", {}).get(symbol, {}).get("day", [])
        if not rows:
            raise ValueError("empty day series")
        normalized = [row[:6] for row in rows if len(row) >= 6]
        frame = pd.DataFrame(
            normalized,
            columns=["date", "open", "close", "high", "low", "volume"],
        )
        frame["date"] = pd.to_datetime(frame["date"], errors="raise")
        return _numeric_ohlcv(
            frame.set_index("date").sort_index().loc[start_date:end_date]
        )

    return _parallel_http_fetch(tickers, worker, "tencent")


def fetch_akshare(
    tickers: Sequence[str],
    start_date: str,
    end_date: str,
    *,
    ak_module: Any | None = None,
) -> ProviderPayload:
    """Fetch Eastmoney-backed raw OHLCV through AKShare."""

    try:
        ak = ak_module or importlib.import_module("akshare")
    except ImportError:
        return ProviderPayload(frames={}, errors=("akshare is not installed",))
    frames: dict[str, pd.DataFrame] = {}
    errors: list[str] = []
    rename = {
        "日期": "date",
        "开盘": "open",
        "最高": "high",
        "最低": "low",
        "收盘": "close",
        "成交量": "volume",
    }
    for ticker in tickers:
        try:
            frame = ak.stock_zh_a_hist(
                symbol=ticker.split(".")[0],
                period="daily",
                start_date=start_date.replace("-", ""),
                end_date=end_date.replace("-", ""),
                adjust="",
            )
            if not isinstance(frame, pd.DataFrame) or frame.empty:
                raise ValueError("empty OHLCV payload")
            frame = frame.rename(columns=rename)
            if not {"date", *_OHLCV}.issubset(frame.columns):
                raise ValueError(f"missing fields: {list(frame.columns)}")
            frame["date"] = pd.to_datetime(frame["date"], errors="raise")
            frames[ticker] = _numeric_ohlcv(frame.set_index("date"))
        except Exception as exc:  # noqa: BLE001 - retained as provider evidence
            errors.append(f"akshare:{ticker}: {exc}")
    return ProviderPayload(frames=frames, errors=tuple(errors))


def fetch_baostock(
    tickers: Sequence[str],
    start_date: str,
    end_date: str,
    *,
    bs_module: Any | None = None,
) -> ProviderPayload:
    """Fetch raw OHLCV through BaoStock using one bounded login session."""

    try:
        bs = bs_module or importlib.import_module("baostock")
    except ImportError:
        return ProviderPayload(frames={}, errors=("baostock is not installed",))
    frames: dict[str, pd.DataFrame] = {}
    errors: list[str] = []
    logged_in = False
    try:
        login = bs.login()
        if login.error_code != "0":
            return ProviderPayload(
                frames={},
                errors=(f"baostock login failed: {login.error_msg}",),
            )
        logged_in = True
        for ticker in tickers:
            code = _baostock_symbol(ticker)
            try:
                result = bs.query_history_k_data_plus(
                    code,
                    "date,open,high,low,close,volume",
                    start_date=start_date,
                    end_date=end_date,
                    frequency="d",
                    adjustflag="3",
                )
                if result.error_code != "0":
                    raise ValueError(result.error_msg)
                rows: list[list[str]] = []
                while result.next():
                    rows.append(result.get_row_data())
                if not rows:
                    raise ValueError("empty OHLCV payload")
                frame = pd.DataFrame(rows, columns=result.fields)
                frame["date"] = pd.to_datetime(frame["date"], errors="raise")
                frames[ticker] = _numeric_ohlcv(frame.set_index("date"))
            except Exception as exc:  # noqa: BLE001 - retained as provider evidence
                errors.append(f"baostock:{ticker}: {exc}")
    finally:
        if logged_in:
            try:
                bs.logout()
            except Exception as exc:  # noqa: BLE001 - logout is diagnostic only
                errors.append(f"baostock:logout: {exc}")
    return ProviderPayload(frames=frames, errors=tuple(errors))


def _yf_column(frame: pd.DataFrame, name: str) -> pd.Series:
    values = frame.get(name)
    if isinstance(values, pd.DataFrame):
        if values.shape[1] != 1:
            raise ValueError(f"ambiguous yfinance {name} columns")
        return values.iloc[:, 0]
    if not isinstance(values, pd.Series):
        raise TypeError(f"missing yfinance {name} column")
    return values


def fetch_yfinance(
    tickers: Sequence[str],
    start_date: str,
    end_date: str,
    *,
    yf_module: Any | None = None,
) -> ProviderPayload:
    """Fetch raw OHLCV through yfinance, converting inclusive end to exclusive."""

    try:
        yf = yf_module or importlib.import_module("yfinance")
    except ImportError:
        return ProviderPayload(frames={}, errors=("yfinance is not installed",))
    frames: dict[str, pd.DataFrame] = {}
    errors: list[str] = []
    exclusive_end = (pd.Timestamp(end_date) + timedelta(days=1)).strftime("%Y-%m-%d")
    for ticker in tickers:
        try:
            downloaded = yf.download(
                _yf_ticker(ticker),
                start=start_date,
                end=exclusive_end,
                progress=False,
                auto_adjust=False,
                actions=False,
                threads=False,
            )
            if not isinstance(downloaded, pd.DataFrame) or downloaded.empty:
                raise ValueError("empty OHLCV payload")
            frame = pd.DataFrame(
                {
                    "open": _yf_column(downloaded, "Open"),
                    "high": _yf_column(downloaded, "High"),
                    "low": _yf_column(downloaded, "Low"),
                    "close": _yf_column(downloaded, "Close"),
                    "volume": _yf_column(downloaded, "Volume"),
                }
            )
            frames[ticker] = frame.loc[start_date:end_date]
        except Exception as exc:  # noqa: BLE001 - retained as provider evidence
            errors.append(f"yfinance:{ticker}: {exc}")
    return ProviderPayload(frames=frames, errors=tuple(errors))


def default_provider_specs() -> tuple[ProviderSpec, ...]:
    """Return the frozen five-source order and canonical-unit declarations.

    AKShare documents Eastmoney volume in lots; BaoStock documents shares.
    A live same-ticker/date check on 2026-08-03 showed Sina volume matching
    shares and Tencent matching rounded lots, so Tencent receives a x100
    conversion.  These declarations are verified again by cross-source price
    evidence before a bundle may pass.
    """

    definitions = (
        (
            "sina",
            fetch_sina,
            "https://quotes.sina.cn/cn/api/json_v2.php/CN_MarketDataService.getKLineData",
            "shares",
            1.0,
        ),
        (
            "tencent",
            fetch_tencent,
            "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get",
            "lots_100_shares",
            100.0,
        ),
        (
            "akshare",
            fetch_akshare,
            "https://push2his.eastmoney.com/api/qt/stock/kline/get",
            "lots_100_shares",
            100.0,
        ),
        (
            "baostock",
            fetch_baostock,
            "http://www.baostock.com/baostock/index.php/Python_API文档",
            "shares",
            1.0,
        ),
        (
            "yfinance",
            fetch_yfinance,
            "https://query1.finance.yahoo.com/v8/finance/chart",
            "shares",
            1.0,
        ),
    )
    return tuple(
        ProviderSpec(
            name=name,
            fetcher=fetcher,
            evidence=ProviderEvidence(
                name=name,
                source_endpoint=endpoint,
                price_adjustment=_ADJUSTMENT_POLICY,
                raw_volume_unit=volume_unit,
                volume_multiplier_to_shares=multiplier,
            ),
        )
        for name, fetcher, endpoint, volume_unit, multiplier in definitions
    )


def fetch_csi300_benchmark(start_date: str, end_date: str) -> BenchmarkPayload:
    """Fetch CSI300 raw closes with explicit AkShare/BaoStock/yfinance fallback."""

    errors: list[str] = []
    try:
        ak = importlib.import_module("akshare")
        frame = ak.stock_zh_index_daily(symbol="sh000300")
        if isinstance(frame, pd.DataFrame) and not frame.empty:
            frame = frame.copy()
            frame["date"] = pd.to_datetime(frame["date"], errors="raise")
            closes = pd.to_numeric(
                frame.set_index("date").sort_index().loc[start_date:end_date, "close"],
                errors="coerce",
            ).dropna()
            if not closes.empty:
                closes.name = "CSI300:akshare"
                return BenchmarkPayload(
                    closes=closes,
                    provider="akshare",
                    source_endpoint="https://akshare.akfamily.xyz/data/index/index.html",
                    errors=tuple(errors),
                )
    except Exception as exc:  # noqa: BLE001 - fallback evidence
        errors.append(f"akshare:CSI300: {exc}")

    try:
        bs = importlib.import_module("baostock")
        login = bs.login()
        if login.error_code != "0":
            raise RuntimeError(login.error_msg)
        try:
            result = bs.query_history_k_data_plus(
                "sh.000300",
                "date,close",
                start_date=start_date,
                end_date=end_date,
                frequency="d",
                adjustflag="3",
            )
            if result.error_code != "0":
                raise RuntimeError(result.error_msg)
            rows: list[list[str]] = []
            while result.next():
                rows.append(result.get_row_data())
        finally:
            bs.logout()
        frame = pd.DataFrame(rows, columns=result.fields)
        if not frame.empty:
            frame["date"] = pd.to_datetime(frame["date"], errors="raise")
            closes = pd.to_numeric(frame.set_index("date")["close"], errors="coerce").dropna()
            closes.name = "CSI300:baostock"
            return BenchmarkPayload(
                closes=closes,
                provider="baostock",
                source_endpoint="http://www.baostock.com/baostock/index.php/Python_API文档",
                errors=tuple(errors),
            )
    except Exception as exc:  # noqa: BLE001 - fallback evidence
        errors.append(f"baostock:CSI300: {exc}")

    payload = fetch_yfinance(["000300.SH"], start_date, end_date)
    if "000300.SH" in payload.frames:
        closes = pd.to_numeric(payload.frames["000300.SH"]["close"], errors="coerce").dropna()
        closes.name = "CSI300:yfinance"
        return BenchmarkPayload(
            closes=closes,
            provider="yfinance",
            source_endpoint="https://query1.finance.yahoo.com/v8/finance/chart",
            errors=(*errors, *payload.errors),
        )
    return BenchmarkPayload(
        closes=pd.Series(dtype=float),
        provider="unavailable",
        source_endpoint="",
        errors=(*errors, *payload.errors),
    )


def _validated_provider_payload(
    spec: ProviderSpec,
    tickers: Sequence[str],
    start_date: str,
    end_date: str,
) -> tuple[dict[str, pd.DataFrame], tuple[str, ...]]:
    try:
        payload = spec.fetcher(tickers, start_date, end_date)
    except Exception as exc:  # noqa: BLE001 - provider failure becomes evidence
        return {}, (f"{spec.name}:batch: {exc}",)
    if not isinstance(payload, ProviderPayload):
        return {}, (f"{spec.name}: invalid ProviderPayload",)
    requested = set(tickers)
    extra = sorted(set(payload.frames) - requested)
    errors = list(payload.errors)
    if extra:
        errors.append(f"{spec.name}: unrequested tickers returned: {extra}")
    frames = {
        ticker: _normalize_frame(
            raw,
            start_date,
            end_date,
            volume_multiplier=spec.evidence.volume_multiplier_to_shares,
        )
        for ticker, raw in payload.frames.items()
        if ticker in requested
    }
    return frames, tuple(errors)


def _combine_primary_frames(
    tickers: Sequence[str],
    frames: Mapping[str, pd.DataFrame],
    minimum_rows: int,
) -> dict[str, pd.DataFrame]:
    common_index: pd.DatetimeIndex | None = None
    for ticker in tickers:
        index = frames[ticker].index
        common_index = index if common_index is None else common_index.intersection(index)
    if common_index is None or len(common_index) < minimum_rows:
        count = 0 if common_index is None else len(common_index)
        raise MarketDataFetchError(
            f"canonical trading-calendar overlap has {count} rows; minimum is {minimum_rows}"
        )
    common_index = common_index.sort_values()
    return {
        field: pd.concat(
            [frames[ticker][field].reindex(common_index).rename(ticker) for ticker in tickers],
            axis=1,
        ).reindex(columns=list(tickers))
        for field in _OHLCV
    }


def fetch_market_data_bundle(
    tickers: Sequence[str],
    start_date: str,
    end_date: str,
    *,
    as_of_time: datetime,
    providers: Sequence[ProviderSpec] | None = None,
    benchmark_fetcher: BenchmarkFetcher = fetch_csi300_benchmark,
    minimum_rows: int = 81,
    minimum_secondary_overlap_days: int = 20,
    minimum_benchmark_rows: int = 60,
    cross_source_tolerance_pct: float = 1.0,
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> MarketDataBundle:
    """Build a complete canonical bundle or fail before downstream quant work."""

    requested = [str(ticker) for ticker in tickers]
    if not requested or len(requested) != len(set(requested)):
        raise MarketDataFetchError("tickers must be non-empty and unique")
    if as_of_time.tzinfo is None or as_of_time.utcoffset() is None:
        raise MarketDataFetchError("as_of_time must be timezone-aware")
    start = pd.Timestamp(start_date).normalize()
    end = pd.Timestamp(end_date).normalize()
    as_of_local = pd.Timestamp(as_of_time).tz_convert("Asia/Shanghai")
    if start > end or end.date() > as_of_local.date():
        raise MarketDataFetchError("requested dates exceed the point-in-time boundary")
    if end.date() == as_of_local.date() and as_of_local.time() < _MARKET_CLOSE:
        raise MarketDataFetchError("end_date is an incomplete trading session")

    specs = tuple(providers or default_provider_specs())
    names = [spec.name for spec in specs]
    if not specs or len(names) != len(set(names)):
        raise MarketDataFetchError("provider names must be non-empty and unique")
    endpoints = [spec.evidence.source_endpoint.strip() for spec in specs]
    if any(not endpoint for endpoint in endpoints) or len(endpoints) != len(set(endpoints)):
        raise MarketDataFetchError("provider endpoints must be non-empty and unique")
    for spec in specs:
        evidence = spec.evidence
        if evidence.name != spec.name:
            raise MarketDataFetchError(f"provider evidence mismatch for {spec.name}")
        if evidence.price_adjustment != _ADJUSTMENT_POLICY:
            raise MarketDataFetchError(f"unsupported adjustment policy for {spec.name}")
        if not np.isfinite(evidence.volume_multiplier_to_shares) or (
            evidence.volume_multiplier_to_shares <= 0
        ):
            raise MarketDataFetchError(f"invalid volume multiplier for {spec.name}")

    stats: dict[str, dict[str, Any]] = {
        spec.name: {
            "primary_requested": 0,
            "primary_covered": 0,
            "secondary_requested": 0,
            "secondary_covered": 0,
            "errors": 0,
            "error_samples": [],
        }
        for spec in specs
    }
    primary_frames: dict[str, pd.DataFrame] = {}
    primary_ledger: dict[str, str] = {}
    for spec in specs:
        missing = [ticker for ticker in requested if ticker not in primary_frames]
        if not missing:
            break
        frames, errors = _validated_provider_payload(spec, missing, start_date, end_date)
        provider_stat = stats[spec.name]
        provider_stat["primary_requested"] += len(missing)
        provider_stat["errors"] += len(errors)
        provider_stat["error_samples"].extend(errors[:3])
        newly_covered = 0
        for ticker in missing:
            frame = frames.get(ticker)
            if frame is not None and _frame_usable(frame, minimum_rows):
                primary_frames[ticker] = frame
                primary_ledger[ticker] = spec.name
                newly_covered += 1
        provider_stat["primary_covered"] += newly_covered

    missing_primary = [ticker for ticker in requested if ticker not in primary_frames]
    if missing_primary:
        raise MarketDataFetchError(
            f"primary coverage incomplete: {len(primary_frames)}/{len(requested)}; "
            f"missing={missing_primary}"
        )

    secondary: dict[str, pd.Series] = {}
    secondary_ledger: dict[str, str] = {}
    for spec in specs:
        eligible = [
            ticker
            for ticker in requested
            if ticker not in secondary and primary_ledger[ticker] != spec.name
        ]
        if not eligible:
            continue
        frames, errors = _validated_provider_payload(spec, eligible, start_date, end_date)
        provider_stat = stats[spec.name]
        provider_stat["secondary_requested"] += len(eligible)
        provider_stat["errors"] += len(errors)
        provider_stat["error_samples"].extend(errors[:3])
        covered = 0
        for ticker in eligible:
            frame = frames.get(ticker)
            if frame is None:
                continue
            primary_close = primary_frames[ticker]["close"]
            secondary_close = frame["close"]
            overlap = primary_close.index.intersection(secondary_close.dropna().index)
            if len(overlap) < minimum_secondary_overlap_days:
                continue
            divergence = (
                (primary_close.loc[overlap] - secondary_close.loc[overlap]).abs()
                / secondary_close.loc[overlap].abs().clip(lower=0.01)
                * 100.0
            )
            if bool((divergence > cross_source_tolerance_pct).any()):
                provider_stat["errors"] += 1
                provider_stat["error_samples"].append(
                    f"{ticker}: cross-source divergence exceeds "
                    f"{cross_source_tolerance_pct}%"
                )
                continue
            secondary[ticker] = secondary_close
            secondary_ledger[ticker] = spec.name
            covered += 1
        provider_stat["secondary_covered"] += covered

    missing_secondary = [ticker for ticker in requested if ticker not in secondary]
    if missing_secondary:
        raise MarketDataFetchError(
            f"independent secondary coverage incomplete: "
            f"{len(secondary)}/{len(requested)}; missing={missing_secondary}"
        )

    combined = _combine_primary_frames(requested, primary_frames, minimum_rows)
    secondary_closes = pd.concat(
        [secondary[ticker].rename(ticker) for ticker in requested],
        axis=1,
    ).sort_index().reindex(columns=requested)

    benchmark = benchmark_fetcher(start_date, end_date)
    if not isinstance(benchmark, BenchmarkPayload):
        raise MarketDataFetchError("benchmark fetcher returned an invalid payload")
    benchmark_closes = pd.to_numeric(benchmark.closes, errors="coerce").dropna()
    if isinstance(benchmark_closes.index, pd.DatetimeIndex):
        benchmark_index = pd.DatetimeIndex(benchmark_closes.index)
        if benchmark_index.tz is not None:
            benchmark_index = benchmark_index.tz_convert("Asia/Shanghai").tz_localize(None)
        benchmark_closes.index = benchmark_index.normalize()
        benchmark_closes = benchmark_closes[
            ~benchmark_closes.index.duplicated(keep="last")
        ].sort_index()
    benchmark_overlap = combined["close"].index.intersection(benchmark_closes.index)
    if (
        not isinstance(benchmark_closes.index, pd.DatetimeIndex)
        or len(benchmark_overlap) < minimum_benchmark_rows
        or not benchmark.provider.strip()
        or not benchmark.source_endpoint.strip()
    ):
        raise MarketDataFetchError(
            f"benchmark evidence incomplete: overlap={len(benchmark_overlap)}; "
            f"errors={list(benchmark.errors[-3:])}"
        )
    benchmark_closes.name = benchmark.closes.name or f"CSI300:{benchmark.provider}"

    retrieved_at = now()
    if retrieved_at.tzinfo is None or retrieved_at.utcoffset() is None:
        raise MarketDataFetchError("retrieval clock must return a timezone-aware datetime")
    if retrieved_at < as_of_time:
        raise MarketDataFetchError("retrieved_at cannot precede as_of_time")
    stats["secondary_audit"] = {
        "covered": len(secondary_ledger),
        "provider_ledger": secondary_ledger,
    }
    stats["benchmark"] = {
        "provider": benchmark.provider,
        "source_endpoint": benchmark.source_endpoint,
        "overlap_rows": len(benchmark_overlap),
        "errors": len(benchmark.errors),
        "error_samples": list(benchmark.errors[-3:]),
    }
    return MarketDataBundle(
        opens=combined["open"],
        highs=combined["high"],
        lows=combined["low"],
        closes=combined["close"],
        volumes=combined["volume"],
        secondary_closes=secondary_closes,
        benchmark_closes=benchmark_closes,
        provider_ledger=primary_ledger,
        provider_stats=stats,
        provider_evidence={spec.name: spec.evidence for spec in specs},
        calendar_id=_CALENDAR_ID,
        adjustment_policy=_ADJUSTMENT_POLICY,
        secondary_label="per_ticker_independent_provider",
        as_of_time=as_of_time,
        retrieved_at=retrieved_at,
    )
