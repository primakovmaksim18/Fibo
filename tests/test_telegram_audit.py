from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("aiogram")

from matryoshka_bot.reporting import level_charts
from matryoshka_bot.telegram_bot.keyboards import (
    AUDIT_LEVELS_ACTION,
    ASSET_PREFIX,
    MENU_TRADING_ACTION,
    make_assets_keyboard,
    make_main_keyboard,
    make_trading_keyboard,
    parse_asset_callback,
)


def test_parse_asset_callback_accepts_known_symbol():
    assert parse_asset_callback(f"{ASSET_PREFIX}BTCUSDT") == "BTCUSDT"
    assert parse_asset_callback("asset:UNKNOWN") is None
    assert parse_asset_callback("bad:BTCUSDT") is None


def test_main_keyboard_contains_audit_and_trading_buttons():
    kb = make_main_keyboard()
    row = kb.inline_keyboard[0]
    datas = {btn.callback_data for btn in row}
    assert AUDIT_LEVELS_ACTION in datas
    assert MENU_TRADING_ACTION in datas


def test_trading_keyboard_has_pause_and_preflight():
    kb = make_trading_keyboard()
    flat = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert "tr:pause" in flat
    assert "tr:preflight" in flat


def test_assets_keyboard_contains_symbols():
    kb = make_assets_keyboard()
    flat = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert f"{ASSET_PREFIX}BTCUSDT" in flat
    assert f"{ASSET_PREFIX}ETHUSDT" in flat


def test_render_symbol_audit_charts_smoke(tmp_path, monkeypatch):
    def fake_fetch_ath_atl(symbol: str) -> tuple[float, float]:
        return 100.0, 200.0

    def fake_fetch_klines(symbol: str, interval: str, limit: int) -> list[dict]:
        candles = []
        base = 120.0 if interval in {"15", "60"} else 140.0
        for idx in range(30):
            price = base + idx * 0.2
            candles.append(
                {
                    "timestamp": 1_700_000_000_000 + idx * 60_000,
                    "open": price,
                    "high": price + 1.0,
                    "low": price - 1.0,
                    "close": price + 0.3,
                }
            )
        return candles

    monkeypatch.setattr(level_charts, "fetch_binance_ath_atl", fake_fetch_ath_atl)
    monkeypatch.setattr(level_charts, "fetch_bybit_klines", fake_fetch_klines)

    paths, context = level_charts.render_symbol_audit_charts(
        symbol="BTCUSDT",
        out_dir=Path(tmp_path),
        timeframes=[("15", "M15"), ("60", "H1")],
        limit=30,
    )
    assert len(paths) == 2
    assert all(path.exists() for path in paths)
    assert context.symbol == "BTCUSDT"
