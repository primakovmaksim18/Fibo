from __future__ import annotations


def simple_rsi(candles: list[dict]) -> float:
    closes = [c["close"] for c in candles]
    gains = []
    losses = []
    for i in range(1, len(closes)):
        change = closes[i] - closes[i - 1]
        gains.append(max(change, 0.0))
        losses.append(abs(min(change, 0.0)))
    avg_gain = sum(gains) / max(len(gains), 1)
    avg_loss = sum(losses) / max(len(losses), 1)
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))
