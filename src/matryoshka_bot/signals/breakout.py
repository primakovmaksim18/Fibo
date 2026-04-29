def _body_ratio(open_price: float, close: float, high: float, low: float) -> float:
    candle_range = max(high - low, 1e-12)
    body = abs(close - open_price)
    return body / candle_range


def breakout_long_confirmed(
    close: float,
    open_price: float,
    high: float,
    low: float,
    level: float,
    volume: float,
    volume_sma20: float,
    next_close: float,
) -> bool:
    closed_above = close > level
    body_strong = _body_ratio(open_price, close, high, low) >= 0.6
    volume_ok = volume >= 1.5 * volume_sma20
    hold_ok = next_close >= level
    return closed_above and body_strong and volume_ok and hold_ok


def breakout_short_confirmed(
    close: float,
    open_price: float,
    high: float,
    low: float,
    level: float,
    volume: float,
    volume_sma20: float,
    next_close: float,
) -> bool:
    closed_below = close < level
    body_strong = _body_ratio(open_price, close, high, low) >= 0.6
    volume_ok = volume >= 1.5 * volume_sma20
    hold_ok = next_close <= level
    return closed_below and body_strong and volume_ok and hold_ok
