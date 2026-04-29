def choose_depth(daily_range_pct: float) -> int:
    return 4 if daily_range_pct > 10.0 else 5
