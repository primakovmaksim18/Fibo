from pathlib import Path

from matryoshka_bot.reporting.level_charts import render_symbol_audit_charts

SYMBOL = "BTCUSDT"
OUT_DIR = Path("artifacts") / "level-charts"


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for old in OUT_DIR.glob("*.jpeg"):
        old.unlink()
    generated, context = render_symbol_audit_charts(symbol=SYMBOL, out_dir=OUT_DIR)

    print("Generated files:")
    print(f"Binance {SYMBOL} ATL={context.atl} ATH={context.ath}")
    for p in generated:
        print(p.as_posix())


if __name__ == "__main__":
    main()
