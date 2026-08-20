#!/usr/bin/env python3
"""Greedy incremental shared-core builder for N=6.

Start with no sharing (29 gates).  At each step, pick the single best next
shared gate f (minimizing cost(f|current core) + sum of per-output mins over
{inputs, core, f}), add it to the core, re-synthesize each output, and use the
decoded gates as new candidates.  Stop when no candidate improves the total.
"""

import json
import math
import time
from multiprocessing import Pool

from single_output import (enumerate_care, check_single, build_single_cnf,
                           decode_single)
from window_opt import parse_blif
from core_gate_search import sim_single_circuit, sim_blif_gates, xor_vectors
from joint_core_search import build_pool

CAND_FILE = "core_candidates.json"

N = 6
CARE = enumerate_care(6)

OUTS = ["p1", "p2", "q1", "q2", "q3", "q4"]
TARGETS = {
    o: [((p if o.startswith("p") else q) >> int(o[1:])) & 1 for x, p, q in CARE]
    for o in OUTS
}
STANDALONE = {"p1": 5, "p2": 5, "q1": 5, "q2": 5, "q3": 6, "q4": 3}
BASELINE = sum(STANDALONE.values())

TIMEOUT = 60.0  # generous; normal searches finish in ~1-2s


def min_k(target, extras, cap):
    if cap is None:
        cap = 7
    for e in extras:
        if target == e:
            return 0
        if [1 - t for t in target] == e:
            return 0
    for i in range(N):
        col = [(x >> i) & 1 for x, _, _ in CARE]
        if col == target or [1 - t for t in col] == target:
            return 0
    if all(v == 0 for v in target) or all(v == 1 for v in target):
        return 0
    for k in range(1, cap + 1):
        sat, _ = check_single(N, CARE, target, k, timeout_seconds=TIMEOUT,
                              extras=extras)
        if sat:
            return k
    return cap  # give up


def eval_candidate(args):
    vec, extras = args
    cost_f = min_k(vec, extras, 6)
    per = {}
    for o in OUTS:
        per[o] = min_k(TARGETS[o], extras + [vec], STANDALONE[o])
    return (vec, cost_f, per, cost_f + sum(per.values()))


def seed_candidates():
    cand = build_pool()          # standalone+blif+xor+2-literal family
    try:
        extra = json.load(open(CAND_FILE))
    except (FileNotFoundError, json.JSONDecodeError):
        extra = {}
    for name, v in extra.items():
        cand[name] = v
    return cand


def dedupe(cand):
    uniq = {}
    for name, v in cand.items():
        tv = tuple(v)
        if tv not in uniq:
            uniq[tv] = name
    return uniq


def main():
    cand = seed_candidates()
    extras = []           # list of truth vectors, in chosen order
    core_names = []       # human names
    core_cost = 0.0       # cumulative cost of the core
    cum = BASELINE        # cumulative construction total
    t0 = time.time()
    print(f"baseline (no sharing) = {cum}")

    step = 0
    while True:
        step += 1
        uniq = dedupe(cand)
        # drop candidates already functionally present (cost 0, no benefit)
        items = []
        for tv, name in uniq.items():
            v = list(tv)
            if any(v == e or [1 - t for t in v] == e for e in extras):
                continue
            items.append((v, extras))
        print(f"\n== step {step}: {len(items)} candidates over core "
              f"{core_names} (core cost {core_cost}) ==")

        best = None
        with Pool(6) as pool:
            for res in pool.imap_unordered(eval_candidate, items):
                vec, cf, per, t = res
                # cumulative total if this gate were adopted: (core_cost + cf)
                # + sum(per).  Marginal total t = cf + sum(per).
                cum_t = core_cost + cf + sum(per.values())
                if best is None or cum_t < best[0]:
                    best = (cum_t, t, vec, cf, per)
        cum_t, t, vec, cf, per = best
        print(f"best: marginal {t} -> CUMULATIVE {cum_t} (cost(f) {cf}) "
              f"per-out {per} [{time.time()-t0:.0f}s]", flush=True)
        if cum_t >= cum:
            print("no cumulative improvement; stopping.")
            break

        # adopt the new core gate
        name = uniq.get(tuple(vec))
        extras.append(vec)
        core_names.append(name)
        core_cost += cf
        cum = cum_t
        print(f"-> adopt {name}: core={core_names} core_cost={core_cost} "
              f"CUMULATIVE={cum}")

        # re-synthesize each output over the new core and harvest new gates
        new_cands = 0
        for o in OUTS:
            k = per[o]
            if k == 0:
                continue
            clauses, nvars, meta = build_single_cnf(N, CARE, TARGETS[o], k,
                                                    extras)
            from pysat.solvers import Solver
            s = Solver(name="cd153")
            for cl in clauses:
                s.add_clause(cl)
            sat = s.solve()
            if not sat:
                s.delete()
                continue
            model = s.get_model()
            s.delete()
            gates, out = decode_single(meta, model)
            for name_, v in sim_single_circuit(gates, out, f"core{step}.{o}",
                                               extras).items():
                if tuple(v) not in cand:
                    cand[name_] = v
                    new_cands += 1
        if new_cands:
            persist = dict(json.load(open(CAND_FILE)) if
                           __import__("os").path.exists(CAND_FILE) else {})
            for name_, v in cand.items():
                if name_.startswith(f"core{step}."):
                    persist[name_] = v
            with open(CAND_FILE, "w") as f:
                json.dump(persist, f)
        print(f"   harvested {new_cands} new candidate functions "
              f"(pool now {len(cand)})")

    print("\n== final incremental core ==")
    print(f"core gates: {core_names}")
    print(f"core cost: {core_cost}")
    print(f"CUMULATIVE TOTAL = {cum}  (baseline 29, current UB 19)")


if __name__ == "__main__":
    main()
