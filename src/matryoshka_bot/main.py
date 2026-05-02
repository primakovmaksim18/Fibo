from __future__ import annotations

import argparse
import logging
import os
import sys
import threading
import time
import traceback

from matryoshka_bot.config.settings import BotSettings, load_settings

_LOGGER = logging.getLogger("matryoshka_bot")


def _run_mode_from_env() -> str:
    return os.getenv("MATRYOSHKA_RUN_MODE", "").strip().lower()


def _engine_restart_backoff_seconds() -> int:
    raw = os.getenv("ENGINE_RESTART_BACKOFF_SECONDS", "30").strip()
    try:
        return max(5, int(raw))
    except ValueError:
        return 30


def _resolve_effective_mode(
    args: argparse.Namespace,
) -> str:
    """One of: combined, telegram, dry_check, trade."""
    if args.telegram_with_live or args.serve:
        return "combined"
    if args.telegram:
        return "telegram"
    if args.dry_check:
        return "dry_check"
    em = _run_mode_from_env()
    if em in ("combined", "serve", "telegram-with-live", "full", "production"):
        return "combined"
    if em in ("telegram", "tg", "bot-only", "bot_only"):
        return "telegram"
    if em in ("dry-check", "dry_check", "preflight", "check"):
        return "dry_check"
    if em in ("trade", "engine", "trading", "live-only", "live_only"):
        return "trade"
    return "trade"


def _configure_logging() -> None:
    raw = os.getenv("MATRYOSHKA_LOG_LEVEL", "INFO").strip().upper()
    level = getattr(logging, raw, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    if level <= logging.DEBUG and not _parse_env_truthy(os.getenv("MATRYOSHKA_HTTP_DEBUG")):
        for name in ("urllib3", "urllib3.connectionpool", "pybit", "pybit._http_manager"):
            logging.getLogger(name).setLevel(logging.INFO)


def _parse_env_truthy(raw: str | None) -> bool:
    if raw is None or not str(raw).strip():
        return False
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Matryoshka Bybit trader (Demo Trading по умолчанию; см. BYBIT_DEMO_TRADING в .env)"
    )
    parser.add_argument(
        "--dry-check",
        action="store_true",
        help="Run preflight checks only (API, wallet, constraints, leverage profile)",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--telegram",
        action="store_true",
        help="Run Telegram audit bot with inline level-check buttons (trading engine not started)",
    )
    mode.add_argument(
        "--telegram-with-live",
        action="store_true",
        help="Run Telegram bot and live trading engine in one process (engine loop in a background thread)",
    )
    mode.add_argument(
        "--serve",
        action="store_true",
        help="Production alias: same as --telegram-with-live (Telegram + engine in one process)",
    )
    return parser


def _run_live_engine_forever(settings: BotSettings) -> None:
    from matryoshka_bot.trading.engine import LiveTradingEngine

    backoff = _engine_restart_backoff_seconds()
    while True:
        try:
            engine = LiveTradingEngine(settings=settings)
            engine.run_forever(sleep_seconds=settings.loop_interval_seconds)
            _LOGGER.warning("LiveTradingEngine.run_forever returned unexpectedly; restarting in %ss", backoff)
        except Exception:
            msg = "[LiveTradingEngine] поток упал — см. трассировку ниже. Перезапуск через %ss.\n" % backoff
            sys.stderr.write(msg)
            traceback.print_exc(file=sys.stderr)
            _LOGGER.exception("LiveTradingEngine crashed; restarting in %s seconds", backoff)
        time.sleep(backoff)


def main() -> None:
    args = build_parser().parse_args()

    settings = load_settings()
    _configure_logging()
    mode = _resolve_effective_mode(args)

    if mode == "combined":
        if not settings.telegram_bot_token:
            raise RuntimeError(
                "TELEGRAM_BOT_TOKEN is required for combined mode (--serve / --telegram-with-live / MATRYOSHKA_RUN_MODE=combined)"
            )
        if not settings.bybit_api_key or not settings.bybit_api_secret:
            raise RuntimeError(
                "BYBIT_API_KEY and BYBIT_API_SECRET are required for combined mode (--serve / MATRYOSHKA_RUN_MODE=combined)"
            )
        from matryoshka_bot.telegram_bot.app import run_telegram_bot

        thread = threading.Thread(
            target=_run_live_engine_forever,
            args=(settings,),
            name="LiveTradingEngine",
            daemon=True,
        )
        thread.start()
        run_telegram_bot(settings=settings)
        return

    if mode == "telegram":
        from matryoshka_bot.telegram_bot.app import run_telegram_bot

        run_telegram_bot(settings=settings)
        return

    if mode == "dry_check":
        from matryoshka_bot.trading.preflight import print_preflight_report, run_preflight

        if not settings.bybit_api_key or not settings.bybit_api_secret:
            raise RuntimeError("Dry check requires BYBIT_API_KEY and BYBIT_API_SECRET")
        report = run_preflight(settings=settings)
        print_preflight_report(report)
        return

    if not settings.bybit_api_key or not settings.bybit_api_secret:
        raise RuntimeError("Live mode requires BYBIT_API_KEY and BYBIT_API_SECRET")

    from matryoshka_bot.trading.engine import LiveTradingEngine

    engine = LiveTradingEngine(settings=settings)
    engine.run(
        iterations=settings.loop_iterations,
        sleep_seconds=settings.loop_interval_seconds,
    )


if __name__ == "__main__":
    main()
