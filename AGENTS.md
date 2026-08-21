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

Column convention (use in all tables):
- **LB** = the optimal circuit has **at least** this many AND gates (SAT-proven).
- **UB** = a verified circuit of **this exact size** has been constructed.
- **Gap** = UB − LB (width of the interval containing the true optimum).
  Gap 0 = proven optimal.

```
N | Semiprimes |  LB |  UB | Gap | UB source
--|------------|----:|----:|----:|-------------------------------------------------
 4|          4 |   1 |   1 |   0 | SAT exact synthesis (proven optimal)
 5|          7 |   4 |   4 |   0 | SAT exact synthesis (proven optimal)
 6|         18 |  11 |  19 |   8 | ABC + corrected ODC windowed resynth
 7|         37 |  12 |  49 |  37 | cegis_lb.py k=11 UNSAT; polish loop (Aug 21)
 8|         76 |  10 | 147 | 137 | ABC + ODC windowed resynth; polish loop (Aug 21)
 9|        149 |   8 | 408 | 400 | per-output exact (p1,p2,q5 k=7 UNSAT); polish loop (Aug 21)
10|        293 |   8 | 970 | 962 | per-output exact (p1,p2 k=7 UNSAT); ABC 2513 + polish loop (Aug 21)
```

LBs for N=4,5 from full SAT proof in `survey.py`. LB for N=6 from
`survey.py` plus `exact_n6_from_above.py` / `run_n6_sweep.py`
(LB=11; k=10 proven UNSAT, k=9 proven UNSAT). N=7 LB is new: `cegis_lb.py`
proved k=10 (3.6s) and k=11 (43s) UNSAT, giving LB=12 (k=12 undecided after
19min — the current wall). N=8 LB from the `survey.py` one-hot SAT encoding.
N=9 LB=8 from per-output exact synthesis (`n9_per_output_lb.py`): p1, p2, q5
each need at least 8 gates alone (k=7 UNSAT), so any full circuit needs at
least 8. N=10 LB=8 same method: p1, p2 need at least 8 gates (k=7 UNSAT).

UBs from ABC + multi-pass windowed resynthesis (corrected ODC mode) plus the
**polish loop (Aug 21)**: alternate `strash; compress2rs; fraig; balance`
(structural, exact on all inputs) with windowed resynthesis (don't-care
exploitation). Neither alone reaches these values; each opens new basins for
the other. N=7 74→49, N=8 208→147, N=9 503→408, N=10 2513→970. N=6 stayed at
19 (structural polish finds nothing there).

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
| `cegis_lb.py` | CEGIS LB loop over care-point subsets (pairwise AMO kept). Validated: N=4 (k=0 UNSAT, k=1 SAT), N=5 (k=3 UNSAT, k=4 SAT), N=6 (k=10 UNSAT in 29.6s, LB=11). |
| `single_output.py` | Per-output exact synthesis: minimum AIG gates for one output bit alone (exact). N=6: p1,p2,q1,q2=5, q3=6, q4=3 → zero-sharing total 29. |
| `n9_per_output_lb.py` | Per-output exact LB; takes N as argv (default 9). N=9/N=10: p1,p2 (and q5 at N=9) k=7 UNSAT → LB=8. |
| `core_gate_search.py` | Rank candidate shared core gates (cost + per-output extension mins). Best single N=6 shared gate: p1's output function → 21. |
| `joint_core_search.py` | 2-gate joint core search over the candidate pool (exact core cost). N=6 best 21 (seed pool) / 20 (enriched pool via beam). |
| `core_build.py` | Greedy incremental shared-core builder; harvests new candidate gates each step into `core_candidates.json` (gitignored). N=6: 3-gate core → 19, plateaus. |
| `beam_core_search.py` | Beam search over cores (size 1→2→3), width 25, exact min-over-orderings core cost. N=6: level-3 best 19. |
| `portfolio.py` | Multi-solver + variable-permutation portfolio across workers. |
| `n6_exact_sweep.py` | Parallel N=6 exact-synthesis sweep over k values. |
| `subset_probe.py` | Parallel care-subset SAT probe for hard-instance diagnosis. |
| `survey.py` | ABC UB survey + SAT LB binary search; source of N=4/N=5 exact proofs. |
| `make_factor9_blif.py` | Builds `factor{N}_opt_final.blif` (ABC baseline, N as argv, default 9) with persistence (survey.py's missing-artifact fix). |
| `exact_n6_from_above.py` | Current N=6 exact-synthesis helper, testing k values from the proven lower bound upward. |
| `run_n6_sweep.py` | N=6 windowed-resynthesis parameter sweep around the 19-gate UB. |
| `exact_factor6_budget.py` | Legacy N=6 budget-based exact-synthesis experiment. |
| `make_blif.py` | N=4 BLIF generator (superseded by survey.py). |
| `factor6_opt_final.blif` | N=6 ABC-optimized baseline (90 AND gates). |
| `factor6_opt_final_opt.blif` | N=6 after windowed resynthesis (19 AND gates). |
| `factor7_opt.blif` | N=7 ABC-optimized baseline (229 AND gates). |
| `factor7_opt_final.blif` | N=7 ABC pipeline baseline (133 AND gates). |
| `factor7_opt_final_opt_opt.blif` | N=7 after windowed resynthesis + polish loop (49 AND gates). |
| `factor8_opt_final.blif` | N=8 ABC pipeline baseline (347 AND gates). |
| `factor8_opt_final_opt_opt_opt_opt_opt.blif` | N=8 after windowed resynthesis + polish loop (147 AND gates). |
| `factor9_opt_final.blif` | N=9 ABC pipeline baseline (1158 AND gates). |
| `factor9_opt_final_opt.blif` | N=9 after windowed resynthesis + polish loop (408 AND gates). |
| `factor10_opt_final.blif` | N=10 ABC pipeline baseline (2513 AND gates). |
| `factor10_opt_final_opt.blif` | N=10 after windowed resynthesis + polish loop (970 AND gates). |

Other tracked files not listed above (`rank_core_gates.py`,
`exact_factor6*.py`, `experiment.py`, `factor4.blif`, `factor6*.blif`,
`factor7_raw.blif`, `factor8_opt.blif`, etc.) are legacy/scratch from
earlier sessions — superseded, kept for history. Superseded intermediate
`_opt`-chain BLIFs were deleted from tracking on Aug 21 (still in git
history).

## Current Handoff

- **State as of Aug 21, 2026** — the results table above is current. Any
  LB/UB claims in NOTES.md not matching the table are archival; the table
  wins. All UBs from the polish loop are verified care-correct.
- Canonical final UB artifacts are `factor6_opt_final_opt.blif`,
  `factor7_opt_final_opt_opt.blif`,
  `factor8_opt_final_opt_opt_opt_opt_opt.blif`,
  `factor9_opt_final_opt.blif`, and `factor10_opt_final_opt.blif`.
  Untouched ABC baselines are the `factor{N}_opt_final.blif` files.
- **The polish loop is the current UB workhorse (Aug 21).** Alternate ABC
  structural polish (`strash; compress2rs; fraig; balance`) with SAT
  windowed resynthesis (`window_opt.py --max-out 4-5 --max-gates 40-100`).
  Each opens basins the other misses: resynthesis alone plateaued N=9 at 503
  and N=10 at 1346; the loop reached 408 and 970. Run ABC from
  `~/factor-circuit/abc/` (workdir) so the `abc.rc` alias scripts load —
  from the repo root `compress2rs`/`resyn2rs` are "unknown command".
  `compress2rs` and `resyn2rs` give similar results; `fraig` alone is weaker.
- **CEGIS/LB findings, do not regress:**
  1. Keep the per-call conflict budget FIXED at 5000 (survey.py `check_k`
     style). Escalating 5000→500k made the identical k=10 instance go from
     ~29s/626K conflicts to undecided at 2.1M+ conflicts.
  2. Care subsets must be rebuilt in SORTED original-index order. A permuted
     care order changed clause insertion order and stalled the same instance.
  3. `--max-add 4` (gradual subset growth) stalls on hard candidate SAT
     searches near the boundary (|S|=12, k=10 N=6: 4.4M conflicts undecided).
     `--max-add 0` (add all failures, jump to full set) matches survey.py
     performance. CEGIS clause reduction does not currently pay off for the
     LB direction.
- **N=6 structure & the 18-gate question:** Only 6 of 12 output bits need
  computation (`p1,p2,q1,q2,q3,q4`); `p0=x0`, the rest are constants.
  Per-output exact minima (no sharing) total 29. The "shared core +
  independent per-output extensions" architecture bottoms out at 19 across
  three independent methods (greedy, joint, beam). **An 18-gate circuit has
  NOT been found and NOT been ruled out**: it would need interleaved /
  extension-sharing structure the core+extension box cannot express, or may
  not exist. Deciding it requires the heavy k=18 exact-synthesis grind or a
  new architecture.
- **Open LB walls:** N=6 k=11 (undecided after 20M+ conflicts across
  encodings/solvers), N=7 k=12 (undecided after 19min/8M conflicts).
  Per-output exact LB (single output, no gate sharing) is stuck at 8 for
  N=9/N=10 — k=7 UNSAT is the feasible limit per output.
- **Most valuable next step** (for the growth-curve goal): **N=11 UB** —
  `make_factor9_blif.py 11` for the ABC baseline (est. ~5.5k gates), then
  the polish loop. Care density stays ~28% so the loop should transfer.
- Generated data `single_output_circuits.json` and `core_candidates.json`
  are gitignored (regenerated by `single_output.py` / `core_build.py`).
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
      ("factor9_opt_final_opt.blif", 9),
      ("factor10_opt_final_opt.blif", 10),
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

## Resynthesis Output Naming

Do NOT chain `_opt` suffixes across windowed-resynthesis passes
(`factor9_opt_final_opt_opt_opt_...`). It happened once and was a mess to
untangle. Instead, keep ONE canonical "current best" file
(`factor{N}_opt_final_opt.blif`) and always write the next pass to it:

1. Run: `python3 window_opt.py factor{N}_opt_final_opt.blif 10 200 --seed S --out /tmp/pass.blif`
2. On success (293/293 verified), replace the canonical file:
   `mv /tmp/pass.blif factor{N}_opt_final_opt.blif`
3. Keep `factor{N}_opt_final.blif` as the untouched ABC baseline.

`window_opt.py` supports `--out PATH` for this (added Aug 20); without it the
default `_opt`-append behavior only makes sense for the FIRST resynthesis pass.

## Working Style

Proceed one substantive action at a time when debugging. Don't give a
cascade of commands before confirming the previous one worked.

## "Handoff" Command

When the user says **"handoff"** (or "wrap up", "leave the repo in a good
state"), run the full handoff routine without asking what it entails:

1. **Save state** — append a session log to `NOTES.md`: what was done, the
   current results table (plain-number LB/UB convention), and remaining
   ideas so a fresh context can pick up where this one left off.
2. **Sync AGENTS.md** — make the "Current Handoff" section and Key Files
   table accurate: current results, canonical artifacts, any new tools or
   techniques (e.g. the polish loop), and current walls/next steps.
3. **Clean up** — delete temp/intermediate artifacts; for regenerable junk
   default to `.gitignore`, not deletion. Don't ask the user about routine
   cleanup decisions.
4. **Verify** — run `python3 -m compileall -q .`, `git diff --check`, and
   the canonical-BLIF verification snippet in this file.
5. **Commit** — stage the intended changes and commit with a concise message
   matching repo style. Do **not** push.

## Git

- Commit when asked, or when completing a logical unit of work.
- Do **not** push. The user handles pushes themselves.
