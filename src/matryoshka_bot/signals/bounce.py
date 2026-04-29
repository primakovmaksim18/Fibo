def bounce_long_confirmed(
    close: float,
    level: float,
    low: float,
    volume: float,
    volume_sma20: float,
    rsi: float,
    prev_rsi: float,
) -> bool:
    touched_support = low <= level
    closed_back_above = close > level
    volume_ok = volume >= 1.3 * volume_sma20
    momentum_ok = rsi > 45 and rsi > prev_rsi
    return touched_support and closed_back_above and volume_ok and momentum_ok


def bounce_short_confirmed(
    close: float,
    level: float,
    high: float,
    volume: float,
    volume_sma20: float,
    rsi: float,
    prev_rsi: float,
) -> bool:
    touched_resistance = high >= level
    closed_back_below = close < level
    volume_ok = volume >= 1.3 * volume_sma20
    momentum_ok = rsi < 55 and rsi < prev_rsi
    return touched_resistance and closed_back_below and volume_ok and momentum_ok
