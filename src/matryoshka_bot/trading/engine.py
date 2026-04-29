from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from matryoshka_bot.config.assets import ASSET_BOUNDS
from matryoshka_bot.config.settings import BotSettings
from matryoshka_bot.exchange.bybit_client import BybitClient, normalize_order_qty
from matryoshka_bot.journal.store import JournalStore
from matryoshka_bot.reporting.metrics import compute_metrics
from matryoshka_bot.risk.sizing import calculate_position_size
from matryoshka_bot.signals.bounce import bounce_long_confirmed, bounce_short_confirmed
from matryoshka_bot.signals.breakout import breakout_long_confirmed, breakout_short_confirmed
from matryoshka_bot.strategy.scanner import scan_symbol
from matryoshka_bot.trading.decision import fib1_trend_bias, merge_higher_tf_trend
from matryoshka_bot.trading.runtime_overrides import (
    effective_base_risk_pct,
    load_telegram_trading_state,
)


@dataclass
class OpenPosition:
    symbol: str
    side: str
    qty: float
    entry: float
    stop: float
    take_profit: float
    setup: str


class LiveTradingEngine:
    def __init__(self, settings: BotSettings, state_path: str = "state/open_positions.json") -> None:
        self.settings = settings
        self.client = BybitClient(settings=settings)
        self.journal = JournalStore()
        self.state_path = Path(state_path)
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.positions = self._load_positions()
        self._last_entry_candle_ts: dict[str, int] = {}
        self._configure_symbols()

    def _run_cycle(self) -> None:
        self._check_daily_stop()
        self._sync_exit_logic()
        self._scan_and_trade()
        self._write_state()
        self._write_report_snapshot()

    def run(self, iterations: int = 1, sleep_seconds: int = 15) -> None:
        sleep_seconds = max(sleep_seconds, 1)
        if iterations <= 0:
            self.run_forever(sleep_seconds=sleep_seconds)
            return
        for _ in range(iterations):
            self._run_cycle()
            time.sleep(sleep_seconds)

    def run_forever(self, sleep_seconds: int = 15) -> None:
        sleep_seconds = max(sleep_seconds, 1)
        while True:
            self._run_cycle()
            time.sleep(sleep_seconds)

    def _scan_and_trade(self) -> None:
        placed_symbols_this_cycle: set[str] = set()
        if len(self.positions) >= self.settings.max_open_positions:
            self.journal.log_event({"type": "risk_guard", "message": "max open positions reached"})
            return

        trade_state = load_telegram_trading_state()
        if trade_state.trading_paused:
            self.journal.log_event({"type": "trading_paused", "message": "telegram pause active — skip new entries"})
            return

        base_risk = effective_base_risk_pct(self.settings, trade_state)

        equity = self.client.get_wallet_equity()
        for symbol, bounds in ASSET_BOUNDS.items():
            if any(p.symbol == symbol for p in self.positions):
                continue
            if symbol in placed_symbols_this_cycle:
                continue

            price = self.client.get_last_price(symbol)
            day_high, day_low, day_close = self.client.get_daily_ohlc(symbol)
            scan = scan_symbol(
                symbol=symbol,
                price=price,
                day_high=day_high,
                day_low=day_low,
                day_close=day_close,
                atl=bounds["atl"],
                ath=bounds["ath"],
            )
            candles = self.client.get_recent_klines(symbol=symbol, interval="15", limit=25)
            if len(candles) < 22:
                continue
            current_candle_ts = int(candles[-1]["timestamp"])
            if self._last_entry_candle_ts.get(symbol) == current_candle_ts:
                self.journal.log_event(
                    {
                        "type": "order_skip",
                        "symbol": symbol,
                        "reason": "duplicate_symbol_same_candle_guard",
                        "candle_ts": current_candle_ts,
                    }
                )
                continue

            d1_close = self.client.get_recent_klines(symbol=symbol, interval="D", limit=1)[-1]["close"]
            h4_close = self.client.get_recent_klines(symbol=symbol, interval="240", limit=1)[-1]["close"]
            trend_d1 = fib1_trend_bias(price=d1_close, fib1_levels=scan.fib1_levels)
            trend_h4 = fib1_trend_bias(price=h4_close, fib1_levels=scan.fib1_levels)
            trend_direction = merge_higher_tf_trend(d1_bias=trend_d1, h4_bias=trend_h4)

            signal = self._build_signal(
                symbol=symbol,
                scan=scan,
                candles=candles,
                trend_direction=trend_direction,
            )
            if signal is None:
                continue

            setup, side, stop, take_profit, entry_level, entry_level_order, is_countertrend = signal
            qty = calculate_position_size(
                equity=equity,
                risk_pct=base_risk,
                entry=price,
                stop=stop,
            )
            constraints = self.client.get_instrument_constraints(symbol)
            safe_qty = normalize_order_qty(raw_qty=qty, price=price, constraints=constraints)
            if safe_qty is None:
                self.journal.log_event(
                    {
                        "type": "order_skip",
                        "symbol": symbol,
                        "reason": "qty_or_notional_constraints_not_met",
                        "raw_qty": qty,
                        "price": price,
                    }
                )
                continue
            order_side = "Buy" if side == "long" else "Sell"
            order = self.client.place_market_order(symbol=symbol, side=order_side, qty=safe_qty)
            self.journal.log_signal(
                {
                    "symbol": symbol,
                    "setup": setup,
                    "side": side,
                    "price": price,
                    "segment_low": scan.segment_low,
                    "segment_high": scan.segment_high,
                    "depth": scan.depth,
                    "daily_range_pct": scan.daily_range_pct,
                    "entry_level": entry_level,
                    "entry_level_order": entry_level_order,
                    "trend_tf_d1": trend_d1,
                    "trend_tf_h4": trend_h4,
                    "trend_direction": trend_direction,
                    "is_countertrend": is_countertrend,
                }
            )
            self.positions.append(
                OpenPosition(
                    symbol=symbol,
                    side=side,
                    qty=safe_qty,
                    entry=price,
                    stop=stop,
                    take_profit=take_profit,
                    setup=setup,
                )
            )
            self.journal.log_trade(
                {
                    "event": "open",
                    "symbol": symbol,
                    "setup": setup,
                    "side": side,
                    "qty": safe_qty,
                    "entry": price,
                    "stop": stop,
                    "take_profit": take_profit,
                    "bybit_order": order,
                }
            )
            placed_symbols_this_cycle.add(symbol)
            self._last_entry_candle_ts[symbol] = current_candle_ts

    def _build_signal(
        self,
        symbol: str,
        scan,
        candles: list[dict],
        trend_direction: str,
    ) -> tuple[str, str, float, float, float, str, bool] | None:
        latest = candles[-1]
        breakout_candle = candles[-2]
        volume_sma20 = sum(c["volume"] for c in candles[-21:-1]) / 20
        rsi = self._simple_rsi(candles[-15:])
        prev_rsi = self._simple_rsi(candles[-16:-1])
        entry_grid = sorted(set(scan.fib2_levels + scan.fib3_levels))
        support, resistance = self._nearest_entry_levels(price=scan.price, levels=entry_grid)
        if support is None or resistance is None:
            return None
        segment_width = max(resistance - support, 1e-12)
        stop_buffer = 0.1 * segment_width
        support_order = self._level_order_name(support, scan.fib2_levels, scan.fib3_levels)
        resistance_order = self._level_order_name(resistance, scan.fib2_levels, scan.fib3_levels)

        candidates: list[tuple[str, str, float, float, float, str]] = []

        if bounce_long_confirmed(
            close=latest["close"],
            level=support,
            low=latest["low"],
            volume=latest["volume"],
            volume_sma20=volume_sma20,
            rsi=rsi,
            prev_rsi=prev_rsi,
        ):
            candidates.append(("bounce", "long", support - stop_buffer, resistance, support, support_order))
        if breakout_long_confirmed(
            close=breakout_candle["close"],
            open_price=breakout_candle["open"],
            high=breakout_candle["high"],
            low=breakout_candle["low"],
            level=resistance,
            volume=breakout_candle["volume"],
            volume_sma20=volume_sma20,
            next_close=latest["close"],
        ):
            candidates.append(
                (
                    "breakout",
                    "long",
                    support - stop_buffer,
                    resistance + segment_width,
                    resistance,
                    resistance_order,
                )
            )
        if bounce_short_confirmed(
            close=latest["close"],
            level=resistance,
            high=latest["high"],
            volume=latest["volume"],
            volume_sma20=volume_sma20,
            rsi=rsi,
            prev_rsi=prev_rsi,
        ):
            candidates.append(("bounce", "short", resistance + stop_buffer, support, resistance, resistance_order))
        if breakout_short_confirmed(
            close=breakout_candle["close"],
            open_price=breakout_candle["open"],
            high=breakout_candle["high"],
            low=breakout_candle["low"],
            level=support,
            volume=breakout_candle["volume"],
            volume_sma20=volume_sma20,
            next_close=latest["close"],
        ):
            candidates.append(
                (
                    "breakout",
                    "short",
                    resistance + stop_buffer,
                    support - segment_width,
                    support,
                    support_order,
                )
            )

        if not candidates:
            return None

        priority_side = trend_direction if trend_direction in {"long", "short"} else None
        sorted_candidates = sorted(
            candidates,
            key=lambda item: (
                0 if (priority_side is not None and item[1] == priority_side) else 1,
                0 if item[0] == "bounce" else 1,
            ),
        )

        for setup, side, stop, take_profit, entry_level, entry_level_order in sorted_candidates:
            is_countertrend = trend_direction in {"long", "short"} and side != trend_direction
            if is_countertrend and setup != "breakout":
                continue
            return (setup, side, stop, take_profit, entry_level, entry_level_order, is_countertrend)
        return None

    @staticmethod
    def _nearest_entry_levels(price: float, levels: list[float]) -> tuple[float | None, float | None]:
        below = [level for level in levels if level <= price]
        above = [level for level in levels if level >= price]
        support = max(below) if below else None
        resistance = min(above) if above else None
        if support is None and levels:
            support = levels[0]
        if resistance is None and levels:
            resistance = levels[-1]
        return support, resistance

    @staticmethod
    def _level_order_name(level: float, fib2_levels: list[float], fib3_levels: list[float]) -> str:
        if any(abs(level - value) <= 1e-6 for value in fib2_levels):
            return "fib2"
        if any(abs(level - value) <= 1e-6 for value in fib3_levels):
            return "fib3"
        return "unknown"

    def _sync_exit_logic(self) -> None:
        alive: list[OpenPosition] = []
        for position in self.positions:
            price = self.client.get_last_price(position.symbol)
            exit_reason = None
            if position.side == "long":
                if price <= position.stop:
                    exit_reason = "stop_loss"
                elif price >= position.take_profit:
                    exit_reason = "take_profit"
            else:
                if price >= position.stop:
                    exit_reason = "stop_loss"
                elif price <= position.take_profit:
                    exit_reason = "take_profit"

            if exit_reason is None:
                alive.append(position)
                continue

            close_side = "Sell" if position.side == "long" else "Buy"
            order = self.client.place_market_order(
                symbol=position.symbol,
                side=close_side,
                qty=position.qty,
                reduce_only=True,
            )
            direction = 1 if position.side == "long" else -1
            pnl = (price - position.entry) * position.qty * direction
            self.journal.log_trade(
                {
                    "event": "close",
                    "reason": exit_reason,
                    "symbol": position.symbol,
                    "setup": position.setup,
                    "side": position.side,
                    "qty": position.qty,
                    "entry": position.entry,
                    "exit": price,
                    "pnl": pnl,
                    "bybit_order": order,
                }
            )
        self.positions = alive

    def _check_daily_stop(self) -> None:
        pnls = self.journal.read_trade_pnls()
        if not pnls:
            return
        metrics = compute_metrics(pnls)
        equity = self.client.get_wallet_equity()
        drawdown_pct = (metrics["net_pnl"] / equity) * 100 if equity else 0.0
        if drawdown_pct <= self.settings.daily_stop_pct:
            raise RuntimeError(f"Daily stop reached: {drawdown_pct:.2f}% <= {self.settings.daily_stop_pct:.2f}%")

    def _configure_symbols(self) -> None:
        for symbol in ASSET_BOUNDS:
            try:
                response = self.client.apply_margin_and_leverage(
                    symbol=symbol,
                    leverage=self.settings.leverage,
                    margin_mode=self.settings.margin_mode,
                )
                self.journal.log_event(
                    {
                        "type": "symbol_profile_configured",
                        "symbol": symbol,
                        "margin_mode": self.settings.margin_mode,
                        "leverage": self.settings.leverage,
                        "response": response,
                    }
                )
            except Exception as exc:  # noqa: BLE001
                self.journal.log_event(
                    {
                        "type": "symbol_profile_error",
                        "symbol": symbol,
                        "margin_mode": self.settings.margin_mode,
                        "leverage": self.settings.leverage,
                        "error": str(exc),
                    }
                )

    def _write_report_snapshot(self) -> None:
        pnls = self.journal.read_trade_pnls()
        metrics = compute_metrics(pnls)
        report_path = Path("logs/strategy_report.json")
        report_path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")

    def _load_positions(self) -> list[OpenPosition]:
        if not self.state_path.exists():
            return []
        data = json.loads(self.state_path.read_text(encoding="utf-8"))
        return [OpenPosition(**row) for row in data]

    def _write_state(self) -> None:
        payload = [asdict(position) for position in self.positions]
        self.state_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    @staticmethod
    def _simple_rsi(candles: list[dict]) -> float:
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
