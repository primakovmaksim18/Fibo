from __future__ import annotations

from bisect import bisect_right

from matryoshka_bot.signals.conditions_audit import (
    audit_bounce_long,
    audit_bounce_short,
    audit_breakout_long,
    audit_breakout_short,
)
from matryoshka_bot.signals.bounce import bounce_long_confirmed, bounce_short_confirmed
from matryoshka_bot.signals.breakout import breakout_long_confirmed, breakout_short_confirmed
from matryoshka_bot.strategy.scanner import ScanResult
from matryoshka_bot.trading.indicators import simple_rsi

# setup, side, stop, take_profit_1, take_profit_2, entry_level, entry_level_order, is_countertrend
SignalTuple = tuple[str, str, float, float, float | None, float, str, bool]


def nearest_entry_levels(price: float, levels: list[float]) -> tuple[float | None, float | None]:
    below = [level for level in levels if level <= price]
    above = [level for level in levels if level >= price]
    support = max(below) if below else None
    resistance = min(above) if above else None
    if support is None and levels:
        support = levels[0]
    if resistance is None and levels:
        resistance = levels[-1]
    return support, resistance


def next_fib_level_beyond(
    entry_grid: list[float], anchor: float, *, search_lower: bool
) -> float | None:
    """Next distinct fib2∪fib3 level beyond `anchor` (strictly below if search_lower else above)."""
    u = sorted(set(entry_grid))
    eps = 1e-9
    if search_lower:
        cands = [x for x in u if x < anchor - eps]
        return max(cands) if cands else None
    cands = [x for x in u if x > anchor + eps]
    return min(cands) if cands else None


def level_order_name(level: float, fib2_levels: list[float], fib3_levels: list[float]) -> str:
    if any(abs(level - value) <= 1e-6 for value in fib2_levels):
        return "fib2"
    if any(abs(level - value) <= 1e-6 for value in fib3_levels):
        return "fib3"
    return "unknown"


def analyze_entry_signals(
    scan: ScanResult,
    candles: list[dict],
    trend_direction: str,
) -> tuple[SignalTuple | None, dict]:
    latest = candles[-1]
    breakout_candle = candles[-2]
    volume_sma20 = sum(c["volume"] for c in candles[-21:-1]) / 20
    rsi = simple_rsi(candles[-15:])
    prev_rsi = simple_rsi(candles[-16:-1])
    entry_grid = sorted(set(scan.fib2_levels + scan.fib3_levels))
    support, resistance = nearest_entry_levels(price=scan.price, levels=entry_grid)

    audits: dict[str, dict] = {}
    diagnostics: dict = {
        "indicators": {
            "rsi_latest_bar": rsi,
            "rsi_prev_bar_window": prev_rsi,
            "volume_sma20_prior": volume_sma20,
            "latest_volume": latest["volume"],
            "volume_ratio_vs_sma20": latest["volume"] / volume_sma20 if volume_sma20 else None,
            "breakout_candle_volume": breakout_candle["volume"],
            "breakout_vol_ratio_vs_sma20": (
                breakout_candle["volume"] / volume_sma20 if volume_sma20 else None
            ),
        },
        "entry_grid": {
            "count_union_fib2_fib3": len(entry_grid),
            "support": support,
            "resistance": resistance,
        },
    }

    if support is None or resistance is None:
        diagnostics["outcome"] = "no_support_resistance_after_nearest_fallback"
        return None, diagnostics

    segment_width = max(resistance - support, 1e-12)
    stop_buffer = 0.1 * segment_width
    support_order = level_order_name(support, scan.fib2_levels, scan.fib3_levels)
    resistance_order = level_order_name(resistance, scan.fib2_levels, scan.fib3_levels)
    diagnostics["entry_grid"]["segment_width"] = segment_width
    diagnostics["entry_grid"]["stop_buffer_0p1_segment"] = stop_buffer
    diagnostics["entry_grid"]["support_order"] = support_order
    diagnostics["entry_grid"]["resistance_order"] = resistance_order

    bl = audit_bounce_long(
        close=latest["close"],
        level=support,
        low=latest["low"],
        volume=latest["volume"],
        volume_sma20=volume_sma20,
        rsi=rsi,
        prev_rsi=prev_rsi,
    )
    audits["bounce_long"] = bl
    bs = audit_bounce_short(
        close=latest["close"],
        level=resistance,
        high=latest["high"],
        volume=latest["volume"],
        volume_sma20=volume_sma20,
        rsi=rsi,
        prev_rsi=prev_rsi,
    )
    audits["bounce_short"] = bs
    bol = audit_breakout_long(
        breakout_close=breakout_candle["close"],
        open_price=breakout_candle["open"],
        high=breakout_candle["high"],
        low=breakout_candle["low"],
        level=resistance,
        breakout_volume=breakout_candle["volume"],
        volume_sma20=volume_sma20,
        next_close=latest["close"],
    )
    audits["breakout_long"] = bol
    bos = audit_breakout_short(
        breakout_close=breakout_candle["close"],
        open_price=breakout_candle["open"],
        high=breakout_candle["high"],
        low=breakout_candle["low"],
        level=support,
        breakout_volume=breakout_candle["volume"],
        volume_sma20=volume_sma20,
        next_close=latest["close"],
    )
    audits["breakout_short"] = bos
    diagnostics["setup_audits"] = audits

    candidates: list[tuple[str, str, float, float, float | None, float, str]] = []

    if bounce_long_confirmed(
        close=latest["close"],
        level=support,
        low=latest["low"],
        volume=latest["volume"],
        volume_sma20=volume_sma20,
        rsi=rsi,
        prev_rsi=prev_rsi,
    ):
        tp2_bl = next_fib_level_beyond(entry_grid, resistance, search_lower=False)
        candidates.append(
            ("bounce", "long", support - stop_buffer, resistance, tp2_bl, support, support_order)
        )
    if breakout_long_confirmed(
        close=breakout_candle["close"],
        open_price=breakout_candle["open"],
        high=breakout_candle["high"],
        low=breakout_candle["low"],
        level=resistance,
        volume=breakout_candle["volume"],
        volume_sma20=volume_sma20,
        next_close=latest["close"],
    ):
        tp1_br_l = resistance + segment_width
        tp2_br_l = next_fib_level_beyond(entry_grid, tp1_br_l, search_lower=False)
        candidates.append(
            (
                "breakout",
                "long",
                support - stop_buffer,
                tp1_br_l,
                tp2_br_l,
                resistance,
                resistance_order,
            )
        )
    if bounce_short_confirmed(
        close=latest["close"],
        level=resistance,
        high=latest["high"],
        volume=latest["volume"],
        volume_sma20=volume_sma20,
        rsi=rsi,
        prev_rsi=prev_rsi,
    ):
        tp2_bs = next_fib_level_beyond(entry_grid, support, search_lower=True)
        candidates.append(
            ("bounce", "short", resistance + stop_buffer, support, tp2_bs, resistance, resistance_order)
        )
    if breakout_short_confirmed(
        close=breakout_candle["close"],
        open_price=breakout_candle["open"],
        high=breakout_candle["high"],
        low=breakout_candle["low"],
        level=support,
        volume=breakout_candle["volume"],
        volume_sma20=volume_sma20,
        next_close=latest["close"],
    ):
        tp1_br_s = support - segment_width
        tp2_br_s = next_fib_level_beyond(entry_grid, tp1_br_s, search_lower=True)
        candidates.append(
            (
                "breakout",
                "short",
                resistance + stop_buffer,
                tp1_br_s,
                tp2_br_s,
                support,
                support_order,
            )
        )

    diagnostics["raw_triggered_candidates"] = [
        {
            "setup": c[0],
            "side": c[1],
            "stop": c[2],
            "take_profit_1": c[3],
            "take_profit_2": c[4],
            "entry_level": c[5],
            "entry_level_order": c[6],
        }
        for c in candidates
    ]

    if not candidates:
        diagnostics["outcome"] = "no_setup_triggered"
        return None, diagnostics

    priority_side = trend_direction if trend_direction in {"long", "short"} else None
    sorted_candidates = sorted(
        candidates,
        key=lambda item: (
            0 if (priority_side is not None and item[1] == priority_side) else 1,
            0 if item[0] == "bounce" else 1,
        ),
    )
    diagnostics["sorting"] = {
        "trend_direction": trend_direction,
        "priority_side_for_sort": priority_side,
        "order_after_sort": [{"setup": c[0], "side": c[1]} for c in sorted_candidates],
    }

    rejections: list[dict] = []
    for setup, side, stop, take_profit_1, take_profit_2, entry_level, entry_level_order in sorted_candidates:
        is_countertrend = trend_direction in {"long", "short"} and side != trend_direction
        if is_countertrend and setup != "breakout":
            rejections.append(
                {
                    "setup": setup,
                    "side": side,
                    "reason": "countertrend_bounce_not_allowed",
                    "is_countertrend": True,
                }
            )
            continue
        chosen: SignalTuple = (
            setup,
            side,
            stop,
            take_profit_1,
            take_profit_2,
            entry_level,
            entry_level_order,
            is_countertrend,
        )
        diagnostics["outcome"] = "signal_selected"
        diagnostics["chosen"] = {
            "setup": setup,
            "side": side,
            "stop": stop,
            "take_profit_1": take_profit_1,
            "take_profit_2": take_profit_2,
            "entry_level": entry_level,
            "entry_level_order": entry_level_order,
            "is_countertrend": is_countertrend,
        }
        diagnostics["candidate_rejections_countertrend_only"] = rejections
        return chosen, diagnostics

    diagnostics["outcome"] = "all_candidates_blocked_countertrend_bounce_rule"
    diagnostics["candidate_rejections_countertrend_only"] = rejections
    return None, diagnostics


def segment_location(price: float, levels: list[float]) -> dict:
    if len(levels) < 2:
        raise ValueError("levels must contain at least two values")
    idx = bisect_right(levels, price)
    if idx <= 0:
        lo, hi = levels[0], levels[1]
        branch = "price_at_or_below_first_level"
    elif idx >= len(levels):
        lo, hi = levels[-2], levels[-1]
        branch = "price_at_or_above_last_level"
    else:
        lo, hi = levels[idx - 1], levels[idx]
        branch = "price_between_sorted_levels"
    width = max(hi - lo, 1e-12)
    rel = (price - lo) / width
    return {
        "segment_low": lo,
        "segment_high": hi,
        "bisect_index_right": idx,
        "branch": branch,
        "relative_position_in_segment_0_to_1": rel,
    }
