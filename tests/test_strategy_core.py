import pytest

from matryoshka_bot.strategy.levels import build_fib_structure, build_unique_levels
from matryoshka_bot.strategy.regime import choose_depth
from matryoshka_bot.strategy.scanner import daily_range_pct, scan_symbol
from matryoshka_bot.strategy.segment import locate_segment
from matryoshka_bot.signals.bounce import bounce_long_confirmed, bounce_short_confirmed
from matryoshka_bot.signals.breakout import breakout_long_confirmed, breakout_short_confirmed
from matryoshka_bot.risk.sizing import calculate_position_size
from matryoshka_bot.reporting.metrics import compute_metrics
from matryoshka_bot.trading.decision import context_bias, fib1_trend_bias, merge_higher_tf_trend

try:
    from matryoshka_bot.exchange.bybit_client import (
        BybitClient,
        InstrumentConstraints,
        normalize_limit_price,
        normalize_order_qty,
    )
except ModuleNotFoundError:  # pragma: no cover - optional test dependency
    BybitClient = None
    InstrumentConstraints = None
    normalize_limit_price = None
    normalize_order_qty = None


def test_build_unique_levels_depth_4_contains_expected_key_levels():
    levels = build_unique_levels(atl=7.85, ath=295.6, depth=4)
    assert 7.85 in levels
    assert 75.759 in levels
    assert 117.7705 in levels
    assert 295.6 in levels
    assert len(levels) == 1297


def test_build_unique_levels_depth_5_more_dense_than_depth_4():
    depth_4 = build_unique_levels(atl=7.85, ath=295.6, depth=4)
    depth_5 = build_unique_levels(atl=7.85, ath=295.6, depth=5)
    assert len(depth_5) > len(depth_4)
    assert len(depth_5) == 7777


def test_build_fib_structure_exposes_fib_orders():
    fib = build_fib_structure(atl=7.85, ath=295.6, depth=5)
    assert len(fib.fib1) == 7
    assert len(fib.fib2) == 37
    assert len(fib.fib3) == 217
    assert 75.759 in fib.fib1
    assert len(fib.all_levels) == 7777


def test_locate_segment_finds_current_price_window():
    levels = build_unique_levels(atl=7.85, ath=295.6, depth=5)
    low, high = locate_segment(price=83.8, levels=levels)
    assert low == 83.743245
    assert high == 83.802332


def test_choose_depth_from_daily_range():
    assert choose_depth(daily_range_pct=11.2) == 4
    assert choose_depth(daily_range_pct=10.0) == 5
    assert choose_depth(daily_range_pct=6.8) == 5


def test_calculate_position_size_with_one_percent_risk():
    size = calculate_position_size(
        equity=10_000.0,
        risk_pct=1.0,
        entry=84.0,
        stop=82.0,
    )
    assert size == 50.0


def test_calculate_position_size_raises_for_invalid_stop_distance():
    try:
        calculate_position_size(
            equity=10_000.0,
            risk_pct=1.0,
            entry=84.0,
            stop=84.0,
        )
        assert False, "expected ValueError"
    except ValueError:
        assert True


def test_bounce_long_confirmed_when_filters_pass():
    assert bounce_long_confirmed(
        close=76.1,
        level=75.78,
        low=75.5,
        volume=1700,
        volume_sma20=1200,
        rsi=49.0,
        prev_rsi=45.0,
    )


def test_bounce_short_confirmed_when_filters_pass():
    assert bounce_short_confirmed(
        close=94.0,
        level=94.23,
        high=94.6,
        volume=1800,
        volume_sma20=1200,
        rsi=51.0,
        prev_rsi=55.0,
    )


def test_breakout_long_confirmed_when_body_volume_and_hold_pass():
    assert breakout_long_confirmed(
        close=95.1,
        open_price=94.2,
        high=95.3,
        low=94.1,
        level=94.23,
        volume=2500,
        volume_sma20=1500,
        next_close=94.5,
    )


def test_breakout_short_confirmed_when_body_volume_and_hold_pass():
    assert breakout_short_confirmed(
        close=75.1,
        open_price=75.9,
        high=76.0,
        low=75.0,
        level=75.78,
        volume=2400,
        volume_sma20=1500,
        next_close=75.5,
    )


def test_daily_range_pct_math():
    value = daily_range_pct(high=110.0, low=100.0, close=105.0)
    assert round(value, 6) == 9.52381


def test_scan_symbol_returns_segment_and_depth():
    result = scan_symbol(
        symbol="SOLUSDT",
        price=83.8,
        day_high=88.0,
        day_low=80.0,
        day_close=83.8,
        atl=7.85,
        ath=295.6,
    )
    assert result.depth == 5
    assert result.segment_low == 83.743245
    assert result.segment_high == 83.802332
    assert len(result.fib1_levels) == 7
    assert len(result.fib2_levels) == 37
    assert len(result.fib3_levels) == 217


def test_context_bias_uses_segment_position():
    assert context_bias(price=76.0, segment_low=75.0, segment_high=95.0) == "long"
    assert context_bias(price=94.0, segment_low=75.0, segment_high=95.0) == "short"
    assert context_bias(price=85.0, segment_low=75.0, segment_high=95.0) == "neutral"


def test_fib1_trend_bias_and_merge_higher_tf():
    fib1 = build_fib_structure(atl=2817.0, ath=126199.63, depth=5).fib1
    assert fib1_trend_bias(price=50000.0, fib1_levels=fib1) == "long"
    assert fib1_trend_bias(price=98000.0, fib1_levels=fib1) == "short"
    assert merge_higher_tf_trend(d1_bias="long", h4_bias="long") == "long"
    assert merge_higher_tf_trend(d1_bias="long", h4_bias="short") == "neutral"
    assert merge_higher_tf_trend(d1_bias="neutral", h4_bias="short") == "short"


def test_compute_metrics_from_trade_pnls():
    metrics = compute_metrics([100.0, -50.0, 25.0, -10.0, 0.0])
    assert metrics["trades"] == 5
    assert metrics["wins"] == 2
    assert metrics["losses"] == 2
    assert round(metrics["win_rate_pct"], 2) == 40.0
    assert round(metrics["profit_factor"], 2) == 2.08


def test_normalize_order_qty_aligns_to_step_and_min_qty():
    if InstrumentConstraints is None or normalize_order_qty is None:
        pytest.skip("pybit is not installed")
    constraints = InstrumentConstraints(
        qty_step=0.001,
        min_qty=0.01,
        min_notional=5.0,
        tick_size=0.1,
    )
    result = normalize_order_qty(raw_qty=0.0104, price=60000.0, constraints=constraints)
    assert result == 0.01


def test_normalize_order_qty_returns_none_when_min_notional_not_met():
    if InstrumentConstraints is None or normalize_order_qty is None:
        pytest.skip("pybit is not installed")
    constraints = InstrumentConstraints(
        qty_step=0.001,
        min_qty=0.001,
        min_notional=100.0,
        tick_size=0.1,
    )
    result = normalize_order_qty(raw_qty=0.001, price=50000.0, constraints=constraints)
    assert result is None


def test_normalize_limit_price_rounds_by_tick_size():
    if InstrumentConstraints is None or normalize_limit_price is None:
        pytest.skip("pybit is not installed")
    constraints = InstrumentConstraints(
        qty_step=0.001,
        min_qty=0.001,
        min_notional=5.0,
        tick_size=0.05,
    )
    assert normalize_limit_price(raw_price=123.127, side="Buy", constraints=constraints) == 123.1
    assert normalize_limit_price(raw_price=123.127, side="Sell", constraints=constraints) == 123.15


def test_retryable_error_detection():
    if BybitClient is None:
        pytest.skip("pybit is not installed")
    assert BybitClient._is_retryable_error(RuntimeError("HTTP 429 rate limit"))
    assert BybitClient._is_retryable_error(RuntimeError("Server 503 unavailable"))
    assert not BybitClient._is_retryable_error(RuntimeError("Invalid api key"))
