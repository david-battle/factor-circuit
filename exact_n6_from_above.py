#!/usr/bin/env python3
"""N=6 exact synthesis from above: try k=10,11,...,18 to close the UB toward the LB.

Uses the proven survey.py one-hot encoding, starting from the known lower
bound and working upward. For each k, asks: "Does a k-AND-gate circuit
implement the N=6 factoring Boolean relation?"

If SAT, decodes and prints the circuit. If UNSAT, moves to k+1.
"""

import sys
import time
from math import isqrt
from pysat.solvers import Solver

N = 6


def is_prime(n):
    if n < 2:
        return False
    for p in range(2, isqrt(n) + 1):
        if n % p == 0:
            return False
    return True


def factor_semiprime(n):
    for p in range(2, isqrt(n) + 1):
        if n % p == 0:
            q = n // p
            if p != q and is_prime(p) and is_prime(q):
                return p, q
    return None


care = []
for x in range(1 << N):
    f = factor_semiprime(x)
    if f:
        care.append((x, f[0], f[1]))
C = len(care)
print(f"N={N}, {C} care points")


def build_cnf(k):
    """Build CNF for k-AND-gate factoring circuit.

    Adapted from survey.py's build_cnf with variable tracking for decoding.
    Returns (clauses, nvars, meta).
    """
    next_var = 1
    clauses = []

    def new_var():
        nonlocal next_var
        v = next_var
        next_var += 1
        return v

    sig = [[new_var() for _ in range(C)] for _ in range(k)]

    # Track for decoding
    gate_sel_list = []    # gate_sel_list[g][input_num] = selectors list
    gate_inv_list = []    # gate_inv_list[g][input_num] = inv var
    gate_avail_list = []  # gate_avail_list[g] = available source names
    gate_selected_list = []  # gate_selected_list[g][input_num] = selected vars

    for g in range(k):
        available = ["const0"] + [f"in{i}" for i in range(N)] + [
            f"g{i}" for i in range(g)
        ]
        gate_selected = []
        gate_selectors = []
        for input_num in range(2):
            selectors = [new_var() for _ in available]
            inv = new_var()
            selected = [new_var() for _ in range(C)]

            clauses.append(selectors)
            for i in range(len(selectors)):
                for j in range(i + 1, len(selectors)):
                    clauses.append([-selectors[i], -selectors[j]])

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
                    else:
                        pg = int(source[1:])
                        v = sig[pg][t]
                        clauses.append([-sel, -v, -inv, -a])
                        clauses.append([-sel, v, inv, -a])
                        clauses.append([-sel, -v, inv, a])
                        clauses.append([-sel, v, -inv, a])

            gate_selected.append(selected)
            gate_selectors.append(selectors)

        # Symmetry breaking: source(input0) <= source(input1)
        sel0, sel1 = gate_selectors
        for i in range(len(sel0)):
            for j in range(i):
                clauses.append([-sel0[i], -sel1[j]])

        # z = a AND b
        a, b = gate_selected
        for t in range(C):
            z = sig[g][t]
            clauses.append([-z, a[t]])
            clauses.append([-z, b[t]])
            clauses.append([z, -a[t], -b[t]])

        gate_sel_list.append(gate_selectors)
        gate_inv_list.append([None, None])  # inv vars not saved yet
        gate_avail_list.append(available)
        gate_selected_list.append(gate_selected)

    # Output encoding — skip constant-0 outputs
    available_out = ["const0"] + [f"in{i}" for i in range(N)] + [
        f"g{i}" for i in range(k)
    ]
    out_info = []  # (selectors, inv, available) for each non-const output

    for out_index in range(2 * N):
        is_p = out_index < N
        bit = N - 1 - (out_index % N)

        is_const_zero = True
        for x, p, q in care:
            required = ((p if is_p else q) >> bit) & 1
            if required:
                is_const_zero = False
                break
        if is_const_zero:
            out_info.append(None)
            continue

        selectors = [new_var() for _ in available_out]
        inv = new_var()
        clauses.append(selectors)
        for i in range(len(selectors)):
            for j in range(i + 1, len(selectors)):
                clauses.append([-selectors[i], -selectors[j]])

        for si, source in enumerate(available_out):
            sel = selectors[si]
            for t, (x, p, q) in enumerate(care):
                required = ((p if is_p else q) >> bit) & 1
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
        'k': k, 'N': N, 'C': C, 'care': care,
        'sig': sig,
        'gate_sel_list': gate_sel_list,
        'gate_avail_list': gate_avail_list,
        'gate_selected_list': gate_selected_list,
        'out_info': out_info,
    }
    return clauses, next_var - 1, meta


def decode_model(model, meta):
    """Decode SAT model into gate-level description."""
    model_set = set(model)
    is_true = lambda v: v in model_set

    k = meta['k']
    gates = []
    for g in range(k):
        gate_def = []
        for input_num in range(2):
            selectors = meta['gate_sel_list'][g][input_num]
            available = meta['gate_avail_list'][g]
            src_name = None
            for si, sel_var in enumerate(selectors):
                if is_true(sel_var):
                    src_name = available[si]
                    break
            gate_def.append(src_name)
        gates.append(gate_def)

    outputs = []
    for out_idx, info in enumerate(meta['out_info']):
        if info is None:
            outputs.append(None)  # constant-0
            continue
        selectors, inv, available = info
        inv_val = is_true(inv)
        src_name = None
        for si, sel_var in enumerate(selectors):
            if is_true(sel_var):
                src_name = available[si]
                break
        outputs.append((src_name, inv_val))

    return gates, outputs


def evaluate(meta, gates, outputs, x_val):
    """Evaluate decoded circuit on input x_val. Returns output bits as (p, q)."""
    k = meta['k']
    N_local = meta['N']
    values = {}
    for i in range(N_local):
        values[f"in{i}"] = (x_val >> i) & 1
    values["const0"] = 0

    for g in range(k):
        src0 = gates[g][0]
        src1 = gates[g][1]
        v0 = values.get(src0, 0)
        v1 = values.get(src1, 0)
        values[f"g{g}"] = v0 & v1

    p = 0
    q = 0
    for bit in range(N_local):
        # p bits: out_info index = bit (p(N-1) is index 0, p0 is index N-1)
        out_idx_p = bit
        if outputs[out_idx_p] is not None:
            src, inv = outputs[out_idx_p]
            val = values.get(src, 0)
            if inv:
                val = 1 - val
            p |= (val << bit)

        # q bits: out_info index = N + bit
        out_idx_q = N_local + bit
        if outputs[out_idx_q] is not None:
            src, inv = outputs[out_idx_q]
            val = values.get(src, 0)
            if inv:
                val = 1 - val
            q |= (val << bit)

    return p, q


def verify(meta, gates, outputs):
    """Verify decoded circuit on all care points."""
    correct = 0
    for x, p_req, q_req in meta['care']:
        p_got, q_got = evaluate(meta, gates, outputs, x)
        if p_got == p_req and q_got == q_req:
            correct += 1
    return correct, len(meta['care'])


def print_circuit(meta, gates, outputs):
    """Pretty-print the decoded circuit."""
    k = meta['k']
    N_local = meta['N']
    out_names = [f"p{i}" for i in range(N_local - 1, -1, -1)] + \
                [f"q{i}" for i in range(N_local - 1, -1, -1)]

    print("  Gates:")
    for g in range(k):
        print(f"    g{g} = {gates[g][0]} AND {gates[g][1]}")

    print("  Outputs:")
    for idx, info in enumerate(outputs):
        if info is None:
            print(f"    {out_names[idx]} = const0")
        else:
            src, inv = info
            print(f"    {out_names[idx]} = ~{src}" if inv else f"    {out_names[idx]} = {src}")


# ── Main ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    ks = [int(x) for x in sys.argv[1:]] if len(sys.argv) > 1 else list(range(10, 19))
    timeout = 120

    print(f"Testing k values: {ks}")
    print(f"Timeout per k: {timeout}s")
    print()

    for k in ks:
        print(f"=== k={k} ===", flush=True)
        t0 = time.time()

        clauses, nvars, meta = build_cnf(k)
        nclauses = len(clauses)
        print(f"  CNF: {nvars} variables, {nclauses} clauses", flush=True)

        s = Solver(name="cd153")
        for cl in clauses:
            s.add_clause(cl)

        budget = 5000
        result = None
        while True:
            s.conf_budget(budget)
            outcome = s.solve_limited()
            elapsed = time.time() - t0
            if outcome is not None:
                result = outcome
                break
            if elapsed >= timeout:
                break
            budget = min(budget * 2, 500000)

        dt = time.time() - t0
        stats = s.accum_stats()
        conflicts = stats.get("conflicts", 0)

        if result is True:
            print(f"  SAT in {dt:.1f}s ({conflicts} conflicts)", flush=True)
            model = s.get_model()
            s.delete()

            gates, outputs = decode_model(model, meta)
            correct, total = verify(meta, gates, outputs)
            print(f"  Verification: {correct}/{total}", flush=True)

            if correct == total:
                print(f"\n  *** EXACT SYNTHESIS PROVEN: k={k} AND gates ***")
                print_circuit(meta, gates, outputs)
                print(f"\n*** RESULT: N=6 exact at k={k} ***")
                sys.exit(0)
            else:
                print(f"  Verification FAILED ({correct}/{total})")
                print(f"  (model satisfies CNF but not care points -- encoding bug?)")

        elif result is False:
            elapsed_str = f"{dt:.1f}s" if dt < 60 else f"{dt/60:.1f}min"
            print(f"  UNSAT in {elapsed_str} ({conflicts} conflicts)")
        else:
            elapsed_str = f"{dt:.1f}s" if dt < 60 else f"{dt/60:.1f}min"
            print(f"  TIMEOUT at {elapsed_str} ({conflicts} conflicts)")

        s.delete()
        print()
