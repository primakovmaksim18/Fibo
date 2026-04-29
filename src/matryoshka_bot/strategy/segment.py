from bisect import bisect_right


def locate_segment(price: float, levels: list[float]) -> tuple[float, float]:
    if len(levels) < 2:
        raise ValueError("levels must contain at least two values")

    idx = bisect_right(levels, price)
    if idx <= 0:
        return levels[0], levels[1]
    if idx >= len(levels):
        return levels[-2], levels[-1]
    return levels[idx - 1], levels[idx]
