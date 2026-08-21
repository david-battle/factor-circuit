#!/usr/bin/env python3
"""Pair-output exact-synthesis lower bound.

Any full factoring circuit, cut down to the gates feeding two outputs (bi, bj),
is a valid AIG computing that pair on the care set.  So the full circuit has at
least as many gates as the minimum for the pair, and the max over pairs of the
pair-minimum is a circuit lower bound (strictly >= the per-output LB).

For a pair, find the largest k for which NO k-gate AIG computes both bits on
the care set.  If k is UNSAT, the pair needs at least k+1 gates.

Usage: pair_output_lb.py N NAME1 NAME2 [--max-k K] [--timeout SEC]
"""

import sys
import time

from single_output import check_multi, enumerate_care


def target_vector(care, name):
    is_p = name.startswith("p")
    bit = int(name[1:])
    return [((p if is_p else q) >> bit) & 1 for x, p, q in care]


def main():
    args = sys.argv[1:]
    N = int(args[0])
    name1, name2 = args[1], args[2]
    max_k = 12
    timeout = 60.0
    if "--max-k" in args:
        max_k = int(args[args.index("--max-k") + 1])
    if "--timeout" in args:
        timeout = float(args[args.index("--timeout") + 1])

    care = enumerate_care(N)
    print(f"{len(care)} care points")
    t1 = target_vector(care, name1)
    t2 = target_vector(care, name2)

    lb = -1  # largest k proven UNSAT
    pair_min = None
    for k in range(0, max_k + 1):
        t0 = time.time()
        sat, _ = check_multi(N, care, [t1, t2], k, timeout_seconds=timeout)
        dt = time.time() - t0
        if sat:
            pair_min = k
            print(f"{name1},{name2}: k={k} SAT ({dt:.1f}s) -> pair-min={k}")
            break
        elif sat is None:
            print(f"{name1},{name2}: k={k} UNDECIDED ({dt:.1f}s) "
                  f"-> LB >= {lb + 1}")
            break
        else:
            lb = k
            print(f"{name1},{name2}: k={k} UNSAT ({dt:.1f}s)")

    if pair_min is not None:
        print(f"{name1},{name2}: exact pair-min = {pair_min}")
    else:
        print(f"{name1},{name2}: PROVEN pair-min >= {lb + 1} "
              f"-> circuit LB >= {lb + 1}")


if __name__ == "__main__":
    main()
