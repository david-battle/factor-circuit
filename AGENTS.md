# Factoring Circuits Project

## ⚠️ DO NOT REVISIT — Rejected Approaches

**Sequential counter (Sinz 2005) for at-most-one encoding:**
Tried in survey.py and exact_factor6_budget.py. Replaced pairwise O(n²)
AMO clauses with O(n) sequential counter clauses. Result: clause count
dropped ~37% but solver got dramatically SLOWER. Pairwise AMO provides
free unit propagation that CDCL solvers exploit heavily — the sequential
counter's weaker propagation costs more in search than it saves in clauses.
**Do not try this or similar compact AMO encodings again.**

**Incremental SAT across binary search steps:**
Rejected because most time is spent on higher k values (by an order of
magnitude), so savings from clause reuse would be minimal. The bottleneck
is encoding size at high k, not the search structure.

**Binary selector encoding (non-one-hot):**
Tried earlier. Fewer variables and clauses but slower to solve. Do not
revisit without a fundamentally different approach.

## Goal

Experimentally investigate whether integer factoring exhibits surprisingly
small Boolean circuits. For each bit-width N, build a one-shot combinational
circuit mapping an N-bit semiprime directly to its two prime factors in
binary. Non-semiprime inputs are don't-cares. Compare circuit size (AND-gate
count) growth with N, and compare constructed upper bounds with
SAT-proven lower bounds.

## Circuit Model

- **Inputs**: N bits (`x0`=LSB through `x(N-1)`=MSB).
- **Outputs**: 2N bits: `p(N-1)...p0` and `q(N-1)...q0` (full-width factors).
- **Care inputs**: Integers with exactly two distinct prime factors.
- **Don't-cares**: All other inputs; outputs unconstrained.
- **Metric**: Number of 2-input AND gates in an AIG. NOT edges and
  complemented inputs are free (ABC AIG convention).
- **Verification**: Care-point simulation (not full CEC, since non-semiprimes
  are don't-cares).

## Results

```
N  | Semiprimes | LB  | UB   | Gap  | UB Source
---|------------|-----|------|------|-------------------------------
 4 |          4 |   1 |    1 |   =  | SAT exact synthesis (proven)
 5 |          7 |   4 |    4 |   =  | SAT exact synthesis (proven)
 6 |         18 | ≥11 |   19 | ≤ 8  | ABC + corrected ODC windowed resynth (LB corrected)
 7 |         37 |  11 |   74 |  63  | ABC + corrected ODC windowed resynth
 8 |         76 |  10 |  208 | 198  | ABC + corrected ODC windowed resynth
```

LBs for N=4,5 from full SAT proof in `survey.py`. LB for N=6 from
`survey.py` plus `exact_n6_from_above.py` / `run_n6_sweep.py`
(LB≥11; k=10 proven UNSAT, k=9 proven UNSAT). N=7 and N=8 LBs are from
the `survey.py` one-hot SAT encoding before the exact-synthesis clause wall.
UBs for N=6-8 from ABC + multi-pass windowed resynthesis (corrected ODC mode).

## Tools

- **Python 3** with python-sat 1.9.dev15. Current main scripts primarily use
  the `cd153` solver; some legacy experiments used Glucose4.
- **Berkeley ABC**: `~/factor-circuit/abc/abc`. Used for heuristic
  optimization and BLIF I/O.
- **WSL Ubuntu** Linux environment.

## Key Files

| File | Purpose |
|------|---------|
| `window_opt.py` | SAT-based windowed resynthesis. Primary UB tool. |
| `survey.py` | ABC UB survey + SAT LB binary search; source of N=4/N=5 exact proofs. |
| `exact_n6_from_above.py` | Current N=6 exact-synthesis helper, testing k values from the proven lower bound upward. |
| `run_n6_sweep.py` | N=6 windowed-resynthesis parameter sweep around the 19-gate UB. |
| `exact_factor6_budget.py` | Legacy N=6 budget-based exact-synthesis experiment. |
| `make_blif.py` | N=4 BLIF generator (superseded by survey.py). |
| `factor6_opt_final.blif` | N=6 ABC-optimized baseline (90 AND gates). |
| `factor6_opt_final_opt.blif` | N=6 after windowed resynthesis (19 AND gates). |
| `factor7_opt.blif` | N=7 ABC-optimized baseline (229 AND gates). |
| `factor7_opt_final.blif` | N=7 ABC pipeline baseline (133 AND gates). |
| `factor7_opt_final_opt_opt.blif` | N=7 after windowed resynthesis (74 AND gates). |
| `factor8_opt_final.blif` | N=8 ABC pipeline baseline (347 AND gates). |
| `factor8_opt_final_opt_opt_opt_opt_opt.blif` | N=8 after windowed resynthesis (208 AND gates). |

## Current Handoff

- Current best results are the table above. Treat older `LB=10` claims for
  N=6 as superseded; the corrected status is `LB≥11`, `UB=19`.
- Canonical final UB artifacts are `factor6_opt_final_opt.blif`,
  `factor7_opt_final_opt_opt.blif`, and
  `factor8_opt_final_opt_opt_opt_opt_opt.blif`.
- Before continuing, run:

  ```bash
  python3 -m compileall -q .
  git diff --check
  ```

- To verify the canonical BLIF artifacts:

  ```bash
  python3 - <<'PY'
  from window_opt import parse_blif, count_and_gates, verify_circuit, enumerate_care

  for path, n in [
      ("factor6_opt_final_opt.blif", 6),
      ("factor7_opt_final_opt_opt.blif", 7),
      ("factor8_opt_final_opt_opt_opt_opt_opt.blif", 8),
  ]:
      aig = parse_blif(path)
      care = enumerate_care(n)
      correct, total = verify_circuit(aig, care, n)
      print(f"{path}: {count_and_gates(aig)} AND gates, {correct}/{total} care points")
  PY
  ```

## Bit-Ordering Convention

All code assumes `x_i` = bit i (LSB). BLIF files list inputs in descending
order (`x(N-1) ... x0`) so that MSB-first truth table patterns align with
this convention. `survey.py`'s `generate_blif()` outputs this order.

## Working Style

Proceed one substantive action at a time when debugging. Don't give a
cascade of commands before confirming the previous one worked.

## Git

- Commit when asked, or when completing a logical unit of work.
- Do **not** push. The user handles pushes themselves.
