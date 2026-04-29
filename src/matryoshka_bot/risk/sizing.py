def calculate_position_size(
    equity: float,
    risk_pct: float,
    entry: float,
    stop: float,
) -> float:
    if equity <= 0:
        raise ValueError("equity must be positive")
    if risk_pct <= 0:
        raise ValueError("risk_pct must be positive")

    stop_distance = abs(entry - stop)
    if stop_distance == 0:
        raise ValueError("entry and stop cannot be equal")

    risk_amount = equity * (risk_pct / 100.0)
    return round(risk_amount / stop_distance, 8)
