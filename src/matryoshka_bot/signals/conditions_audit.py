from __future__ import annotations

from matryoshka_bot.signals.breakout import _body_ratio
from matryoshka_bot.signals.bounce import bounce_long_confirmed, bounce_short_confirmed
from matryoshka_bot.signals.breakout import breakout_long_confirmed, breakout_short_confirmed


def audit_bounce_long(
    close: float,
    level: float,
    low: float,
    volume: float,
    volume_sma20: float,
    rsi: float,
    prev_rsi: float,
) -> dict:
    touched_support = low <= level
    closed_back_above = close > level
    threshold_vol = 1.3 * volume_sma20
    volume_ok = volume >= threshold_vol
    momentum_ok = rsi > 45 and rsi > prev_rsi
    confirmed = bounce_long_confirmed(
        close=close,
        level=level,
        low=low,
        volume=volume,
        volume_sma20=volume_sma20,
        rsi=rsi,
        prev_rsi=prev_rsi,
    )
    return {
        "setup": "bounce_long",
        "level": level,
        "confirmed": confirmed,
        "checks": {
            "touched_support": {"pass": touched_support, "detail": "low<=level"},
            "closed_back_above": {"pass": closed_back_above, "detail": "close>level"},
            "volume": {
                "pass": volume_ok,
                "volume": volume,
                "threshold_1p3x_sma20": threshold_vol,
                "volume_sma20": volume_sma20,
            },
            "momentum": {"pass": momentum_ok, "rsi": rsi, "prev_rsi": prev_rsi, "detail": "rsi>45 && rsi>prev_rsi"},
        },
    }


def audit_bounce_short(
    close: float,
    level: float,
    high: float,
    volume: float,
    volume_sma20: float,
    rsi: float,
    prev_rsi: float,
) -> dict:
    touched_resistance = high >= level
    closed_back_below = close < level
    threshold_vol = 1.3 * volume_sma20
    volume_ok = volume >= threshold_vol
    momentum_ok = rsi < 55 and rsi < prev_rsi
    confirmed = bounce_short_confirmed(
        close=close,
        level=level,
        high=high,
        volume=volume,
        volume_sma20=volume_sma20,
        rsi=rsi,
        prev_rsi=prev_rsi,
    )
    return {
        "setup": "bounce_short",
        "level": level,
        "confirmed": confirmed,
        "checks": {
            "touched_resistance": {"pass": touched_resistance, "detail": "high>=level"},
            "closed_back_below": {"pass": closed_back_below, "detail": "close<level"},
            "volume": {
                "pass": volume_ok,
                "volume": volume,
                "threshold_1p3x_sma20": threshold_vol,
                "volume_sma20": volume_sma20,
            },
            "momentum": {"pass": momentum_ok, "rsi": rsi, "prev_rsi": prev_rsi, "detail": "rsi<55 && rsi<prev_rsi"},
        },
    }


def audit_breakout_long(
    breakout_close: float,
    open_price: float,
    high: float,
    low: float,
    level: float,
    breakout_volume: float,
    volume_sma20: float,
    next_close: float,
) -> dict:
    closed_above = breakout_close > level
    ratio = _body_ratio(open_price, breakout_close, high, low)
    body_strong = ratio >= 0.6
    threshold_vol = 1.5 * volume_sma20
    volume_ok = breakout_volume >= threshold_vol
    hold_ok = next_close >= level
    confirmed = breakout_long_confirmed(
        close=breakout_close,
        open_price=open_price,
        high=high,
        low=low,
        level=level,
        volume=breakout_volume,
        volume_sma20=volume_sma20,
        next_close=next_close,
    )
    return {
        "setup": "breakout_long",
        "level": level,
        "confirmed": confirmed,
        "checks": {
            "breakout_closed_above_level": {"pass": closed_above},
            "body_ratio_vs_0p6": {
                "pass": body_strong,
                "body_ratio": ratio,
                "open": open_price,
                "close": breakout_close,
                "high": high,
                "low": low,
            },
            "volume": {
                "pass": volume_ok,
                "breakout_volume": breakout_volume,
                "threshold_1p5x_sma20": threshold_vol,
                "volume_sma20": volume_sma20,
            },
            "hold_next_close": {"pass": hold_ok, "next_close": next_close, "detail": "next_close>=level"},
        },
    }


def audit_breakout_short(
    breakout_close: float,
    open_price: float,
    high: float,
    low: float,
    level: float,
    breakout_volume: float,
    volume_sma20: float,
    next_close: float,
) -> dict:
    closed_below = breakout_close < level
    ratio = _body_ratio(open_price, breakout_close, high, low)
    body_strong = ratio >= 0.6
    threshold_vol = 1.5 * volume_sma20
    volume_ok = breakout_volume >= threshold_vol
    hold_ok = next_close <= level
    confirmed = breakout_short_confirmed(
        close=breakout_close,
        open_price=open_price,
        high=high,
        low=low,
        level=level,
        volume=breakout_volume,
        volume_sma20=volume_sma20,
        next_close=next_close,
    )
    return {
        "setup": "breakout_short",
        "level": level,
        "confirmed": confirmed,
        "checks": {
            "breakout_closed_below_level": {"pass": closed_below},
            "body_ratio_vs_0p6": {
                "pass": body_strong,
                "body_ratio": ratio,
                "open": open_price,
                "close": breakout_close,
                "high": high,
                "low": low,
            },
            "volume": {
                "pass": volume_ok,
                "breakout_volume": breakout_volume,
                "threshold_1p5x_sma20": threshold_vol,
                "volume_sma20": volume_sma20,
            },
            "hold_next_close": {"pass": hold_ok, "next_close": next_close, "detail": "next_close<=level"},
        },
    }
