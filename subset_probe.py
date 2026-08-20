#!/usr/bin/env python3
"""Probe k=11 on several care subsets in parallel to see if a small subset is
already UNSAT (raising LB) or yields a quickly-found candidate.

Usage: python3 subset_probe.py N k [--subsets a-b,c-d,...] [--workers W]
                                   [--per-worker S]
"""

import argparse
import time
import multiprocessing as mp
import cegis_lb
from pysat.solvers import Solver

CONF_BUDGET = 5000
SOLVERS = ["cd153", "g4", "mc", "maplesat", "m22", "mcm", "cd19", "g3"]


def worker(args):
    N, k, subset, cap, solver_name = args
    clauses, nvars, meta = cegis_lb.build_cnf(N, subset, k)
    s = Solver(name=solver_name)
    for cl in clauses:
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
        result = s.solve()
    conflicts = s.accum_stats().get("conflicts", 0)
    dt = time.time() - t0
    s.delete()
    return {"subset": len(subset), "solver": solver_name, "status":
            "timeout" if result is None else ("unsat" if result is False else "sat"),
            "conflicts": conflicts, "elapsed": dt,
            "nclauses": len(clauses)}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("N", type=int)
    p.add_argument("k", type=int)
    p.add_argument("--subsets", type=str, default=None,
                   help="comma-separated sizes or ranges like '10,12,14' or '10-14'")
    p.add_argument("--workers", type=int, default=16)
    p.add_argument("--per-worker", type=int, default=300)
    args = p.parse_args()

    care = cegis_lb.enumerate_care(args.N)
    C = len(care)
    sizes = []
    for tok in (args.subsets or f"{C}").split(","):
        tok = tok.strip()
        if "-" in tok:
            a, b = tok.split("-")
            sizes.extend(range(int(a), int(b) + 1))
        else:
            sizes.append(int(tok))
    sizes = sorted(set(s for s in sizes if 1 <= s <= C))

    tasks = []
    label = {}
    for size in sizes:
        idxs = list(range(0, C, max(1, C // size)))[:size]
        idxs = sorted(set(idxs))
        if len(idxs) < size:  # top up with middle indices
            j = C - 1
            while len(idxs) < size:
                idxs = sorted(set(idxs) | {j})
                j -= 1
        idxs = idxs[:size]
        label[size] = [care[i][0] for i in idxs]
        for w in range(args.workers):
            tasks.append((args.N, args.k, [care[i] for i in idxs],
                          args.per_worker, SOLVERS[(w + size) % len(SOLVERS)]))

    print(f"N={args.N} k={args.k} subsets={sizes} workers/size={args.workers} "
          f"per-worker={args.per_worker}s", flush=True)
    t0 = time.time()
    pool = mp.get_context("fork").Pool(min(args.workers * len(sizes), mp.cpu_count()))
    results = list(pool.imap_unordered(worker, tasks))
    pool.terminate(); pool.join()

    for size in sizes:
        rs = [r for r in results if r["subset"] == size]
        dec = [r for r in rs if r["status"] in ("sat", "unsat")]
        if dec:
            r = min(dec, key=lambda r: r["elapsed"])
            print(f"subset={size} care={label[size]}: {r['status'].upper()} "
                  f"{r['elapsed']:.1f}s {r['conflicts']}c "
                  f"(solver={r['solver']}, {r['nclauses']} clauses)", flush=True)
        else:
            r = max(rs, key=lambda r: r["conflicts"])
            print(f"subset={size}: undecided ({len(rs)} workers, "
                  f"max {r['conflicts']}c)", flush=True)
    print(f"wall={time.time()-t0:.1f}s", flush=True)


if __name__ == "__main__":
    main()
