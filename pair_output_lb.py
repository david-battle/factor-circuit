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
    raw = sys.argv[1:]
    N = int(raw[0])
    names = []
    max_k = 12
    timeout = 60.0
    i = 1
    while i < len(raw):
        a = raw[i]
        if a == "--max-k":
            max_k = int(raw[i + 1])
            i += 2
        elif a == "--timeout":
            timeout = float(raw[i + 1])
            i += 2
        else:
            names.append(a)
            i += 1
    if len(names) < 2:
        sys.exit("usage: pair_output_lb.py N NAME1 NAME2 [NAME3 ...] "
                 "[--max-k K] [--timeout SEC]")

    care = enumerate_care(N)
    print(f"{len(care)} care points")
    targets = [target_vector(care, name) for name in names]
    label = ",".join(names)

    lb = -1  # largest k proven UNSAT
    multi_min = None
    for k in range(0, max_k + 1):
        t0 = time.time()
        sat, _ = check_multi(N, care, targets, k, timeout_seconds=timeout)
        dt = time.time() - t0
        if sat:
            multi_min = k
            print(f"{label}: k={k} SAT ({dt:.1f}s) -> k-tuple-min={k}")
            break
        elif sat is None:
            print(f"{label}: k={k} UNDECIDED ({dt:.1f}s) "
                  f"-> LB >= {lb + 1}")
            break
        else:
            lb = k
            print(f"{label}: k={k} UNSAT ({dt:.1f}s)")

    if multi_min is not None:
        print(f"{label}: exact k-tuple-min = {multi_min}")
    else:
        print(f"{label}: PROVEN k-tuple-min >= {lb + 1} "
              f"-> circuit LB >= {lb + 1}")


if __name__ == "__main__":
    main()
