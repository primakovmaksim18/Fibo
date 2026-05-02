# Matryoshka Trading Bot (Bybit)

Trading bot based on a static multi-level Fibonacci structure from absolute historical bounds (`ATL -> ATH`).

**Уровни (логика сетки, сила и порядок Fib 1→3) для переиспользования:** см. [README_LEVELS.md](README_LEVELS.md).

## Strategy Snapshot

- Exchange: `Bybit` Unified v5 `linear` (USDT perpetual)
- По умолчанию: **Demo Trading** — REST `https://api-demo.bybit.com`, ключи API создаются в интерфейсе Bybit в режиме **Demo Trading** (отдельный демо-счёт, не Testnet).
- Для торговли на основном счёте: в `.env` задайте `BYBIT_DEMO_TRADING=false` и используйте production API keys (**реальные средства**).
- **Инструменты (10 USDT perp):** `BTCUSDT`, `ETHUSDT`, `SOLUSDT`, `BNBUSDT`, `XRPUSDT`, `DOGEUSDT`, `ADAUSDT`, `AVAXUSDT`, `LINKUSDT`, `DOTUSDT` — порядок и границы `ATL/ATH` в `src/matryoshka_bot/config/assets.py` (`TRADE_SYMBOLS`, `ASSET_BOUNDS`).
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
├── README_LEVELS.md
├── AGENTS.md
├── .env.example
├── pyproject.toml
├── docs/
│   ├── GITHUB.md          # push в GitHub и git clone на сервере
│   └── SERVER_DEPLOY.md   # venv, .env, systemd
├── deploy/
│   └── systemd/           # unit-файл для Linux
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
│       │   ├── bybit_client.py
│       │   └── bybit_clock.py
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
│       │   ├── breakout.py
│       │   └── conditions_audit.py
│       ├── strategy/
│       │   ├── __init__.py
│       │   ├── levels.py
│       │   ├── regime.py
│       │   ├── scanner.py
│       │   ├── scan_snapshot.py
│       │   └── segment.py
│       ├── trading/
│       │   ├── __init__.py
│       │   ├── decision.py
│       │   ├── engine.py
│       │   ├── indicators.py
│       │   ├── preflight.py
│       │   └── signal_evaluation.py
│       └── telegram_bot/
│           ├── __init__.py
│           ├── app.py
│           ├── handlers.py
│           ├── keyboards.py
│           └── trade_alerts.py
├── artifacts/             # не в git — создаётся ботом (графики Telegram / алерты)
├── tools/
│   └── kill_matryoshka_bot_processes.ps1
├── logs/                  # не в git — журналы и отчёты при работе
├── state/                 # не в git — open_positions.json и т.д.
└── tests/
    ├── test_level_logging.py
    ├── test_runtime_overrides.py
    ├── test_telegram_audit.py
    ├── test_trade_alerts.py
    └── test_strategy_core.py
```

В git попадают только исходники и шаблон `.env.example`; секреты и runtime-каталоги см. [.gitignore](.gitignore). Деплой: **[docs/GITHUB.md](docs/GITHUB.md)** → **[docs/SERVER_DEPLOY.md](docs/SERVER_DEPLOY.md)**.

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
- Assets: BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT, DOGEUSDT, ADAUSDT, AVAXUSDT, LINKUSDT, DOTUSDT.
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

## Runtime Flow (USDT perpetual, Demo или Main по `.env`)

1. Load settings and validate keys.
2. Fetch market data (`ticker`, `daily OHLC`, `15m klines`) from Bybit v5 `linear` category (endpoint выбирается pybit по `BYBIT_DEMO_TRADING`).
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
14. При настроенных **Telegram trade alerts** (см. ниже) движок шлёт в чат уведомления: сигнал, открытие/закрытие сделки, отмена входа по `qty`/notional (текст + H1-график, данные с Bybit + `state` где уместно).

### Выход из позиции (кратко)

- Частичное закрытие на **TP1** (уровень Fib 2/3 как раньше), доля задаётся **`PARTIAL_TP_FRACTION`** (по умолчанию 50%).
- Остаток: стоп → **безубыток** с учётом **`BREAKEVEN_OFFSET_BPS`** и шага цены; второе закрытие на **следующем** уровне сетки Fib 2∪F3 в сторону прибыли (**TP2**). Подробнее — `.env.example`.

### Логи и state при перезапуске

- Каталог **`logs/`** (`*.jsonl`, отчёты) **дополняется**, при перезапуске процесса **не очищается** — история сделок и циклов сохраняется.
- **`state/open_positions.json`** — локальные позиции бота (размер фазы, TP1/TP2, стоп); при старте движок **подгружает** этот файл и продолжает вести уже открытые сделки.
- В **`logs/events.jsonl`** при каждом старте движка пишется **`startup_exchange_positions`**: список символов с **ненулевым размером на Bybit** и список символов из **локального state** (удобно сверить после ребута). Позиции, открытые **вне бота**, бот не переучитывает в своём SL/TP — только логирует.

## Startup (Bybit v5 Unified)

1. Create `.env` from `.env.example`.
2. Fill `BYBIT_API_KEY` and `BYBIT_API_SECRET` (**ключи должны соответствовать режиму**: для Demo Trading — ключи, созданные в Demo Trading на `api-demo.bybit.com`; для основного счёта — production keys на `api.bybit.com`).
3. Set `BYBIT_DEMO_TRADING` (рекомендуется `true` для демо):
   - `true` — демо-счёт Bybit (**ордера на демо, не реальные деньги**), домен REST `api-demo.bybit.com` (см. [Demo Trading Service](https://bybit-exchange.github.io/docs/v5/demo)).
   - `false` — основной счёт Bybit (**реальные средства**).
4. Set:
   - `MARGIN_MODE=cross`
   - `LEVERAGE=10`
   - `API_RETRY_ATTEMPTS=4`
   - `API_RETRY_BACKOFF_MS=300`
   - `LOOP_INTERVAL_SECONDS=15`
   - `LOOP_ITERATIONS=1` — для «вечного» цикла **только** у `-m matryoshka_bot.main` без Telegram можно задать `0` или отрицательное число; в режиме `--telegram-with-live` движок работает **пока запущен процесс**, это значение не ограничивает цикл.
   - Telegram:
     - `TELEGRAM_BOT_TOKEN=<токен от @BotFather>`
     - `TELEGRAM_ALLOWED_CHAT_IDS=<id1,id2>` — **числовые** Telegram user / chat id через запятую (узнать id: [@userinfobot](https://t.me/userinfobot) и т.п.). Без id push **не уходит** (некуда доставлять). Пустой список: бот в polling может принимать любой чат; ограничение доступа к кнопкам — только при **непустом** списке.
     - `TELEGRAM_TRADE_ALERTS=true` (по умолчанию) — см. раздел **Telegram trade alerts** ниже; отключить: `false`.
   - Логирование (опционально): `MATRYOSHKA_LOG_LEVEL=INFO|DEBUG|WARNING`; при `DEBUG` подавляется спам HTTP от `urllib3`/`pybit`; полный трасс запросов: `MATRYOSHKA_HTTP_DEBUG=1`.
5. Install dependencies:
   - `python3 -m pip install -e ".[dev]"`
6. Run tests:
   - `python3 -m pytest -q`
7. Start trading engine:
   - `python3 -m matryoshka_bot.main`
8. Run preflight only (`API + wallet + constraints + cross x10 apply`):
   - `python3 -m matryoshka_bot.main --dry-check`
9. Generate report snapshot manually any time:
   - `python3 -m matryoshka_bot.reporting.report`
10. Start Telegram level-audit bot (inline buttons):
   - `python3 -m matryoshka_bot.main --telegram`
11. **Full bot (recommended):** Telegram UI + торговый движок в **одном процессе**:
   - `python3 -m matryoshka_bot.main --serve` (или `--telegram-with-live` — то же самое)
   - На сервере можно без флага: в `.env` задать `MATRYOSHKA_RUN_MODE=combined` (см. **[docs/SERVER_DEPLOY.md](docs/SERVER_DEPLOY.md)**).
   - Requires `TELEGRAM_BOT_TOKEN`, `BYBIT_API_KEY`, and `BYBIT_API_SECRET` in `.env`. The engine loop runs in a **background thread** until you stop the process (`Ctrl+C`). Polling interval between engine cycles: `LOOP_INTERVAL_SECONDS`. После сбоя сети поток движка перезапускается с паузой **`ENGINE_RESTART_BACKOFF_SECONDS`** (по умолчанию 30 с).
   - После правок кода перезапустите процесс, чтобы подхватить изменения. На Windows можно завершить все экземпляры командой  
     `powershell -ExecutionPolicy Bypass -File tools/kill_matryoshka_bot_processes.ps1`  
     и снова запустить нужный режим из п. 7–11 (обычно `python -m matryoshka_bot.main --serve` из активированного venv).

### Запуск на VPS (systemd)

Пошаговая инструкция для Linux и **одной команды** через `MATRYOSHKA_RUN_MODE` или `--serve`: **[docs/SERVER_DEPLOY.md](docs/SERVER_DEPLOY.md)**.

Сводка за период (например, следующий день): **`logs/levels.jsonl`**, **`logs/trades.jsonl`**, **`logs/strategy_report.json`**, при необходимости **`logs/events.jsonl`** (в т.ч. `startup_exchange_positions` после рестарта).

## Telegram bot (`--telegram`)

- Запуск: `--telegram` (только аудит/UI) или `--telegram-with-live` (то же + live-движок в фоновом потоке). После старта отправьте `/start`.
- **Главное меню:** `Проверка уровней` | `Торговля`.
- **Проверка уровней:** инструмент → **инлайн-кнопки таймфрейма `H1` / `M30`** → один JPEG: сетка `F1` (красный, метки %), `F2` (синий), `F3` (зелёный), акцент ближайших F2/F3 к last close выбранного ТФ + тренд `D1+H4` в caption.
- **Торговля:** пауза входов / снять паузу; пресеты **риска на сделку** `0.25%` … `2%` от equity (override в `state/telegram_trading.json`); «Что значит риск на сделку»; сброс к `BASE_RISK_PCT` из `.env`; **Preflight Bybit**; **Статус** (equity, кратко позиции из `state`); **Открытые позиции (Bybit + график)** — актуальные данные с биржи (`get_positions`), сверка с `state/open_positions.json`, JPEG **H1** с уровнями и линиями entry/mark/SL/TP (биржа и бот).
- Состояние паузы и override риска: `state/telegram_trading.json` (читает live-движок).
- Доступ к кнопкам: при **непустом** `TELEGRAM_ALLOWED_CHAT_IDS` — только перечисленные chat id.

Примечание: старые сообщения могут показывать устаревшие кнопки; актуальное меню — у последнего `/start` или «Назад в главное меню».

### Telegram trade alerts (push от движка)

При **`TELEGRAM_TRADE_ALERTS=true`**, заданных **`TELEGRAM_BOT_TOKEN`** и **непустом `TELEGRAM_ALLOWED_CHAT_IDS`** торговый движок отправляет в эти чаты (отдельными сообщениями):

1. **Сигнал обнаружен** — до отправки ордера: setup, сторона, цена, SL/TP, тренд D1/H4, риск %, equity / wallet / available (USDT), фрагмент `signal_analysis`; **JPEG H1** с уровнями (как аудит).
2. **Ордер открыт** — после успешного market entry: qty, оценка входа, SL/TP, риск %, equity/wallet/available, `orderId`; снова **H1**.
3. **Позиция закрыта** — после SL/TP (market reduce-only): причина, entry/exit, оценка PnL, equity/wallet/available, `orderId`; **H1**.
4. **Вход отменён** — если сигнал был, но не прошли ограничения по qty/notional (только текст).

Графики для алертов складываются в `artifacts/trade-alerts/`. Ошибки Telegram или построения графика не останавливают движок (события можно искать в `logs/events.jsonl`).

Отключить все push: `TELEGRAM_TRADE_ALERTS=false`.

## Если «ничего не поднимается» (типичные ошибки из лога)

- **`Failed to fetch updates - TelegramConflict` / конфликт getUpdates**  
  С тем же `TELEGRAM_BOT_TOKEN` уже крутится другой процесс (второй терминал, Cloud, старый Python). Остановите все экземпляры; при необходимости сбросьте webhook вручную:  
  `https://api.telegram.org/bot<TOKEN>/deleteWebhook?drop_pending_updates=true`

- **`pybit` ErrCode `10002` (timestamp / recv_window)**  
  Обычно **часы Windows чуть опережают сервер Bybit** (в логе видно `req_timestamp` выше `server_timestamp`). По умолчанию клиент синхронизируется через **`GET /v5/market/time`** (`BYBIT_ALIGN_TIME_WITH_SERVER=true` в `.env.example`). Если отключите выравнивание — включите NTP на ПК и при необходимости увеличьте **`BYBIT_RECV_WINDOW_MS`** (например `60000`).

- **`InvalidRequestError` / запросы на `api.bybit.com` при демо-ключах**  
  Для Demo Trading должно быть **`BYBIT_DEMO_TRADING=true`** и ключи, созданные **в режиме Demo Trading** на Bybit. Иначе подпись/ключ не совпадут с доменом.

- **Поток `LiveTradingEngine` падает, Telegram вроде живёт**  
  Раньше ошибка в фоновом потоке могла быть неочевидной. Сейчас трассировка пишется в **stderr**; проверьте также `logs/events.jsonl`. Сначала добейтесь успешного `python -m matryoshka_bot.main --dry-check`.

## Logging and Reports

- `logs/levels.jsonl`: один JSON на **каждый проход символа** в цикле сканирования.
  - `outcome`: `no_entry` | `skipped` | `order_placed` | `order_skipped` и текст в `skip_reason` при необходимости.
  - `matryoshka_levels`: полные списки `fib1_levels`, `fib2_levels`, `fib3_levels`, `all_levels_sorted_unique`, сегмент по `scan.all_levels`, счётчики.
  - `fib1_bias_context`: тренд по D1/H4 и контекст относительно Fib1 для spot-цены.
  - `entry_grid`: nearest F2/F3, support/resistance в сетке F2∪F3, дистанции в % от цены.
  - `candles_15m`: последняя временная метка свечи + до 5 баров OHLCV (для трассировки).
  - `signal_analysis`: индикаторы (RSI, объёмы), **покомпонентные аудиты** `bounce_long` / `bounce_short` / `breakout_long` / `breakout_short` (каждый чек с порогами), сортировка кандидатов, итог `outcome` (`no_setup_triggered`, `signal_selected`, …).
  - при исполнении: `sizing_attempt`, `instrument_constraints`, `execution.bybit_place_order_response`.
- `logs/signals.jsonl`: every evaluated/triggered signal context.
  - includes `trend_tf_d1`, `trend_tf_h4`, `trend_direction`,
    `entry_level`, `entry_level_order` (`fib2` or `fib3`), `is_countertrend`.
- `logs/trades.jsonl`: all open/close trades with order payload and realized `pnl`.
- `logs/events.jsonl`: risk guards, runtime events, exceptions; также `telegram_alert_chart_error` при сбое JPEG для push.
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

- Режим API задаётся `BYBIT_DEMO_TRADING`: при `false` используются **реальные** ордера и баланс на основном счёте Bybit.
- Рынок `linear` (USDT perpetual); Testnet в проекте **не используется** и не поддерживается.
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
- [x] Bybit Demo Trading по умолчанию (`BYBIT_DEMO_TRADING` + `demo` в pybit); Testnet не используется
- [x] Add instrument-level order guards (`qty step`, `min qty`, `min notional`)
- [x] Add instrument cache + limit price normalization (`tickSize`)
- [x] Add preflight mode (`--dry-check`) for API/wallet/constraints checks
- [x] Add symbol profile setup (`cross margin + x10 leverage`)
- [x] Add retry/backoff wrapper for Bybit API transient errors
- [x] Add anti-duplicate order guard (same symbol, same candle, same cycle)
- [x] Detailed per-symbol level + signal diagnostics (`logs/levels.jsonl`)
- [x] Telegram: выбор H1/M30 для графика уровней после выбора инструмента
- [x] Telegram: открытые позиции с Bybit + H1-график; push-уведомления о сигнале/ордере/закрытии + H1
- [x] 10 торговых пар (топ ликвидности): расширение universe в `config/assets.py`; при старте лог `startup_exchange_positions`

## Fibonacci Matryoshka Clarification

Подробнее (пошагово, приоритеты Fib 1→3, динамический `depth`) — **[README_LEVELS.md](README_LEVELS.md)**. Кратко:

- Base range is `ATL -> ATH`.
- Main level percentages: `0 / 23.6 / 38.2 / 50 / 61.8 / 78.6 / 100`.
- For each nesting order, levels are generated inside every adjacent parent interval (`strategy/levels.py`).
- Trading role split:
  - `Fib 1` -> trend context (`D1 + H4`)
  - `Fib 2` / `Fib 3` -> entry levels (`bounce` / `breakout`)
- Execution policy: trend-preferred, countertrend only for strong breakout.
- Depth selection: `4` when daily range > 10%, otherwise `5`.

Pipeline:
`Build levels -> Detect trend(Fib1 D1+H4) -> Entry(Fib2/Fib3) -> Risk/Execution`
