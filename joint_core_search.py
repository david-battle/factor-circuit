#!/usr/bin/env python3
"""2-gate joint core search for N=6.

Enumerate cores {f,g} drawn from a candidate pool, evaluate each exactly:
    core_cost  = min(cost(f)+cost(g|f), cost(g)+cost(f|g))
    extensions = per-output min gates over {inputs, f, g}
    cumulative = core_cost + sum(extensions)
Report the best cores.  Budgets are generous (60s per search); normal
searches finish in ~1-2s, so a search only runs long if something is wrong.
"""

import json
import math
import time
from multiprocessing import Pool

from single_output import enumerate_care, check_single
from core_gate_search import sim_single_circuit, sim_blif_gates, xor_vectors

N = 6
CARE = enumerate_care(6)
OUTS = ["p1", "p2", "q1", "q2", "q3", "q4"]
TARGETS = {
    o: [((p if o.startswith("p") else q) >> int(o[1:])) & 1 for x, p, q in CARE]
    for o in OUTS
}
STANDALONE = {"p1": 5, "p2": 5, "q1": 5, "q2": 5, "q3": 6, "q4": 3}
BASELINE = 29

BUDGET = 60.0  # generous; normal search ~1-2s


def min_k(target, extras, cap):
    """Exact min gates; returns k, or None if undecided within BUDGET."""
    for e in extras:
        if target == e or [1 - t for t in target] == e:
            return 0
    for i in range(N):
        col = [(x >> i) & 1 for x, _, _ in CARE]
        if col == target or [1 - t for t in col] == target:
            return 0
    if all(v == 0 for v in target) or all(v == 1 for v in target):
        return 0
    for k in range(1, cap + 1):
        sat, _ = check_single(N, CARE, target, k, timeout_seconds=BUDGET,
                              extras=extras)
        if sat:
            return k
        if sat is None:
            return None
    return None  # cap should be >= true min (extras only help)


def build_pool():
    """Candidate pool: known circuit gates + 2-literal AND/OR family + XORs."""
    cand = {}
    j = json.load(open("single_output_circuits.json"))
    for name, spec in j.items():
        for kname, v in sim_single_circuit(spec["gates"], spec["out"],
                                           name).items():
            cand[kname] = v
    for kname, v in sim_blif_gates().items():
        cand[kname] = v
    for kname, v in xor_vectors().items():
        cand[kname] = v
    # 2-literal AND/OR family
    for i in range(N):
        for j in range(i + 1, N):
            for oi in (0, 1):   # polarity of literal i
                for oj in (0, 1):
                    for op in ("and", "or"):
                        ci = [(x >> i) & 1 for x, _, _ in CARE]
                        cj = [(x >> j) & 1 for x, _, _ in CARE]
                        li = [t ^ oi for t in ci]
                        lj = [t ^ oj for t in cj]
                        if op == "and":
                            v = [a & b for a, b in zip(li, lj)]
                            cand[f"lit(i={i},oi={oi},j={j},oj={oj},and)"] = v
                        else:
                            v = [a | b for a, b in zip(li, lj)]
                            cand[f"lit(i={i},oi={oi},j={j},oj={oj},or)"] = v
    return cand


def single_gate_eval(args):
    """Cost + per-output mins for sharing one function. Returns total."""
    vec = args
    cf = min_k(vec, [], 6)
    if cf is None:
        return (tuple(vec), None)
    total = cf
    for o in OUTS:
        k = min_k(TARGETS[o], [vec], STANDALONE[o])
        if k is None:
            return (tuple(vec), None)
        total += k
    return (tuple(vec), total)


def eval_pair(args):
    f, g = args
    cf = min_k(f, [], 6)
    cgf = min_k(g, [f], 6)
    cg = min_k(g, [], 6)
    cfg = min_k(f, [g], 6)
    if None in (cf, cgf, cg, cfg):
        return (None, None, None, None)
    core_cost = min(cf + cgf, cg + cfg)
    ext = {}
    for o in OUTS:
        k = min_k(TARGETS[o], [f, g], STANDALONE[o])
        if k is None:
            return (None, None, None, None)
        ext[o] = k
    return (core_cost, ext, core_cost + sum(ext.values()))


def main():
    t0 = time.time()
    cand = build_pool()
    uniq = {}
    for name, v in cand.items():
        tv = tuple(v)
        if tv not in uniq:
            uniq[tv] = name
    pool_vecs = [list(v) for v in uniq]
    print(f"pool: {len(cand)} raw -> {len(pool_vecs)} unique", flush=True)

    # Phase 1: single-gate totals -> filter pool
    nw = 12
    single = []
    with Pool(nw) as pool:
        for tv, total in pool.imap_unordered(single_gate_eval, pool_vecs):
            if total is not None:
                single.append((total, tv))
    single.sort()
    useful = [tv for total, tv in single if total < BASELINE]
    print(f"single-gate phase: {len(single)} evaluated, "
          f"{len(useful)} useful (< {BASELINE}) [{time.time()-t0:.0f}s]", flush=True)
    print("top-10 single gates:")
    for total, tv in single[:10]:
        print(f"   {uniq[tv]:<20} {total}")

    POOL = useful[:40]
    print(f"\njoint-core pool: {len(POOL)} functions "
          f"(top 40 by single-gate benefit)", flush=True)
    pairs = [(POOL[i], POOL[j]) for i in range(len(POOL))
             for j in range(i + 1, len(POOL))]
    print(f"pairs: {len(pairs)}", flush=True)
    print(f"est: ~{len(pairs) * 10 * 1.5 / nw / 60:.0f} min "
          f"@ ~1.5s/search avg over {nw} workers", flush=True)

    best = None
    n_done = 0
    t_phase = time.time()
    with Pool(nw) as pool:
        for (core_cost, ext, cum) in pool.imap_unordered(eval_pair, pairs):
            n_done += 1
            if cum is None:
                continue
            if best is None or cum < best[0]:
                best = (cum, core_cost, ext)
                print(f"  NEW BEST cumulative={cum} core_cost={core_cost} "
                      f"ext={ext} [{time.time()-t0:.0f}s]",
                      flush=True)
            if n_done % 200 == 0:
                print(f"  ... {n_done}/{len(pairs)} "
                      f"[{time.time()-t_phase:.0f}s]", flush=True)
    if best is None:
        print("no valid joint core found")
        return
    cum, core_cost, ext = best
    print("\n== best 2-gate joint core ==")
    print(f"cumulative = {cum} (baseline 29, current UB 19)")
    print(f"core_cost = {core_cost}, extensions = {ext}")


if __name__ == "__main__":
    main()
