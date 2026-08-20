#!/usr/bin/env python3
"""Rank all candidate shared gates by total (cost(f) + per-output mins)."""
import json
from multiprocessing import Pool

from single_output import enumerate_care
from core_gate_search import (sim_single_circuit, sim_blif_gates, xor_vectors,
                              evaluate_candidate)

CARE = enumerate_care(6)
cand = {}
j = json.load(open("single_output_circuits.json"))
for name, spec in j.items():
    for kname, v in sim_single_circuit(spec["gates"], spec["out"], name).items():
        cand[kname] = v
for kname, v in sim_blif_gates().items():
    cand[kname] = v
for kname, v in xor_vectors().items():
    cand[kname] = v

uniq = {}
for name, v in cand.items():
    tv = tuple(v)
    if tv not in uniq:
        uniq[tv] = name

def main():
    results = []
    with Pool(6) as pool:
        for res in pool.imap_unordered(evaluate_candidate,
                                       (list(v) for v in uniq)):
            vec, cf, per, tot, _ = res
            if tot is not None:
                results.append((tot, uniq[tuple(vec)], cf, per))
    results.sort()
    print(f"{'total':>5} {'f':<18} {'cost(f)':>7}  per-out")
    for tot, name, cf, per in results[:20]:
        print(f"{tot:>5} {name:<18} {cf:>7}  {per}")


if __name__ == "__main__":
    main()
