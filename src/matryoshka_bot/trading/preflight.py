from __future__ import annotations

import json

from matryoshka_bot.config.assets import ASSET_BOUNDS
from matryoshka_bot.config.settings import BotSettings
from matryoshka_bot.exchange.bybit_client import BybitClient


def run_preflight(settings: BotSettings) -> dict:
    client = BybitClient(settings=settings)
    report: dict = {
        "api": {"status": "ok"},
        "wallet": {},
        "symbols": {},
    }

    equity = client.get_wallet_equity()
    report["wallet"] = {"equity_usdt": equity}

    for symbol in ASSET_BOUNDS:
        constraints = client.get_instrument_constraints(symbol)
        last_price = client.get_last_price(symbol)
        profile = client.apply_margin_and_leverage(
            symbol=symbol,
            leverage=settings.leverage,
            margin_mode=settings.margin_mode,
        )
        report["symbols"][symbol] = {
            "last_price": last_price,
            "qty_step": constraints.qty_step,
            "min_qty": constraints.min_qty,
            "min_notional": constraints.min_notional,
            "tick_size": constraints.tick_size,
            "margin_leverage_apply": profile,
        }
    return report


def print_preflight_report(report: dict) -> None:
    print(json.dumps(report, indent=2))


def format_preflight_report_text(report: dict, max_len: int = 3800) -> str:
    text = json.dumps(report, indent=2, ensure_ascii=False)
    if len(text) <= max_len:
        return text
    return text[: max_len - 20] + "\n... [truncated]"
