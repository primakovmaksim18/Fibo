from __future__ import annotations

from dataclasses import dataclass


FIB_PCTS = (0.0, 23.6, 38.2, 50.0, 61.8, 78.6, 100.0)


@dataclass(frozen=True)
class FibStructure:
    depth: int
    by_order: dict[int, list[float]]

    @property
    def fib1(self) -> list[float]:
        return self.by_order.get(1, [])

    @property
    def fib2(self) -> list[float]:
        return self.by_order.get(2, [])

    @property
    def fib3(self) -> list[float]:
        return self.by_order.get(3, [])

    @property
    def all_levels(self) -> list[float]:
        values: set[float] = set()
        for levels in self.by_order.values():
            values.update(levels)
        return sorted(values)


def _iter_interval_levels(start: float, end: float, fib_pcts: tuple[float, ...]) -> list[float]:
    interval = end - start
    return [round(start + interval * (pct / 100.0), 6) for pct in fib_pcts]


def _sorted_unique(values: list[float]) -> list[float]:
    return sorted(set(values))


def build_levels_by_order(atl: float, ath: float, depth: int) -> dict[int, list[float]]:
    if depth < 1:
        raise ValueError("depth must be >= 1")
    if ath <= atl:
        raise ValueError("ath must be > atl")

    by_order: dict[int, list[float]] = {}
    parent_prices = _sorted_unique(_iter_interval_levels(atl, ath, FIB_PCTS))
    by_order[1] = parent_prices

    for current_order in range(2, depth + 1):
        next_prices: list[float] = []
        for idx in range(1, len(parent_prices)):
            start = parent_prices[idx - 1]
            end = parent_prices[idx]
            if end <= start:
                continue
            next_prices.extend(_iter_interval_levels(start, end, FIB_PCTS))
        parent_prices = _sorted_unique(next_prices)
        by_order[current_order] = parent_prices

    return by_order


def build_fib_structure(atl: float, ath: float, depth: int) -> FibStructure:
    by_order = build_levels_by_order(atl=atl, ath=ath, depth=depth)
    return FibStructure(depth=depth, by_order=by_order)


def build_unique_levels(atl: float, ath: float, depth: int) -> list[float]:
    return build_fib_structure(atl=atl, ath=ath, depth=depth).all_levels
