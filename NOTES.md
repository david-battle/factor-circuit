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
 6 |         18 |  10 |   19 |   9  | ABC + ODC windowed resynthesis
 7 |         37 |  11 |   74 |  63  | ABC + ODC windowed resynthesis
 8 |         76 |  10 |  208 | 198  | ABC + ODC windowed resynthesis
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

**N=6 results:** ABC baseline 90 gates → **19 gates** (79% reduction).

**N=7 results:** ABC baseline 229 gates → **74 gates** (68% reduction).

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

## Session: Larger Window Experiment (Aug 19, 2026)

### Motivation

Previous windowed resynthesis used max_inputs=6, max_outputs=3,
max_gates=15. DESIGN.md noted larger windows cause SAT timeouts due to
one-hot encoding scaling. Wanted to test whether a modest gate increase
(max_gates 15→20, same I/O bounds) could find deeper improvements without
hitting the scaling wall.

### Changes Made

- **`window_opt.py`**: Changed default `max_gates` from 15 to 20 in both
  `optimize_circuit()` signature and CLI defaults. (Lines 992, 1123.)
  CLI flags `--max-in`, `--max-out`, `--max-gates` already existed for
  overriding.

### Results

**N=7 smoke test** (factor7_opt_final.blif, 133 gates):
- 200 iterations, max_gates=20
- **133 → 128 AND gates** (5 saved, 4 improvements)
- No SAT timeouts — all solves completed within budget
- Improvements found at iterations 10, 51, 101, 154 (small windows:
  3–6 gates within the 20-gate budget)
- Conclusion: larger gate budget doesn't cause timeout issues; solver
  handles it comfortably

**N=8 full run** (factor8_opt_final.blif, 347 gates):
- 200 iterations, max_gates=20
- **347 → 346 AND gates** (1 saved, 1 improvement)
- Nearly every SAT solution failed verification — hundreds of failures,
  most getting 70–75/76 care points correct but not all
- The one success was a trivial 5→4 gate reduction at iteration 151
- Conclusion: the solver finds SAT solutions readily, but they almost
  all fail post-splice verification

### Diagnosis: Verification Failure Pattern

The systematic nature of the failures (70–75/76 correct, not random)
suggests a bug or structural issue, not just bad luck. Key observations:

1. SAT solver returns valid models (satisfies all CNF clauses)
2. Models decode to valid gate circuits
3. After splice + prune, verify_circuit() reports 70–75/76 correct
4. The same window with max_gates=15 (previous sessions) also showed
   frequent verification failures on N=8, but had more successes
   because the circuit was larger (567→347 over 10 passes)

Possible causes under investigation:
- **ODC care set over-approximation**: The ODC loop uses `care_set[in].add(out)`
  (set union across care points sharing an in_pattern). If two care points
  have the same window-input pattern but different allowed output patterns,
  the union is larger than the intersection. The SAT solver can then pick
  a pattern that satisfies one care point but not the other. The correct
  approach is to intersect allowed sets across care points with the same
  in_pattern.
- **eval_order / fanout cone correctness**: The fanout cone traces forward
  from W_out through BUF/NOT/AND. Nodes in the cone but not in W_out are
  re-simulated. Need to verify that re-simulated values are consistent
  with what the spliced circuit actually computes.

A diagnostic script (`diagnose_odc.py`) was written to compare the SAT
solution's output against the original circuit's output per care point,
but the session ended before the root cause was conclusively identified.

### Impact Assessment

The verification failure issue predates the max_gates increase — it also
occurred with max_gates=15 on N=8. The larger gate budget just makes it
more visible because more SAT solutions are found (and more fail). The
root cause likely affects all window sizes and all N values, but is masked
at smaller N where fewer care points share the same in_pattern.

**Next steps:**
1. Fix the ODC union→intersection bug if confirmed
2. Re-run N=8 with corrected ODC
3. Then retry larger windows (max_gates=20+) to see if they help

## Session: ODC Intersection Fix (Aug 19, 2026)

### Root Cause Confirmed and Fixed

The ODC care set over-approximation bug was the primary cause of
verification failures. When multiple care points share the same
`in_pattern` (window-input values) but have different global requirements,
the old code unioned their allowed output sets via `care_set[in].add(out)`.
This let the SAT solver pick an output valid for one care point but not
another with the same inputs.

**Fix** (`window_opt.py:317-354`): Collect per-care-point allowed sets in
`per_point[in_pattern][(x,p,q)]`, then intersect across care points:
```python
care_set[in_pattern] = sets[0].intersection(*sets[1:])
```

### Results — Dramatic Improvement

Re-ran windowed resynthesis with corrected ODC on all N values:

**N=6** (factor6_opt_final.blif, 90 gates):
- 200 iterations, max_gates=25
- **90 → 19 AND gates** (79% reduction, 20 improvements)
- Previous best was 20 (off by 1)

**N=7** (factor7_opt_final.blif, 133 gates):
- Pass 1 (seed=42, 200 iter): 133 → 80 (34 improvements)
- Pass 2 (seed=999, 300 iter): 80 → 74 (5 improvements)
- Pass 3 (seed=5555, 300 iter): 74 → 74 (0 improvements, plateau)
- **Final: 74 AND gates** (44% reduction from previous best of 90)

**N=8** (factor8_opt_final.blif, 347 gates):
- Pass 1 (seed=42, 200 iter, max_gates=20): 347 → 240 (56 improvements)
- Pass 2 (seed=1337, 200 iter, max_gates=30, max_out=4): 240 → 227 (9)
- Pass 3 (seed=2026, 200 iter, max_gates=30, max_out=4): 227 → 212 (9)
- Pass 4 (seed=314, 200 iter): 212 → 209 (3)
- Pass 5 (seed=7777, 300 iter): 209 → 208 (1, plateau)
- **Final: 208 AND gates** (40% reduction from previous best of 347)

### Updated Results Table

```
N  | Semiprimes | LB  | UB   | Gap  | UB Source
---|------------|-----|------|------|-------------------------------
 4 |          4 |   1 |    1 |   =  | SAT exact synthesis (proven)
 5 |          7 |   4 |    4 |   =  | SAT exact synthesis (proven)
 6 |         18 |  10 |   19 |   9  | ABC + corrected ODC windowed resynth
 7 |         37 |  11 |   74 |  63  | ABC + corrected ODC windowed resynth
 8 |         76 |  10 |  208 | 198  | ABC + corrected ODC windowed resynth
```

### Key Observations

1. **The intersection fix was critical.** Pre-fix, nearly every SAT
   solution on N=8 failed verification (70-75/76 correct). Post-fix,
   56 out of ~200 iterations produced verified improvements.

2. **Larger windows help with corrected ODC.** Bumping max_gates to 30
   and max_out to 4 found improvements that smaller windows missed,
   though with diminishing returns.

3. **N=7 improved more than N=8 proportionally.** N=7 went from 90→74
   (18% improvement) while N=8 went from 347→208 (40% improvement).
   The bug disproportionately affected N=8 because more care points
   share the same in_pattern (76 vs 37).

4. **Still some verification failures remain** (e.g. 75/76, 73/76
   correct). These are correctly rejected. They represent cases where
   the SAT solver finds a valid circuit for the CNF but the splice
   introduces subtle interactions with downstream gates. The rate of
   failures is much lower than before the fix.

### What's Left To Do

**High priority:**
- ~~Incremental SAT for LB binary search~~ — REJECTED.
- Run N=9, N=10 UB surveys (zero implementation effort)

**Medium priority:**
- Even larger windows (max_inputs=7+ requires smaller SAT encoding)
- Investigate remaining verification failures (75/76 correct patterns)

**Low priority:**
- Investigate growth rate of UB/LB with N
- Depth optimization (currently only gate count)
- N=6 LB proving (gap is now only 9 — might be provable with better encoding)

**Tried and failed:**
- Binary selector encoding: fewer variables and clauses but slower to solve.
  Do not revisit without a fundamentally different approach.
- Sequential counter (Sinz 2005) for at-most-one: Replaced pairwise O(n²)
  AMO clauses with O(n) sequential counter. Clause count dropped ~37%
  but solver got dramatically slower. Pairwise AMO's redundant clauses
  provide free unit propagation that CDCL solvers exploit heavily.
  Compact AMO encodings weaken propagation and hurt performance more
  than they help clause count.
