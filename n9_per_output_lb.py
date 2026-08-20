#!/usr/bin/env python3
"""Per-output exact-synthesis lower bound for N=9.

For each nontrivial output bit, proves UNSAT for as large a gate budget k as
feasible. If k UNSAT, that output needs at least k+1 gates, so the full
factoring circuit (which must compute this output) needs at least k+1 gates.
The max over outputs is the circuit lower bound.
"""

import time

from single_output import check_single, enumerate_care


def main():
    N = 9
    care = enumerate_care(N)
    print(f"{len(care)} care points")

    names = [f"p{i}" for i in range(N)] + [f"q{i}" for i in range(N)]
    best_lb = 0
    for name in names:
        is_p = name.startswith("p")
        bit = int(name[1:])
        target = [((p if is_p else q) >> bit) & 1 for x, p, q in care]

        # trivial: constant or equal to an input (or complement)
        if all(v == target[0] for v in target):
            print(f"{name}: constant {target[0]} -> 0 gates")
            continue
        direct = None
        for i in range(N):
            col = [(x >> i) & 1 for x, _, _ in care]
            if col == target or [1 - v for v in col] == target:
                direct = i
                break
        if direct is not None:
            print(f"{name}: = input x{direct} -> 0 gates")
            continue

        # find largest k provably UNSAT (and confirm a SAT witness exists)
        lb = 0          # largest k proven UNSAT
        witness = None  # k where SAT found
        for k in range(1, 8):
            t0 = time.time()
            sat, _ = check_single(N, care, target, k, timeout_seconds=30.0)
            dt = time.time() - t0
            if sat:
                print(f"{name}: k={k} SAT ({dt:.1f}s) -> min={k}")
                witness = k
                break
            elif sat is None:
                print(f"{name}: k={k} UNDECIDED ({dt:.1f}s) -> LB >= {lb+1}")
                break
            else:
                lb = k
                print(f"{name}: k={k} UNSAT ({dt:.1f}s)")
        if witness is None and lb > 0:
            # proved UNSAT without finding SAT yet
            print(f"{name}: PROVEN min >= {lb + 1}")
        best_lb = max(best_lb, lb)

    print(f"\nBest proven circuit LB = {best_lb + 1} AND gates "
          f"({best_lb} UNSAT, so every circuit needs >= {best_lb + 1})")


if __name__ == "__main__":
    main()
