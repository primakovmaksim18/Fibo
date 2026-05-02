from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from matryoshka_bot.config.assets import TRADE_SYMBOLS

ASSETS = TRADE_SYMBOLS

AUDIT_LEVELS_ACTION = "audit_levels"
MENU_TRADING_ACTION = "menu_trading"
MENU_MAIN_ACTION = "menu_main"

ASSET_PREFIX = "asset:"
# audit_tf:<SYMBOL>:<BYBIT_INTERVAL> — только разрешённые интервалы (см. level_charts)
AUDIT_TF_PREFIX = "audit_tf:"
AUDIT_TF_INTERVALS_PUBLIC = frozenset({"30", "60"})
AUDIT_TF_LABELS = {"30": "M30", "60": "H1"}

TRADING_PAUSE = "tr:pause"
TRADING_RESUME = "tr:resume"
TRADING_RISK_CALLBACK_PREFIX = "tr:risk:"
TRADING_RISK_RESET = "tr:risk:reset"
TRADING_RISK_HELP = "tr:risk:help"
TRADING_PREFLIGHT = "tr:preflight"
TRADING_STATUS = "tr:status"
TRADING_OPEN_POSITIONS = "tr:positions"

_TR_PRESETS_ROW1 = ("0.25", "0.5")
_TR_PRESETS_ROW2 = ("1", "2")


def make_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Проверка уровней", callback_data=AUDIT_LEVELS_ACTION),
                InlineKeyboardButton(text="Торговля", callback_data=MENU_TRADING_ACTION),
            ],
        ]
    )


def make_trading_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Пауза входов", callback_data=TRADING_PAUSE),
                InlineKeyboardButton(text="Снять паузу", callback_data=TRADING_RESUME),
            ],
            [
                InlineKeyboardButton(text="Риск 0.25%", callback_data=f"{TRADING_RISK_CALLBACK_PREFIX}{_TR_PRESETS_ROW1[0]}"),
                InlineKeyboardButton(text="Риск 0.5%", callback_data=f"{TRADING_RISK_CALLBACK_PREFIX}{_TR_PRESETS_ROW1[1]}"),
            ],
            [
                InlineKeyboardButton(text="Риск 1%", callback_data=f"{TRADING_RISK_CALLBACK_PREFIX}{_TR_PRESETS_ROW2[0]}"),
                InlineKeyboardButton(text="Риск 2%", callback_data=f"{TRADING_RISK_CALLBACK_PREFIX}{_TR_PRESETS_ROW2[1]}"),
            ],
            [InlineKeyboardButton(text="Сброс риска → из .env", callback_data=TRADING_RISK_RESET)],
            [
                InlineKeyboardButton(
                    text="Что значит «риск на сделку»",
                    callback_data=TRADING_RISK_HELP,
                ),
            ],
            [
                InlineKeyboardButton(text="Preflight Bybit", callback_data=TRADING_PREFLIGHT),
                InlineKeyboardButton(text="Статус", callback_data=TRADING_STATUS),
            ],
            [
                InlineKeyboardButton(
                    text="Открытые позиции (Bybit + график)",
                    callback_data=TRADING_OPEN_POSITIONS,
                ),
            ],
            [InlineKeyboardButton(text="Назад в главное меню", callback_data=MENU_MAIN_ACTION)],
        ]
    )


def audit_tf_callback_data(symbol: str, bybit_interval: str) -> str:
    return f"{AUDIT_TF_PREFIX}{symbol}:{bybit_interval}"


def make_timeframe_audit_keyboard(symbol: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="H1",
                    callback_data=audit_tf_callback_data(symbol, "60"),
                ),
                InlineKeyboardButton(
                    text="M30",
                    callback_data=audit_tf_callback_data(symbol, "30"),
                ),
            ],
            [
                InlineKeyboardButton(text="← К инструментам", callback_data=AUDIT_LEVELS_ACTION),
            ],
            [InlineKeyboardButton(text="« Главное меню", callback_data=MENU_MAIN_ACTION)],
        ]
    )


def make_assets_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=symbol, callback_data=f"{ASSET_PREFIX}{symbol}")]
        for symbol in ASSETS
    ]
    rows.append([InlineKeyboardButton(text="Назад", callback_data=MENU_MAIN_ACTION)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def parse_audit_tf_callback(data: str) -> tuple[str, str] | None:
    if not data.startswith(AUDIT_TF_PREFIX):
        return None
    tail = data.removeprefix(AUDIT_TF_PREFIX)
    if ":" not in tail:
        return None
    symbol, interval = tail.rsplit(":", 1)
    if symbol not in ASSETS:
        return None
    if interval not in AUDIT_TF_INTERVALS_PUBLIC:
        return None
    return symbol, interval


def parse_asset_callback(data: str) -> str | None:
    if not data.startswith(ASSET_PREFIX):
        return None
    symbol = data.removeprefix(ASSET_PREFIX)
    if symbol not in ASSETS:
        return None
    return symbol
