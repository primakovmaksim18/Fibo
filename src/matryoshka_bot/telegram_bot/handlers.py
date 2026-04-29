from __future__ import annotations

import asyncio
import html
import json
from pathlib import Path

from aiogram import F, Router
from aiogram.types import CallbackQuery, FSInputFile, InputMediaPhoto, Message

from matryoshka_bot.config.settings import BotSettings
from matryoshka_bot.exchange.bybit_client import BybitClient
from matryoshka_bot.reporting.level_charts import render_symbol_audit_charts
from matryoshka_bot.trading.preflight import format_preflight_report_text, run_preflight
from matryoshka_bot.trading.runtime_overrides import load_telegram_trading_state, save_telegram_trading_state
from matryoshka_bot.telegram_bot.keyboards import (
    AUDIT_LEVELS_ACTION,
    MENU_MAIN_ACTION,
    MENU_TRADING_ACTION,
    TRADING_PAUSE,
    TRADING_PREFLIGHT,
    TRADING_RESUME,
    TRADING_RISK_1,
    TRADING_RISK_2,
    TRADING_RISK_RESET,
    TRADING_STATUS,
    make_assets_keyboard,
    make_main_keyboard,
    make_trading_keyboard,
    parse_asset_callback,
)

POSITIONS_PATH = Path("state") / "open_positions.json"


def build_router(allowed_chat_ids: set[int], settings: BotSettings) -> Router:
    router = Router(name="matryoshka_telegram")

    async def _is_allowed(chat_id: int) -> bool:
        return not allowed_chat_ids or chat_id in allowed_chat_ids

    @router.message(F.text == "/start")
    async def on_start(message: Message) -> None:
        if not await _is_allowed(message.chat.id):
            await message.answer("Доступ запрещен для этого chat_id.")
            return
        await message.answer(
            "Matryoshka: аудит уровней и управление торговлей.\n"
            "Выбери раздел кнопками ниже.",
            reply_markup=make_main_keyboard(),
        )

    @router.callback_query(F.data == MENU_MAIN_ACTION)
    async def on_menu_main(query: CallbackQuery) -> None:
        if not await _is_allowed(query.message.chat.id):
            await query.answer("Доступ запрещен", show_alert=True)
            return
        await query.message.answer("Главное меню:", reply_markup=make_main_keyboard())
        await query.answer()

    @router.callback_query(F.data == MENU_TRADING_ACTION)
    async def on_menu_trading(query: CallbackQuery) -> None:
        if not await _is_allowed(query.message.chat.id):
            await query.answer("Доступ запрещен", show_alert=True)
            return
        st = load_telegram_trading_state()
        pause_txt = "пауза ВКЛ" if st.trading_paused else "пауза выкл"
        risk_txt = f"{st.base_risk_pct_override}%" if st.base_risk_pct_override is not None else "из .env"
        await query.message.answer(
            f"Торговля: {pause_txt}, базовый риск: {risk_txt}.",
            reply_markup=make_trading_keyboard(),
        )
        await query.answer()

    @router.callback_query(F.data == TRADING_PAUSE)
    async def on_trading_pause(query: CallbackQuery) -> None:
        if not await _is_allowed(query.message.chat.id):
            await query.answer("Доступ запрещен", show_alert=True)
            return
        st = load_telegram_trading_state()
        st.trading_paused = True
        save_telegram_trading_state(st)
        await query.answer("Пауза новых входов включена", show_alert=False)
        await query.message.answer("Новые сделки не открываются (выходы по SL/TP продолжают работать).")

    @router.callback_query(F.data == TRADING_RESUME)
    async def on_trading_resume(query: CallbackQuery) -> None:
        if not await _is_allowed(query.message.chat.id):
            await query.answer("Доступ запрещен", show_alert=True)
            return
        st = load_telegram_trading_state()
        st.trading_paused = False
        save_telegram_trading_state(st)
        await query.answer("Пауза снята")
        await query.message.answer("Можно снова открывать сделки по сигналам.")

    @router.callback_query(F.data == TRADING_RISK_1)
    async def on_risk_1(query: CallbackQuery) -> None:
        await _set_risk_preset(query, 1.0)

    @router.callback_query(F.data == TRADING_RISK_2)
    async def on_risk_2(query: CallbackQuery) -> None:
        await _set_risk_preset(query, 2.0)

    async def _set_risk_preset(query: CallbackQuery, pct: float) -> None:
        if not await _is_allowed(query.message.chat.id):
            await query.answer("Доступ запрещен", show_alert=True)
            return
        st = load_telegram_trading_state()
        st.base_risk_pct_override = pct
        save_telegram_trading_state(st)
        await query.answer(f"Базовый риск {pct}%")
        await query.message.answer(
            f"Базовый риск для новых входов: <b>{pct}%</b> (override до сброса).",
            parse_mode="HTML",
        )

    @router.callback_query(F.data == TRADING_RISK_RESET)
    async def on_risk_reset(query: CallbackQuery) -> None:
        if not await _is_allowed(query.message.chat.id):
            await query.answer("Доступ запрещен", show_alert=True)
            return
        st = load_telegram_trading_state()
        st.base_risk_pct_override = None
        save_telegram_trading_state(st)
        await query.answer("Сброс")
        await query.message.answer(
            f"Риск снова из .env: <b>{settings.base_risk_pct}%</b>.",
            parse_mode="HTML",
        )

    @router.callback_query(F.data == TRADING_PREFLIGHT)
    async def on_preflight(query: CallbackQuery) -> None:
        if not await _is_allowed(query.message.chat.id):
            await query.answer("Доступ запрещен", show_alert=True)
            return
        if not settings.bybit_api_key or not settings.bybit_api_secret:
            await query.answer("Нет ключей Bybit в .env")
            await query.message.answer("Задай BYBIT_API_KEY и BYBIT_API_SECRET в .env.")
            return
        await query.answer("Запрос к Bybit...")
        try:
            report = await asyncio.to_thread(run_preflight, settings)
            text = html.escape(format_preflight_report_text(report))
            await query.message.answer(f"<pre>{text}</pre>", parse_mode="HTML")
        except Exception as exc:  # noqa: BLE001
            await query.message.answer(f"Preflight ошибка: `{exc}`")

    @router.callback_query(F.data == TRADING_STATUS)
    async def on_status(query: CallbackQuery) -> None:
        if not await _is_allowed(query.message.chat.id):
            await query.answer("Доступ запрещен", show_alert=True)
            return
        await query.answer("Сбор статуса...")
        st = load_telegram_trading_state()
        lines = [
            f"Пауза входов: <b>{'да' if st.trading_paused else 'нет'}</b>",
            f"Базовый риск: <b>{st.base_risk_pct_override if st.base_risk_pct_override is not None else settings.base_risk_pct}%</b> "
            f"({'override' if st.base_risk_pct_override is not None else '.env'})",
        ]
        if POSITIONS_PATH.exists():
            try:
                raw = json.loads(POSITIONS_PATH.read_text(encoding="utf-8"))
                lines.append(f"Открытых позиций в state: <b>{len(raw)}</b>")
                for row in raw[:10]:
                    sym = row.get("symbol", "?")
                    side = row.get("side", "?")
                    qty = row.get("qty", "?")
                    lines.append(f"- {sym} {side} qty={qty}")
                if len(raw) > 10:
                    lines.append("...")
            except Exception as exc:  # noqa: BLE001
                lines.append(f"Ошибка чтения позиций: {exc}")
        else:
            lines.append("Файл позиций отсутствует.")

        if settings.bybit_api_key and settings.bybit_api_secret:
            try:

                def _equity() -> float:
                    return BybitClient(settings=settings).get_wallet_equity()

                eq = await asyncio.to_thread(_equity)
                lines.insert(1, f"Equity USDT: <b>{eq:.4f}</b>")
            except Exception as exc:  # noqa: BLE001
                lines.append(f"Equity: недоступно ({exc})")
        else:
            lines.append("Ключи Bybit не заданы — equity не запрашивается.")

        await query.message.answer("\n".join(lines), parse_mode="HTML")

    @router.callback_query(F.data == AUDIT_LEVELS_ACTION)
    async def on_audit_levels(query: CallbackQuery) -> None:
        if not await _is_allowed(query.message.chat.id):
            await query.answer("Доступ запрещен", show_alert=True)
            return
        await query.message.answer("Выбери инструмент для аудита уровней:", reply_markup=make_assets_keyboard())
        await query.answer()

    @router.callback_query(F.data.startswith("asset:"))
    async def on_asset_selected(query: CallbackQuery) -> None:
        if not await _is_allowed(query.message.chat.id):
            await query.answer("Доступ запрещен", show_alert=True)
            return
        symbol = parse_asset_callback(query.data or "")
        if symbol is None:
            await query.answer("Некорректный инструмент", show_alert=True)
            return
        await query.answer("Готовлю графики...")

        out_dir = Path("artifacts") / "telegram-level-charts"
        paths, context = await asyncio.to_thread(render_symbol_audit_charts, symbol, out_dir)
        media = []
        for idx, path in enumerate(paths):
            if idx == 0:
                caption = (
                    f"{symbol} level audit\n"
                    f"ATL/ATH: {context.atl:.4f}/{context.ath:.4f}\n"
                    f"Trend D1/H4: {context.trend_d1}/{context.trend_h4} -> {context.trend_direction}\n"
                    f"Nearest F2/F3: {context.nearest_fib2:.4f}/{context.nearest_fib3:.4f}"
                )
            else:
                caption = None
            media.append(InputMediaPhoto(media=FSInputFile(path), caption=caption))

        for i in range(0, len(media), 10):
            await query.message.answer_media_group(media=media[i : i + 10])

    return router
