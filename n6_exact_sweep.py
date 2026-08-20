#!/usr/bin/env python3
"""Parallel N=6 exact-synthesis sweep.

Runs the CEGIS loop (SAT direction: small care subset, gradual counterexample
growth) for k=11..19 across the available cores.  The smallest k that returns
a verified circuit is the exact minimum, provided every smaller k is proven
UNSAT.  Follow-up full-seed UNSAT proofs close any lower-bound uncertainty.

Usage:
  python3 n6_exact_sweep.py [--workers N] [--per-k S] [--start k0] [--end k1]
"""

import argparse
import time
import multiprocessing as mp
import cegis_lb

N = 6


def one_k(args):
    k, seed_size, max_add, timeout = args
    full_care = cegis_lb.enumerate_care(N)
    return k, cegis_lb.cegis_prove(N, k, full_care, seed_size=seed_size,
                                   timeout=timeout, max_add=max_add)


def main():
    p = argparse.ArgumentParser(description="Parallel N=6 exact-synthesis sweep")
    p.add_argument("--workers", type=int, default=min(16, mp.cpu_count()))
    p.add_argument("--per-k", type=int, default=600, help="per-k timeout (s)")
    p.add_argument("--start", type=int, default=11)
    p.add_argument("--end", type=int, default=19)
    p.add_argument("--max-add", type=int, default=4,
                   help="counterexamples per iteration (0 = add all)")
    p.add_argument("--seed", type=int, default=None,
                   help="initial care-subset size (default: small, CEGIS-native)")
    args = p.parse_args()

    ks = list(range(args.start, args.end + 1))
    full_care = cegis_lb.enumerate_care(N)
    seed_size = args.seed if args.seed is not None else \
        max(1, min(8, len(full_care) // 4))

    print(f"N={N} C={len(full_care)} sweep k={ks} workers={args.workers} "
          f"per-k={args.per_k}s seed={seed_size} max_add={args.max_add}",
          flush=True)

    tasks = [(k, seed_size, args.max_add, args.per_k) for k in ks]
    t0 = time.time()
    with mp.get_context("fork").Pool(args.workers) as pool:
        results = dict(pool.imap_unordered(one_k, tasks))

    print(f"\nsweep finished in {time.time() - t0:.1f}s", flush=True)
    print(f"{'k':>3} | {'status':>8} | {'iters':>5} | {'subset':>6} | "
          f"{'clauses':>7} | {'conflicts':>9} | {'elapsed':>8}", flush=True)
    print("-" * 75, flush=True)
    for k in ks:
        r = results[k]
        print(f"{k:>3} | {r['status']:>8} | {r.get('iterations', 0):>5} | "
              f"{r.get('subset_size', 0):>6} | {r.get('clauses', 0):>7} | "
              f"{r.get('conflicts', 0):>9} | {r.get('elapsed', 0):>7.1f}s",
              flush=True)

    sat_ks = [k for k in ks if results[k]['status'] == 'sat']
    unsat_ks = [k for k in ks if results[k]['status'] == 'unsat']
    undec_ks = [k for k in ks if results[k]['status'] == 'timeout']

    print("\n--- summary ---", flush=True)
    if sat_ks:
        kmin = min(sat_ks)
        lower_undecided = [k for k in ks if k < kmin and k not in unsat_ks]
        print(f"smallest SAT k = {kmin} (exact minimum candidate)", flush=True)
        if lower_undecided:
            print(f"CAUTION: k values {lower_undecided} below {kmin} are "
                  f"NOT proven UNSAT (timed out); run follow-up full-seed "
                  f"UNSAT proofs to confirm LB = {kmin}.", flush=True)
            print(f"Current lower bound: {max(unsat_ks) + 1 if unsat_ks else 11}",
                  flush=True)
        else:
            print(f"ALL k<{kmin} proven UNSAT -> EXACT minimum = {kmin} "
                  f"(gap to UB closed)", flush=True)
    else:
        print("no SAT found in range; lower bound raised to "
              f"{max(unsat_ks) + 1 if unsat_ks else 'unknown'}", flush=True)
    if undec_ks:
        print(f"timed out k: {undec_ks}", flush=True)


if __name__ == "__main__":
    main()
