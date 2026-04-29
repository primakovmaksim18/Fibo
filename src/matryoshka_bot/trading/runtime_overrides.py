from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from matryoshka_bot.config.settings import BotSettings

DEFAULT_STATE_PATH = Path("state") / "telegram_trading.json"


@dataclass
class TelegramTradingState:
    trading_paused: bool = False
    base_risk_pct_override: float | None = None


def load_telegram_trading_state(path: Path | str = DEFAULT_STATE_PATH) -> TelegramTradingState:
    p = Path(path)
    if not p.exists():
        return TelegramTradingState()
    data = json.loads(p.read_text(encoding="utf-8"))
    return TelegramTradingState(
        trading_paused=bool(data.get("trading_paused", False)),
        base_risk_pct_override=_parse_optional_float(data.get("base_risk_pct_override")),
    )


def save_telegram_trading_state(state: TelegramTradingState, path: Path | str = DEFAULT_STATE_PATH) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(asdict(state), indent=2), encoding="utf-8")
    tmp.replace(p)


def _parse_optional_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str) and value.strip() in ("", "null"):
        return None
    return float(value)


def effective_base_risk_pct(settings: BotSettings, state: TelegramTradingState | None = None) -> float:
    s = state if state is not None else load_telegram_trading_state()
    if s.base_risk_pct_override is not None:
        return s.base_risk_pct_override
    return settings.base_risk_pct
