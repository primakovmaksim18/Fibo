from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class JournalStore:
    def __init__(self, base_dir: str = "logs") -> None:
        self.base_path = Path(base_dir)
        self.base_path.mkdir(parents=True, exist_ok=True)
        self.signals_path = self.base_path / "signals.jsonl"
        self.trades_path = self.base_path / "trades.jsonl"
        self.events_path = self.base_path / "events.jsonl"

    def log_signal(self, payload: dict[str, Any]) -> None:
        self._append(self.signals_path, payload)

    def log_trade(self, payload: dict[str, Any]) -> None:
        self._append(self.trades_path, payload)

    def log_event(self, payload: dict[str, Any]) -> None:
        self._append(self.events_path, payload)

    def read_trade_pnls(self) -> list[float]:
        if not self.trades_path.exists():
            return []
        values: list[float] = []
        for raw in self.trades_path.read_text().splitlines():
            if not raw.strip():
                continue
            row = json.loads(raw)
            if "pnl" in row:
                values.append(float(row["pnl"]))
        return values

    def _append(self, path: Path, payload: dict[str, Any]) -> None:
        row = {
            "ts": datetime.now(UTC).isoformat(),
            **payload,
        }
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=True) + "\n")
