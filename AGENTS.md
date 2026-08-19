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
 6 |         18 |  10 |   19 |   9  | ABC + corrected ODC windowed resynth
 7 |         37 |  11 |   74 |  63  | ABC + corrected ODC windowed resynth
 8 |         76 |  10 |  208 | 198  | ABC + corrected ODC windowed resynth
```

LBs for N=4,5 from full SAT proof. LBs for N=6,7 from `survey.py` SAT
encoding with one-hot selectors (~50K clause wall at k=11+).
UBs for N=6-8 from ABC + multi-pass windowed resynthesis (corrected ODC mode).

## Tools

- **Python 3** with python-sat 1.9.dev15 (Glucose4 solver).
- **Berkeley ABC9**: `~/factor-circuit/abc/abc`. Used for heuristic
  optimization and BLIF I/O.
- **WSL Ubuntu** Linux environment.

## Key Files

| File | Purpose |
|------|---------|
| `window_opt.py` | SAT-based windowed resynthesis (~1166 lines). Primary UB tool. |
| `survey.py` | ABC UB survey + SAT LB binary search (~603 lines). |
| `exact_factor4.py` | SAT exact synthesizer for N=4 (validated approach). |
| `exact_factor6_budget.py` | SAT exact synthesizer for N=6 with budget-based solving. |
| `make_blif.py` | N=4 BLIF generator (superseded by survey.py). |
| `factor6_opt_final.blif` | N=6 ABC-optimized baseline (90 AND gates). |
| `factor6_opt_final_opt.blif` | N=6 after windowed resynthesis (19 AND gates). |
| `factor7_opt.blif` | N=7 ABC-optimized baseline (229 AND gates). |
| `factor7_opt_final.blif` | N=7 ABC pipeline baseline (133 AND gates). |
| `factor7_opt_final_opt_opt.blif` | N=7 after windowed resynthesis (74 AND gates). |
| `factor8_opt_final.blif` | N=8 ABC pipeline baseline (347 AND gates). |
| `factor8_opt_final_opt_opt_opt_opt_opt.blif` | N=8 after windowed resynthesis (208 AND gates). |

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
