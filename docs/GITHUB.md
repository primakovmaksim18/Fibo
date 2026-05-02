# GitHub и сервер: одна схема

Репозиторий рассчитан на **приватный** GitHub-репозиторий: код в git, **секреты только на сервере** в файле `.env` (файл `.env` в `.gitignore`, в репозитории остаётся только `.env.example`).

## Что не попадает в git

См. **[.gitignore](../.gitignore)**: `.env`, `logs/`, `state/`, `artifacts/`, `.venv/`, кэши Python.

После `git clone` на сервере каталоги `logs/`, `state/`, `artifacts/` создаст сам бот при работе.

## 1. Первый раз: отправка кода на GitHub (с вашего ПК)

1. Создайте **новый репозиторий** на https://github.com/new (рекомендуется **Private**).
2. Не добавляйте README/License через веб, если репозиторий уже есть локально.

В каталоге проекта (ветка обычно `main` или `master`):

```bash
git status
git add -A
git commit -m "Initial push for server deploy"
git branch -M main
git remote add origin https://github.com/YOUR_USER/YOUR_REPO.git
git push -u origin main
```

Замените `YOUR_USER/YOUR_REPO` на свой путь. Для SSH:

```bash
git remote add origin git@github.com:YOUR_USER/YOUR_REPO.git
```

Если `remote origin` уже существует:

```bash
git remote set-url origin https://github.com/YOUR_USER/YOUR_REPO.git
git push -u origin main
```

## 2. Клонирование на сервере

Рекомендуемый путь: `/opt/matryoshka-bot`.

```bash
sudo mkdir -p /opt
sudo chown "$USER:$USER" /opt   # или сразу деплой-пользователь
cd /opt
git clone https://github.com/YOUR_USER/YOUR_REPO.git matryoshka-bot
cd matryoshka-bot
```

Дальше — как в **[SERVER_DEPLOY.md](SERVER_DEPLOY.md)** (venv, `.env`, `--dry-check`, systemd).

Кратко:

```bash
python3 -m venv .venv
.venv/bin/pip install -U pip
.venv/bin/pip install -e "."
cp .env.example .env
chmod 600 .env
nano .env   # ключи, MATRYOSHKA_RUN_MODE=combined, …
.venv/bin/python -m matryoshka_bot.main --dry-check
```

## 3. Обновление кода на сервере

```bash
cd /opt/matryoshka-bot
sudo systemctl stop matryoshka-bot
git pull origin main
.venv/bin/pip install -e "."
sudo systemctl start matryoshka-bot
```

Если менялись зависимости в `pyproject.toml`, шаг `pip install -e "."` обязателен.

## 4. Безопасность

- Не коммитьте `.env`, ключи Bybit, токен Telegram, логи сделок.
- Репозиторий лучше держать **Private**.
- На сервере: `chmod 600 .env`, пользователь сервиса без лишних прав (см. SERVER_DEPLOY.md).
