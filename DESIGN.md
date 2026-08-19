# Design Document

## Overview

Three complementary approaches to finding small factoring circuits:

1. **SAT exact synthesis** (`survey.py` LB phase): Proves lower bounds by
   showing no k-gate circuit exists. It proves N=4 and N=5 optimal, proves
   N=6 has LB≥11 (`k=10` UNSAT), and then hits scaling limits on larger
   exact searches.

2. **SAT-based windowed resynthesis** (`window_opt.py`): Constructs upper
   bounds by taking an ABC-optimized circuit and iteratively replacing small
   subcircuits with SAT-proven optimal replacements.

3. **ABC heuristic synthesis** (`survey.py` UB phase): Generates initial
   upper-bound circuits via alternating dch/dc2 optimization pipelines.

---

## Implemented: Windowed Resynthesis (`window_opt.py`)

### Architecture

```
Load BLIF → AIG → [optimize_circuit loop] → Write BLIF
                         |
                    ┌────┴────┐
                    │ per iter │
                    └────┬────┘
                         │
            1. select_window()
            2. get_window_care_set()
            3. for k = 0..old-1:
                 build_window_cnf_tracked(k)
                 SAT solve
            4. decode_model()
            5. splice_window()
            6. prune() + has_cycle() check
            7. verify_circuit()
```

### AIG Representation

Nodes are stored in `aig.nodes` dict (name → type, args):
- `('PI', [])` — primary input
- `('CONST0', [])` / `('CONST1', [])`
- `('BUF', [src])` / `('NOT', [src])`
- `('AND', [src1, inv1, src2, inv2, inv_out])` — 2-input AND with
  complemented inputs and optional output inversion.

Free edges: inv1, inv2, inv_out are booleans. No explicit NOT nodes needed
for complemented inputs — matches ABC's AIG convention where inversions
cost nothing.

### Window Selection: `select_window()`

Topological growth from a random AND-gate seed:
1. Start with W_gates = {seed}.
2. Find adjacent AND gates (fanin via `trace_to_source`, fanout via
   `compute_fanout()`). Only AND gates are candidates — BUF/NOT are free.
3. Add first candidate where |W_in| <= max_inputs AND |W_out| <= max_outputs.
4. Stop when no candidate fits or max_gates reached.

Definitions:
- **W_in**: Boundary nodes feeding into W_gates but not in W_gates.
  Must be PIs or AND gates outside the window.
- **W_out**: Nodes produced by W_gates that are consumed outside W_gates
  or are primary outputs.

### Care Set Extraction: `get_window_care_set()`

Returns `dict[tuple(in_vals) -> set(tuple(out_vals))]`.

**SDC mode** (`--sdc`, currently working): For each global care point,
simulate the full circuit, record what W_in→W_out mapping the original
circuit produces. Each input pattern maps to exactly one output pattern.

**ODC mode** (default, working): For each care point and each of
2^|W_out| possible output patterns, re-simulate the fanout cone of W_out
with the trial output values, check if global outputs still match. Allows
multiple output patterns per input pattern, giving SAT more freedom.

### SAT Encoding: `build_window_cnf_tracked(I, O, care_list, k)`

One-hot selector encoding:
- **Gate sources**: For each of k gates, two inputs, each selects from
  ["const0"] + I inputs + (g-1) prior gates via one-hot selector.
- **Inversion**: One boolean per gate input.
- **Symmetry breaking**: source(input0) <= source(input1).
- **Gate values**: `sig[g][t]` = gate g output on care point t, computed
  as AND of its two selected+inverted inputs.
- **Output sources**: Each of O outputs selects from all available sources.
- **ODC constraints**: For each care point, forbid output patterns not in
  the allowed set (list of disallowed pattern clauses).

Variables: ~3000 for typical windows (I=6, O=3, k=15, C=37).
Clauses: ~8000-12000. Current runs use python-sat with the `cd153` solver.

### Splicing: `splice_window()`

1. Remove old W_gates from aig.nodes.
2. Add new SAT-synthesized internal gates with fresh prefix names.
3. Rewrite W_out node definitions (keeping original names so downstream
   references remain valid).
4. `aig.prune()` removes nodes not reachable from outputs.
5. `aig.has_cycle()` detects cycles (reverts splice if found).

### Verification: `verify_circuit()`

Simulate the AIG for all N-bit semiprimes. Check that p and q outputs
match the expected factors. Bit mapping: `input_vals = {f"x{i}": (x >> i) & 1}`.

### CLI

```
python3 window_opt.py <blif> [N] [iterations] [--sdc] [--seed S] \
    [--max-in I] [--max-out O] [--max-gates G]
```

Defaults: N=6, 200 iterations, ODC mode, max_inputs=6, max_outputs=3,
max_gates=20.

### Status: ODC Fixed (two bugs)

**Bug 1 — W_gates in eval_order:** The fanout-cone re-simulation excluded
W_gates from `eval_order`, so downstream nodes that depended on both W_out
and a W_gate were re-simulated with stale W_gate values. Fix: include
W_gates in `eval_order`. Validated by brute-force comparison on 20 random
windows (N=6, all matched).

**Bug 2 — care set over-approximation:** When multiple care points share
the same `in_pattern` (window-input values) but have different global
requirements, the old code unioned their allowed output sets via
`care_set[in].add(out)`. This let the SAT solver pick an output valid for
one care point but not another. Fix (`window_opt.py:317-354`): collect
per-care-point allowed sets, then intersect:
`care_set[in_pattern] = sets[0].intersection(*sets[1:])`.

Impact of Bug 2 fix: N=8 UB dropped from 347 → 208 gates (40%); N=7 from
90 → 74 gates (18%); N=6 from 20 → 19 gates (5%).

---

## Implemented: Survey Tool (`survey.py`)

### UB Phase

1. `generate_blif(N, care, path)`: Creates a sparse BLIF with one `.names`
   per output listing the care-point patterns that produce a 1.
2. Runs a battery of ABC optimization strategies:
   - Single-pass strategies (24 variants with dc2, dch, resub, mfs2, etc.)
   - Iterated single pipelines (up to 10 passes each)
   - Alternating dch+dc2 pipelines (up to 30 passes, no_improve>=8 stop)
3. Tracks best AND-gate count and its BLIF file.

Best ABC strategy for N=7: alternating
`dch; dc2; rewrite; refactor; balance; resub` with
`dc2; rewrite; refactor; balance; resub`, ~10 passes.
Achieved 229 gates from raw 372 (after strash).

### LB Phase

Binary search on k (number of AND gates). For each k:
1. `build_cnf(N, care, k)`: One-hot selector encoding identical in
   structure to window_opt.py but with N inputs, 2N outputs, and all
   care points as constraints.
2. Solve with budget-based `conf_budget()` / `solve_limited()` (5000
   conflicts per round, 30s timeout).
3. If UNSAT → no k-gate circuit exists. If SAT → k is an upper bound.

Performance with optimizations (skip constant-0 outputs, gate symmetry
breaking):

| k   | Clauses | Time (N=7) |
|-----|---------|------------|
| 10  | 39,280  | 3.5s       |
| 11  | 44,824  | 42.5s      |
| 12  | 50,727  | >10min     |

---

## Implemented: Exact Synthesis (N=4, N=5, N=6)

### `survey.py`

Proves the small exact lower bounds: N=4 optimal at 1 AND gate and N=5
optimal at 4 AND gates. For N=6, it proves k=9 and k=10 UNSAT, establishing
LB≥11.

### `exact_n6_from_above.py` / `run_n6_sweep.py`

Current N=6 exact-synthesis and sweep helpers. They start from the corrected
lower-bound region and try to close the gap between LB≥11 and the 19-gate UB.

### `exact_factor6_budget.py`

Legacy N=6 budget-based SAT experiment using `conf_budget()` /
`solve_limited()`. It is retained for comparison, but is not an N=7 proof
source.

---

## Tried and Failed: Binary Selector Encoding

**Result:** Fewer variables and clauses than one-hot, but the SAT solver
takes longer to solve. Do not revisit without a fundamentally different
approach.

## Rejected: Incremental SAT for LB

Currently `survey.py` rebuilds the entire CNF from scratch for each k.
python-sat supports incremental solving. However, this was rejected: most
time is spent on higher k values (by an order of magnitude), so savings
from clause reuse across binary search steps would be minimal. The
bottleneck is encoding size at high k, not the search structure.

## Implemented: Larger Windows

Default CLI window parameters are 6 inputs, 3 outputs, and 20 gates. The corrected
ODC care set (intersection instead of union) prevents verification failures
that previously plagued larger windows. Larger windows find deeper
optimizations: N=8 dropped from 347 → 208 gates in the best recorded
multi-pass run. Typical solve times remain under 1s per window.

Even larger windows (7+ inputs) still cause SAT timeouts due to one-hot
encoding scaling.

## Partially Implemented: Higher N

N=8 survey completed: 535 gates from ABC, reduced to 208 via windowed
resynthesis. LB=10 (same one-hot clause wall as N=7). N=9 and N=10
surveys not yet run. UB phase works; LB will hit walls early but even
partial LBs are useful for growth-rate analysis.
