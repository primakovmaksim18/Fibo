"""Торгуемые USDT perpetual на Bybit linear: порядок важен для UI (Telegram)."""

from __future__ import annotations

# Первые 5 — исходный набор; следующие 5 — крупные по капитализации ликвидные пары (USDT perp).
TRADE_SYMBOLS: tuple[str, ...] = (
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "BNBUSDT",
    "XRPUSDT",
    "DOGEUSDT",
    "ADAUSDT",
    "AVAXUSDT",
    "LINKUSDT",
    "DOTUSDT",
)

# ATL/ATH — статические границы для сетки matryoshka (исторические ориентиры, как у исходных 5).
ASSET_BOUNDS: dict[str, dict[str, float]] = {
    "BTCUSDT": {"atl": 15460.0, "ath": 109000.0},
    "ETHUSDT": {"atl": 880.0, "ath": 4868.0},
    "SOLUSDT": {"atl": 7.85, "ath": 295.6},
    "BNBUSDT": {"atl": 183.0, "ath": 793.0},
    "XRPUSDT": {"atl": 0.114, "ath": 3.4},
    "DOGEUSDT": {"atl": 0.048, "ath": 0.74},
    "ADAUSDT": {"atl": 0.017, "ath": 3.1},
    "AVAXUSDT": {"atl": 8.7, "ath": 146.0},
    "LINKUSDT": {"atl": 0.15, "ath": 53.0},
    "DOTUSDT": {"atl": 2.65, "ath": 55.0},
}

if set(ASSET_BOUNDS.keys()) != set(TRADE_SYMBOLS):
    raise RuntimeError("ASSET_BOUNDS keys must match TRADE_SYMBOLS")
