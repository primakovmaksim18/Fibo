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
from matryoshka_bot.strategy.scan_snapshot import build_levels_cycle_snapshot
from matryoshka_bot.strategy.scanner import scan_symbol
from matryoshka_bot.trading.decision import fib1_trend_bias, merge_higher_tf_trend
from matryoshka_bot.trading.signal_evaluation import analyze_entry_signals
from matryoshka_bot.telegram_bot.trade_alerts import (
    build_h1_audit_chart,
    extract_order_id,
    format_order_close_html,
    format_order_open_html,
    format_order_skipped_html,
    format_signal_alert_html,
    send_trade_alert_bundle,
)
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
    take_profit_2: float | None = None
    phase: str = "open"


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
        self._log_startup_exchange_positions()

    def _log_startup_exchange_positions(self) -> None:
        """Снимок открытых позиций на бирже vs state после перезапуска (логи не затираются)."""
        try:
            rows = self.client.get_open_linear_positions()
            self.journal.log_event(
                {
                    "type": "startup_exchange_positions",
                    "count": len(rows),
                    "exchange_symbols": [str(r.get("symbol", "")) for r in rows],
                    "local_open_symbols": [p.symbol for p in self.positions],
                }
            )
        except Exception as exc:  # noqa: BLE001
            self.journal.log_event(
                {"type": "startup_exchange_positions_error", "error": str(exc)}
            )

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
            d1_close = self.client.get_recent_klines(symbol=symbol, interval="D", limit=1)[-1]["close"]
            h4_close = self.client.get_recent_klines(symbol=symbol, interval="240", limit=1)[-1]["close"]
            trend_d1 = fib1_trend_bias(price=d1_close, fib1_levels=scan.fib1_levels)
            trend_h4 = fib1_trend_bias(price=h4_close, fib1_levels=scan.fib1_levels)
            trend_direction = merge_higher_tf_trend(d1_bias=trend_d1, h4_bias=trend_h4)
            current_candle_ts = int(candles[-1]["timestamp"]) if candles else 0

            if len(candles) < 22:
                snap = build_levels_cycle_snapshot(
                    symbol=symbol,
                    atl=bounds["atl"],
                    ath=bounds["ath"],
                    price=price,
                    day_high=day_high,
                    day_low=day_low,
                    day_close=day_close,
                    scan=scan,
                    d1_close=d1_close,
                    h4_close=h4_close,
                    trend_d1=trend_d1,
                    trend_h4=trend_h4,
                    trend_direction=trend_direction,
                    candles=candles,
                    current_candle_ts=current_candle_ts,
                    outcome="skipped",
                    skip_reason=f"insufficient_15m_bars_need_22_got_{len(candles)}",
                    bybit_demo_trading=self.settings.bybit_demo_trading,
                )
                snap["signal_analysis"] = {"skipped": True, "reason": "insufficient_bars_before_signal_evaluation"}
                self.journal.log_levels_snapshot(snap)
                continue

            if self._last_entry_candle_ts.get(symbol) == current_candle_ts:
                self.journal.log_event(
                    {
                        "type": "order_skip",
                        "symbol": symbol,
                        "reason": "duplicate_symbol_same_candle_guard",
                        "candle_ts": current_candle_ts,
                    }
                )
                snap = build_levels_cycle_snapshot(
                    symbol=symbol,
                    atl=bounds["atl"],
                    ath=bounds["ath"],
                    price=price,
                    day_high=day_high,
                    day_low=day_low,
                    day_close=day_close,
                    scan=scan,
                    d1_close=d1_close,
                    h4_close=h4_close,
                    trend_d1=trend_d1,
                    trend_h4=trend_h4,
                    trend_direction=trend_direction,
                    candles=candles,
                    current_candle_ts=current_candle_ts,
                    outcome="skipped",
                    skip_reason="duplicate_symbol_same_candle_guard",
                    bybit_demo_trading=self.settings.bybit_demo_trading,
                )
                snap["signal_analysis"] = {"skipped": True, "reason": "duplicate_guard_entry_not_evaluated"}
                self.journal.log_levels_snapshot(snap)
                continue

            signal, diag = analyze_entry_signals(
                scan=scan,
                candles=candles,
                trend_direction=trend_direction,
            )
            if signal is None:
                snap = build_levels_cycle_snapshot(
                    symbol=symbol,
                    atl=bounds["atl"],
                    ath=bounds["ath"],
                    price=price,
                    day_high=day_high,
                    day_low=day_low,
                    day_close=day_close,
                    scan=scan,
                    d1_close=d1_close,
                    h4_close=h4_close,
                    trend_d1=trend_d1,
                    trend_h4=trend_h4,
                    trend_direction=trend_direction,
                    candles=candles,
                    current_candle_ts=current_candle_ts,
                    outcome="no_entry",
                    skip_reason=str(diag.get("outcome", "unknown")),
                    bybit_demo_trading=self.settings.bybit_demo_trading,
                )
                snap["signal_analysis"] = diag
                self.journal.log_levels_snapshot(snap)
                continue

            setup, side, stop, take_profit, take_profit_2, entry_level, entry_level_order, is_countertrend = signal
            try:
                snap_eq, snap_wb, snap_av = self.client.get_usdt_wallet_snapshot()
            except Exception:
                snap_eq, snap_wb, snap_av = equity, 0.0, 0.0
            sig_chart: Path | None = None
            sig_cap = ""
            try:
                sig_chart, sig_cap = build_h1_audit_chart(symbol)
            except Exception as exc:
                self.journal.log_event(
                    {"type": "telegram_alert_chart_error", "symbol": symbol, "phase": "signal", "error": str(exc)}
                )
            send_trade_alert_bundle(
                self.settings,
                html=format_signal_alert_html(
                    symbol=symbol,
                    setup=setup,
                    side=side,
                    price=price,
                    stop=stop,
                    take_profit=take_profit,
                    take_profit_2=take_profit_2,
                    entry_level=entry_level,
                    entry_level_order=entry_level_order,
                    equity=snap_eq,
                    wallet_balance=snap_wb,
                    available_balance=snap_av,
                    base_risk_pct=base_risk,
                    trend_d1=trend_d1,
                    trend_h4=trend_h4,
                    trend_direction=trend_direction,
                    is_countertrend=is_countertrend,
                    bybit_demo=self.settings.bybit_demo_trading,
                    diag=diag,
                ),
                photo_path=sig_chart,
                photo_caption=sig_cap,
            )

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
                snap_qty = build_levels_cycle_snapshot(
                    symbol=symbol,
                    atl=bounds["atl"],
                    ath=bounds["ath"],
                    price=price,
                    day_high=day_high,
                    day_low=day_low,
                    day_close=day_close,
                    scan=scan,
                    d1_close=d1_close,
                    h4_close=h4_close,
                    trend_d1=trend_d1,
                    trend_h4=trend_h4,
                    trend_direction=trend_direction,
                    candles=candles,
                    current_candle_ts=current_candle_ts,
                    outcome="order_skipped",
                    skip_reason="qty_or_notional_constraints_not_met",
                    bybit_demo_trading=self.settings.bybit_demo_trading,
                )
                snap_qty["signal_analysis"] = diag
                snap_qty["sizing_attempt"] = {
                    "equity_usdt_for_sizing": equity,
                    "base_risk_pct_applied": base_risk,
                    "raw_qty_from_risk_model": qty,
                    "normalized_qty": None,
                    "estimated_notional_at_price": qty * price,
                }
                snap_qty["instrument_constraints"] = {
                    "qty_step": constraints.qty_step,
                    "min_qty": constraints.min_qty,
                    "min_notional": constraints.min_notional,
                    "tick_size": constraints.tick_size,
                }
                self.journal.log_levels_snapshot(snap_qty)
                send_trade_alert_bundle(
                    self.settings,
                    html=format_order_skipped_html(
                        symbol=symbol,
                        reason="qty_or_notional_constraints_not_met",
                        equity=equity,
                        raw_qty=qty,
                        price=price,
                        bybit_demo=self.settings.bybit_demo_trading,
                    ),
                    photo_path=None,
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
                    take_profit_2=take_profit_2,
                    phase="open",
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
                    "take_profit_2": take_profit_2,
                    "bybit_order": order,
                }
            )
            snap_ok = build_levels_cycle_snapshot(
                symbol=symbol,
                atl=bounds["atl"],
                ath=bounds["ath"],
                price=price,
                day_high=day_high,
                day_low=day_low,
                day_close=day_close,
                scan=scan,
                d1_close=d1_close,
                h4_close=h4_close,
                trend_d1=trend_d1,
                trend_h4=trend_h4,
                trend_direction=trend_direction,
                candles=candles,
                current_candle_ts=current_candle_ts,
                outcome="order_placed",
                skip_reason=None,
                bybit_demo_trading=self.settings.bybit_demo_trading,
            )
            snap_ok["signal_analysis"] = diag
            snap_ok["sizing_attempt"] = {
                "equity_usdt_for_sizing": equity,
                "base_risk_pct_applied": base_risk,
                "raw_qty_from_risk_model": qty,
                "normalized_qty": safe_qty,
                "estimated_notional_at_price": qty * price,
            }
            snap_ok["instrument_constraints"] = {
                "qty_step": constraints.qty_step,
                "min_qty": constraints.min_qty,
                "min_notional": constraints.min_notional,
                "tick_size": constraints.tick_size,
            }
            snap_ok["execution"] = {
                "order_side": order_side,
                "bybit_place_order_response": order,
                "chosen_stop_take": {
                    "stop": stop,
                    "take_profit_1": take_profit,
                    "take_profit_2": take_profit_2,
                },
                "chosen_setup_side": {"setup": setup, "side": side, "is_countertrend": is_countertrend},
            }
            self.journal.log_levels_snapshot(snap_ok)

            try:
                open_eq, open_wb, open_av = self.client.get_usdt_wallet_snapshot()
            except Exception:
                open_eq, open_wb, open_av = equity, 0.0, 0.0
            open_chart: Path | None = None
            open_cap = ""
            try:
                open_chart, open_cap = build_h1_audit_chart(symbol)
            except Exception as exc:
                self.journal.log_event(
                    {"type": "telegram_alert_chart_error", "symbol": symbol, "phase": "open", "error": str(exc)}
                )
            send_trade_alert_bundle(
                self.settings,
                html=format_order_open_html(
                    symbol=symbol,
                    setup=setup,
                    side=side,
                    order_side=order_side,
                    qty=safe_qty,
                    entry=price,
                    stop=stop,
                    take_profit=take_profit,
                    take_profit_2=take_profit_2,
                    equity=open_eq,
                    wallet_balance=open_wb,
                    available_balance=open_av,
                    base_risk_pct=base_risk,
                    order_id=extract_order_id(order),
                    bybit_demo=self.settings.bybit_demo_trading,
                ),
                photo_path=open_chart,
                photo_caption=open_cap,
            )

            placed_symbols_this_cycle.add(symbol)
            self._last_entry_candle_ts[symbol] = current_candle_ts

    def _breakeven_stop_price(self, position: OpenPosition) -> float:
        c = self.client.get_instrument_constraints(position.symbol)
        bps = max(0.0, self.settings.breakeven_offset_bps)
        pct_off = position.entry * (bps / 10000.0)
        tick_off = 2.0 * c.tick_size
        offset = max(pct_off, tick_off)
        if position.side == "long":
            return position.entry - offset
        return position.entry + offset

    def _split_qty_partial(self, total: float, price: float, symbol: str) -> tuple[float | None, float | None]:
        c = self.client.get_instrument_constraints(symbol)
        frac = max(0.0, min(1.0, self.settings.partial_tp_fraction))
        if frac <= 0 or frac >= 1 or total <= 0:
            return None, None
        raw_first = total * frac
        first = normalize_order_qty(raw_first, price, c)
        if first is None or first <= 0 or first >= total:
            return None, None
        rest = total - first
        rest_n = normalize_order_qty(rest, price, c)
        if rest_n is None or rest_n <= 0:
            return None, None
        return first, rest_n

    def _close_market_notify(
        self,
        position: OpenPosition,
        price: float,
        qty: float,
        exit_reason: str,
    ) -> None:
        close_side = "Sell" if position.side == "long" else "Buy"
        order = self.client.place_market_order(
            symbol=position.symbol,
            side=close_side,
            qty=qty,
            reduce_only=True,
        )
        direction = 1 if position.side == "long" else -1
        pnl = (price - position.entry) * qty * direction
        self.journal.log_trade(
            {
                "event": "close",
                "reason": exit_reason,
                "symbol": position.symbol,
                "setup": position.setup,
                "side": position.side,
                "qty": qty,
                "entry": position.entry,
                "exit": price,
                "pnl": pnl,
                "bybit_order": order,
            }
        )
        try:
            cls_eq, cls_wb, cls_av = self.client.get_usdt_wallet_snapshot()
        except Exception:
            cls_eq, cls_wb, cls_av = 0.0, 0.0, 0.0
        cls_chart: Path | None = None
        cls_cap = ""
        try:
            cls_chart, cls_cap = build_h1_audit_chart(position.symbol)
        except Exception as exc:
            self.journal.log_event(
                {
                    "type": "telegram_alert_chart_error",
                    "symbol": position.symbol,
                    "phase": "close",
                    "error": str(exc),
                }
            )
        send_trade_alert_bundle(
            self.settings,
            html=format_order_close_html(
                symbol=position.symbol,
                setup=position.setup,
                side=position.side,
                reason=exit_reason,
                qty=qty,
                entry=position.entry,
                exit_price=price,
                pnl=pnl,
                equity=cls_eq,
                wallet_balance=cls_wb,
                available_balance=cls_av,
                order_id=extract_order_id(order),
                bybit_demo=self.settings.bybit_demo_trading,
            ),
            photo_path=cls_chart,
            photo_caption=cls_cap,
        )

    def _sync_exit_logic(self) -> None:
        alive: list[OpenPosition] = []
        for position in self.positions:
            price = self.client.get_last_price(position.symbol)
            tp1 = position.take_profit
            tp2 = position.take_profit_2

            if tp2 is None:
                exit_reason = None
                if position.side == "long":
                    if price <= position.stop:
                        exit_reason = "stop_loss"
                    elif price >= tp1:
                        exit_reason = "take_profit"
                else:
                    if price >= position.stop:
                        exit_reason = "stop_loss"
                    elif price <= tp1:
                        exit_reason = "take_profit"

                if exit_reason is None:
                    alive.append(position)
                else:
                    self._close_market_notify(position, price, position.qty, exit_reason)
                continue

            phase = position.phase
            if phase == "open":
                if position.side == "long":
                    if price <= position.stop:
                        self._close_market_notify(position, price, position.qty, "stop_loss")
                        continue
                    if price >= tp1:
                        first, rest = self._split_qty_partial(position.qty, price, position.symbol)
                        if first is None:
                            self._close_market_notify(position, price, position.qty, "take_profit_1_full")
                            continue
                        po = self.client.place_market_order(
                            symbol=position.symbol,
                            side="Sell",
                            qty=first,
                            reduce_only=True,
                        )
                        pnl_p = (price - position.entry) * first
                        self.journal.log_trade(
                            {
                                "event": "partial_tp",
                                "reason": "take_profit_1",
                                "symbol": position.symbol,
                                "setup": position.setup,
                                "side": position.side,
                                "qty": first,
                                "qty_remaining": rest,
                                "entry": position.entry,
                                "exit": price,
                                "pnl": pnl_p,
                                "bybit_order": po,
                            }
                        )
                        position.qty = rest
                        position.stop = self._breakeven_stop_price(position)
                        position.phase = "after_partial"
                        if price >= tp2:
                            self._close_market_notify(position, price, position.qty, "take_profit_2")
                            continue
                        alive.append(position)
                        continue
                else:
                    if price >= position.stop:
                        self._close_market_notify(position, price, position.qty, "stop_loss")
                        continue
                    if price <= tp1:
                        first, rest = self._split_qty_partial(position.qty, price, position.symbol)
                        if first is None:
                            self._close_market_notify(position, price, position.qty, "take_profit_1_full")
                            continue
                        po = self.client.place_market_order(
                            symbol=position.symbol,
                            side="Buy",
                            qty=first,
                            reduce_only=True,
                        )
                        pnl_p = (position.entry - price) * first
                        self.journal.log_trade(
                            {
                                "event": "partial_tp",
                                "reason": "take_profit_1",
                                "symbol": position.symbol,
                                "setup": position.setup,
                                "side": position.side,
                                "qty": first,
                                "qty_remaining": rest,
                                "entry": position.entry,
                                "exit": price,
                                "pnl": pnl_p,
                                "bybit_order": po,
                            }
                        )
                        position.qty = rest
                        position.stop = self._breakeven_stop_price(position)
                        position.phase = "after_partial"
                        if price <= tp2:
                            self._close_market_notify(position, price, position.qty, "take_profit_2")
                            continue
                        alive.append(position)
                        continue

                alive.append(position)
                continue

            if phase == "after_partial":
                if position.side == "long":
                    if price <= position.stop:
                        self._close_market_notify(position, price, position.qty, "breakeven_or_stop")
                        continue
                    if price >= tp2:
                        self._close_market_notify(position, price, position.qty, "take_profit_2")
                        continue
                else:
                    if price >= position.stop:
                        self._close_market_notify(position, price, position.qty, "breakeven_or_stop")
                        continue
                    if price <= tp2:
                        self._close_market_notify(position, price, position.qty, "take_profit_2")
                        continue

            alive.append(position)

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
        rows: list[OpenPosition] = []
        for row in data:
            row.setdefault("take_profit_2", None)
            row.setdefault("phase", "open")
            rows.append(OpenPosition(**row))
        return rows

    def _write_state(self) -> None:
        payload = [asdict(position) for position in self.positions]
        self.state_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
