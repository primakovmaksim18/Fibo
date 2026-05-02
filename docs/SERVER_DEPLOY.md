# Развёртывание Matryoshka-bot на Linux-сервере

Этот документ рассчитан на **любого оператора или ИИ-агента**: выполняйте шаги по порядку на чистой Ubuntu/Debian VPS (или аналоге с `systemd`).

## Цель

Один долгоживущий процесс: **Telegram-бот (polling) + торговый движок Bybit** в одном процессе, автоперезапуск при падении процесса через **systemd**, автоперезапуск **потока движка** после сетевых ошибок (см. `ENGINE_RESTART_BACKOFF_SECONDS`).

## Предварительные условия

- Сервер с **исходящим HTTPS (443)** к `api.telegram.org`, `api.bybit.com` или `api-demo.bybit.com`.
- **Python 3.11+**.
- Уже есть: ключи Bybit (demo или prod), токен Telegram от `@BotFather`, при необходимости числовые `TELEGRAM_ALLOWED_CHAT_IDS`.

## 1. Получение кода с GitHub

Рекомендуемый путь приложения: `/opt/matryoshka-bot`. Код клонируйте **приватный** репозиторий (см. полный сценарий: **[GITHUB.md](GITHUB.md)**).

```bash
sudo mkdir -p /opt
sudo chown "$USER:$USER" /opt
cd /opt
git clone https://github.com/YOUR_USER/YOUR_REPO.git matryoshka-bot
cd matryoshka-bot
```

Замените URL на свой (SSH: `git@github.com:USER/REPO.git`). В репозитории не хранятся `.env`, `logs/`, `state/`, `artifacts/` — на сервере создаётся только `.env` из `.env.example` и рабочие каталоги при запуске бота.

Минимальный набор в клоне:

- `pyproject.toml`
- `src/matryoshka_bot/`
- `.env.example`

## 2. Виртуальное окружение и зависимости

```bash
cd /opt/matryoshka-bot
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/pip install -e "."
```

Для проверки тестов (опционально): `.venv/bin/pip install -e ".[dev]"` и `.venv/bin/pytest -q`.

## 3. Конфигурация `.env`

```bash
cp .env.example .env
chmod 600 .env
nano .env   # или vim
```

Обязательно задайте по смыслу вашего режима:

| Переменная | Назначение |
|------------|------------|
| `BYBIT_API_KEY` / `BYBIT_API_SECRET` | Ключи API |
| `BYBIT_DEMO_TRADING` | `true` — демо (`api-demo.bybit.com`), `false` — **реальный счёт** |
| `TELEGRAM_BOT_TOKEN` | Токен бота |
| `TELEGRAM_ALLOWED_CHAT_IDS` | Через запятую, если нужны ограничение чатов и trade alerts |
| `MATRYOSHKA_RUN_MODE` | Для сервера: **`combined`** (Telegram + движок без CLI-флагов) |
| `ENGINE_RESTART_BACKOFF_SECONDS` | Пауза перед повторным стартом потока движка после ошибки (по умолчанию `30`) |
| `LOOP_INTERVAL_SECONDS` | Интервал между циклами сканирования |

Режимы `MATRYOSHKA_RUN_MODE`:

- `combined` — то же, что `python -m matryoshka_bot.main --serve` (Telegram + engine).
- `telegram` — только Telegram.
- `trade` — только движок (число циклов из `LOOP_ITERATIONS`; для «бесконечно» задайте `LOOP_ITERATIONS=0`).
- `dry_check` — одиночный preflight (как `--dry-check`).

Альтернатива переменной: в `ExecStart` указать явный флаг `--serve` (см. ниже).

## 4. Ручная проверка перед systemd

Из каталога проекта с активированным venv:

```bash
cd /opt/matryoshka-bot
set -a && source .env && set +a
.venv/bin/python -m matryoshka_bot.main --dry-check
```

Затем краткий тест комбинированного режима (остановка `Ctrl+C`):

```bash
.venv/bin/python -m matryoshka_bot.main --serve
```

или

```bash
MATRYOSHKA_RUN_MODE=combined .venv/bin/python -m matryoshka_bot.main
```

Убедитесь, что бот отвечает в Telegram и в логах нет фатальных ошибок.

## 5. Пользователь сервиса и права

Не запускайте бота под `root`. Пример:

```bash
sudo useradd --system --home /opt/matryoshka-bot --shell /usr/sbin/nologin matryoshka || true
sudo chown -R matryoshka:matryoshka /opt/matryoshka-bot
```

Каталоги `logs/`, `state/`, `artifacts/` должны быть доступны пользователю `matryoshka` на запись (они создаются при первом запуске, если их нет — создайте и выдайте права).

## 6. Установка unit-файла systemd

Файл в репозитории: `deploy/systemd/matryoshka-bot.service`.

Пути в unit рассчитаны на `/opt/matryoshka-bot` и venv `.venv`. При другом пути отредактируйте `WorkingDirectory`, `EnvironmentFile`, `ExecStart`.

```bash
sudo cp /opt/matryoshka-bot/deploy/systemd/matryoshka-bot.service /etc/systemd/system/matryoshka-bot.service
sudo systemctl daemon-reload
sudo systemctl enable matryoshka-bot
sudo systemctl start matryoshka-bot
sudo systemctl status matryoshka-bot
```

Логи systemd (если включите `StandardOutput=journal` в unit):

```bash
journalctl -u matryoshka-bot -f
```

Иначе смотрите файлы в `/opt/matryoshka-bot/logs/` и при необходимости перенаправьте stdout/stderr в файл через `ExecStart`/`redirect` или обёртку.

## 7. Обновление кода

```bash
cd /opt/matryoshka-bot
sudo systemctl stop matryoshka-bot
git pull origin main
.venv/bin/pip install -e "."
sudo systemctl start matryoshka-bot
```

(Ветка может называться иначе — подставьте свою, см. [GITHUB.md](GITHUB.md).)

## 8. Частые проблемы

- **TelegramConflict** — уже запущен второй процесс с тем же токеном. Остановите дубликаты: `sudo systemctl stop matryoshka-bot` на других машинах или процессы вручную; при необходимости сбросьте webhook:  
  `https://api.telegram.org/bot<TOKEN>/deleteWebhook?drop_pending_updates=true`
- **Нет связи с api.telegram.org** — firewall исходящих, блокировки сети, sleeps на VPS.
- **Bybit ErrCode 10002** — время на сервере; включите NTP (`timedatectl`), оставьте `BYBIT_ALIGN_TIME_WITH_SERVER=true`, при необходимости увеличьте `BYBIT_RECV_WINDOW_MS`.

## Краткая шпаргалка команд запуска

| Задача | Команда |
|--------|---------|
| Production (явный флаг) | `python -m matryoshka_bot.main --serve` |
| То же через env | `MATRYOSHKA_RUN_MODE=combined python -m matryoshka_bot.main` |
| Старый синоним | `python -m matryoshka_bot.main --telegram-with-live` |
| CLI entrypoint (после `pip install -e .`) | `matryoshka-bot` (аргументы те же) |
| Preflight | `python -m matryoshka_bot.main --dry-check` |

После установки пакета в venv первый аргумент можно не указывать, если в `.env` задано `MATRYOSHKA_RUN_MODE=combined` — **systemd ExecStart** может быть просто:

`ExecStart=/opt/matryoshka-bot/.venv/bin/python -m matryoshka_bot.main`
