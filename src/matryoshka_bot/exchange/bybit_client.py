from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Any, Callable

from pybit.unified_trading import HTTP

from matryoshka_bot.config.settings import BotSettings


@dataclass(frozen=True)
class InstrumentConstraints:
    qty_step: float
    min_qty: float
    min_notional: float
    tick_size: float


def normalize_order_qty(raw_qty: float, price: float, constraints: InstrumentConstraints) -> float | None:
    if raw_qty <= 0 or price <= 0:
        return None
    if constraints.qty_step <= 0:
        return None

    stepped_qty = math.floor(raw_qty / constraints.qty_step) * constraints.qty_step
    precision = max(0, len(f"{constraints.qty_step:.12f}".rstrip("0").split(".")[-1]))
    stepped_qty = round(stepped_qty, precision)
    if stepped_qty < constraints.min_qty:
        return None
    if stepped_qty * price < constraints.min_notional:
        return None
    return stepped_qty


def normalize_limit_price(raw_price: float, side: str, constraints: InstrumentConstraints) -> float:
    if raw_price <= 0:
        raise ValueError("raw_price must be positive")
    if constraints.tick_size <= 0:
        raise ValueError("tick_size must be positive")
    steps = raw_price / constraints.tick_size
    rounded_steps = math.floor(steps) if side == "Buy" else math.ceil(steps)
    precision = max(0, len(f"{constraints.tick_size:.12f}".rstrip("0").split(".")[-1]))
    return round(rounded_steps * constraints.tick_size, precision)


class BybitClient:
    def __init__(self, settings: BotSettings) -> None:
        api_key = settings.bybit_api_key or None
        api_secret = settings.bybit_api_secret or None
        self._session = HTTP(
            api_key=api_key,
            api_secret=api_secret,
            testnet=False,
        )
        self._market_category = "linear"
        self._constraints_cache: dict[str, InstrumentConstraints] = {}
        self._retry_attempts = max(1, settings.api_retry_attempts)
        self._retry_backoff_ms = max(1, settings.api_retry_backoff_ms)

    def get_last_price(self, symbol: str) -> float:
        result = self._call_with_retry(
            lambda: self._session.get_tickers(category=self._market_category, symbol=symbol)
        )
        last_price = result["result"]["list"][0]["lastPrice"]
        return float(last_price)

    def place_market_order(
        self,
        symbol: str,
        side: str,
        qty: float,
        reduce_only: bool = False,
    ) -> dict:
        return self._call_with_retry(
            lambda: self._session.place_order(
                category="linear",
                symbol=symbol,
                side=side,
                orderType="Market",
                qty=str(qty),
                reduceOnly=reduce_only,
            )
        )

    def place_limit_order(
        self,
        symbol: str,
        side: str,
        qty: float,
        raw_price: float,
        reduce_only: bool = False,
    ) -> dict:
        constraints = self.get_instrument_constraints(symbol)
        price = normalize_limit_price(raw_price=raw_price, side=side, constraints=constraints)
        return self._call_with_retry(
            lambda: self._session.place_order(
                category="linear",
                symbol=symbol,
                side=side,
                orderType="Limit",
                qty=str(qty),
                price=str(price),
                timeInForce="GTC",
                reduceOnly=reduce_only,
            )
        )

    def get_daily_ohlc(self, symbol: str) -> tuple[float, float, float]:
        data = self._call_with_retry(
            lambda: self._session.get_kline(
                category=self._market_category,
                symbol=symbol,
                interval="D",
                limit=1,
            )
        )
        candle = data["result"]["list"][0]
        high = float(candle[2])
        low = float(candle[3])
        close = float(candle[4])
        return high, low, close

    def get_recent_klines(self, symbol: str, interval: str = "15", limit: int = 25) -> list[dict]:
        data = self._call_with_retry(
            lambda: self._session.get_kline(
                category=self._market_category,
                symbol=symbol,
                interval=interval,
                limit=limit,
            )
        )
        rows = []
        for candle in data["result"]["list"]:
            rows.append(
                {
                    "timestamp": int(candle[0]),
                    "open": float(candle[1]),
                    "high": float(candle[2]),
                    "low": float(candle[3]),
                    "close": float(candle[4]),
                    "volume": float(candle[5]),
                }
            )
        rows.sort(key=lambda x: x["timestamp"])
        return rows

    def get_wallet_equity(self, coin: str = "USDT") -> float:
        result = self._call_with_retry(
            lambda: self._session.get_wallet_balance(accountType="UNIFIED", coin=coin)
        )
        coins = result["result"]["list"][0]["coin"]
        for item in coins:
            if item["coin"] == coin:
                return float(item["equity"])
        raise ValueError(f"equity for coin {coin} not found")

    def get_instrument_constraints(self, symbol: str) -> InstrumentConstraints:
        if symbol in self._constraints_cache:
            return self._constraints_cache[symbol]
        result = self._call_with_retry(
            lambda: self._session.get_instruments_info(category="linear", symbol=symbol)
        )
        item = result["result"]["list"][0]
        lot_size = item["lotSizeFilter"]
        price_filter = item["priceFilter"]
        constraints = InstrumentConstraints(
            qty_step=float(lot_size["qtyStep"]),
            min_qty=float(lot_size["minOrderQty"]),
            min_notional=float(lot_size.get("minNotionalValue", "0")),
            tick_size=float(price_filter["tickSize"]),
        )
        self._constraints_cache[symbol] = constraints
        return constraints

    def apply_margin_and_leverage(self, symbol: str, leverage: int, margin_mode: str) -> dict:
        responses: dict[str, dict] = {}
        if margin_mode == "cross":
            if hasattr(self._session, "switch_margin_mode"):
                try:
                    responses["margin_mode"] = self._call_with_retry(
                        lambda: self._session.switch_margin_mode(
                            category="linear",
                            symbol=symbol,
                            tradeMode=0,
                            buyLeverage=str(leverage),
                            sellLeverage=str(leverage),
                        )
                    )
                except Exception as exc:  # noqa: BLE001
                    responses["margin_mode_error"] = {"error": str(exc)}
        responses["leverage"] = self._call_with_retry(
            lambda: self._session.set_leverage(
                category="linear",
                symbol=symbol,
                buyLeverage=str(leverage),
                sellLeverage=str(leverage),
            )
        )
        return responses

    def _call_with_retry(self, fn: Callable[[], Any]) -> Any:
        last_error: Exception | None = None
        for attempt in range(1, self._retry_attempts + 1):
            try:
                return fn()
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                if attempt >= self._retry_attempts or not self._is_retryable_error(exc):
                    raise
                sleep_s = (self._retry_backoff_ms * (2 ** (attempt - 1))) / 1000.0
                time.sleep(sleep_s)
        if last_error is not None:
            raise last_error
        raise RuntimeError("Retry wrapper reached invalid state")

    @staticmethod
    def _is_retryable_error(exc: Exception) -> bool:
        text = str(exc).lower()
        retry_markers = ("429", "500", "502", "503", "504", "timeout", "temporarily", "rate limit")
        return any(marker in text for marker in retry_markers)
