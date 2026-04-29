# Matryoshka Trading Bot (Bybit)

Trading bot based on a static multi-level Fibonacci structure from absolute historical bounds (`ATL -> ATH`).

## Strategy Snapshot

- Exchange: `Bybit` (live only)
- Assets: `BTCUSDT`, `ETHUSDT`, `SOLUSDT`, `BNBUSDT`, `XRPUSDT`
- Context timeframe: `4H`
- Entry timeframe: `15m`
- Depth regime:
  - `Depth=4` when `DailyRange > 10%`
  - `Depth=5` when `DailyRange <= 10%`
- Per-cell Fibonacci percentages: `0, 23.6, 38.2, 50, 61.8, 78.6, 100`
- Each next depth is built inside every adjacent pair from the previous depth
- Overlapping prices are deduplicated into unique sorted levels

## Signal Model

- Trend context is defined by `Fib 1` structure confirmed on `D1 + H4`.
- Entries are executed on `Fib 2` / `Fib 3` levels only.
- Bounce LONG/SHORT: rejection from `Fib 2/3` level with volume + momentum filters.
- Breakout LONG/SHORT: `Fib 2/3` level break with strong body, volume expansion and hold.
- Trade filter is trend-preferred: countertrend is allowed only for strong breakout setups.

## Risk Model

- Risk per trade: `1%` base, `2%` strong setup, `3%` disabled at bootstrap.
- Max open positions: `3`
- Max aggregate open risk: `5%`
- Daily stop trading: `-4%` equity

## Project Structure

```text
.
├── README.md
├── .env.example
├── pyproject.toml
├── src/
│   └── matryoshka_bot/
│       ├── __init__.py
│       ├── main.py
│       ├── config/
│       │   ├── __init__.py
│       │   ├── assets.py
│       │   └── settings.py
│       ├── exchange/
│       │   ├── __init__.py
│       │   └── bybit_client.py
│       ├── journal/
│       │   ├── __init__.py
│       │   └── store.py
│       ├── reporting/
│       │   ├── __init__.py
│       │   ├── level_charts.py
│       │   ├── metrics.py
│       │   └── report.py
│       ├── risk/
│       │   ├── __init__.py
│       │   └── sizing.py
│       ├── signals/
│       │   ├── __init__.py
│       │   ├── bounce.py
│       │   └── breakout.py
│       └── strategy/
│           ├── __init__.py
│           ├── levels.py
│           ├── regime.py
│           ├── scanner.py
│           └── segment.py
│       └── trading/
│           ├── __init__.py
│           ├── decision.py
│           ├── engine.py
│           └── preflight.py
│       └── telegram_bot/
│           ├── __init__.py
│           ├── app.py
│           ├── handlers.py
│           └── keyboards.py
├── logs/
│   ├── events.jsonl
│   ├── signals.jsonl
│   ├── strategy_report.json
│   └── trades.jsonl
├── state/
│   └── open_positions.json
└── tests/
    └── test_strategy_core.py
```

## Project Prompt (reference)

```text
You are a senior quant developer. Build a production-ready Bybit trading bot using
the "Static Global Matryoshka" strategy.

Rules:
- Build static multi-level Fibonacci grid from ATL to ATH.
- Fibonacci levels per cell: 0, 23.6, 38.2, 50, 61.8, 78.6, 100.
- Build next depth inside every adjacent pair produced by previous depth.
- Resolve overlaps by priority so higher-order parent levels are preserved.
- Depth=4 when DailyRange>10%, else Depth=5.
- Assets: BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT.
- Context TF: 4H, execution TF: 15m.

Signals:
- Bounce LONG/SHORT with price action + volume + momentum filters.
- Breakout with volume expansion and hold confirmation.

Risk:
- 1-3% per trade, max 3 open positions, max 5% aggregate risk.
- Daily stop-trading at -4%.

Deliverables:
- Modular architecture, config-driven rules, unit tests, live trade loop,
  structured logging, and metrics reporting.
```

## Runtime Flow (live perpetuals)

1. Load settings and validate keys.
2. Fetch market data (`ticker`, `daily OHLC`, `15m klines`) from Bybit v5 `linear` category.
3. Build matryoshka segment context (`scan_symbol`).
4. Build trend direction from `Fib 1` on `D1 + H4`.
5. Evaluate entries on `Fib 2/3` (`bounce`, `breakout`) with trend-preferred filter.
   - trend-aligned trades are allowed by default
   - countertrend is allowed only for strong `breakout`
6. Calculate raw size from risk model.
7. Normalize order quantity by instrument constraints (`qty step`, `min qty`, `min notional`).
8. Apply symbol profile: `cross` margin mode + `x10` leverage.
9. Place market orders only when constraints pass.
10. Track open positions in `state/open_positions.json`.
11. Close by TP/SL and write all events to `logs/*.jsonl`.
12. Rebuild report snapshot (`logs/strategy_report.json`) after each cycle.
13. Protect API calls with retry/backoff and skip duplicate entries for same symbol/candle.

## Live Startup (real funds, Bybit v5)

1. Create `.env` from `.env.example`.
2. Fill `BYBIT_API_KEY` and `BYBIT_API_SECRET`.
3. Set:
   - `MARGIN_MODE=cross`
   - `LEVERAGE=10`
   - `API_RETRY_ATTEMPTS=4`
   - `API_RETRY_BACKOFF_MS=300`
   - `LOOP_INTERVAL_SECONDS=15`
   - `LOOP_ITERATIONS=1` (increase for daemon-like execution)
   - For Telegram audit mode:
     - `TELEGRAM_BOT_TOKEN=<your_telegram_bot_token>`
     - `TELEGRAM_ALLOWED_CHAT_IDS=<chat_id_1,chat_id_2>`
4. Install dependencies:
   - `python3 -m pip install -e ".[dev]"`
5. Run tests:
   - `python3 -m pytest -q`
6. Start live engine:
   - `python3 -m matryoshka_bot.main`
7. Run preflight only (`API + wallet + constraints + cross x10 apply`):
   - `python3 -m matryoshka_bot.main --dry-check`
8. Generate report snapshot manually any time:
   - `python3 -m matryoshka_bot.reporting.report`
9. Start Telegram level-audit bot (inline buttons):
   - `python3 -m matryoshka_bot.main --telegram`
10. **Full bot (recommended):** Telegram UI + live trading engine in **one process**:
   - `python3 -m matryoshka_bot.main --telegram-with-live`
   - Requires `TELEGRAM_BOT_TOKEN`, `BYBIT_API_KEY`, and `BYBIT_API_SECRET` in `.env`. The engine loop runs in a **background thread** until you stop the process (`Ctrl+C`). Polling interval between engine cycles: `LOOP_INTERVAL_SECONDS`.

## Telegram bot (`--telegram`)

- Launch with `--telegram` (audit/UI only) or `--telegram-with-live` (same UI plus live engine), then send `/start`.
- **Главное меню:** `Проверка уровней` | `Торговля`.
- **Проверка уровней:** выбор инструмента → JPEG с `Fib1/Fib2/Fib3`, тренд `D1+H4`, ближайшие `F2/F3`.
- **Торговля:** пауза новых входов / снять паузу; пресеты базового риска `1%` / `2%`; сброс риска к значению из `.env`; **Preflight Bybit** (нужны ключи в `.env`); **Статус** (equity, позиции из `state/open_positions.json`).
- Состояние паузы и override риска сохраняется в `state/telegram_trading.json` (используется live-движком при запуске торговли).
- Доступ: при непустом `TELEGRAM_ALLOWED_CHAT_IDS` — только перечисленные chat id.

Примечание: старые сообщения в чате могут показывать устаревшие кнопки; актуальное меню всегда у последнего `/start` или после «Назад в главное меню».

## Logging and Reports

- `logs/signals.jsonl`: every evaluated/triggered signal context.
  - includes `trend_tf_d1`, `trend_tf_h4`, `trend_direction`,
    `entry_level`, `entry_level_order` (`fib2` or `fib3`), `is_countertrend`.
- `logs/trades.jsonl`: all open/close trades with order payload and realized `pnl`.
- `logs/events.jsonl`: risk guards, runtime events, exceptions.
- `logs/events.jsonl` also contains `order_skip` with detailed reason when
  `qty step` / `min qty` / `min notional` checks fail.
- `logs/events.jsonl` contains duplicate-entry protection events:
  `duplicate_symbol_same_candle_guard`.
- `logs/events.jsonl` contains symbol profile apply result (`cross + x10`) per symbol.
- `logs/strategy_report.json`: summary metrics:
  - trades
  - wins/losses
  - win rate
  - gross profit / gross loss
  - net PnL
  - profit factor

## Safety Notes

- Runtime is hard-wired to Bybit live linear perpetuals.
- If cumulative daily result breaches `DAILY_STOP_PCT`, runtime raises and stops.
- Quantity validation is enforced per-symbol using Bybit instrument filters before order submission.
- Instrument metadata (`get_instruments_info`) is cached in-memory per symbol.
- Limit price normalization by `tickSize` is implemented for future limit-order flow.
- All exchange requests use retry/backoff for transient errors (`429/5xx/timeout`).
- Duplicate order protection prevents repeated entry on same symbol and same 15m candle.

## Progress Log

- [x] Bootstrap `pyproject.toml`
- [x] Add initial TDD tests for strategy core
- [x] Implement first strategy core modules (`levels`, `regime`, `segment`)
- [x] Run tests and harden edge cases
- [x] Add initial risk layer (`risk/sizing.py`)
- [x] Add initial Bybit integration and demo runtime scaffold
- [x] Add signal engines (`bounce`, `breakout`) and tests
- [x] Add live trading engine (`signals -> sizing -> order -> pnl`)
- [x] Add persistent state and full journal logging
- [x] Add reporting module and metrics snapshot
- [x] Remove demo/testnet toggles (live-only perpetual mode)
- [x] Add instrument-level order guards (`qty step`, `min qty`, `min notional`)
- [x] Add instrument cache + limit price normalization (`tickSize`)
- [x] Add preflight mode (`--dry-check`) for API/wallet/constraints checks
- [x] Add symbol profile setup (`cross margin + x10 leverage`)
- [x] Add retry/backoff wrapper for Bybit API transient errors
- [x] Add anti-duplicate order guard (same symbol, same candle, same cycle)

## Fibonacci Matryoshka Clarification

Current implementation follows MT5 reference logic:

- Base range is `ATL -> ATH`.
- Main level percentages: `0 / 23.6 / 38.2 / 50 / 61.8 / 78.6 / 100`.
- For each depth step, levels are generated inside every adjacent parent interval.
- Trading role split:
  - `Fib 1` -> trend context (`D1 + H4`)
  - `Fib 2` / `Fib 3` -> entry levels (`bounce` / `breakout`)
- Execution policy: trend-preferred, countertrend only for strong breakout.
- Depth selection remains: `4` when daily range > 10%, otherwise `5`.

Pipeline:
`Build levels -> Detect trend(Fib1 D1+H4) -> Entry(Fib2/Fib3) -> Risk/Execution`
