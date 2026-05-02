# Подсказки для ИИ-агента / оператора

## GitHub → сервер

Первый push с ПК и клон на VPS: **[docs/GITHUB.md](docs/GITHUB.md)**.

## Запуск на сервере (полная процедура)

Читайте и выполняйте по шагам: **[docs/SERVER_DEPLOY.md](docs/SERVER_DEPLOY.md)**.

## Минимум для production-процесса (Telegram + торговля)

1. На сервере: `git clone` репозитория, затем `python3 -m venv .venv`, `pip install -e "."`.
2. Файл `.env` из `.env.example` с заполненными `BYBIT_*`, `TELEGRAM_BOT_TOKEN`, при необходимости `TELEGRAM_ALLOWED_CHAT_IDS`.
3. В `.env` для режима без CLI-флагов: **`MATRYOSHKA_RUN_MODE=combined`**  
   Или запуск: **`python -m matryoshka_bot.main --serve`** (эквивалент `--telegram-with-live`).
4. Unit systemd: **[deploy/systemd/matryoshka-bot.service](deploy/systemd/matryoshka-bot.service)** — поправьте пути под свой каталог.
5. Перед systemd: **`python -m matryoshka_bot.main --dry-check`**.

## Переменные режима

| Переменная | Значение |
|------------|----------|
| `MATRYOSHKA_RUN_MODE` | `combined` — основной серверный режим; иначе см. SERVER_DEPLOY.md |
| `ENGINE_RESTART_BACKOFF_SECONDS` | Пауза перед перезапуском потока движка после ошибки (по умолчанию 30) |

## Точка входа Python

- Модуль: `python -m matryoshka_bot.main`
- После `pip install -e .`: консольная команда `matryoshka-bot` (те же аргументы)
