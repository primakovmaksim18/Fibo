from matryoshka_bot.strategy.segment import locate_segment


def context_bias(price: float, segment_low: float, segment_high: float) -> str:
    width = max(segment_high - segment_low, 1e-12)
    x = (price - segment_low) / width
    if x <= 0.35:
        return "long"
    if x >= 0.65:
        return "short"
    return "neutral"


def fib1_trend_bias(price: float, fib1_levels: list[float]) -> str:
    low, high = locate_segment(price=price, levels=fib1_levels)
    return context_bias(price=price, segment_low=low, segment_high=high)


def merge_higher_tf_trend(d1_bias: str, h4_bias: str) -> str:
    if d1_bias == h4_bias and d1_bias in {"long", "short"}:
        return d1_bias
    if d1_bias in {"long", "short"} and h4_bias == "neutral":
        return d1_bias
    if h4_bias in {"long", "short"} and d1_bias == "neutral":
        return h4_bias
    return "neutral"
