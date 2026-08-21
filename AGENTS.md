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
| `polish_loop.py` | Overnight UB driver: alternates ABC structural polish with `window_opt.py` passes, verifies care-correctness after every op, keeps `factor{N}_opt_final_opt.blif` monotonic. Flags: `--no-window`, `--no-abc`, `--win-iters N`, `--seed S`, `--max-out A,B`, `--max-gates A,B`. Run under `setsid nohup` so shell timeouts can't group-kill it. |
| `cegis_lb.py` | CEGIS LB loop over care-point subsets (pairwise AMO kept). Validated: N=4 (k=0 UNSAT, k=1 SAT), N=5 (k=3 UNSAT, k=4 SAT), N=6 (k=10 UNSAT in 29.6s, LB=11). |
| `single_output.py` | Per-output exact synthesis: minimum AIG gates for one output bit alone (exact). Multi-output mode via `build_multi_cnf`/`check_multi`/`decode_multi` (shared k-gate structure, one output selector per target; used by `pair_output_lb.py`). N=6: p1,p2,q1,q2=5, q3=6, q4=3 → zero-sharing total 29. |
| `n9_per_output_lb.py` | Per-output exact LB; takes N as argv (default 9). N=9/N=10: p1,p2 (and q5 at N=9) k=7 UNSAT → LB=8. Superseded by pair-output LB for the headline numbers (see `pair_output_lb.py`). |
| `pair_output_lb.py` | Multi-output exact-synthesis LB (multi-output mode of `single_output.py`): min AIG gates to compute 2+ output bits jointly on the care set. Max over pairs dominates per-output LB; k-tuples dominate pairs. N=9 LB=10, N=10 LB=10, N=11 LB=11, N=12 direct LB=10; N=6 triples independently confirm LB=11. Usage: `pair_output_lb.py N NAME1 NAME2 [NAME3...] [--max-k K] [--timeout SEC]`. |
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
| `factor11_opt_final.blif` | N=11 ABC pipeline baseline (5264 AND gates). |
| `factor11_opt_final_opt.blif` | N=11 after polish loop (2283 AND gates). |
| `factor12_opt_final.blif` | N=12 ABC pipeline baseline (10763 AND gates). |
| `factor12_opt_final_opt.blif` | N=12 after polish loop (5943 AND gates at the Aug 22 handoff; the loop was still running and lowering it). |

Other tracked files not listed above (`rank_core_gates.py`,
`exact_factor6*.py`, `experiment.py`, `factor4.blif`, `factor6*.blif`,
`factor7_raw.blif`, `factor8_opt.blif`, etc.) are legacy/scratch from
earlier sessions — superseded, kept for history. Superseded intermediate
`_opt`-chain BLIFs were deleted from tracking on Aug 21 (still in git
history).

## Current Handoff

- **State as of Aug 22, 2026 (written mid-run)** — the results table at the
  end of this file is current. Any LB/UB claims in NOTES.md not matching the
  table are archival; the table wins. All UBs from the polish loop are
  verified care-correct. **The N=12 polish loop is STILL RUNNING** (pid
  29269, `polish_loop.py 12 1440 --win-iters 80`, log `polish12.log`,
  gitignored): it writes new bests to `factor12_opt_final_opt.blif` (~5943 at
  handoff), so that file's gate count may differ from the table — re-verify
  before citing it. Budget: 24h from ~8:46 EDT Aug 21 → self-terminates
  ~8:46 Aug 22.
- Canonical final UB artifacts are `factor6_opt_final_opt.blif`,
  `factor7_opt_final_opt_opt.blif`,
  `factor8_opt_final_opt_opt_opt_opt_opt.blif`,
  `factor9_opt_final_opt.blif`, `factor10_opt_final_opt.blif`,
  `factor11_opt_final_opt.blif`, and `factor12_opt_final_opt.blif`.
  Untouched ABC baselines are the `factor{N}_opt_final.blif` files.
- **Pair-output exact synthesis is the LB workhorse** (added Aug 22,
  `pair_output_lb.py`): `max over pairs of pair-min` dominates the
  per-output LB. It climbed N=9 8→10, N=10 8→10, N=11 10→11, all by proving
  pair UNSAT at k where per-output was SAT/stuck. The multi-output encoder
  (`build_multi_cnf` in `single_output.py`) also supports k-tuples for a
  future rung.
- **The polish loop is the current UB workhorse.** Alternate ABC
  structural polish (`strash; compress2rs; fraig; balance`) with SAT
  windowed resynthesis (`window_opt.py --max-out 4-5 --max-gates 40-100`).
  Each opens basins the other misses: resynthesis alone plateaued N=9 at 503
  and N=10 at 1346; the loop reached 408, 970, 2283 (N=11), 7381 (N=12).
  Run ABC from `~/factor-circuit/abc/` (workdir) so the `abc.rc` alias
  scripts load — from the repo root `compress2rs`/`resyn2rs` are "unknown
  command". `compress2rs` and `resyn2rs` give similar results; `fraig` alone
  is weaker. `polish_loop.py` automates the cycle overnight.
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
  encodings/solvers, plus triple k=11 undecided @1h), N=7 k=12 (undecided
  after 19min/8M conflicts). Pair-output walls: N=9/N=10 k=10 (undecided
  @1800s/3600s — would give LB=11), N=11 k=11 (undecided @3600s — would give
  LB=12), N=12 k=10 pair (undecided @1h — would give direct LB=11).
- **Most valuable next step** (for the growth-curve goal): the N=12 UB polish
  loop is running to its budget (~5943 and still dropping). For LB: N=12 is at
  direct LB=10 / inherited 11 — a longer N=12 k=10 pair grind (or N=12 triple
  probes) could push the direct LB to 11-12. N=13 baseline is cheap (~2.1x
  N=12 ≈ 22k) but the loop gets slower per pass.
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
      ("factor11_opt_final_opt.blif", 11),
      ("factor12_opt_final_opt.blif", 12),
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

Run anything expected to take longer than ~10 seconds in the background
(`setsid nohup ... &`, redirect to a log) so the session isn't blocked;
poll the log asynchronously and report when something crosses a boundary.

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

## Results

The current LB/UB table is the last thing in this file (tail ~N+2 lines to see
it). Column convention (use in all tables):
- **LB** = the optimal circuit has **at least** this many AND gates (SAT-proven).
- **UB** = a verified circuit of **this exact size** has been constructed.
- **Gap** = UB − LB (width of the interval containing the true optimum).
  Gap 0 = proven optimal.

**Lower bounds.** LBs for N=4,5 from full SAT proof in `survey.py`. N=6 LB
from `survey.py` plus `exact_n6_from_above.py` / `run_n6_sweep.py` (LB=11;
k=10 proven UNSAT, k=9 proven UNSAT). N=6 k-tuple (triple) probes: four
triples `(q3,{p1|p2},{q1|q2})`; `(q3,p1,q2)` and `(q3,p2,q2)` each prove k=10
UNSAT (2444s/2676s) → triple-min ≥ 11, independently confirming LB=11 (k=11
undecided @1h — the wall; pairs cannot beat 11 at N=6 since pair-min ≤
minA+minB ≤ 11, triples can reach 16). N=7 LB from `cegis_lb.py`: k=10 (3.6s)
and k=11 (43s) UNSAT → LB=12 (k=12 undecided after 19min — the wall). N=8 LB
from the `survey.py` one-hot SAT encoding. N=9/N=10/N=11 LBs from **pair-output
exact synthesis** (`pair_output_lb.py`, multi-output mode of `single_output.py`):
any full circuit cut down to the gates feeding two outputs is a valid circuit
for that pair on the care set, so `max over pairs of pair-min` is a circuit LB
that dominates the per-output LB. N=9: (p1,p2), (p1,q5), (p2,q5) each prove
k=9 UNSAT (246/851/505s) → LB=10 (k=10 undecided @1800s). N=10: the same
three pairs prove k=9 UNSAT (1365/1135/1150s) → LB=10 (k=10 undecided
@3600s). N=11: (p1,q5) k=10 UNSAT 2841s and (p2,q5) k=10 UNSAT 3080s →
LB=11 (k=11 undecided @3600s). Historical per-output LBs these replaced:
N=9 LB=8 (`n9_per_output_lb.py`, p1,p2,q5 k=7 UNSAT), N=10 LB=8 (p1,p2 k=7
UNSAT), N=11 LB=10 (`single_output.py`, p1,q5 k=9 UNSAT). N=12 direct LB=10
from pair `(p2,q5)` k=9 UNSAT (1262s; p1/p2/q5 singles each prove k=8 UNSAT →
≥9). The N=12 care set contains the N=11 care set (restrict a 12-bit circuit
to x11=0 → a valid 11-bit circuit), so `min_12 ≥ min_11` for every output and
k-tuple — the inherited N=12 LB is ≥ 11.

**Upper bounds.** UBs from ABC + multi-pass windowed resynthesis (corrected
ODC mode) plus the **polish loop**: alternate `strash; compress2rs; fraig;
balance` (structural, exact on all inputs) with windowed resynthesis
(don't-care exploitation). Neither alone reaches these values; each opens new
basins for the other. N=7 74→49, N=8 208→147, N=9 503→408, N=10 2513→970,
N=11 5264→2283, N=12 10763→5943 (still dropping every round — the loop was
still running at handoff). N=6 stayed at 19 (structural polish finds nothing
there).

```
N | Semiprimes |  LB |  UB | Gap | UB source
--|------------|----:|----:|----:|-------------------------------------------------
 4|          4 |   1 |   1 |   0 | SAT exact synthesis (proven optimal)
 5|          7 |   4 |   4 |   0 | SAT exact synthesis (proven optimal)
 6|         18 |  11 |  19 |   8 | ABC + corrected ODC windowed resynth
 7|         37 |  12 |  49 |  37 | cegis_lb.py k=11 UNSAT; polish loop (Aug 21)
 8|         76 |  10 | 147 | 137 | ABC + ODC windowed resynth; polish loop (Aug 21)
 9|        149 |  10 | 408 | 398 | pair-output exact (p1,p2/p1,q5/p2,q5 k=9 UNSAT); polish loop (Aug 21)
10|        293 |  10 | 970 | 960 | pair-output exact (p1,p2/p1,q5/p2,q5 k=9 UNSAT); ABC 2513 + polish loop (Aug 21)
11|        575 |  11 |2283 |2272 | pair-output exact (p1,q5/p2,q5 k=10 UNSAT); ABC 5264 + polish loop (Aug 22)
12|       1106 |  10 |5943 |  —  | pair-output exact (p2,q5 k=9 UNSAT; inherited ≥11); ABC 10763 + polish loop (Aug 22, still running)
```
