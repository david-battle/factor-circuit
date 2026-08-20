#!/usr/bin/env python3
"""Beam search over shared cores for N=6, sizes 1->2->3.

At each level keep the top-B cores by cumulative total (core_cost + sum of
per-output extension mins).  Core cost is exact: min over gate orderings.
Budgets are generous (60s/search); normal searches finish in ~1-2s.
"""

import json
import time
from multiprocessing import Pool

from single_output import enumerate_care, check_single
from joint_core_search import build_pool, min_k, TARGETS, STANDALONE, BASELINE

OUTS = ["p1", "p2", "q1", "q2", "q3", "q4"]
BEAM = 25


def core_cost(gates):
    """Exact cost of building the gate set {gates} from inputs (min ordering)."""
    m = len(gates)
    if m == 1:
        return min_k(gates[0], [], 6)
    if m == 2:
        f, g = gates
        cf = min_k(f, [], 6)
        cgf = min_k(g, [f], 6)
        cg = min_k(g, [], 6)
        cfg = min_k(f, [g], 6)
        if None in (cf, cgf, cg, cfg):
            return None
        return min(cf + cgf, cg + cfg)
    a, b, c = gates
    ca = min_k(a, [], 6); cb = min_k(b, [], 6); cc = min_k(c, [], 6)
    cab = min_k(b, [a], 6); cba = min_k(a, [b], 6)
    cac = min_k(c, [a], 6); cca = min_k(a, [c], 6)
    cbc = min_k(c, [b], 6); ccb = min_k(b, [c], 6)
    cabc = min_k(c, [a, b], 6); cbac = min_k(b, [a, c], 6); ccab = min_k(a, [b, c], 6)
    if None in (ca, cb, cc, cab, cba, cac, cca, cbc, ccb, cabc, cbac, ccab):
        return None
    perms = [
        ca + cab + cabc, ca + cac + cbac,
        cb + cba + cabc, cb + cbc + ccab,
        cc + cca + cbac, cc + ccb + ccab,
    ]
    return min(perms)


def eval_task(task):
    """task = tuple of gate vectors. Returns (canonical set, cumulative)."""
    gates = task
    cc = core_cost(list(gates))
    if cc is None:
        return (tuple(sorted(gates)), None)
    total = cc
    for o in OUTS:
        k = min_k(TARGETS[o], list(gates), STANDALONE[o])
        if k is None:
            return (tuple(sorted(gates)), None)
        total += k
    return (tuple(sorted(gates)), total)


def main():
    t0 = time.time()
    pool = build_pool()
    try:
        extra = json.load(open("core_candidates.json"))
    except (FileNotFoundError, json.JSONDecodeError):
        extra = {}
    for name, v in extra.items():
        pool[name] = v
    uniq = {}
    for name, v in pool.items():
        uniq[tuple(v)] = name
    pool_vecs = [tuple(v) for v in uniq]
    print(f"pool: {len(pool)} raw -> {len(uniq)} unique", flush=True)

    nw = 12

    # level 1
    results = []
    with Pool(nw) as pool:
        for key, tot in pool.imap_unordered(eval_task, [[v] for v in pool_vecs]):
            if tot is not None:
                results.append((tot, key))
    results.sort()
    level1 = results[:BEAM]
    print(f"level 1: {len(results)} cores, best {results[0][0]}, "
          f"keeping top {len(level1)} [{time.time()-t0:.0f}s]", flush=True)

    # level 2
    tasks = set()
    for _, key in level1:
        g1 = key[0]
        for tv in pool_vecs:
            if tv == g1:
                continue
            tasks.add(tuple(sorted((g1, tv))))
    print(f"level 2 est: {len(tasks)} pairs x ~10 searches "
          f"~ {len(tasks)*10*1.5/nw/60:.0f} min", flush=True)
    cores2 = []
    with Pool(nw) as pool:
        for key, tot in pool.imap_unordered(eval_task, list(tasks)):
            if tot is not None:
                cores2.append((tot, key))
    cores2.sort()
    level2 = cores2[:BEAM]
    print(f"level 2: best {cores2[0][0]} over {len(cores2)} pairs, "
          f"keeping top {len(level2)} [{time.time()-t0:.0f}s]", flush=True)
    for tot, key in cores2[:5]:
        print(f"   {tot}  {[uniq.get(g) for g in key]}")

    # level 3
    tasks = set()
    for _, key in level2:
        for tv in pool_vecs:
            if tv in key:
                continue
            tasks.add(tuple(sorted(key + (tv,))))
    print(f"level 3 est: {len(tasks)} triples x ~18 searches "
          f"~ {len(tasks)*18*1.5/nw/60:.0f} min", flush=True)
    best = None
    n3 = 0
    with Pool(nw) as pool:
        for key, tot in pool.imap_unordered(eval_task, list(tasks)):
            n3 += 1
            if tot is not None and (best is None or tot < best[0]):
                best = (tot, key)
                print(f"  NEW BEST size-3 cumulative={tot} "
                      f"gates={[uniq.get(g) for g in key]} "
                      f"[{time.time()-t0:.0f}s]", flush=True)
            if n3 % 300 == 0:
                print(f"  ... {n3}/{len(tasks)} [{time.time()-t0:.0f}s]", flush=True)
    print(f"\n== beam result ==")
    print(f"level 1 best: {level1[0][0]}")
    print(f"level 2 best: {cores2[0][0]}")
    if best:
        print(f"level 3 best: {best[0]}")
        print(f"   gates: {[uniq.get(g) for g in best[1]]}")
    print(f"   (baseline 29, current UB 19, greedy plateau 19)")
    print(f"total wall time: {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
