#!/usr/bin/env python3
"""Time-bounded factoring circuit size survey.

For a given N, runs two phases:
  1. Upper bound: ABC heuristic synthesis to find a working circuit
  2. Lower bound: SAT proof that no smaller circuit exists

Outputs a table row: N | UB | LB | gap | time
"""

import sys
import time
import subprocess
import tempfile
import os
from math import isqrt
from pysat.solvers import Solver

# ── Configuration ────────────────────────────────────────────────────
ABC_BIN = os.path.expanduser("~/factor-circuit/abc/abc")
UB_TIME = 300   # seconds for upper-bound phase
LB_TIME = 300   # seconds for lower-bound phase
SAT_TIMEOUT = 30  # seconds per SAT query in binary search
# ─────────────────────────────────────────────────────────────────────

def is_prime(n):
    if n < 2:
        return False
    for p in range(2, isqrt(n) + 1):
        if n % p == 0:
            return False
    return True

def factor_semiprime(n):
    for p in range(2, isqrt(n) + 1):
        if n % p == 0:
            q = n // p
            if p != q and is_prime(p) and is_prime(q):
                return p, q
    return None

def enumerate_care(N):
    """Returns list of (input_val, p, q) for all N-bit semiprimes."""
    care = []
    for x in range(1 << N):
        f = factor_semiprime(x)
        if f:
            care.append((x, f[0], f[1]))
    return care


# ── SAT Encoder ──────────────────────────────────────────────────────

def build_cnf(N, care, k):
    """Build CNF for k-AND-gate AIG factoring circuit.

    Optimizations applied:
    - Skip constant-0 outputs (no variables/clauses needed)
    - Gate input symmetry breaking (a AND b = b AND a)

    Returns (clauses, nvars).
    """
    C = len(care)
    next_var = 1
    clauses = []

    def new_var():
        nonlocal next_var
        v = next_var
        next_var += 1
        return v

    def add_clause(clause):
        clauses.append(clause)

    sig = [[new_var() for _ in range(C)] for _ in range(k)]

    for g in range(k):
        available = ["const0"] + [f"in{i}" for i in range(N)] + [
            f"g{i}" for i in range(g)
        ]
        gate_selected = []
        gate_selectors = []
        for input_num in range(2):
            selectors = [new_var() for _ in available]
            inv = new_var()
            selected = [new_var() for _ in range(C)]

            add_clause(selectors)
            for i in range(len(selectors)):
                for j in range(i + 1, len(selectors)):
                    add_clause([-selectors[i], -selectors[j]])

            for si, source in enumerate(available):
                sel = selectors[si]
                for t, (x, _, _) in enumerate(care):
                    a = selected[t]
                    if source == "const0":
                        add_clause([-sel, -inv, a])
                        add_clause([-sel, inv, -a])
                    elif source.startswith("in"):
                        bit = int(source[2:])
                        value = (x >> bit) & 1
                        if value == 0:
                            add_clause([-sel, -inv, a])
                            add_clause([-sel, inv, -a])
                        else:
                            add_clause([-sel, -inv, -a])
                            add_clause([-sel, inv, a])
                    else:
                        pg = int(source[1:])
                        v = sig[pg][t]
                        add_clause([-sel, -v, -inv, -a])
                        add_clause([-sel, v, inv, -a])
                        add_clause([-sel, -v, inv, a])
                        add_clause([-sel, v, -inv, a])

            gate_selected.append(selected)
            gate_selectors.append(selectors)

        # Symmetry breaking: source(input0) <= source(input1)
        # Since a AND b = b AND a, enforce canonical ordering.
        sel0, sel1 = gate_selectors
        for i in range(len(sel0)):
            for j in range(i):
                # Can't have input0=source_i AND input1=source_j when i > j
                add_clause([-sel0[i], -sel1[j]])

        # z = a AND b
        a, b = gate_selected
        for t in range(C):
            z = sig[g][t]
            add_clause([-z, a[t]])
            add_clause([-z, b[t]])
            add_clause([z, -a[t], -b[t]])

    # Output encoding — skip constant-0 outputs
    available_out = ["const0"] + [f"in{i}" for i in range(N)] + [
        f"g{i}" for i in range(k)
    ]
    for out_index in range(2 * N):
        is_p = out_index < N
        bit = N - 1 - (out_index % N)

        # Check if this output is constant 0 across all care points
        is_const_zero = True
        for x, p, q in care:
            required = ((p if is_p else q) >> bit) & 1
            if required:
                is_const_zero = False
                break
        if is_const_zero:
            continue

        selectors = [new_var() for _ in available_out]
        inv = new_var()
        add_clause(selectors)
        for i in range(len(selectors)):
            for j in range(i + 1, len(selectors)):
                add_clause([-selectors[i], -selectors[j]])

        for si, source in enumerate(available_out):
            sel = selectors[si]
            for t, (x, p, q) in enumerate(care):
                required = ((p if is_p else q) >> bit) & 1
                if source == "const0":
                    if required:
                        add_clause([-sel, inv])
                    else:
                        add_clause([-sel, -inv])
                elif source.startswith("in"):
                    source_value = (x >> int(source[2:])) & 1
                    if source_value == required:
                        add_clause([-sel, -inv])
                    else:
                        add_clause([-sel, inv])
                else:
                    source_value = sig[int(source[1:])][t]
                    if required:
                        add_clause([-sel, source_value, inv])
                        add_clause([-sel, -source_value, -inv])
                    else:
                        add_clause([-sel, -source_value, inv])
                        add_clause([-sel, source_value, -inv])

    return clauses, next_var - 1



def check_k(N, care, k, timeout_seconds=None):
    """Check if k AND gates suffice. Returns (sat, conflicts, time, timed_out)."""
    clauses, nvars = build_cnf(N, care, k)

    s = Solver(name="cd153")
    for cl in clauses:
        s.add_clause(cl)

    if timeout_seconds is not None:
        # Use conflict-budgeted solving
        budget = 5000
        elapsed = 0.0
        total_conflicts = 0
        t0 = time.time()
        while elapsed < timeout_seconds:
            s.conf_budget(budget)
            result = s.solve_limited()
            if result is not None:
                # Decided
                dt = time.time() - t0
                stats = s.accum_stats()
                s.delete()
                return result, stats.get("conflicts", 0), dt, False
            stats = s.accum_stats()
            total_conflicts = stats.get("conflicts", 0)
            elapsed = time.time() - t0
        # Timeout
        s.delete()
        return None, total_conflicts, elapsed, True
    else:
        t0 = time.time()
        sat = s.solve()
        dt = time.time() - t0
        stats = s.accum_stats()
        s.delete()
        return sat, stats.get("conflicts", 0), dt, False


# ── Upper Bound: ABC Heuristic ───────────────────────────────────────

def generate_blif(N, care, path):
    """Generate BLIF with sparse .names tables for the factoring function."""
    # Inputs in descending order: x(N-1) x(N-2) ... x1 x0
    # This matches the MSB-first truth table convention so that x_i = bit i.
    inputs = [f"x{i}" for i in range(N - 1, -1, -1)]
    outputs = (
        [f"p{i}" for i in range(N - 1, -1, -1)] +
        [f"q{i}" for i in range(N - 1, -1, -1)]
    )

    lines = [
        f".model factor{N}",
        ".inputs " + " ".join(inputs),
        ".outputs " + " ".join(outputs),
        "",
    ]

    for output_name in outputs:
        ones = []
        for x, p, q in care:
            value = p if output_name.startswith("p") else q
            bit = int(output_name[1:])
            if (value >> bit) & 1:
                pattern = format(x, f"0{N}b")
                ones.append(pattern)

        if not ones:
            # Constant-0 output: no inputs, no product terms
            lines.append(f".names {output_name}")
        else:
            lines.append(f".names {' '.join(inputs)} {output_name}")
            for pattern in ones:
                lines.append(f"{pattern} 1")
        lines.append("")

    lines.append(".end")
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")



def count_abc_gates_from_output(stdout):
    """Extract AND gate count from ABC stdout."""
    for line in stdout.split("\n"):
        if "and =" in line:
            return int(line.split("and =")[1].split()[0])
    return None


def run_abc_optimize(blif_path, timeout=30):
    """Run ABC optimization strategies, return best AND count.

    Two phases:
    1. One-shot strategies (each reads fresh from blif_path)
    2. Iterated pipelines (each pass feeds into the next via temp file)
    """
    # Phase 1: one-shot strategies
    strategies = [
        "strash; rewrite; refactor; balance",
        "strash; rewrite; refactor; balance; resub",
        "strash; rewrite; refactor; balance; resub -K 8",
        "strash; rewrite; refactor; balance; resub -K 16",
        "strash; rewrite; refactor; balance; resub -K 32",
        "strash; rewrite; refactor; balance; resub -K 64",
        "strash; rewrite -K 6; refactor -K 6; balance; resub -K 16",
        "strash; rewrite -K 8; refactor -K 8; balance; resub -K 32",
        "strash; rewrite; refactor; balance; resub; resub -K 16",
        "strash; rewrite; refactor; balance; resub; resub -K 32",
        "strash; rewrite -K 4; refactor; balance; resub -K 8",
        "strash; rewrite -K 10; refactor -K 10; balance; resub",
        "strash; dc2; rewrite; refactor; balance",
        "strash; dc2; rewrite; refactor; balance; resub",
        "strash; dc2; dc2; rewrite; refactor; balance",
        "strash; dc2; dc2; rewrite; refactor; balance; resub",
        "strash; dc2; mfs2; rewrite; refactor; balance",
        "strash; dc2; mfs2; rewrite; refactor; balance; resub",
        "strash; dc2; dc2; mfs2; rewrite; refactor; balance",
        "strash; dc2; dc2; mfs2; rewrite; refactor; balance; resub",
        "strash; dch; rewrite; refactor; balance",
        "strash; dch; rewrite; refactor; balance; resub",
        "strash; dch; dc2; rewrite; refactor; balance",
        "strash; dch; dc2; rewrite; refactor; balance; resub",
    ]

    best = None
    best_blif = None
    for strat in strategies:
        try:
            cmd = f"read_blif {blif_path}; {strat}; print_stats"
            result = subprocess.run(
                [ABC_BIN, "-c", cmd],
                capture_output=True, text=True, timeout=timeout
            )
            gates = count_abc_gates_from_output(result.stdout)
            if gates is not None and (best is None or gates < best):
                best = gates
        except Exception:
            pass

    # Phase 2: iterated pipelines — feed output back as input
    # Single pipelines
    single_pipelines = [
        ("dc2; rewrite; refactor; balance; resub", 8),
        ("dch; dc2; rewrite; refactor; balance; resub", 10),
    ]

    for pipeline, max_passes in single_pipelines:
        try:
            current_blif = blif_path
            no_improve = 0
            for pass_num in range(max_passes):
                with tempfile.NamedTemporaryFile(suffix=".blif", delete=False, dir="/tmp") as f:
                    next_blif = f.name
                cmd = f"read_blif {current_blif}; strash; {pipeline}; write_blif {next_blif}; print_stats"
                result = subprocess.run(
                    [ABC_BIN, "-c", cmd],
                    capture_output=True, text=True, timeout=timeout
                )
                gates = count_abc_gates_from_output(result.stdout)
                if gates is not None:
                    if best is None or gates < best:
                        best = gates
                        best_blif = next_blif
                        no_improve = 0
                    else:
                        no_improve += 1
                    if no_improve >= 2:
                        os.unlink(next_blif)
                        break
                else:
                    os.unlink(next_blif)
                    break
                current_blif = next_blif
            if current_blif != blif_path and current_blif != best_blif:
                try:
                    os.unlink(current_blif)
                except OSError:
                    pass
        except Exception:
            pass

    # Alternating pipeline: dch → dc2 → dch → dc2 ... (biggest improvement)
    try:
        current_blif = blif_path
        no_improve = 0
        alt_pipelines = [
            "dch; dc2; rewrite; refactor; balance; resub",
            "dc2; rewrite; refactor; balance; resub",
        ]
        for pass_num in range(30):
            pipeline = alt_pipelines[pass_num % 2]
            with tempfile.NamedTemporaryFile(suffix=".blif", delete=False, dir="/tmp") as f:
                next_blif = f.name
            cmd = f"read_blif {current_blif}; strash; {pipeline}; write_blif {next_blif}; print_stats"
            result = subprocess.run(
                [ABC_BIN, "-c", cmd],
                capture_output=True, text=True, timeout=timeout
            )
            gates = count_abc_gates_from_output(result.stdout)
            if gates is not None:
                if best is None or gates < best:
                    best = gates
                    best_blif = next_blif
                    no_improve = 0
                else:
                    no_improve += 1
                if no_improve >= 8:
                    os.unlink(next_blif)
                    break
            else:
                os.unlink(next_blif)
                break
            current_blif = next_blif
        if current_blif != blif_path and current_blif != best_blif:
            try:
                os.unlink(current_blif)
            except OSError:
                pass
    except Exception:
        pass

    return best


def run_upper_bound(N, care, budget_seconds):
    """Find the best circuit we can via ABC heuristics."""
    with tempfile.NamedTemporaryFile(suffix=".blif", delete=False, dir="/tmp") as f:
        blif_path = f.name

    try:
        generate_blif(N, care, blif_path)

        best = None
        t0 = time.time()
        round_num = 0

        while time.time() - t0 < budget_seconds:
            round_num += 1
            result = run_abc_optimize(blif_path, timeout=30)
            elapsed = time.time() - t0

            if result is not None:
                improved = ""
                if best is None or result < best:
                    best = result
                    improved = " *NEW BEST*"
                print(f"  [{elapsed:6.1f}s] round {round_num}: {result} AND gates{improved}", flush=True)
            else:
                print(f"  [{elapsed:6.1f}s] round {round_num}: ABC failed", flush=True)

        return best
    finally:
        os.unlink(blif_path)


# ── Lower Bound: SAT Binary Search ──────────────────────────────────

def run_lower_bound(N, care, budget_seconds, known_ub=None):
    """Find the largest k that is provably UNSAT (no k-gate circuit exists).

    Strategy:
    1. Quick probes at small k to establish initial range
    2. Binary search with SAT timeout to tighten the lower bound
    """
    t0 = time.time()
    best_lb = -1  # largest k proved UNSAT
    best_ub = known_ub  # smallest k found SAT (or unknown)

    # Phase 1: Quick probes at small k
    print(f"  Phase 1: Quick probes...", flush=True)
    for k in range(0, 20):
        if time.time() - t0 >= budget_seconds:
            break
        elapsed = time.time() - t0
        sat, conflicts, dt, timed_out = check_k(N, care, k, timeout_seconds=10)

        if timed_out:
            print(f"  [{elapsed:6.1f}s] k={k}: TIMEOUT ({dt:.1f}s)", flush=True)
            break
        elif sat:
            print(f"  [{elapsed:6.1f}s] k={k}: SAT ({dt:.1f}s, {conflicts} conflicts)", flush=True)
            best_ub = k
            break
        else:
            print(f"  [{elapsed:6.1f}s] k={k}: UNSAT ({dt:.1f}s, {conflicts} conflicts)", flush=True)
            best_lb = k

    if best_ub is not None and best_lb + 1 >= best_ub:
        print(f"  Bounds tight: LB={best_lb} UB={best_ub} → optimum = {best_ub}", flush=True)
        return best_lb, best_ub, time.time() - t0

    # Phase 2: Binary search between best_lb+1 and best_ub (or a large upper)
    if best_ub is None:
        # No UB known yet; try to find one by probing large k
        print(f"  Phase 2: Finding initial UB...", flush=True)
        for k in [50, 100, 200, 500]:
            if time.time() - t0 >= budget_seconds:
                break
            elapsed = time.time() - t0
            sat, conflicts, dt, timed_out = check_k(N, care, k, timeout_seconds=15)
            if timed_out:
                print(f"  [{elapsed:6.1f}s] k={k}: TIMEOUT ({dt:.1f}s)", flush=True)
                continue
            elif sat:
                print(f"  [{elapsed:6.1f}s] k={k}: SAT ({dt:.1f}s)", flush=True)
                best_ub = k
                break
            else:
                print(f"  [{elapsed:6.1f}s] k={k}: UNSAT ({dt:.1f}s)", flush=True)
                best_lb = k

    if best_ub is None:
        print(f"  Could not establish UB within budget. LB={best_lb}", flush=True)
        return best_lb, None, time.time() - t0

    # Phase 3: Binary search with timeout
    print(f"  Phase 3: Binary search [{best_lb+1}, {best_ub}]...", flush=True)
    lo = best_lb + 1
    hi = best_ub
    timeout_per_query = min(SAT_TIMEOUT, (budget_seconds - (time.time() - t0)) / max(1, 2 * (hi - lo).bit_length()))

    while lo < hi and time.time() - t0 < budget_seconds:
        mid = (lo + hi) // 2
        elapsed = time.time() - t0
        remaining = budget_seconds - elapsed
        if remaining < 5:
            break

        query_timeout = min(SAT_TIMEOUT, remaining / 2)
        sat, conflicts, dt, timed_out = check_k(N, care, mid, timeout_seconds=query_timeout)

        if timed_out:
            print(f"  [{elapsed:6.1f}s] k={mid}: TIMEOUT ({dt:.1f}s) [{lo}, {hi}]", flush=True)
            # Timeout is ambiguous; can't update bounds. Try slightly higher.
            lo = mid + 1
        elif sat:
            print(f"  [{elapsed:6.1f}s] k={mid}: SAT ({dt:.1f}s) [{lo}, {hi}]", flush=True)
            hi = mid
            best_ub = mid
        else:
            print(f"  [{elapsed:6.1f}s] k={mid}: UNSAT ({dt:.1f}s) [{lo}, {hi}]", flush=True)
            lo = mid + 1
            best_lb = mid

    # Final check
    if lo == hi and time.time() - t0 < budget_seconds:
        elapsed = time.time() - t0
        remaining = budget_seconds - elapsed
        if remaining >= 5:
            sat, conflicts, dt, timed_out = check_k(N, care, lo, timeout_seconds=min(SAT_TIMEOUT, remaining))
            if not timed_out:
                if sat:
                    best_ub = lo
                    print(f"  [{elapsed:6.1f}s] k={lo}: SAT ({dt:.1f}s) — OPTIMAL", flush=True)
                else:
                    best_lb = lo
                    print(f"  [{elapsed:6.1f}s] k={lo}: UNSAT ({dt:.1f}s)", flush=True)

    total_time = time.time() - t0
    return best_lb, best_ub, total_time


# ── Main ─────────────────────────────────────────────────────────────

def run_survey(N, ub_time=UB_TIME, lb_time=LB_TIME):
    """Run the full survey for a given N."""
    care = enumerate_care(N)
    print(f"\n{'='*60}")
    print(f"N={N}  |  {len(care)} semiprimes out of {1<<N} inputs")
    print(f"{'='*60}")

    total_t0 = time.time()

    # Phase 1: Upper bound
    print(f"\n--- Upper Bound Phase ({ub_time}s budget) ---", flush=True)
    ub = run_upper_bound(N, care, ub_time)
    if ub is not None:
        print(f"\n  Best upper bound: {ub} AND gates", flush=True)
    else:
        print(f"\n  No upper bound found!", flush=True)

    # Phase 2: Lower bound
    print(f"\n--- Lower Bound Phase ({lb_time}s budget) ---", flush=True)
    lb, lb_ub, lb_time_actual = run_lower_bound(N, care, lb_time, known_ub=ub)
    print(f"\n  Best lower bound: {lb} AND gates", flush=True)

    total_time = time.time() - total_t0
    gap = f"{ub - lb}" if (ub is not None and lb >= 0) else "?"

    # If SAT phase proved the optimum exactly, report it
    sat_proven_opt = None
    if lb >= 0 and lb_ub is not None and lb + 1 == lb_ub:
        sat_proven_opt = lb_ub

    print(f"\n{'='*60}")
    if sat_proven_opt is not None:
        print(f"N={N} | OPTIMAL={sat_proven_opt} (SAT-proven) | ABC heuristic={ub} | time={total_time:.0f}s")
    else:
        print(f"N={N} | UB={ub} | LB={lb} | gap={gap} | time={total_time:.0f}s")
    print(f"{'='*60}\n")

    return N, ub, lb, gap, total_time


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} N [ub_time] [lb_time]")
        sys.exit(1)

    N = int(sys.argv[1])
    ub_time = int(sys.argv[2]) if len(sys.argv) > 2 else UB_TIME
    lb_time = int(sys.argv[3]) if len(sys.argv) > 3 else LB_TIME

    run_survey(N, ub_time, lb_time)
