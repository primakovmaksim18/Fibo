from __future__ import annotations

import pytest

from matryoshka_bot.signals.conditions_audit import audit_bounce_long
from matryoshka_bot.strategy.scanner import ScanResult, scan_symbol
from matryoshka_bot.strategy.scan_snapshot import build_levels_cycle_snapshot
from matryoshka_bot.trading.indicators import simple_rsi
from matryoshka_bot.trading.signal_evaluation import (
    analyze_entry_signals,
    nearest_entry_levels,
    next_fib_level_beyond,
    segment_location,
)


def test_audit_bounce_long_matches_engine_logic() -> None:
    audit = audit_bounce_long(
        close=101.0,
        level=100.0,
        low=99.0,
        volume=130.0,
        volume_sma20=100.0,
        rsi=50.0,
        prev_rsi=40.0,
    )
    assert audit["confirmed"] is True
    assert all(audit["checks"][k]["pass"] for k in ("touched_support", "closed_back_above", "volume", "momentum"))


def test_nearest_entry_levels_brackets_price() -> None:
    levels = [10.0, 20.0, 30.0, 40.0]
    s, r = nearest_entry_levels(price=25.0, levels=levels)
    assert s == 20.0 and r == 30.0


def test_next_fib_level_beyond_adjacent() -> None:
    grid = [10.0, 20.0, 30.0, 40.0]
    assert next_fib_level_beyond(grid, 30.0, search_lower=True) == 20.0
    assert next_fib_level_beyond(grid, 30.0, search_lower=False) == 40.0
    assert next_fib_level_beyond(grid, 10.0, search_lower=True) is None


def test_segment_location_middle() -> None:
    ctx = segment_location(price=25.0, levels=[10.0, 20.0, 30.0, 40.0])
    assert ctx["segment_low"] == 20.0
    assert ctx["segment_high"] == 30.0
    assert ctx["branch"] == "price_between_sorted_levels"


@pytest.fixture
def scan_btc_like() -> ScanResult:
    return scan_symbol(
        symbol="BTCUSDT",
        price=50000.0,
        day_high=51000.0,
        day_low=49000.0,
        day_close=50000.0,
        atl=15460.0,
        ath=109000.0,
    )


def test_build_levels_cycle_snapshot_contains_full_fib_arrays(scan_btc_like: ScanResult) -> None:
    candles = [
        {"timestamp": i * 60_000, "open": 1.0, "high": 1.05, "low": 0.95, "close": 1.0, "volume": 50.0} for i in range(5)
    ]
    snap = build_levels_cycle_snapshot(
        symbol="BTCUSDT",
        atl=15460.0,
        ath=109000.0,
        price=50000.0,
        day_high=51000.0,
        day_low=49000.0,
        day_close=50000.0,
        scan=scan_btc_like,
        d1_close=49900.0,
        h4_close=50100.0,
        trend_d1="neutral",
        trend_h4="neutral",
        trend_direction="neutral",
        candles=candles,
        current_candle_ts=240_000,
        outcome="no_entry",
        skip_reason="no_setup_triggered",
        bybit_demo_trading=True,
    )
    ml = snap["matryoshka_levels"]
    assert ml["counts"]["fib1"] == len(ml["fib1_levels"])
    assert len(ml["all_levels_sorted_unique"]) >= len(ml["fib1_levels"])
    assert snap["type"] == "level_cycle"
    assert snap["entry_grid"]["nearest_fib2"]["nearest"] is not None


def test_simple_rsi_flat_returns_hundred_when_no_losses() -> None:
    flat = [{"close": 100.0} for _ in range(20)]
    r = simple_rsi(flat[-15:])
    assert r == 100.0


def test_analyze_entry_signals_no_setup_audit_present(scan_btc_like: ScanResult) -> None:
    candles = [{"timestamp": i, "open": 1.0, "high": 1.05, "low": 0.95, "close": 1.0, "volume": 10.0} for i in range(25)]
    sig, diag = analyze_entry_signals(
        scan=scan_btc_like,
        candles=candles,
        trend_direction="neutral",
    )
    assert sig is None
    assert "setup_audits" in diag
    assert "bounce_long" in diag["setup_audits"]
