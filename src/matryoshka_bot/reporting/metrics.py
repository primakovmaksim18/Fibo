from __future__ import annotations


def compute_metrics(pnls: list[float]) -> dict[str, float]:
    trades = len(pnls)
    wins = sum(1 for x in pnls if x > 0)
    losses = sum(1 for x in pnls if x < 0)
    gross_profit = sum(x for x in pnls if x > 0)
    gross_loss = abs(sum(x for x in pnls if x < 0))
    net_pnl = sum(pnls)
    win_rate = (wins / trades * 100.0) if trades else 0.0
    if gross_loss == 0:
        profit_factor = float("inf") if gross_profit > 0 else 0.0
    else:
        profit_factor = gross_profit / gross_loss

    return {
        "trades": float(trades),
        "wins": float(wins),
        "losses": float(losses),
        "win_rate_pct": win_rate,
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "net_pnl": net_pnl,
        "profit_factor": profit_factor,
    }
