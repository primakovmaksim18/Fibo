from __future__ import annotations

import argparse
import threading

from matryoshka_bot.config.settings import BotSettings, load_settings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Matryoshka Bybit live trader")
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
    return parser


def _run_live_engine_forever(settings: BotSettings) -> None:
    from matryoshka_bot.trading.engine import LiveTradingEngine

    engine = LiveTradingEngine(settings=settings)
    engine.run_forever(sleep_seconds=settings.loop_interval_seconds)


def main() -> None:
    args = build_parser().parse_args()

    settings = load_settings()
    if args.telegram_with_live:
        if not settings.telegram_bot_token:
            raise RuntimeError("TELEGRAM_BOT_TOKEN is required for --telegram-with-live")
        if not settings.bybit_api_key or not settings.bybit_api_secret:
            raise RuntimeError("Live mode requires BYBIT_API_KEY and BYBIT_API_SECRET for --telegram-with-live")
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

    if args.telegram:
        from matryoshka_bot.telegram_bot.app import run_telegram_bot

        run_telegram_bot(settings=settings)
        return

    if args.dry_check:
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
