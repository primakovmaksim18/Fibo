# Matryoshka levels (reference for other systems)

Portable description of **how Fibonacci grids are built** in this bot and **how roles / strength / priority map to trading**. Use this doc when wiring the same idea into another engine or discretionary framework — without coupling to Telegram or execution.

---

## 1. Source interval (global anchoring)

- **High bound:** historic **ATH** (all‑time high)  
- **Low bound:** historic **ATL** (all‑time low)  
- Requirement: **`ATH > ATL`** (positive range).

Everything is subdivided **inside this single `[ATL, ATH]` segment** (static grid, not a rolling swing).

---

## 2. Canonical Fibonacci percentages (per cell)

Each cell applies the **same** fixed ratio set **in left‑to‑right order** (`0 → 100` along the interval low → high):

`0`, `23.6`, `38.2`, `50`, `61.8`, `78.6`, `100` (percent inside the cell).

For endpoints `start`, `end` of a cell (with `end > start`):

`level = round(start + (end - start) * (pct / 100), 6)`

---

## 3. Recursive “Matryoshka” construction (`order`)

- **Order 1:** run the percentages once on **`[ATL, ATH]`**.  
  Output: sorted list `L₁` (same as subdividing ATL‑ATH into the standard ratios).

- **Order k (k ≥ 2):** walk **every adjacent pair** `(L[k-1][i-1], L[k-1][i])` from the previous level’s list that has positive width. Inside each pair, compute the **same seven ratios** again. Collect all prices → **sorted unique** → `L[k]`.

- **Maximum order** is **`depth`** (integer ≥ 1). The structure stores **`by_order[1] … by_order[depth]`**.

Higher `order` = **finer subdivision** nested inside intervals produced at the previous order.

Implementation reference: `src/matryoshka_bot/strategy/levels.py` (`build_levels_by_order`, `build_fib_structure`).

---

## 4. Dynamic depth (`depth` = how many nesting steps)

Chosen from **one daily bar** for the instrument:

- **`daily_range_pct = 100 × (day_high - day_low) / day_close`**
- **If `daily_range_pct > 10`** → **`depth = 4`**
- **Else** → **`depth = 5`**

So on very wide days the tree stops one step earlier (slightly coarser grid).

Reference: `src/matryoshka_bot/strategy/regime.py` (`choose_depth`).

---

## 5. Unified price list

- **`all_levels`** = **union** of all prices from `by_order[1] … by_order[depth]`, then **sorted** and **deduplicated** (same price from different orders appears once).

This list is used to **bucket spot price** between two neighbours (current segment bracket).

Segment lookup: bisect‑style — find the pair of consecutive `all_levels` that bracket the traded price (`locate_segment` in `strategy/segment.py`).

---

## 6. Trading roles in this codebase (Fib 1 vs 2 vs 3)

The bot **fixes semantic mapping**:

| Structural layer (`order`) | Name in docs / signals | Typical role |
|----------------------------|------------------------|--------------|
| `1` | **Fib 1** | Macro structure relative to ATH/ATL; combined with **`D1` + `H4`** to define **bias / trend context** (not primary entry ladders by themselves). |
| `2` | **Fib 2** | Entry grid (bounce / breakout candidates). |
| `3` | **Fib 3** | Finer entry grid (same signal family as Fib 2). |

**Execution** only considers **Fib 2** and **Fib 3** levels for triggers; **Fib 1** frames direction, not the tick‑level ladder for entries.

---

## 7. Strength and priority (senior → junior)

Use this ordering when two ideas conflict (e.g. discretionary filter or a second system):

1. **Session / risk controls** (outside this file) — always win.  
2. **Fib 1 structural bias** (**D1 + H4** aligned with Fib 1) — strongest **directional** prior: trade **with** it unless you explicitly allow strong counter‑trend rules.  
3. **Fib 2 levels** — **stronger entry tier** than Fib 3 in this strategy (coarser nesting = anchors closer to intermediate structure).  
4. **Fib 3 levels** — **most granular** entry tier; treat as refinement inside the same global matryoshka.

When the **same price** appears after deduplication in `all_levels`, the implementation **does not** retain which order coined it inside that merged number — signal code uses **`fib2_levels`** / **`fib3_levels`** separately for tagging entries. Prefer **Fib 2** labelling logic when migrating logic elsewhere if a collision must be resolved.

---

## 8. Numeric example (micro)

`ATL = 0`, `ATH = 100`, `depth = 2`:

- **Order 1:** `0, 23.6, 38.2, 50, 61.8, 78.6, 100`
- **Order 2:** for each adjacent segment (e.g. `0–23.6`, `23.6–38.2`, …) run the same ratios; merge + unique + sort.

With **`depth = 5`**, orders 4 and 5 add very dense clusters near parent intervals.

---

## 9. What this document intentionally omits

- Signal filters (bounce/breakout, volume, RSI) — see `signals/` and `README.md`.
- Broker sizing, Telegram, journaling — unrelated to the **pure grid definition**.

For runtime dumps of grids per scan, see `logs/levels.jsonl` (`fib1_levels`, `fib2_levels`, `fib3_levels`, `all_levels_sorted_unique`).

**Графики в Telegram** (`reporting/level_charts.py`) — упрощённая визуализация первых трёх проходов от `ATL→ATH`; **торговые решения и логирование цикла** следуют `scan_symbol` → `FibStructure` с переменным `depth` (4 или 5). Для портирования логики в другую систему ориентируйтесь на `strategy/levels.py` и `strategy/scanner.py`, а не на код отрисовки.
