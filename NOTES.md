# Project Notes — Catch-Up Summary

## What This Project Is

We are experimentally investigating whether integer factoring has
surprisingly small Boolean circuits. For each bit-width N, we build a
combinational circuit that maps an N-bit semiprime directly to its two
prime factors. Non-semiprime inputs are don't-cares.

**Results so far:**

```
N  | Semiprimes | LB  | UB   | Gap  | UB Source
---|------------|-----|------|------|-------------------------------
 4 |          4 |   1 |    1 |   =  | SAT exact synthesis (proven)
 5 |          7 |   4 |    4 |   =  | SAT exact synthesis (proven)
 6 |         18 |  10 |   20 |  10  | ABC + ODC windowed resynthesis
 7 |         37 |  11 |   90 |  79  | ABC + ODC windowed resynthesis
 8 |         76 |  10 |  347 | 337  | ABC + ODC windowed resynthesis
```

## How We Got Here — Chronological Summary

### Phase 1: ABC Exploration (early sessions)

Started by feeding factoring specifications into ABC as sparse BLIF files.
For N=4, ABC found a 14-gate circuit (later proven suboptimal). For N=7,
ABC's best was 267 gates with basic strategies.

Key ABC finding: **alternating `dch` and `dc2` pipelines** breaks through
single-pipeline plateaus. `dch` and `dc2` exploit different structural
redundancies. This pushed N=7 ABC UB from 267 → 246 → 225 gates.

### Phase 2: SAT Exact Synthesis (middle sessions)

Built custom SAT encoders (`exact_factor4.py`, `exact_factor6_budget.py`)
that prove circuit-size lower bounds. Encoding: one-hot source selectors,
gate symmetry breaking, skip constant-0 outputs.

- N=4: Proved optimal at 1 AND gate.
- N=5: Proved optimal at 4 AND gates.
- N=6: Proved LB=10 (k=10 SAT, k=9 UNSAT).
- N=7: Proved LB=11 (k=11 solvable at ~42s; k=12 hits 50K clause wall).

The one-hot encoding scales as O(k² × C) clauses. For N=7 (C=37 care
points), k=12 requires ~51K clauses — beyond what Glucose4 can handle
in reasonable time. This is the fundamental scalability bottleneck.

### Phase 3: Windowed Resynthesis (recent sessions)

Implemented `window_opt.py` (~1166 lines) — a SAT-based tool that takes
an ABC-optimized circuit and iteratively replaces small subcircuits with
SAT-proven optimal replacements.

**How it works:**
1. Select a random window (up to 6 inputs, 3 outputs, 15 gates).
2. Extract care set: for each of the ~37 care points, observe what the
   original circuit produces at window inputs/outputs.
3. Try k=0,1,2,... gates — ask SAT for a circuit that produces the same
   outputs for the same inputs.
4. If found with fewer gates, splice it in and verify.
5. Repeat hundreds of times.

**N=6 results:** ABC baseline 90 gates → **20 gates** (78% reduction).

**N=7 results:** ABC baseline 229 gates → **90 gates** (61% reduction).

**Key limitation:** Window size is bounded by SAT encoding size. With 7+
inputs or 4+ outputs, the SAT solver times out. This is the same one-hot
encoding bottleneck as the LB approach.

### Phase 4: Bug Fixes and Infrastructure (most recent)

- **Fixed BLIF input ordering**: `survey.py`'s `generate_blif()` listed
  inputs as `x0 x1...` (ascending), making x0=MSB in truth tables. But
  all simulation code assumes `x_i` = bit i (LSB). Fixed to descending
  order. This was causing N=7 care-point verification to fail 31/37.
- **Added CLI flags**: `--max-in`, `--max-out`, `--max-gates`, `--sdc`,
  `--seed` to `window_opt.py`.
- **Added AIG methods**: `prune()` (remove unreachable nodes), `has_cycle()`
  (DFS cycle detection), robust `toposort()` (handles missing nodes).

### Phase 5: ODC Fix and UB Improvement

- **Fixed ODC mode** in `window_opt.py`: Removed W_gates exclusion from
  `eval_order` so downstream nodes depending on both W_out and W_gates are
  re-simulated with correct (updated) W_gate values. Validated by
  brute-force comparison on 20 random windows at N=6.
- **Re-ran windowed resynthesis** with ODC enabled, chaining multiple passes
  with different seeds:
  - N=6: 25 → **20** gates (78% reduction from ABC baseline)
  - N=7: 133 → **90** gates (61% reduction from ABC baseline)
- Plateaued at these values — further passes with different seeds produced
  0 improvements, suggesting near the limit of current window constraints.

## ODC Bug — Fixed

The previous bug was that the fanout-cone re-simulation excluded W_gates from
`eval_order`, so downstream nodes that depended on both W_out and a W_gate
were re-simulated with stale W_gate values. Fix: include W_gates in
`eval_order` (window_opt.py:313). Validated by brute-force comparison on 20
random windows at N=6 — all matched the gold-standard full-circuit
re-simulation.

## Key Technical Insights

1. **Don't-care ratio is enormous.** For N=7: 37 care points out of 128
   inputs. For N=6: 18 out of 64. This is why windowed resynthesis works
   so well — local windows have massive freedom.

2. **One-hot encoding is the bottleneck** for both LB proving and larger
   window sizes. Binary selector encoding could fix this.

3. **Windowed resynthesis plateaus.** Once the circuit is small, random
   windows rarely find overlapping structures that can be further
   compressed. Larger windows would help but SAT can't handle them yet.

4. **ABC is good but not optimal.** ABC's global heuristics find decent
   circuits (229 for N=7) but windowed resynthesis can cut them by 61-78%.

## Session: N=8 Attempt (Aug 19, 2026 ~12:13)

Started N=8 exploration. 76 semiprimes to factor.

### N=8 UB Survey

Running `survey.py 8 600 60` to get initial ABC upper bound.
76 semiprimes, 256 total inputs. Don't-care ratio: 76/256 = 29.7%.

**Result: UB=535 AND gates.** ABC plateaued at 535 for all 172 rounds
with alternating dch/dc2 pipeline. No improvement over 10 minutes.

### N=8 LB Attempt

SAT binary search with one-hot encoding:
- k=0..10: UNSAT (proven, k=10 took 2.5s)
- k=11: TIMEOUT (clause wall hit)

**Result: LB=10.** Same wall as N=7 — one-hot encoding scales O(k^2 * C)
and k=11 exceeds budget at ~50K clauses.

### N=8 Windowed Resynthesis

Now running `window_opt.py` on the best ABC BLIF to try to improve UB from 535.

**Results (10 passes, diminishing returns):**

| Pass | Seed | Gates | Saved |
|------|------|-------|-------|
| ABC baseline | — | 567 | — |
| 1 | 42 | 419 | 148 |
| 2 | 123 | 399 | 20 |
| 3 | 777 | 386 | 13 |
| 4 | 999 | 375 | 11 |
| 5 | 2026 | 373 | 2 |
| 6 | 4242 | 362 | 11 |
| 7 | 314 | 351 | 11 |
| 8 | 1337 | 351 | 0 |
| 9 | 2718 | 349 | 2 |
| 10 | 5555 | 347 | 2 |

**Final UB: 347 AND gates** (39% reduction from ABC baseline of 567).
Note: ABC raw output was 535 gates, but strash to 2-input AIG inflated to 567.

### N=8 Summary

```
N=8 | LB=10 | UB=347 | gap=337
```

Comparison with smaller N:
```
N  | Semiprimes | LB  | UB   | Gap  | UB Source
---|------------|-----|------|------|-------------------------------
 4 |          4 |   1 |    1 |   =  | SAT exact synthesis (proven)
 5 |          7 |   4 |    4 |   =  | SAT exact synthesis (proven)
 6 |         18 |  10 |   20 |  10  | ABC + ODC windowed resynthesis
 7 |         37 |  11 |   90 |  79  | ABC + ODC windowed resynthesis
 8 |         76 |  10 |  347 | 337  | ABC + ODC windowed resynthesis
```

The UB/LB gap is exploding. Both UB and LB need better techniques
(binary selector encoding) to make progress.

### What's Left To Do

**High priority:**
- ~~Incremental SAT for LB binary search~~ — REJECTED: Most time is spent
  on higher k values (by an order of magnitude or more), so savings from
  incremental clause reuse across binary search steps would be minimal.
  The bottleneck is the encoding size at high k, not the search structure.

**Medium priority:**
- Larger windows (need smaller window SAT encoding)
- Run N=9, N=10 UB surveys (zero implementation effort)

**Low priority:**
- Investigate growth rate of UB/LB with N
- Depth optimization (currently only gate count)

**Tried and failed:**
- Binary selector encoding: fewer variables and clauses but slower to solve.
  Do not revisit without a fundamentally different approach.
- Sequential counter (Sinz 2005) for at-most-one: Replaced pairwise O(n²)
  AMO clauses with O(n) sequential counter in survey.py and
  exact_factor6_budget.py. Clause count dropped ~37% (e.g., k=10 N=6:
  30K→19K clauses) but solver got dramatically slower — k=10 for N=6
  (previously SAT in seconds) failed to complete in 120s. Pairwise AMO's
  redundant clauses provide free unit propagation that CDCL solvers exploit
  heavily. Compact AMO encodings weaken propagation and hurt performance
  more than they help clause count.
