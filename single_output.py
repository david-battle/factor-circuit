#!/usr/bin/env python3
"""Per-output exact synthesis: synthesize each output bit as its OWN circuit.

For each nontrivial output bit of the N=6 factoring function, find the minimum
number of AIG AND gates needed to realize that partial Boolean function on the
care points, with the output allowed to come from any gate/input/constant with
free inversion.  Gates are NOT shared between outputs; the sum of per-output
minimums is the zero-sharing construction cost.
"""

import math
import time

from pysat.solvers import Solver

# ── encoding (mirrors cegis_lb.build_cnf, single output) ──────────────

def build_multi_cnf(N, care, targets, k, extras=None):
    """Encode "a k-gate AIG whose outputs equal targets[j][t] on care[t]".

    targets is a list of truth vectors (len C); targets[j][t] in {0,1} is the
    required value of output j on care point t.  Outputs may select any gate,
    input, or constant (free inversion), so two outputs can share one gate.
    extras: list of truth vectors (len C) for shared sources available to every
    output (e.g. previously-chosen core gates).  Returns (clauses, nvars, meta).
    """
    C = len(care)
    extras = extras or []
    next_var = 1
    clauses = []

    def new_var():
        nonlocal next_var
        v = next_var
        next_var += 1
        return v

    sig = [[new_var() for _ in range(C)] for _ in range(k)]
    gate_sel_list = []
    gate_inv_list = []
    gate_avail_list = []

    for g in range(k):
        available = ["const0"] + [f"in{i}" for i in range(N)] + [
            f"ex{j}" for j in range(len(extras))
        ] + [f"g{i}" for i in range(g)]
        gate_selectors = []
        gate_invs = []
        gate_selected = []
        for input_num in range(2):
            selectors = [new_var() for _ in available]
            inv = new_var()
            selected = [new_var() for _ in range(C)]

            clauses.append(selectors)  # at-least-one
            for i in range(len(selectors)):
                for j in range(i + 1, len(selectors)):
                    clauses.append([-selectors[i], -selectors[j]])  # pairwise AMO

            for si, source in enumerate(available):
                sel = selectors[si]
                for t, (x, _, _) in enumerate(care):
                    a = selected[t]
                    if source == "const0":
                        clauses.append([-sel, -inv, a])
                        clauses.append([-sel, inv, -a])
                    elif source.startswith("in"):
                        bit = int(source[2:])
                        value = (x >> bit) & 1
                        if value == 0:
                            clauses.append([-sel, -inv, a])
                            clauses.append([-sel, inv, -a])
                        else:
                            clauses.append([-sel, -inv, -a])
                            clauses.append([-sel, inv, a])
                    elif source.startswith("ex"):
                        value = extras[int(source[2:])][t]
                        if value == 0:
                            clauses.append([-sel, -inv, a])
                            clauses.append([-sel, inv, -a])
                        else:
                            clauses.append([-sel, -inv, -a])
                            clauses.append([-sel, inv, a])
                    else:
                        pg = int(source[1:])
                        v = sig[pg][t]
                        clauses.append([-sel, -v, -inv, -a])
                        clauses.append([-sel, v, inv, -a])
                        clauses.append([-sel, -v, inv, a])
                        clauses.append([-sel, v, -inv, a])

            gate_selectors.append(selectors)
            gate_invs.append(inv)
            gate_selected.append(selected)

        # input symmetry: source(input0) <= source(input1)
        sel0, sel1 = gate_selectors
        for i in range(len(sel0)):
            for j in range(i):
                clauses.append([-sel0[i], -sel1[j]])

        a, b = gate_selected
        for t in range(C):
            z = sig[g][t]
            clauses.append([-z, a[t]])
            clauses.append([-z, b[t]])
            clauses.append([z, -a[t], -b[t]])

        gate_sel_list.append(gate_selectors)
        gate_inv_list.append(gate_invs)
        gate_avail_list.append(available)

    # outputs, each pinned to its own target vector
    available_out = ["const0"] + [f"in{i}" for i in range(N)] + [
        f"ex{j}" for j in range(len(extras))
    ] + [f"g{i}" for i in range(k)]
    out_info = []
    for target_bits in targets:
        selectors = [new_var() for _ in available_out]
        inv = new_var()
        clauses.append(selectors)
        for i in range(len(selectors)):
            for j in range(i + 1, len(selectors)):
                clauses.append([-selectors[i], -selectors[j]])

        for si, source in enumerate(available_out):
            sel = selectors[si]
            for t, (x, _, _) in enumerate(care):
                required = target_bits[t]
                if source == "const0":
                    if required:
                        clauses.append([-sel, inv])
                    else:
                        clauses.append([-sel, -inv])
                elif source.startswith("in"):
                    source_value = (x >> int(source[2:])) & 1
                    if source_value == required:
                        clauses.append([-sel, -inv])
                    else:
                        clauses.append([-sel, inv])
                elif source.startswith("ex"):
                    source_value = extras[int(source[2:])][t]
                    if source_value == required:
                        clauses.append([-sel, -inv])
                    else:
                        clauses.append([-sel, inv])
                else:
                    source_value = sig[int(source[1:])][t]
                    if required:
                        clauses.append([-sel, source_value, inv])
                        clauses.append([-sel, -source_value, -inv])
                    else:
                        clauses.append([-sel, -source_value, inv])
                        clauses.append([-sel, source_value, -inv])

        out_info.append((selectors, inv, available_out))

    meta = {
        'k': k, 'N': N, 'care': care,
        'gate_sel_list': gate_sel_list,
        'gate_inv_list': gate_inv_list,
        'gate_avail_list': gate_avail_list,
        'out_info': out_info,
    }
    return clauses, next_var - 1, meta


def decode_multi(meta, model, extras_names=None):
    """Return (gate_specs, output_specs) from a SAT model.

    gate_specs[g] = (src0, inv0, src1, inv1) for gate g; output_specs[j] =
    (src, inv) for output j.
    """
    k = meta['k']
    model_set = set(model)
    is_true = lambda v: v in model_set
    gate_specs = []
    for g in range(k):
        srcs = []
        for input_num in range(2):
            sel = meta['gate_sel_list'][g][input_num]
            avail = meta['gate_avail_list'][g]
            picked = [avail[i] for i, v in enumerate(sel) if is_true(v)]
            assert len(picked) == 1, picked
            inv = meta['gate_inv_list'][g][input_num]
            srcs.append((picked[0], is_true(inv)))
        gate_specs.append(tuple(srcs))
    output_specs = []
    for sel, inv, avail in meta['out_info']:
        picked = [avail[i] for i, v in enumerate(sel) if is_true(v)]
        assert len(picked) == 1, picked
        output_specs.append((picked[0], is_true(inv)))
    return gate_specs, output_specs


def decode_single(meta, model, extras_names=None):
    """Single-output wrapper around decode_multi."""
    gate_specs, output_specs = decode_multi(meta, model)
    return gate_specs, output_specs[0]


def check_multi(N, care, targets, k, timeout_seconds=None, extras=None):
    """Check if a k-gate multi-output circuit exists. Returns (sat, model)."""
    clauses, nvars, meta = build_multi_cnf(N, care, targets, k, extras)
    s = Solver(name="cd153")
    for cl in clauses:
        s.add_clause(cl)
    sat = None
    model = None
    if timeout_seconds is not None:
        budget = 5000
        elapsed = 0.0
        t0 = time.time()
        while elapsed < timeout_seconds:
            s.conf_budget(budget)
            result = s.solve_limited()
            if result is not None:
                sat = result
                if sat:
                    model = s.get_model()
                break
            elapsed = time.time() - t0
    else:
        sat = s.solve()
        if sat:
            model = s.get_model()
    s.delete()
    return sat, model


def check_single(N, care, target_bits, k, timeout_seconds=None, extras=None):
    """Check if a k-gate single-output circuit exists. Returns (sat, model)."""
    return check_multi(N, care, [target_bits], k, timeout_seconds, extras)


# ── target bit extraction ─────────────────────────────────────────────

def factor(n):
    if n < 2:
        return None
    for p in range(2, math.isqrt(n) + 1):
        if n % p == 0:
            q = n // p
            if p != q and factor(p) is not None and factor(q) is not None \
               and all(not (p % d == 0 and p != d) for d in range(2, math.isqrt(p) + 1)):
                return p, q
    return None


def is_prime(n):
    if n < 2:
        return False
    for d in range(2, math.isqrt(n) + 1):
        if n % d == 0:
            return False
    return True


def enumerate_care(N):
    care = []
    for x in range(2 ** N):
        for p in range(2, math.isqrt(x) + 1):
            if x % p == 0:
                q = x // p
                if p != q and is_prime(p) and is_prime(q):
                    care.append((x, p, q))
                    break
    return care


if __name__ == "__main__":
    N = 6
    care = enumerate_care(N)
    print(f"{len(care)} care points")

    out_names = ([f"p{i}" for i in range(N)] +
                 [f"q{i}" for i in range(N)])
    total = 0
    results = {}
    circuits = {}
    for name in out_names:
        is_p = name.startswith("p")
        bit = int(name[1:])
        target = [((p if is_p else q) >> bit) & 1 for x, p, q in care]

        # trivial checks
        v0 = target[0]
        if all(v == v0 for v in target):
            print(f"{name}: constant {v0} -> 0 gates")
            results[name] = 0
            continue
        direct = None
        for i in range(N):
            col = [(x >> i) & 1 for x, _, _ in care]
            if col == target:
                direct = (f"x{i}", 0)
            if [1 - v for v in col] == target:
                direct = (f"~x{i}", 0)
        if direct:
            print(f"{name}: = {direct[0]} -> 0 gates")
            results[name] = 0
            continue

        print(f"{name}: min gates:", end=" ")
        found = None
        for k in range(1, 9):
            sat, model = check_single(N, care, target, k, timeout_seconds=25.0)
            if sat:
                m = {'k': k, 'N': N, 'care': care}
                m['gate_sel_list'] = [[None]] * k
                # need full meta to decode; rebuild cheaply below
                found = (k, model)
                break
            print(f"{k}(U) ", end="", flush=True)
        if found is None:
            print("  -> NOT FOUND within max_k/time")
            continue
        k, model = found
        clauses, nvars, meta = build_multi_cnf(N, care, [target], k)
        s = Solver(name="cd153")
        for cl in clauses:
            s.add_clause(cl)
        sat = s.solve()
        assert sat
        full_model = s.get_model()
        s.delete()
        gate_specs, output = decode_single(meta, full_model)
        circuits[name] = {"gates": gate_specs, "out": output, "k": k}
        print(f"{k}")
        for g, ((a, ia), (b, ib)) in enumerate(gate_specs):
            print(f"    g{g} = ({'~' if ia else ''}{a}) & ({'~' if ib else ''}{b})")
        src, iov = output
        print(f"    out = {'~' if iov else ''}{src}")
        results[name] = k
        total += k

    import json
    with open("single_output_circuits.json", "w") as f:
        json.dump(circuits, f, indent=1)
    print("\n(dumped standalone circuits to single_output_circuits.json)")

    print("\n== summary ==")
    for name in out_names:
        print(f"  {name}: {results.get(name, '?')}")
    print(f"  TOTAL (zero-sharing construction) = {sum(results.values())}")
