#!/usr/bin/env python3
"""Parallel portfolio for a single (N, k) exact-synthesis query.

Builds the canonical full-care CNF once (cegis_lb.build_cnf), then runs W
workers, each on a variable-permuted isomorphic copy (random permutation of
variable indices; a bijection, so satisfiability is preserved but the CDCL
search space differs).  Fixed 5000-conflict budget, first-to-decide wins.

A SAT result is decoded in the permuted space back to the original variable
numbering and verified against ALL care points before being reported.

Usage:
  python3 portfolio.py N k [--workers W] [--per-worker S]
"""

import argparse
import time
import random
import multiprocessing as mp
from pysat.solvers import Solver
import cegis_lb

CONF_BUDGET = 5000


def worker(args):
    N, k, clauses, nvars, perm, cap, solver_name = args
    pclauses = [[(perm[abs(l)] if l > 0 else -perm[abs(l)]) for l in cl]
                for cl in clauses]

    s = Solver(name=solver_name)
    for cl in pclauses:
        s.add_clause(cl)

    t0 = time.time()
    result = None
    try:
        while time.time() - t0 < cap:
            s.conf_budget(CONF_BUDGET)
            result = s.solve_limited()
            if result is not None:
                break
    except NotImplementedError:
        # Solver lacks limited solving (e.g. Lingeling): run unbounded.
        # The pool is terminated as soon as any worker decides, so a slow
        # unbounded worker is killed rather than blocking the portfolio.
        result = s.solve()
    conflicts = s.accum_stats().get("conflicts", 0)
    dt = time.time() - t0

    if result is None:
        s.delete()
        return {"status": "timeout", "k": k, "conflicts": conflicts, "elapsed": dt}

    if result is False:
        s.delete()
        return {"status": "unsat", "k": k, "conflicts": conflicts, "elapsed": dt}

    # SAT: recover original-variable model values.
    model = s.get_model()
    s.delete()
    model_set = set(model)
    inv_perm = [0] * (nvars + 1)
    for v in range(1, nvars + 1):
        inv_perm[perm[v]] = v
    orig_model = [inv_perm[abs(m)] if m > 0 else -inv_perm[abs(m)] for m in model]

    full_care = cegis_lb.enumerate_care(N)
    _, _, meta = cegis_lb.build_cnf(N, full_care, k)
    gates, outputs = cegis_lb.decode_model(orig_model, meta)
    correct, total, failing = cegis_lb.verify_care(meta, gates, outputs, full_care)
    return {"status": "sat" if correct == total else "error",
            "k": k, "conflicts": conflicts, "elapsed": dt,
            "correct": correct, "total": total,
            "gates": gates, "outputs": outputs}


def main():
    p = argparse.ArgumentParser(description="Parallel portfolio exact-synthesis query")
    p.add_argument("N", type=int)
    p.add_argument("ks", type=int, nargs="+")
    p.add_argument("--workers", type=int, default=16)
    p.add_argument("--per-worker", type=int, default=900)
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--solvers", type=str,
                   default="cd153,g4,mc,maplesat,m22,mcm,cd19,g3",
                   help="comma-separated solver names, round-robined across workers (lgl has no budgeted solving; exclude it)")
    args = p.parse_args()
    solvers = [s.strip() for s in args.solvers.split(",") if s.strip()]

    full_care = cegis_lb.enumerate_care(args.N)
    tasks = []
    per_k = {}
    for k in args.ks:
        clauses, nvars, _ = cegis_lb.build_cnf(args.N, full_care, k)
        per_k[k] = (nvars, len(clauses))
        w_start = (k - min(args.ks)) * args.workers
        rng = random.Random(args.seed + k)
        for w in range(args.workers):
            vals = list(range(1, nvars + 1))
            rng.shuffle(vals)
            perm = [0] * (nvars + 1)
            for v in range(1, nvars + 1):
                perm[v] = vals[v - 1]  # bijection on {1..nvars}
            sname = solvers[(w_start + w) % len(solvers)]
            tasks.append((args.N, k, clauses, nvars, perm, args.per_worker, sname))
    print(f"N={args.N} ks={args.ks} C={len(full_care)} "
          f"cnf={[(k, per_k[k][0], per_k[k][1]) for k in args.ks]} "
          f"workers={args.workers}/k per-worker={args.per_worker}s "
          f"solvers={solvers}", flush=True)

    t0 = time.time()
    pool_size = min(args.workers * len(args.ks), mp.cpu_count())
    pool = mp.get_context("fork").Pool(pool_size)
    results = list(pool.imap_unordered(worker, tasks))
    pool.terminate()
    pool.join()
    wall = time.time() - t0

    print(f"\nwall={wall:.1f}s", flush=True)
    for k in args.ks:
        rs = [r for r in results if r["k"] == k]
        sat = [r for r in rs if r["status"] == "sat"]
        unsat = [r for r in rs if r["status"] == "unsat"]
        decided = sat + unsat
        if decided:
            r = min(decided, key=lambda r: r["elapsed"])
            if r["status"] == "sat":
                print(f"k={k}: ** SAT ** {r['elapsed']:.1f}s {r['conflicts']}c "
                      f"(verified {r['correct']}/{r['total']})", flush=True)
                cegis_lb.print_circuit({'N': args.N, 'k': k},
                                       r["gates"], r["outputs"])
            else:
                print(f"k={k}: ** UNSAT ** {r['elapsed']:.1f}s "
                      f"{r['conflicts']}c -> LB >= {k+1}", flush=True)
        else:
            n = len(rs)
            print(f"k={k}: undecided ({n} workers, "
                  f"max {max(rs, key=lambda r: r['conflicts'])['conflicts']}c)",
                  flush=True)


if __name__ == "__main__":
    main()
