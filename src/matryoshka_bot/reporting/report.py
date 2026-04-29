from __future__ import annotations

import json
from pathlib import Path

from matryoshka_bot.journal.store import JournalStore
from matryoshka_bot.reporting.metrics import compute_metrics


def main() -> None:
    store = JournalStore()
    pnls = store.read_trade_pnls()
    metrics = compute_metrics(pnls)
    print(json.dumps(metrics, indent=2))
    Path("logs/strategy_report.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
