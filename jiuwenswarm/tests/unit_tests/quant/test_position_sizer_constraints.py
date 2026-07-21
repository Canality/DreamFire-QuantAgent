"""Invariant tests for final portfolio constraints."""

from jiuwenswarm.quant.factors import PositionConfig, PositionSizer


def _assert_constraints(raw_weights, sectors):
    sizer = PositionSizer(PositionConfig())
    weights = sizer._apply_constraints(
        raw_weights,
        sectors,
        {ticker: 0.0 for ticker in raw_weights},
    )
    sector_weights = {}
    for ticker, weight in weights.items():
        assert weight <= 0.10 + 1e-6, (ticker, weight)
        sector = sectors[ticker]
        sector_weights[sector] = sector_weights.get(sector, 0.0) + weight
    assert sum(weights.values()) <= 0.95 + 1e-6
    assert max(sector_weights.values()) <= 0.25 + 1e-6


def test_constraints_hold_with_only_two_sectors():
    raw = {f"T{i}": 1 / 15 for i in range(15)}
    sectors = {f"T{i}": "A" if i < 8 else "B" for i in range(15)}
    _assert_constraints(raw, sectors)


def test_constraints_hold_for_extreme_single_stock_concentration():
    raw = {"A1": 0.80, "B1": 0.05, "C1": 0.05, "D1": 0.05, "E1": 0.05}
    sectors = {ticker: ticker[0] for ticker in raw}
    _assert_constraints(raw, sectors)


def test_constraints_hold_for_normal_six_sector_portfolio():
    raw = {f"T{i}": 1 / 15 for i in range(15)}
    sectors = {f"T{i}": f"S{i % 6}" for i in range(15)}
    _assert_constraints(raw, sectors)


def test_single_stock_cap_holds_after_sector_redistribution():
    """Codex regression: 8-stock input that previously produced 13.69%."""
    # Simulate risk-parity output where one stock dominates
    raw = {
        "A1": 0.18, "B1": 0.14, "C1": 0.13, "D1": 0.12,
        "E1": 0.12, "F1": 0.11, "G1": 0.10, "H1": 0.10,
    }
    sectors = {t: t[0] for t in raw}  # each stock in its own sector
    _assert_constraints(raw, sectors)


def test_single_stock_cap_holds_in_crowded_sector():
    """Codex regression: 15-stock, 2-sector input that produced 12.44%."""
    raw = {f"T{i}": 1 / 15 for i in range(15)}
    sectors = {f"T{i}": "A" if i < 10 else "B" for i in range(15)}
    _assert_constraints(raw, sectors)


def test_six_sector_portfolio_uses_all_feasible_capacity():
    """Do not satisfy caps by silently discarding feasible investment capacity."""
    raw = {
        "T0": 0.00003, "T1": 0.00001, "T2": 0.026, "T3": 0.045,
        "T4": 0.058, "T5": 0.596, "T6": 0.026, "T7": 0.057,
        "T8": 0.00001, "T9": 0.050, "T10": 0.064, "T11": 0.069,
        "T12": 0.001, "T13": 0.004, "T14": 0.004,
    }
    total = sum(raw.values())
    raw = {ticker: weight / total for ticker, weight in raw.items()}
    sectors = {
        "T0": "S0", "T1": "S4", "T2": "S0", "T3": "S2",
        "T4": "S5", "T5": "S4", "T6": "S0", "T7": "S1",
        "T8": "S0", "T9": "S0", "T10": "S0", "T11": "S3",
        "T12": "S0", "T13": "S0", "T14": "S0",
    }
    sizer = PositionSizer(PositionConfig())
    weights = sizer._apply_constraints(
        raw, sectors, {ticker: 0.0 for ticker in raw},
    )
    _assert_constraints(raw, sectors)
    counts = {}
    for sector in sectors.values():
        counts[sector] = counts.get(sector, 0) + 1
    feasible_capacity = min(
        0.95,
        sum(min(count * 0.10, 0.25) for count in counts.values()),
    )
    # 15 four-decimal truncations can lose at most 0.0015.
    assert sum(weights.values()) >= feasible_capacity - 0.0015
