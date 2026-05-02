from __future__ import annotations

import asyncio
import html
import json
from pathlib import Path

from aiogram import F, Router
from aiogram.types import CallbackQuery, FSInputFile, Message

from matryoshka_bot.config.settings import BotSettings
from matryoshka_bot.exchange.bybit_client import BybitClient
from matryoshka_bot.reporting.level_charts import render_open_position_chart, render_symbol_audit_charts
from matryoshka_bot.trading.preflight import format_preflight_report_text, run_preflight
from matryoshka_bot.trading.runtime_overrides import (
    effective_base_risk_pct,
    load_telegram_trading_state,
    save_telegram_trading_state,
)
from matryoshka_bot.telegram_bot.keyboards import (
    AUDIT_LEVELS_ACTION,
    AUDIT_TF_LABELS,
    AUDIT_TF_PREFIX,
    MENU_MAIN_ACTION,
    MENU_TRADING_ACTION,
    TRADING_PAUSE,
    TRADING_OPEN_POSITIONS,
    TRADING_PREFLIGHT,
    TRADING_RESUME,
    TRADING_RISK_CALLBACK_PREFIX,
    TRADING_STATUS,
    make_assets_keyboard,
    make_main_keyboard,
    make_timeframe_audit_keyboard,
    make_trading_keyboard,
    parse_asset_callback,
    parse_audit_tf_callback,
)

POSITIONS_PATH = Path("state") / "open_positions.json"

_RISK_PRESET_ALLOWED = frozenset({0.25, 0.5, 1.0, 2.0})


def _float_field(row: dict[str, object] | None, *keys: str) -> float | None:
    if not row:
        return None
    for key in keys:
        if key not in row:
            continue
        raw = row[key]
        if raw is None or str(raw).strip() == "":
            continue
        try:
            return float(raw)
        except (TypeError, ValueError):
            continue
    return None


def _load_bot_positions_map() -> dict[str, dict[str, object]]:
    if not POSITIONS_PATH.exists():
        return {}
    try:
        raw = json.loads(POSITIONS_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    out: dict[str, dict[str, object]] = {}
    for row in raw:
        sym = row.get("symbol")
        if isinstance(sym, str) and sym:
            out[sym] = row
    return out


def _format_exchange_position_html(pos: dict[str, object], bot: dict[str, object] | None) -> str:
    sym = html.escape(str(pos.get("symbol", "?")))
    side = html.escape(str(pos.get("side", "?")))
    size = html.escape(str(pos.get("size", "?")))
    entry = _float_field(pos, "avgPrice", "entryPrice")
    mark = _float_field(pos, "markPrice")
    upnl = _float_field(pos, "unrealisedPnl", "unrealizedPnl")
    lev = _float_field(pos, "leverage")
    liq = _float_field(pos, "liqPrice", "liquidationPrice")
    pval = _float_field(pos, "positionValue")
    sl_ex = _float_field(pos, "stopLoss")
    tp_ex = _float_field(pos, "takeProfit")
    lines = [
        f"<b>{sym}</b> {side} size=<code>{size}</code>",
    ]
    if entry is not None:
        lines.append(f"Entry (avg): <code>{entry:.8g}</code>")
    if mark is not None:
        lines.append(f"Mark: <code>{mark:.8g}</code>")
    if pval is not None:
        lines.append(f"Notional: <code>{pval:.6g}</code> USDT")
    if lev is not None:
        lines.append(f"Leverage: <code>{lev:g}</code>x")
    if upnl is not None:
        lines.append(f"uPnL: <code>{upnl:+.6g}</code> USDT")
    if liq is not None:
        lines.append(f"Liq: <code>{liq:.8g}</code>")
    lines.append(f"SL на бирже: <code>{sl_ex:.8g}</code>" if sl_ex is not None else "SL на бирже: —")
    lines.append(f"TP на бирже: <code>{tp_ex:.8g}</code>" if tp_ex is not None else "TP на бирже: —")
    if bot:
        setup = html.escape(str(bot.get("setup", "?")))
        sb = bot.get("stop")
        tb = bot.get("take_profit")
        lines.append(
            f"Бот <code>state</code> — setup <code>{setup}</code>, "
            f"SL <code>{html.escape(str(sb))}</code>, TP <code>{html.escape(str(tb))}</code>"
        )
    return "\n".join(lines)


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
        eff = effective_base_risk_pct(settings, st)
        src = "Telegram override" if st.base_risk_pct_override is not None else ".env"
        risk_line = f"риск на сделку сейчас: <b>{eff:g}%</b> от equity ({src}, при сбросе = {settings.base_risk_pct}% из .env)."
        await query.message.answer(
            f"Торговля: {pause_txt}.\n{risk_line}",
            reply_markup=make_trading_keyboard(),
            parse_mode="HTML",
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

    async def _set_risk_preset(query: CallbackQuery, pct: float) -> None:
        if not await _is_allowed(query.message.chat.id):
            await query.answer("Доступ запрещен", show_alert=True)
            return
        st = load_telegram_trading_state()
        st.base_risk_pct_override = pct
        save_telegram_trading_state(st)
        await query.answer(f"Риск {pct:g}%")
        await query.message.answer(
            f"Риск на новые входы: <b>{pct:g}%</b> от equity (override до «Сброс риска»).",
            parse_mode="HTML",
        )

    @router.callback_query(F.data.startswith(TRADING_RISK_CALLBACK_PREFIX))
    async def on_tr_risk_menu(query: CallbackQuery) -> None:
        if not await _is_allowed(query.message.chat.id):
            await query.answer("Доступ запрещен", show_alert=True)
            return
        tail = (query.data or "").removeprefix(TRADING_RISK_CALLBACK_PREFIX)
        if tail == "reset":
            st = load_telegram_trading_state()
            st.base_risk_pct_override = None
            save_telegram_trading_state(st)
            await query.answer("Сброс")
            await query.message.answer(
                f"Риск снова из .env: <b>{settings.base_risk_pct}%</b>.",
                parse_mode="HTML",
            )
            return
        if tail == "help":
            await query.answer()
            await query.message.answer(
                "<b>Что такое «риск на сделку» (BASE_RISK_PCT / override)</b>\n\n"
                f"Это <b>не</b> «1% депозита в марже на ордер».\n\n"
                f"В коде: сумма в USDT, которую ты готов <b>потерять, если цена дойдёт до стопа</b>: "
                f"<code>risk_usdt = equity × (risk% / 100)</code>.\n"
                f"Размер позиции на бирже в монетах: "
                f"<code>qty = risk_usdt / |entry − stop|</code>.\n\n"
                f"Если стоп узкий — <code>|entry − stop|</code> маленький ⇒ <b>qty и номинал сделки большие</b> ⇒ "
                f"иногда биржа вернёт <code>ErrCode 110007</code> (не хватает <u>available</u> баланса под маржу), "
                f"даже при risk% = 1%.\n\n"
                f"Пресеты ниже уже в процентах от equity как выше.",
                parse_mode="HTML",
            )
            return
        try:
            pct = float(tail.replace(",", "."))
        except ValueError:
            await query.answer("Некорректные данные", show_alert=True)
            return
        if pct not in _RISK_PRESET_ALLOWED:
            await query.answer("Только пресеты с клавиатуры", show_alert=True)
            return
        await _set_risk_preset(query, pct)

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
        er = effective_base_risk_pct(settings, st)
        risk_src = "override в Telegram" if st.base_risk_pct_override is not None else ".env"
        lines = [
            f"Пауза входов: <b>{'да' if st.trading_paused else 'нет'}</b>",
            f"Риск на сделку: <b>{er:g}%</b> от equity (<i>{risk_src}</i>; сброс → {settings.base_risk_pct}% из .env).",
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

    @router.callback_query(F.data == TRADING_OPEN_POSITIONS)
    async def on_open_positions(query: CallbackQuery) -> None:
        if not await _is_allowed(query.message.chat.id):
            await query.answer("Доступ запрещен", show_alert=True)
            return
        if not settings.bybit_api_key or not settings.bybit_api_secret:
            await query.answer("Нет ключей Bybit")
            await query.message.answer("Задай BYBIT_API_KEY и BYBIT_API_SECRET в .env.")
            return
        await query.answer("Позиции + графики...")

        def _fetch() -> tuple[list[dict[str, object]], dict[str, dict[str, object]]]:
            client = BybitClient(settings=settings)
            return client.get_open_linear_positions(), _load_bot_positions_map()

        try:
            positions, bot_map = await asyncio.to_thread(_fetch)
        except Exception as exc:  # noqa: BLE001
            await query.message.answer(
                f"Ошибка Bybit: <code>{html.escape(str(exc))}</code>", parse_mode="HTML"
            )
            return

        acct = "demo" if settings.bybit_demo_trading else "production"
        head = [
            "<b>Открытые позиции</b> (REST Bybit, не кэш бота).",
            f"Счёт: <code>{html.escape(acct)}</code>.",
            "",
        ]
        ex_syms = {str(p.get("symbol")) for p in positions if p.get("symbol")}
        orphan = set(bot_map.keys()) - ex_syms
        if orphan:
            olist = ", ".join(sorted(orphan))
            head.append(
                "⚠️ В <code>open_positions.json</code> остались записи "
                f"без позиции на бирже: <b>{html.escape(olist)}</b> (уже вне рынка или вручную закрыто)."
            )
            head.append("")

        if not positions:
            head.append("Сейчас на Bybit <b>нет</b> открытых контрактов (size = 0 по всем символам).")
            head.append("")
            head.append(
                "Значит бот <i>не в рынке</i>: ждёт сетап по стратегии или пауза в этом меню."
            )
            await query.message.answer("\n".join(head), parse_mode="HTML")
            return

        head.append(f"Позиций на бирже: <b>{len(positions)}</b>. Ниже детали и график H1 по каждой.")
        await query.message.answer("\n".join(head), parse_mode="HTML")

        out_dir = Path("artifacts") / "telegram-position-charts"
        for pos in positions:
            sym = str(pos.get("symbol") or "")
            if not sym:
                continue
            bot_row = bot_map.get(sym)
            detail = _format_exchange_position_html(pos, bot_row)
            await query.message.answer(detail, parse_mode="HTML")

            entry = _float_field(pos, "avgPrice", "entryPrice")
            mark = _float_field(pos, "markPrice")
            if entry is None or entry <= 0:
                entry = mark if mark and mark > 0 else None
            if entry is None:
                await query.message.answer(f"{sym}: нет корректной цены входа — график пропущен.")
                continue

            mark_eff = mark if mark is not None and mark > 0 else entry
            sl_ex = _float_field(pos, "stopLoss")
            tp_ex = _float_field(pos, "takeProfit")
            side = str(pos.get("side") or "Buy")
            upnl = _float_field(pos, "unrealisedPnl", "unrealizedPnl")
            lev = _float_field(pos, "leverage")
            liq = _float_field(pos, "liqPrice", "liquidationPrice")
            stop_bot = _float_field(bot_row, "stop") if bot_row else None
            tp_bot = _float_field(bot_row, "take_profit") if bot_row else None
            out_path = out_dir / f"{sym}_open.jpeg"

            def _render() -> None:
                render_open_position_chart(
                    sym,
                    out_path,
                    position_side=side,
                    entry_price=entry,
                    mark_price=mark_eff,
                    stop_exchange=sl_ex,
                    take_profit_exchange=tp_ex,
                    stop_bot=stop_bot,
                    take_profit_bot=tp_bot,
                    unrealised_pnl=upnl,
                    liq_price=liq,
                    leverage=lev,
                )

            try:
                await asyncio.to_thread(_render)
                cap = (
                    f"{sym} {side} | H1 + matryoshka | "
                    f"uPnL≈{upnl if upnl is not None else '?'} USDT"
                )
                await query.message.answer_photo(
                    photo=FSInputFile(out_path),
                    caption=cap[:1024],
                )
            except Exception as exc:  # noqa: BLE001
                await query.message.answer(
                    f"График {html.escape(sym)}: <code>{html.escape(str(exc))}</code>",
                    parse_mode="HTML",
                )

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
        await query.answer()
        await query.message.answer(
            f"<b>{symbol}</b>: выберите таймфрейм свечного графика (уровни F1/F2/F3 с теми же процентами).\n",
            reply_markup=make_timeframe_audit_keyboard(symbol),
            parse_mode="HTML",
        )

    @router.callback_query(F.data.startswith(AUDIT_TF_PREFIX))
    async def on_audit_timeframe(query: CallbackQuery) -> None:
        if not await _is_allowed(query.message.chat.id):
            await query.answer("Доступ запрещен", show_alert=True)
            return
        parsed = parse_audit_tf_callback(query.data or "")
        if parsed is None:
            await query.answer("Некорректный таймфрейм", show_alert=True)
            return
        symbol, interval = parsed
        tf_label = AUDIT_TF_LABELS.get(interval, interval)
        await query.answer("Готовлю график...")
        out_dir = Path("artifacts") / "telegram-level-charts"
        paths, context = await asyncio.to_thread(
            render_symbol_audit_charts,
            symbol,
            out_dir,
            [(interval, tf_label)],
            140,
        )
        path = paths[0]
        caption = (
            f"{symbol} | {tf_label}\n"
            f"ATL/ATH: {context.atl:.4f}/{context.ath:.4f}\n"
            f"Trend D1/H4: {context.trend_d1}/{context.trend_h4} → {context.trend_direction}\n"
            f"Nearest F2/F3 (от M15 last): {context.nearest_fib2:.4f}/{context.nearest_fib3:.4f}"
        )
        await query.message.answer_photo(
            photo=FSInputFile(path),
            caption=caption,
        )

    return router
