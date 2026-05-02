"""CLI shape for matryoshka_bot.main (no network)."""

from matryoshka_bot.main import build_parser


def test_telegram_with_live_flag_parsed() -> None:
    args = build_parser().parse_args(["--telegram-with-live"])
    assert args.telegram_with_live is True
    assert args.telegram is False
    assert args.serve is False


def test_serve_flag_parsed() -> None:
    args = build_parser().parse_args(["--serve"])
    assert args.serve is True
    assert args.telegram_with_live is False


def test_telegram_mutually_exclusive_with_telegram_with_live() -> None:
    parser = build_parser()
    err = None
    try:
        parser.parse_args(["--telegram", "--telegram-with-live"])
    except SystemExit as e:
        err = e
    assert err is not None


def test_help_includes_telegram_with_live() -> None:
    parser = build_parser()
    help_text = parser.format_help()
    assert "--telegram-with-live" in help_text
    assert "--serve" in help_text


def test_telegram_mutually_exclusive_with_serve() -> None:
    parser = build_parser()
    err = None
    try:
        parser.parse_args(["--telegram", "--serve"])
    except SystemExit as e:
        err = e
    assert err is not None
