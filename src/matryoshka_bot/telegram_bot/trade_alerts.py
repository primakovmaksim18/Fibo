from __future__ import annotations

import asyncio
import html
import json
import logging
import time
from pathlib import Path
from typing import Any

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import FSInputFile

from matryoshka_bot.config.settings import BotSettings
from matryoshka_bot.reporting.level_charts import render_symbol_audit_charts

_LOGGER = logging.getLogger(__name__)

_ALERTS_DIR = Path("artifacts") / "trade-alerts"


def trade_alerts_enabled(settings: BotSettings) -> bool:
    if not settings.telegram_trade_alerts:
        return False
    if not (settings.telegram_bot_token or "").strip():
        return False
    if not settings.telegram_allowed_chat_ids:
        return False
    return True


def _truncate(text: str, max_len: int = 3800) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


async def _send_html_and_optional_photo(
    settings: BotSettings,
    html_text: str,
    photo_path: Path | None,
    photo_caption: str,
) -> None:
    bot = Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    try:
        for cid in settings.telegram_allowed_chat_ids:
            await bot.send_message(chat_id=cid, text=_truncate(html_text))
            if photo_path is not None and photo_path.exists():
                cap = photo_caption[:1024] if photo_caption else ""
                await bot.send_photo(
                    chat_id=cid,
                    photo=FSInputFile(photo_path),
                    caption=cap,
                )
    finally:
        await bot.session.close()


def send_trade_alert_bundle(
    settings: BotSettings,
    *,
    html: str,
    photo_path: Path | None = None,
    photo_caption: str = "",
) -> None:
    if not trade_alerts_enabled(settings):
        return
    try:
        asyncio.run(
            _send_html_and_optional_photo(
                settings,
                html,
                photo_path,
                photo_caption,
            )
        )
    except RuntimeError as exc:
        if "asyncio.run() cannot be called from a running event loop" in str(exc):
            _LOGGER.warning("Telegram alert skipped: already inside asyncio loop (%s)", exc)
            return
        _LOGGER.exception("Telegram trade alert failed")
    except Exception:
        _LOGGER.exception("Telegram trade alert failed")


def build_h1_audit_chart(symbol: str) -> tuple[Path, str]:
    _ALERTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = int(time.time() * 1000)
    out_dir = _ALERTS_DIR / f"{stamp}_{symbol}"
    paths, ctx = render_symbol_audit_charts(
        symbol,
        out_dir,
        timeframes=[("60", "H1")],
        limit=140,
    )
    path = paths[0]
    cap = (
        f"{symbol} H1 | тренд D1/H4: {ctx.trend_d1}/{ctx.trend_h4} → {ctx.trend_direction} | "
        f"ATL/ATH {ctx.atl:.4f}/{ctx.ath:.4f}"
    )
    return path, cap


def format_signal_alert_html(
    *,
    symbol: str,
    setup: str,
    side: str,
    price: float,
    stop: float,
    take_profit: float,
    take_profit_2: float | None,
    entry_level: float,
    entry_level_order: str,
    equity: float,
    wallet_balance: float,
    available_balance: float,
    base_risk_pct: float,
    trend_d1: str,
    trend_h4: str,
    trend_direction: str,
    is_countertrend: bool,
    bybit_demo: bool,
    diag: dict[str, Any],
) -> str:
    mode = "demo" if bybit_demo else "production"
    diag_txt = html.escape(json.dumps(diag, ensure_ascii=False, default=str)[:3500])
    return (
        "<b>Сигнал обнаружен</b> (до отправки ордера)\n"
        f"Счёт: <code>{html.escape(mode)}</code>\n"
        f"<b>{html.escape(symbol)}</b> | setup <code>{html.escape(setup)}</code> | "
        f"сторона <code>{html.escape(side)}</code>\n"
        f"Цена (last): <code>{price:.8g}</code> | уровень входа: <code>{entry_level:.8g}</code> "
        f"(<code>{html.escape(entry_level_order)}</code>)\n"
        f"Стоп: <code>{stop:.8g}</code> | TP1: <code>{take_profit:.8g}</code>"
        + (
            f" | TP2: <code>{take_profit_2:.8g}</code>\n"
            if take_profit_2 is not None
            else "\n"
        )
        + f"Тренд D1/H4/merge: <code>{html.escape(trend_d1)}</code> / "
        f"<code>{html.escape(trend_h4)}</code> / <code>{html.escape(trend_direction)}</code>\n"
        f"Контртренд: <code>{is_countertrend}</code>\n"
        f"Риск на сделку: <code>{base_risk_pct:g}%</code> от equity\n"
        f"Equity USDT: <code>{equity:.6g}</code>\n"
        f"Wallet USDT: <code>{wallet_balance:.6g}</code> | доступно≈ <code>{available_balance:.6g}</code>\n\n"
        f"<pre>{diag_txt}</pre>"
    )


def format_order_open_html(
    *,
    symbol: str,
    setup: str,
    side: str,
    order_side: str,
    qty: float,
    entry: float,
    stop: float,
    take_profit: float,
    take_profit_2: float | None,
    equity: float,
    wallet_balance: float,
    available_balance: float,
    base_risk_pct: float,
    order_id: str | None,
    bybit_demo: bool,
) -> str:
    mode = "demo" if bybit_demo else "production"
    oid = html.escape(order_id) if order_id else "—"
    return (
        "<b>Ордер открыт</b> (market)\n"
        f"Счёт: <code>{html.escape(mode)}</code>\n"
        f"<b>{html.escape(symbol)}</b> | <code>{html.escape(setup)}</code> | "
        f"<code>{html.escape(side)}</code> → биржа <code>{html.escape(order_side)}</code>\n"
        f"Qty: <code>{qty:.8g}</code> | цена входа (оценка): <code>{entry:.8g}</code>\n"
        f"SL <code>{stop:.8g}</code> | TP1 <code>{take_profit:.8g}</code>"
        + (
            f" | TP2 <code>{take_profit_2:.8g}</code> (остаток после части на TP1 → BE)\n"
            if take_profit_2 is not None
            else "\n"
        )
        + f"Риск: <code>{base_risk_pct:g}%</code> equity\n"
        f"Equity USDT: <code>{equity:.6g}</code>\n"
        f"Wallet USDT: <code>{wallet_balance:.6g}</code> | доступно≈ <code>{available_balance:.6g}</code>\n"
        f"OrderId: <code>{oid}</code>"
    )


def format_order_close_html(
    *,
    symbol: str,
    setup: str,
    side: str,
    reason: str,
    qty: float,
    entry: float,
    exit_price: float,
    pnl: float,
    equity: float,
    wallet_balance: float,
    available_balance: float,
    order_id: str | None,
    bybit_demo: bool,
) -> str:
    mode = "demo" if bybit_demo else "production"
    oid = html.escape(order_id) if order_id else "—"
    return (
        "<b>Позиция закрыта</b> (market reduce-only)\n"
        f"Счёт: <code>{html.escape(mode)}</code>\n"
        f"<b>{html.escape(symbol)}</b> | <code>{html.escape(setup)}</code> | "
        f"<code>{html.escape(side)}</code>\n"
        f"Причина: <code>{html.escape(reason)}</code>\n"
        f"Qty: <code>{qty:.8g}</code> | entry <code>{entry:.8g}</code> | выход <code>{exit_price:.8g}</code>\n"
        f"PnL (оценка): <code>{pnl:+.6g}</code> USDT\n"
        f"Equity USDT: <code>{equity:.6g}</code>\n"
        f"Wallet USDT: <code>{wallet_balance:.6g}</code> | доступно≈ <code>{available_balance:.6g}</code>\n"
        f"OrderId: <code>{oid}</code>"
    )


def format_order_skipped_html(
    *,
    symbol: str,
    reason: str,
    equity: float,
    raw_qty: float,
    price: float,
    bybit_demo: bool,
) -> str:
    mode = "demo" if bybit_demo else "production"
    return (
        "<b>Вход отменён</b> (сигнал был, ордер не отправлен)\n"
        f"Счёт: <code>{html.escape(mode)}</code> | <b>{html.escape(symbol)}</b>\n"
        f"Причина: <code>{html.escape(reason)}</code>\n"
        f"Equity: <code>{equity:.6g}</code> | raw qty: <code>{raw_qty:.8g}</code> | цена: <code>{price:.8g}</code>"
    )


def extract_order_id(order_response: dict[str, Any]) -> str | None:
    try:
        res = order_response.get("result") or {}
        oid = res.get("orderId") or res.get("order_id")
        if oid:
            return str(oid)
    except (TypeError, AttributeError):
        pass
    return None
