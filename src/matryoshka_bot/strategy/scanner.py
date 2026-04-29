from __future__ import annotations

from dataclasses import dataclass

from matryoshka_bot.strategy.levels import build_fib_structure
from matryoshka_bot.strategy.regime import choose_depth
from matryoshka_bot.strategy.segment import locate_segment


@dataclass(frozen=True)
class ScanResult:
    symbol: str
    price: float
    depth: int
    segment_low: float
    segment_high: float
    daily_range_pct: float
    fib1_levels: list[float]
    fib2_levels: list[float]
    fib3_levels: list[float]
    all_levels: list[float]


def daily_range_pct(high: float, low: float, close: float) -> float:
    if close <= 0:
        raise ValueError("close must be positive")
    return ((high - low) / close) * 100.0


def scan_symbol(
    symbol: str,
    price: float,
    day_high: float,
    day_low: float,
    day_close: float,
    atl: float,
    ath: float,
) -> ScanResult:
    range_pct = daily_range_pct(high=day_high, low=day_low, close=day_close)
    depth = choose_depth(range_pct)
    fib = build_fib_structure(atl=atl, ath=ath, depth=depth)
    low_level, high_level = locate_segment(price=price, levels=fib.all_levels)
    return ScanResult(
        symbol=symbol,
        price=price,
        depth=depth,
        segment_low=low_level,
        segment_high=high_level,
        daily_range_pct=range_pct,
        fib1_levels=fib.fib1,
        fib2_levels=fib.fib2,
        fib3_levels=fib.fib3,
        all_levels=fib.all_levels,
    )
