#!/usr/bin/env python3
"""Find the single best shared core gate for N=6.

Total with a shared gate f = cost(f) + sum over outputs of min gates to
realize the output over {inputs, f}.  Candidates are the gates of all known
circuits (standalone per-output circuits + the 19-gate UB BLIF) plus all
XOR/XNOR functions of input pairs.  Baseline (no sharing) = 29 gates.
"""

import json
import math
import time
from multiprocessing import Pool

from window_opt import parse_blif
from single_output import enumerate_care, check_single

N = 6
CARE = enumerate_care(6)


def is_prime(n):
    if n < 2:
        return False
    for d in range(2, math.isqrt(n) + 1):
        if n % d == 0:
            return False
    return True


def target_bits(name):
    is_p = name.startswith("p")
    bit = int(name[1:])
    return [((p if is_p else q) >> bit) & 1 for x, p, q in CARE]


OUTS = ["p1", "p2", "q1", "q2", "q3", "q4"]
TARGETS = {o: target_bits(o) for o in OUTS}
STANDALONE = {"p1": 5, "p2": 5, "q1": 5, "q2": 5, "q3": 6, "q4": 3}


def sim_single_circuit(gates, out, name, extras=None):
    """Compute every gate's truth vector over CARE for a circuit over extras."""
    extras = extras or []
    vals = {"const0": [0] * len(CARE)}
    for i in range(N):
        vals[f"in{i}"] = [(x >> i) & 1 for x, _, _ in CARE]
    for j, ev in enumerate(extras):
        vals[f"ex{j}"] = list(ev)
    vecs = {}
    for g, ((a, ia), (b, ib)) in enumerate(gates):
        va = vals[a]
        vb = vals[b]
        v = [((va[t] ^ ia) & (vb[t] ^ ib)) for t in range(len(CARE))]
        vecs[f"{name}.g{g}"] = v
        vals[f"g{g}"] = v
    src, inv = out
    vecs[f"{name}.out"] = [vals[src][t] ^ inv for t in range(len(CARE))]
    return vecs


def sim_blif_gates():
    aig = parse_blif("factor6_opt_final_opt.blif")
    nodevals = {}
    vecs = {}
    for n, (typ, args) in aig.nodes.items():
        if typ == "PI":
            bit = int(n[1:])
            nodevals[n] = [(x >> bit) & 1 for x, _, _ in CARE]
        elif typ == "CONST0":
            nodevals[n] = [0] * len(CARE)
        elif typ == "CONST1":
            nodevals[n] = [1] * len(CARE)
        elif typ == "BUF":
            nodevals[n] = nodevals[args[0]]
        elif typ == "NOT":
            nodevals[n] = [1 - v for v in nodevals[args[0]]]
        elif typ == "AND":
            v = [nodevals[args[0]][t] & nodevals[args[2]][t]
                 for t in range(len(CARE))]
            nodevals[n] = v
            vecs[f"blif.{n}"] = v
    return vecs


def xor_vectors():
    vecs = {}
    for i in range(N):
        for j in range(i + 1, N):
            col_i = [(x >> i) & 1 for x, _, _ in CARE]
            col_j = [(x >> j) & 1 for x, _, _ in CARE]
            v = [a ^ b for a, b in zip(col_i, col_j)]
            vecs[f"xor({i},{j})"] = v
            vecs[f"xnor({i},{j})"] = [1 - t for t in v]
    return vecs


def min_k(target, extras, cap):
    """Min gates to realize target with sources = inputs + extras, capped at cap."""
    if cap is None:
        cap = 9
    # k=0: target equals const / input literal / extra vector (or complement)
    for e in extras:
        if target == e:
            return 0, ("ex", e)
        if [1 - t for t in target] == e:
            return 0, ("ex~", e)
    for i in range(N):
        col = [(x >> i) & 1 for x, _, _ in CARE]
        if col == target:
            return 0, ("in", i)
        if [1 - t for t in col] == target:
            return 0, ("in~", i)
    if all(v == 0 for v in target):
        return 0, ("const0", None)
    if all(v == 1 for v in target):
        return 0, ("const1", None)
    for k in range(1, cap + 1):
        sat, model = check_single(N, CARE, target, k, timeout_seconds=8.0,
                                  extras=extras)
        if sat:
            return k, ("gates", None)
    return None, ("undecided", None)


def evaluate_candidate(vec):
    # cost(f): min gates to build f from inputs alone
    c, _ = min_k(vec, [], 6)
    if c is None:
        return (vec, None, None, None, None)
    cost_f = c

    total = cost_f
    per_out = {}
    for o in OUTS:
        cap = STANDALONE[o]
        k, _ = min_k(TARGETS[o], [vec], cap)
        if k is None:
            k = cap  # give up gracefully
        per_out[o] = k
        total += k
    return (vec, cost_f, per_out, total, None)


def main():
    cand = {}

    # standalone circuit gates
    j = json.load(open("single_output_circuits.json"))
    for name, spec in j.items():
        for kname, v in sim_single_circuit(spec["gates"], spec["out"], name).items():
            cand[kname] = v
    # blif gates
    for kname, v in sim_blif_gates().items():
        cand[kname] = v
    # xor/xnor pairs (cost computed exactly)
    for kname, v in xor_vectors().items():
        cand[kname] = v

    # dedupe by truth vector, keep first name
    uniq = {}
    for name, v in cand.items():
        tv = tuple(v)
        if tv not in uniq:
            uniq[tv] = name
    print(f"{len(cand)} raw candidates -> {len(uniq)} unique functions")

    items = [list(v) for v in uniq]  # vector list per candidate

    best = None
    t0 = time.time()
    with Pool(6) as pool:
        for i, res in enumerate(pool.imap_unordered(evaluate_candidate, items)):
            vec, cost_f, per_out, total, _ = res
            if total is None:
                continue
            if best is None or total < best[0]:
                best = (total, uniq[tuple(vec)], cost_f, per_out)
                print(f"[{i}/{len(items)} {time.time()-t0:.0f}s] NEW BEST total={total} "
                      f"f={uniq[tuple(vec)]} cost(f)={cost_f} per-out={per_out}", flush=True)
            if (i + 1) % 25 == 0:
                print(f"  ... {i+1}/{len(items)} done, current best {best[0]} "
                      f"({time.time()-t0:.0f}s)", flush=True)

    print("\n== best single shared gate ==")
    total, name, cost_f, per_out = best
    print(f"f = {name}")
    print(f"cost(f) = {cost_f}")
    print(f"per-output mins with f: {per_out}")
    print(f"TOTAL = {total}  (baseline no-sharing 29, current UB 19)")


if __name__ == "__main__":
    main()
