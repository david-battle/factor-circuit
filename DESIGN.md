# Design Document

## Overview

Two complementary approaches to finding small factoring circuits:

1. **SAT exact synthesis** (`survey.py` LB phase): Proves lower bounds by
   showing no k-gate circuit exists. Works for N<=5; hits a ~50K clause wall
   at k=12 for N=6+.

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
                 build_window_cnf(k)
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

**ODC mode** (default, currently broken): For each care point and each of
2^|W_out| possible output patterns, re-simulate the fanout cone of W_out
with the trial output values, check if global outputs still match. Allows
multiple output patterns per input pattern, giving SAT more freedom.

### SAT Encoding: `build_window_cnf(I, O, care_list, k)`

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
Clauses: ~8000-12000. Solves in <1s with Glucose4.

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
max_gates=15.

### Known Bugs

**ODC mode produces incorrect care sets.** A brute-force comparison shows
ODC rejects many output patterns that are actually valid (too conservative).
The ODC fanout-cone re-simulation only checks global output nodes in
`req.items()` but does not re-evaluate all nodes in the cone. Additionally,
the brute-force test itself may have a bug (it re-simulates window gates
with new output values, which changes their fanout incorrectly). This
contradicts earlier observations where ODC solutions failed verification.
Root cause unclear; needs investigation.

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

## Implemented: Exact Synthesis (N=4, N=6)

### `exact_factor4.py`

Proved N=4 optimal at 1 AND gate. Full enumeration: k=0 UNSAT, k=1 SAT.
Validated the SAT encoding approach. Only 4 of 16 inputs are care points;
massive don't-care freedom.

### `exact_factor6_budget.py`

Budget-based SAT solver for N=6 with `conf_budget()` / `solve_limited()`.
Established LB=10 for N=6 (k=10 SAT, k=9 UNSAT).

---

## Unimplemented: Binary Selector Encoding

The one-hot source selector is the main scalability bottleneck. For a gate
with s possible sources, one-hot uses s variables + s(s-1)/2 AMO clauses.
Binary encoding uses ceil(log2(s)) variables instead.

For k=20 with N=7 (s=28): 5 variables vs 28 per selector, eliminating the
quadratic AMO blowup. Tradeoff: more complex propagation clauses, but total
clause count drops substantially.

Expected impact: Push LB from 11 to ~15-20 for N=7. Make N=8+ LB tractable.
Also enables larger windows in window_opt.py (currently limited by SAT
encoding size).

## Unimplemented: Incremental SAT for LB

Currently `survey.py` rebuilds the entire CNF from scratch for each k.
python-sat supports incremental solving. A circuit with k gates is a strict
superset of k-1 gates — add one gate's variables/clauses and re-solve
without losing learned clauses.

Expected impact: Much faster LB binary search, especially for UNSAT proofs
where learned clauses at k transfer to k+1.

## Unimplemented: Larger Windows

Current window size (6 inputs, 3 outputs, 15 gates) limits optimization.
Larger windows (7+ inputs, 4+ outputs) cause SAT timeouts due to one-hot
encoding scaling. Requires binary selector encoding (above) or ODC fix
(to make SAT instances easier with larger don't-care sets).

## Unimplemented: ODC Fix

SDC mode is conservative (only the original output pattern is allowed per
input pattern). ODC mode allows multiple output patterns, giving SAT more
freedom. Currently ODC is broken — see Known Bugs above.

The correct approach: for each care point, re-simulate only the fanout cone
of W_out (downstream nodes that depend on W_out), checking that all global
output nodes still match their required values. Do NOT re-simulate W_gates
themselves (they're being replaced).

## Unimplemented: Higher N

Run survey.py at N=8 (76 semiprimes), N=9 (149), N=10. UB phase works;
LB will hit walls early but even partial LBs are useful for growth-rate
analysis.
