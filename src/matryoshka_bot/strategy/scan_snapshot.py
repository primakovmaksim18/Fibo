from __future__ import annotations

from datetime import UTC, datetime

from matryoshka_bot.strategy.scanner import ScanResult
from matryoshka_bot.trading.decision import context_bias, fib1_trend_bias
from matryoshka_bot.trading.signal_evaluation import nearest_entry_levels, segment_location


def _iso_ms(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=UTC).isoformat()


def _candle_row(c: dict) -> dict:
    return {
        "ts": _iso_ms(int(c["timestamp"])),
        "open": c["open"],
        "high": c["high"],
        "low": c["low"],
        "close": c["close"],
        "volume": c["volume"],
    }


def _nearest_in_list(price: float, levels: list[float]) -> dict:
    if not levels:
        return {"nearest": None, "distance_abs": None, "distance_pct_of_price": None}
    nearest = min(levels, key=lambda lv: abs(lv - price))
    dist = abs(nearest - price)
    return {
        "nearest": nearest,
        "distance_abs": dist,
        "distance_pct_of_price": (dist / price * 100.0) if price else None,
    }


def build_levels_cycle_snapshot(
    *,
    symbol: str,
    atl: float,
    ath: float,
    price: float,
    day_high: float,
    day_low: float,
    day_close: float,
    scan: ScanResult,
    d1_close: float,
    h4_close: float,
    trend_d1: str,
    trend_h4: str,
    trend_direction: str,
    candles: list[dict],
    current_candle_ts: int,
    outcome: str,
    skip_reason: str | None = None,
    bybit_demo_trading: bool | None = None,
) -> dict:
    entry_grid = sorted(set(scan.fib2_levels + scan.fib3_levels))
    sup, res = nearest_entry_levels(price=scan.price, levels=entry_grid)

    fib1_price_ctx = segment_location(price=scan.price, levels=scan.fib1_levels)
    low_f1, high_f1 = fib1_price_ctx["segment_low"], fib1_price_ctx["segment_high"]
    spot_fib1_bias = context_bias(price=scan.price, segment_low=low_f1, segment_high=high_f1)

    d1_bias = fib1_trend_bias(price=d1_close, fib1_levels=scan.fib1_levels)
    h4_bias = fib1_trend_bias(price=h4_close, fib1_levels=scan.fib1_levels)

    tail = candles[-5:] if len(candles) >= 5 else candles

    payload: dict = {
        "type": "level_cycle",
        "symbol": symbol,
        "outcome": outcome,
        "skip_reason": skip_reason,
        "bybit_demo_trading": bybit_demo_trading,
        "market_inputs": {
            "last_price": price,
            "daily_ohlc": {"high": day_high, "low": day_low, "close": day_close},
            "d1_last_close": d1_close,
            "h4_last_close": h4_close,
        },
        "bounds_atl_ath": {"atl": atl, "ath": ath, "range": ath - atl},
        "daily_regime": {
            "daily_range_pct": scan.daily_range_pct,
            "chosen_depth_for_matryoshka": scan.depth,
        },
        "matryoshka_levels": {
            "segment_for_price_union_levels": {
                "segment_low": scan.segment_low,
                "segment_high": scan.segment_high,
                **segment_location(price=scan.price, levels=scan.all_levels),
            },
            "counts": {
                "fib1": len(scan.fib1_levels),
                "fib2": len(scan.fib2_levels),
                "fib3": len(scan.fib3_levels),
                "unique_union_all_orders": len(scan.all_levels),
            },
            "fib1_levels": scan.fib1_levels,
            "fib2_levels": scan.fib2_levels,
            "fib3_levels": scan.fib3_levels,
            "all_levels_sorted_unique": scan.all_levels,
        },
        "fib1_bias_context": {
            "from_spot_price": {
                **fib1_price_ctx,
                "context_bias_near_fib1": spot_fib1_bias,
            },
            "trend_tf_d1": trend_d1,
            "trend_tf_h4": trend_h4,
            "computed_trend_direction": trend_direction,
            "fib1_bias_recomputed_from_closes": {"d1_close": d1_bias, "h4_close": h4_bias},
        },
        "entry_grid": {
            "nearest_fib2": _nearest_in_list(scan.price, scan.fib2_levels),
            "nearest_fib3": _nearest_in_list(scan.price, scan.fib3_levels),
            "support_below_or_equal_price": sup,
            "resistance_above_or_equal_price": res,
            "distance_to_support_pct": ((scan.price - sup) / scan.price * 100.0) if sup and scan.price else None,
            "distance_to_resistance_pct": ((res - scan.price) / scan.price * 100.0) if res and scan.price else None,
        },
        "candles_15m": {
            "current_open_time_ms": current_candle_ts,
            "current_open_time": _iso_ms(current_candle_ts),
            "bars_in_window": len(candles),
            "last_5_closed_or_open_sequence": [_candle_row(c) for c in tail],
        },
    }
    payload["fib1_bias_context"]["note"] = "trend_tf_* = fib1_trend_bias(close on tf vs fib1_levels); spot uses last_price"
    return payload
