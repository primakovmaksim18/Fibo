from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

ASSETS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")

AUDIT_LEVELS_ACTION = "audit_levels"
MENU_TRADING_ACTION = "menu_trading"
MENU_MAIN_ACTION = "menu_main"

ASSET_PREFIX = "asset:"

TRADING_PAUSE = "tr:pause"
TRADING_RESUME = "tr:resume"
TRADING_RISK_1 = "tr:risk:1"
TRADING_RISK_2 = "tr:risk:2"
TRADING_RISK_RESET = "tr:risk:reset"
TRADING_PREFLIGHT = "tr:preflight"
TRADING_STATUS = "tr:status"


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
                InlineKeyboardButton(text="Риск 1%", callback_data=TRADING_RISK_1),
                InlineKeyboardButton(text="Риск 2%", callback_data=TRADING_RISK_2),
            ],
            [InlineKeyboardButton(text="Сброс риска (.env)", callback_data=TRADING_RISK_RESET)],
            [
                InlineKeyboardButton(text="Preflight Bybit", callback_data=TRADING_PREFLIGHT),
                InlineKeyboardButton(text="Статус", callback_data=TRADING_STATUS),
            ],
            [InlineKeyboardButton(text="Назад в главное меню", callback_data=MENU_MAIN_ACTION)],
        ]
    )


def make_assets_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=symbol, callback_data=f"{ASSET_PREFIX}{symbol}")]
        for symbol in ASSETS
    ]
    rows.append([InlineKeyboardButton(text="Назад", callback_data=MENU_MAIN_ACTION)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def parse_asset_callback(data: str) -> str | None:
    if not data.startswith(ASSET_PREFIX):
        return None
    symbol = data.removeprefix(ASSET_PREFIX)
    if symbol not in ASSETS:
        return None
    return symbol
