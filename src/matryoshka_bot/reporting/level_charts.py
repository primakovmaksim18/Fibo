from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

from matryoshka_bot.strategy.levels import FIB_PCTS
from matryoshka_bot.trading.decision import fib1_trend_bias, merge_higher_tf_trend

BYBIT_KLINES_URL = "https://api.bybit.com/v5/market/kline"
BINANCE_KLINES_URL = "https://api.binance.com/api/v3/klines"
DEFAULT_TIMEFRAMES = [
    ("M", "M"),
    ("60", "H"),
    ("D", "D"),
    ("240", "H4"),
    ("60", "H1"),
    ("15", "M15"),
]


@dataclass(frozen=True)
class AuditContext:
    symbol: str
    atl: float
    ath: float
    trend_d1: str
    trend_h4: str
    trend_direction: str
    nearest_fib2: float
    nearest_fib3: float


def fetch_bybit_klines(symbol: str, interval: str, limit: int) -> list[dict]:
    query = urllib.parse.urlencode(
        {
            "category": "linear",
            "symbol": symbol,
            "interval": interval,
            "limit": str(limit),
        }
    )
    with urllib.request.urlopen(f"{BYBIT_KLINES_URL}?{query}", timeout=20) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    rows: list[dict] = []
    for candle in payload["result"]["list"]:
        rows.append(
            {
                "timestamp": int(candle[0]),
                "open": float(candle[1]),
                "high": float(candle[2]),
                "low": float(candle[3]),
                "close": float(candle[4]),
            }
        )
    rows.sort(key=lambda x: x["timestamp"])
    return rows


def fetch_binance_ath_atl(symbol: str) -> tuple[float, float]:
    start_ms = 1502942400000
    limit = 1000
    all_rows: list[list] = []
    while True:
        query = urllib.parse.urlencode(
            {"symbol": symbol, "interval": "1d", "startTime": str(start_ms), "limit": str(limit)}
        )
        with urllib.request.urlopen(f"{BINANCE_KLINES_URL}?{query}", timeout=30) as resp:
            rows = json.loads(resp.read().decode("utf-8"))
        if not rows:
            break
        all_rows.extend(rows)
        if len(rows) < limit:
            break
        start_ms = int(rows[-1][0]) + 24 * 60 * 60 * 1000

    atl = min(float(row[3]) for row in all_rows)
    ath = max(float(row[2]) for row in all_rows)
    return atl, ath


def build_level_orders(atl: float, ath: float) -> tuple[list[float], list[float], list[float]]:
    def interval_levels(start: float, end: float) -> list[float]:
        span = end - start
        return [round(start + span * (pct / 100.0), 6) for pct in FIB_PCTS]

    fib1 = sorted(set(interval_levels(atl, ath)))
    fib2_raw: list[float] = []
    for i in range(1, len(fib1)):
        fib2_raw.extend(interval_levels(fib1[i - 1], fib1[i]))
    fib2 = sorted(set(fib2_raw))

    fib3_raw: list[float] = []
    for i in range(1, len(fib2)):
        fib3_raw.extend(interval_levels(fib2[i - 1], fib2[i]))
    fib3 = sorted(set(fib3_raw))
    return fib1, fib2, fib3


def _timestamp_to_text(ms: int) -> str:
    dt = datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M UTC")


def _draw_candles(ax: plt.Axes, candles: list[dict]) -> None:
    width = 0.6
    for idx, c in enumerate(candles):
        color = "#1f9d55" if c["close"] >= c["open"] else "#e63946"
        ax.vlines(idx, c["low"], c["high"], color=color, linewidth=0.8, alpha=0.9, zorder=2)
        body_low = min(c["open"], c["close"])
        body_high = max(c["open"], c["close"])
        height = max(body_high - body_low, 1e-12)
        ax.add_patch(
            Rectangle(
                (idx - width / 2, body_low),
                width,
                height,
                facecolor=color,
                edgecolor=color,
                alpha=0.85,
                zorder=3,
            )
        )


def _label_group(ax: plt.Axes, levels: list[float], y_min: float, y_max: float, label: str, color: str) -> None:
    visible = [lv for lv in levels if y_min <= lv <= y_max]
    step = max(1, len(visible) // 8)
    for idx, lv in enumerate(visible):
        if idx % step != 0:
            continue
        ax.text(
            0.2,
            lv,
            f"{label} {lv:.2f}",
            color=color,
            fontsize=7,
            va="center",
            ha="left",
            zorder=7,
            bbox={"facecolor": "white", "alpha": 0.55, "edgecolor": "none", "pad": 1.1},
        )


def render_symbol_timeframe_chart(
    symbol: str,
    tf_label: str,
    candles: list[dict],
    fib1: list[float],
    fib2: list[float],
    fib3: list[float],
    out_path: Path,
) -> None:
    fig, ax = plt.subplots(figsize=(16, 9), dpi=120)
    _draw_candles(ax, candles)

    lows = [c["low"] for c in candles]
    highs = [c["high"] for c in candles]
    min_y = min(lows)
    max_y = max(highs)
    pad = (max_y - min_y) * 0.06 if max_y > min_y else max_y * 0.06
    y_min = min_y - pad
    y_max = max_y + pad

    visible_fib1 = [lv for lv in fib1 if y_min <= lv <= y_max]
    visible_fib2 = [lv for lv in fib2 if y_min <= lv <= y_max]
    visible_fib3 = [lv for lv in fib3 if y_min <= lv <= y_max]
    latest_close = candles[-1]["close"]

    for lv in visible_fib3:
        ax.axhline(y=lv, color="#2ca02c", linewidth=0.45, alpha=0.45, zorder=1)
    for lv in visible_fib2:
        ax.axhline(y=lv, color="#1f77b4", linewidth=0.75, alpha=0.65, zorder=2)
    for lv in visible_fib1:
        ax.axhline(y=lv, color="#d62728", linewidth=1.2, alpha=0.9, zorder=4)

    nearest_fib2 = min(fib2, key=lambda lv: abs(lv - latest_close))
    nearest_fib3 = min(fib3, key=lambda lv: abs(lv - latest_close))
    if y_min <= nearest_fib2 <= y_max:
        ax.axhline(y=nearest_fib2, color="#1f77b4", linewidth=1.6, alpha=1.0, zorder=5)
    if y_min <= nearest_fib3 <= y_max:
        ax.axhline(y=nearest_fib3, color="#2ca02c", linewidth=1.6, alpha=1.0, zorder=5)

    for pct in FIB_PCTS:
        lv = round(fib1[0] + (fib1[-1] - fib1[0]) * (pct / 100.0), 6)
        if y_min <= lv <= y_max:
            ax.text(
                len(candles) - 0.2,
                lv,
                f"F1 {pct:g}% {lv:.2f}",
                color="#d62728",
                fontsize=8,
                va="center",
                ha="left",
                zorder=6,
                bbox={"facecolor": "white", "alpha": 0.6, "edgecolor": "none", "pad": 1.2},
            )

    _label_group(ax=ax, levels=fib2, y_min=y_min, y_max=y_max, label="F2", color="#1f77b4")
    _label_group(ax=ax, levels=fib3, y_min=y_min, y_max=y_max, label="F3", color="#2ca02c")

    trend = fib1_trend_bias(price=latest_close, fib1_levels=fib1)
    first_ts = _timestamp_to_text(candles[0]["timestamp"])
    last_ts = _timestamp_to_text(candles[-1]["timestamp"])
    ax.set_title(
        f"{symbol} | TF={tf_label} | trend(F1)={trend} | F1={len(visible_fib1)} F2={len(visible_fib2)} F3={len(visible_fib3)}\n"
        f"{first_ts} → {last_ts}\n"
        "Легенда: F1 красный (подписи %), F2 синий, F3 зелёный; bold — ближайшие F2/F3 к last close."
    )
    ax.set_xlim(-1, len(candles))
    ax.set_ylim(y_min, y_max)
    ax.set_xlabel("Candle index")
    ax.set_ylabel("Price")
    ax.grid(alpha=0.2, linestyle="--")
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, format="jpeg")
    plt.close(fig)


def render_open_position_chart(
    symbol: str,
    out_path: Path,
    *,
    position_side: str,
    entry_price: float,
    mark_price: float,
    stop_exchange: float | None,
    take_profit_exchange: float | None,
    stop_bot: float | None,
    take_profit_bot: float | None,
    unrealised_pnl: float | None,
    liq_price: float | None,
    leverage: float | None,
    interval: str = "60",
    tf_label: str = "H1",
    limit: int = 96,
) -> None:
    """Candles + matryoshka levels + entry/mark/SL/TP lines for Telegram monitoring."""
    atl, ath = fetch_binance_ath_atl(symbol=symbol)
    fib1, fib2, fib3 = build_level_orders(atl=atl, ath=ath)
    candles = fetch_bybit_klines(symbol=symbol, interval=interval, limit=limit)

    anchors = [entry_price, mark_price]
    for raw in (stop_exchange, take_profit_exchange, stop_bot, take_profit_bot, liq_price):
        if raw is not None:
            anchors.append(float(raw))

    fig, ax = plt.subplots(figsize=(16, 9), dpi=120)
    _draw_candles(ax, candles)

    lows = [c["low"] for c in candles]
    highs = [c["high"] for c in candles]
    min_y = min(lows + anchors)
    max_y = max(highs + anchors)
    pad = (max_y - min_y) * 0.08 if max_y > min_y else max(abs(min_y), abs(max_y)) * 0.02
    y_min = min_y - pad
    y_max = max_y + pad

    visible_fib1 = [lv for lv in fib1 if y_min <= lv <= y_max]
    visible_fib2 = [lv for lv in fib2 if y_min <= lv <= y_max]
    visible_fib3 = [lv for lv in fib3 if y_min <= lv <= y_max]

    for lv in visible_fib3:
        ax.axhline(y=lv, color="#2ca02c", linewidth=0.45, alpha=0.45, zorder=1)
    for lv in visible_fib2:
        ax.axhline(y=lv, color="#1f77b4", linewidth=0.75, alpha=0.65, zorder=2)
    for lv in visible_fib1:
        ax.axhline(y=lv, color="#d62728", linewidth=1.0, alpha=0.85, zorder=4)

    latest_close = candles[-1]["close"]
    nearest_fib2 = min(fib2, key=lambda lv: abs(lv - latest_close))
    nearest_fib3 = min(fib3, key=lambda lv: abs(lv - latest_close))
    if y_min <= nearest_fib2 <= y_max:
        ax.axhline(y=nearest_fib2, color="#1f77b4", linewidth=1.4, alpha=1.0, zorder=5)
    if y_min <= nearest_fib3 <= y_max:
        ax.axhline(y=nearest_fib3, color="#2ca02c", linewidth=1.4, alpha=1.0, zorder=5)

    def _hline(y: float, color: str, style: str, label: str, lw: float = 2.0) -> None:
        ax.axhline(y=y, color=color, linestyle=style, linewidth=lw, alpha=0.95, zorder=8)
        ax.text(
            len(candles) - 0.35,
            y,
            label,
            color=color,
            fontsize=8,
            va="center",
            ha="left",
            zorder=9,
            bbox={"facecolor": "white", "alpha": 0.7, "edgecolor": "none", "pad": 1.0},
        )

    _hline(entry_price, "#ff7f0e", "-", f"Entry {entry_price:.4f}", lw=2.2)
    _hline(mark_price, "#9467bd", ":", f"Mark {mark_price:.4f}", lw=1.8)

    if stop_exchange is not None and y_min <= stop_exchange <= y_max:
        _hline(stop_exchange, "#e63946", "--", f"SL (биржа) {stop_exchange:.4f}", lw=1.8)
    if take_profit_exchange is not None and y_min <= take_profit_exchange <= y_max:
        _hline(take_profit_exchange, "#2ca02c", "--", f"TP (биржа) {take_profit_exchange:.4f}", lw=1.8)

    if stop_bot is not None and stop_bot != stop_exchange and y_min <= stop_bot <= y_max:
        _hline(stop_bot, "#c0392b", "-.", f"SL (бот state) {stop_bot:.4f}", lw=1.4)
    if (
        take_profit_bot is not None
        and take_profit_bot != take_profit_exchange
        and y_min <= take_profit_bot <= y_max
    ):
        _hline(take_profit_bot, "#27ae60", "-.", f"TP (бот state) {take_profit_bot:.4f}", lw=1.4)

    if liq_price is not None and y_min <= liq_price <= y_max:
        _hline(liq_price, "#7f7f7f", ":", f"Liq {liq_price:.4f}", lw=1.2)

    lev_txt = f"{leverage:g}x" if leverage is not None else "?"
    pnl_txt = f"{unrealised_pnl:+.4f}" if unrealised_pnl is not None else "?"
    first_ts = _timestamp_to_text(candles[0]["timestamp"])
    last_ts = _timestamp_to_text(candles[-1]["timestamp"])
    ax.set_title(
        f"{symbol} | {position_side} | TF={tf_label} | lev≈{lev_txt} | uPnL≈{pnl_txt} USDT\n"
        f"{first_ts} → {last_ts}\n"
        "Оранжевый — entry, фиолетовый — mark; SL/TP сплошные/пунктир — биржа vs бот; серый — ликвидация."
    )
    ax.set_xlim(-1, len(candles))
    ax.set_ylim(y_min, y_max)
    ax.set_xlabel("Bar index")
    ax.set_ylabel("Price")
    ax.grid(alpha=0.2, linestyle="--")
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, format="jpeg")
    plt.close(fig)


def build_audit_context(symbol: str, fib1: list[float], fib2: list[float], fib3: list[float]) -> AuditContext:
    d1_close = fetch_bybit_klines(symbol=symbol, interval="D", limit=1)[-1]["close"]
    h4_close = fetch_bybit_klines(symbol=symbol, interval="240", limit=1)[-1]["close"]
    trend_d1 = fib1_trend_bias(price=d1_close, fib1_levels=fib1)
    trend_h4 = fib1_trend_bias(price=h4_close, fib1_levels=fib1)
    trend_direction = merge_higher_tf_trend(d1_bias=trend_d1, h4_bias=trend_h4)
    latest_m15 = fetch_bybit_klines(symbol=symbol, interval="15", limit=1)[-1]["close"]
    nearest_fib2 = min(fib2, key=lambda lv: abs(lv - latest_m15))
    nearest_fib3 = min(fib3, key=lambda lv: abs(lv - latest_m15))
    atl, ath = fetch_binance_ath_atl(symbol=symbol)
    return AuditContext(
        symbol=symbol,
        atl=atl,
        ath=ath,
        trend_d1=trend_d1,
        trend_h4=trend_h4,
        trend_direction=trend_direction,
        nearest_fib2=nearest_fib2,
        nearest_fib3=nearest_fib3,
    )


def render_symbol_audit_charts(
    symbol: str,
    out_dir: Path,
    timeframes: list[tuple[str, str]] | None = None,
    limit: int = 120,
) -> tuple[list[Path], AuditContext]:
    timeframes = timeframes or DEFAULT_TIMEFRAMES
    atl, ath = fetch_binance_ath_atl(symbol=symbol)
    fib1, fib2, fib3 = build_level_orders(atl=atl, ath=ath)
    context = build_audit_context(symbol=symbol, fib1=fib1, fib2=fib2, fib3=fib3)

    output_paths: list[Path] = []
    out_dir.mkdir(parents=True, exist_ok=True)
    for interval, tf_label in timeframes:
        candles = fetch_bybit_klines(symbol=symbol, interval=interval, limit=limit)
        out_path = out_dir / f"{symbol}_{tf_label}.jpeg"
        render_symbol_timeframe_chart(
            symbol=symbol,
            tf_label=tf_label,
            candles=candles,
            fib1=fib1,
            fib2=fib2,
            fib3=fib3,
            out_path=out_path,
        )
        output_paths.append(out_path)
    return output_paths, context
