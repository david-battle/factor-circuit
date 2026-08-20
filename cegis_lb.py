#!/usr/bin/env python3
"""CEGIS lower-bound proof for the k-AND-gate semiprime-factoring circuit.

Question: does an AIG with k 2-input AND gates implement the N-bit factoring
Boolean relation (care points = semiprimes, don't-cares elsewhere)?

Standard counterexample-guided synthesis:
  Maintain a care-point subset S.
  Loop:
    SAT-solve "does a k-gate AIG satisfy every point in S?"
    - UNSAT: no k-gate circuit satisfies S, hence none satisfies all care
             points -> proven LOWER BOUND (k impossible). Done.
    - SAT:   decode the candidate circuit, simulate it on ALL care points.
        * all pass -> a k-gate circuit exists (k achievable). Done.
        * else    -> add the failing points to S, repeat.

Correctness:
  - UNSAT on ANY subset S is a valid impossibility proof (LB): if no circuit
    satisfies even S, none satisfies the whole care set.
  - SAT + full-care verification is a valid achievability proof.
  - |S| grows monotonically and is bounded by the care set, so the loop
    always terminates.

The encoding is survey.py's one-shot encoding (pairwise at-most-one for the
one-hot gate-input/output selectors, NOT a sequential counter), applied to
the current subset S.  Only care-indexed variables (sig[g][t], selected[t])
depend on S; the selector/inverter structure is shared, so a decoded circuit
is valid over all care points regardless of |S|.
"""

import sys
import time
from math import isqrt
from pysat.solvers import Solver

# ── Care-point enumeration (identical to survey.py) ───────────────────

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

def enumerate_care(N):
    """Return [(input_val, p, q)] for all N-bit semiprimes (x_i = bit i)."""
    out = []
    for x in range(1 << N):
        f = factor_semiprime(x)
        if f:
            out.append((x, f[0], f[1]))
    return out

# ── CNF builder over a care subset ────────────────────────────────────

def build_cnf(N, care_subset, k, irreducible=False):
    """Encode "exists a k-gate AIG satisfying all points in care_subset".

    Mirrors survey.py:build_cnf / exact_n6_from_above.py (pairwise AMO,
    input symmetry breaking, constant-0 output skipping) but only constrains
    the given care points.  Returns (clauses, nvars, meta).

    If irreducible=True, additionally forces every gate to be non-constant and
    pairwise distinct (also distinct from every input bit column).  This is
    WLOG-safe for FINDING circuits (the exact minimum is always realizable by
    an irreducible circuit), and it prunes the search enormously, but it is
    NOT a valid lower-bound encoding: a reducible circuit can have fewer gates
    after removing redundancy, so irreducible-UNSAT does not imply full-UNSAT.
    Only use irreducible=True on the full care set (an input bit constant on a
    subset would make the distinctness constraints spurious).
    """
    C = len(care_subset)
    next_var = 1
    clauses = []

    def new_var():
        nonlocal next_var
        v = next_var
        next_var += 1
        return v

    sig = [[new_var() for _ in range(C)] for _ in range(k)]

    gate_sel_list = []     # gate_sel_list[g][input_num] = selectors list
    gate_inv_list = []     # gate_inv_list[g][input_num] = inv var
    gate_avail_list = []   # gate_avail_list[g] = available source names
    gate_selected_list = []  # gate_selected_list[g][input_num] = selected vars

    for g in range(k):
        available = ["const0"] + [f"in{i}" for i in range(N)] + [
            f"g{i}" for i in range(g)
        ]
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
                for t, (x, _, _) in enumerate(care_subset):
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

            gate_selectors.append(selectors)
            gate_invs.append(inv)
            gate_selected.append(selected)

        # Symmetry breaking: source(input0) <= source(input1)
        sel0, sel1 = gate_selectors
        for i in range(len(sel0)):
            for j in range(i):
                clauses.append([-sel0[i], -sel1[j]])

        # z = a AND b, where selected[t] = source_value XOR inv.
        a, b = gate_selected
        for t in range(C):
            z = sig[g][t]
            clauses.append([-z, a[t]])
            clauses.append([-z, b[t]])
            clauses.append([z, -a[t], -b[t]])

        gate_sel_list.append(gate_selectors)
        gate_inv_list.append(gate_invs)
        gate_avail_list.append(available)
        gate_selected_list.append(gate_selected)

    # Output encoding — skip constant-0 outputs (per subset).
    available_out = ["const0"] + [f"in{i}" for i in range(N)] + [
        f"g{i}" for i in range(k)
    ]
    # out_info[i]: for i < N -> p bit (N-1-i); for N <= i < 2N -> q bit (2N-1-i).
    # None means the output is constant 0 over the subset.
    out_info = [None] * (2 * N)

    for out_index in range(2 * N):
        is_p = out_index < N
        bit = N - 1 - (out_index % N)

        is_const_zero = True
        for x, p, q in care_subset:
            required = ((p if is_p else q) >> bit) & 1
            if required:
                is_const_zero = False
                break
        if is_const_zero:
            continue

        selectors = [new_var() for _ in available_out]
        inv = new_var()
        clauses.append(selectors)
        for i in range(len(selectors)):
            for j in range(i + 1, len(selectors)):
                clauses.append([-selectors[i], -selectors[j]])

        for si, source in enumerate(available_out):
            sel = selectors[si]
            for t, (x, p, q) in enumerate(care_subset):
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

        out_info[out_index] = (selectors, inv, available_out)

    if irreducible:
        # Gate outputs are non-constant over the care set: each gate has at
        # least one 0 and one 1 among the care points.
        for g in range(k):
            clauses.append(sig[g])                       # at least one 1
            clauses.append([-v for v in sig[g]])         # at least one 0
        # Pairwise distinct gate outputs: for a<b, OR_t (sig[a][t] != sig[b][t]).
        for a in range(k):
            for b in range(a + 1, k):
                dvs = []
                for t in range(len(sig[a])):
                    av = sig[a][t]
                    bv = sig[b][t]
                    dv = new_var()
                    # dv = (av != bv)
                    clauses.append([av, bv, -dv])
                    clauses.append([-av, -bv, -dv])
                    clauses.append([av, -bv, dv])
                    clauses.append([-av, bv, dv])
                    dvs.append(dv)
                clauses.append(dvs)
        # Each gate differs from every input bit column over the care set.
        input_cols = [[((x >> i) & 1) for x, _, _ in care_subset]
                      for i in range(N)]
        for g in range(k):
            for i in range(N):
                d = []
                for t in range(len(sig[g])):
                    a = sig[g][t]
                    bitv = input_cols[i][t]
                    dv = new_var()
                    # dv = (a != bitv)
                    if bitv == 0:
                        clauses.append([a, -dv])
                        clauses.append([-a, dv])
                    else:
                        clauses.append([-a, -dv])
                        clauses.append([a, dv])
                    d.append(dv)
                clauses.append(d)

    meta = {
        'k': k, 'N': N, 'care': care_subset,
        'gate_sel_list': gate_sel_list,
        'gate_inv_list': gate_inv_list,
        'gate_avail_list': gate_avail_list,
        'out_info': out_info,
    }
    return clauses, next_var - 1, meta

# ── Incremental CEGIS builder ──────────────────────────────────────────

def build_incremental(N, full_care, k, initial_idx):
    """Structural CNF + per-care-point clause generator for incremental CEGIS.

    Structural variables (gate/output selectors, inverters) are allocated once;
    each care point's constraints (sig vars, selected vars, output pinning) are
    generated on demand by the returned `add_care_point(x, p, q)` closure, so a
    live solver can absorb new care points and keep its learned clauses.

    Const-zero outputs are determined over the FULL care set up front (correct
    even as the incremental subset grows).  Returns (base_clauses, meta, add).
    """
    next_var = 1
    clauses = []

    def new_var():
        nonlocal next_var
        v = next_var
        next_var += 1
        return v

    # const-zero outputs over the full care set
    nz_out = []
    for out_index in range(2 * N):
        is_p = out_index < N
        bit = N - 1 - (out_index % N)
        if any(((p if is_p else q) >> bit) & 1 for _, p, q in full_care):
            nz_out.append(out_index)

    # gate structural vars
    gate_sel_list = []
    gate_inv_list = []
    gate_avail_list = []
    for g in range(k):
        available = ["const0"] + [f"in{i}" for i in range(N)] + [
            f"g{i}" for i in range(g)
        ]
        sel = [[new_var() for _ in available] for _ in range(2)]
        inv = [new_var(), new_var()]
        for s in sel:
            clauses.append(s)
            for i in range(len(s)):
                for j in range(i + 1, len(s)):
                    clauses.append([-s[i], -s[j]])  # pairwise AMO
        for i in range(len(sel[0])):
            for j in range(i):
                clauses.append([-sel[0][i], -sel[1][j]])  # input symmetry
        gate_sel_list.append(sel)
        gate_inv_list.append(inv)
        gate_avail_list.append(available)

    # output structural vars
    available_out = ["const0"] + [f"in{i}" for i in range(N)] + [
        f"g{i}" for i in range(k)
    ]
    out_info = [None] * (2 * N)
    for out_index in nz_out:
        sel = [new_var() for _ in available_out]
        inv = new_var()
        clauses.append(sel)
        for i in range(len(sel)):
            for j in range(i + 1, len(sel)):
                clauses.append([-sel[i], -sel[j]])
        out_info[out_index] = (sel, inv, available_out)

    meta = {
        'k': k, 'N': N, 'care': None,
        'gate_sel_list': gate_sel_list,
        'gate_inv_list': gate_inv_list,
        'gate_avail_list': gate_avail_list,
        'out_info': out_info,
    }

    sig = [[] for _ in range(k)]  # sig[g] list parallel to added care points

    def add_care_point(x, p, q):
        """Return clauses constraining the circuit on one care point."""
        c = []
        for g in range(k):
            sels = gate_sel_list[g]
            invs = gate_inv_list[g]
            avail = gate_avail_list[g]
            vals = [None, None]
            for inp in range(2):
                a = new_var()  # selected literal for this care point
                for si, source in enumerate(avail):
                    sel = sels[inp][si]
                    inv = invs[inp]
                    if source == "const0":
                        c.append([-sel, -inv, a])
                        c.append([-sel, inv, -a])
                    elif source.startswith("in"):
                        bit = int(source[2:])
                        value = (x >> bit) & 1
                        if value == 0:
                            c.append([-sel, -inv, a])
                            c.append([-sel, inv, -a])
                        else:
                            c.append([-sel, -inv, -a])
                            c.append([-sel, inv, a])
                    else:
                        pg = int(source[1:])
                        v = sig[pg][-1]  # current care point's value for gate pg
                        c.append([-sel, -v, -inv, -a])
                        c.append([-sel, v, inv, -a])
                        c.append([-sel, -v, inv, a])
                        c.append([-sel, v, -inv, a])
                vals[inp] = a
            z = new_var()  # sig[g] for this care point
            sig[g].append(z)
            a, b = vals
            c.append([-z, a])
            c.append([-z, b])
            c.append([z, -a, -b])
        for out_index in nz_out:
            is_p = out_index < N
            bit = N - 1 - (out_index % N)
            required = ((p if is_p else q) >> bit) & 1
            sel, inv, avail = out_info[out_index]
            for si, source in enumerate(avail):
                if source == "const0":
                    if required:
                        c.append([-sel[si], inv])
                    else:
                        c.append([-sel[si], -inv])
                elif source.startswith("in"):
                    sv = (x >> int(source[2:])) & 1
                    if sv == required:
                        c.append([-sel[si], -inv])
                    else:
                        c.append([-sel[si], inv])
                else:
                    sv = sig[int(source[1:])][-1]
                    if required:
                        c.append([-sel[si], sv, inv])
                        c.append([-sel[si], -sv, -inv])
                    else:
                        c.append([-sel[si], -sv, inv])
                        c.append([-sel[si], sv, -inv])
        return c

    # emit initial care points in sorted order
    for idx in sorted(initial_idx):
        x, p, q = full_care[idx]
        clauses.extend(add_care_point(x, p, q))

    return clauses, meta, add_care_point, next_var - 1

# ── Decode / simulate ─────────────────────────────────────────────────

def decode_model(model, meta):
    """Extract a gate-level AIG from a satisfying model.

    Selector/inverter vars are shared across care points, so this is a valid
    circuit description independent of which points were in the subset.
    """
    model_set = set(model)
    is_true = lambda v: v in model_set

    k = meta['k']
    gates = []
    for g in range(k):
        gate_def = []
        for input_num in range(2):
            selectors = meta['gate_sel_list'][g][input_num]
            inv = meta['gate_inv_list'][g][input_num]
            available = meta['gate_avail_list'][g]
            src_name = None
            for si, sel_var in enumerate(selectors):
                if is_true(sel_var):
                    src_name = available[si]
                    break
            gate_def.append((src_name, is_true(inv)))
        gates.append(gate_def)

    outputs = []
    for info in meta['out_info']:
        if info is None:
            outputs.append(None)
            continue
        selectors, inv, available = info
        src_name = None
        for si, sel_var in enumerate(selectors):
            if is_true(sel_var):
                src_name = available[si]
                break
        outputs.append((src_name, is_true(inv)))
    return gates, outputs

def evaluate(meta, gates, outputs, x_val):
    """Simulate the decoded AIG on input x_val; return (p, q)."""
    N = meta['N']
    k = meta['k']
    values = {"const0": 0}
    for i in range(N):
        values[f"in{i}"] = (x_val >> i) & 1

    for g in range(k):
        src0, inv0 = gates[g][0]
        src1, inv1 = gates[g][1]
        v0 = values.get(src0, 0) ^ inv0
        v1 = values.get(src1, 0) ^ inv1
        values[f"g{g}"] = v0 & v1

    p = 0
    q = 0
    for out_index, info in enumerate(outputs):
        if info is None:
            continue
        src, inv = info
        val = values.get(src, 0) ^ inv
        if out_index < N:
            bit = N - 1 - out_index
            p |= val << bit
        else:
            bit = 2 * N - 1 - out_index
            q |= val << bit
    return p, q

def verify_care(meta, gates, outputs, full_care):
    """Return (correct_count, total_count, failing_indices)."""
    total = len(full_care)
    correct = 0
    failing = []
    for idx, (x, p_req, q_req) in enumerate(full_care):
        p_got, q_got = evaluate(meta, gates, outputs, x)
        if p_got == p_req and q_got == q_req:
            correct += 1
        else:
            failing.append(idx)
    return correct, total, failing

# ── CEGIS loop ────────────────────────────────────────────────────────

def seed_subset(full_care, size):
    """Pick a spread-out initial subset of care points (at least the extremes)."""
    C = len(full_care)
    if size >= C:
        return list(range(C))
    idxs = set()
    idxs.add(0)
    idxs.add(C - 1)
    idxs.add(C // 2)
    step = max(1, C // size)
    for i in range(0, C, step):
        idxs.add(i)
    return sorted(list(idxs))[:size]

def cegis_prove(N, k, full_care, seed_size=None, timeout=120, max_iter=200,
                max_add=4, iter_cap=None):
    """Prove k gates impossible (LB) or find a k-gate circuit (UB).

    max_add caps how many counterexamples are folded back into the subset per
    iteration.  Adding only a few failures keeps each SAT call small, so the
    subset grows gradually toward a (hopefully small) unsat core instead of
    collapsing to the full care set on iteration 2.

    Returns dict with status:
      'unsat'  -> k impossible; LB >= k+1
      'sat'    -> k achievable; decoded circuit returned
      'timeout'
    """
    if seed_size is None:
        seed_size = max(1, min(8, len(full_care) // 4))
    seed_size = min(seed_size, len(full_care))
    if iter_cap is None:
        iter_cap = max(10, timeout // 4)

    subset_idx = seed_subset(full_care, seed_size)
    S_idx_set = set(subset_idx)
    S = [full_care[i] for i in sorted(S_idx_set)]

    t0 = time.time()
    for it in range(1, max_iter + 1):
        if time.time() - t0 >= timeout:
            return {'status': 'timeout', 'iterations': it - 1,
                    'subset_size': len(S), 'elapsed': time.time() - t0}

        # Keep S in sorted (original-index) order: clause insertion order
        # matters a lot for cd153.  A permuted care order made the identical
        # k=10 N=6 UNSAT instance go from 29s/626K conflicts to undecided.
        S = [full_care[i] for i in sorted(S_idx_set)]
        clauses, nvars, meta = build_cnf(N, S, k)
        nclauses = len(clauses)

        s = Solver(name="cd153")
        for cl in clauses:
            s.add_clause(cl)

        # Budgeted solving: fixed 5000-conflict budget, exactly as
        # survey.py:check_k.  Escalating the budget (5000->500k) was found to
        # be pathologically slower on the k=10 N=6 UNSAT proof (171s undecided
        # at 2.1M conflicts vs 29s/626K for the fixed budget), so keep it fixed.
        iter_t0 = time.time()
        budget = 5000
        result = None
        while time.time() - iter_t0 < iter_cap:
            s.conf_budget(budget)
            result = s.solve_limited()
            if result is not None:
                break
        conflicts = s.accum_stats().get("conflicts", 0)
        dt = time.time() - t0
        decided_time = time.time() - t0
        print(f"  iter {it}: |S|={len(S):2d} clauses={nclauses:6d} "
              f"vars={nvars:4d} conflicts={conflicts:7d} "
              f"result={'T' if result is None else ('SAT' if result else 'UNSAT')} "
              f"iter={time.time()-iter_t0:5.1f}s", flush=True)
        if result is None:
            s.delete()
            return {'status': 'timeout', 'iterations': it - 1,
                    'subset_size': len(S), 'elapsed': dt}

        if result is False:
            s.delete()
            return {'status': 'unsat', 'iterations': it, 'subset_size': len(S),
                    'clauses': nclauses, 'vars': nvars, 'conflicts': conflicts,
                    'elapsed': dt, 'last_iter_time': decided_time}
        elif result is True:
            model = s.get_model()
            s.delete()
            gates, outputs = decode_model(model, meta)
            correct, total, failing = verify_care(meta, gates, outputs, full_care)
            if correct == total:
                return {'status': 'sat', 'iterations': it, 'subset_size': len(S),
                        'clauses': nclauses, 'vars': nvars, 'conflicts': conflicts,
                        'elapsed': dt, 'gates': gates, 'outputs': outputs}
            else:
                # Add up to max_add failing points (not already present) to S.
                # Ordering by spread keeps the subset diverse; a cap keeps each
                # per-call CNF small so growth is gradual.
                new_fail = [fi for fi in failing if fi not in S_idx_set]
                added = 0
                if max_add == 0:
                    new_fail = list(reversed(new_fail))  # keep spread; all added
                nf = len(new_fail)
                step = max(1, nf // max_add) if (max_add and nf) else 1
                for j in range(0, nf, step):
                    if max_add and added >= max_add:
                        break
                    fi = new_fail[j]
                    S_idx_set.add(fi)
                    added += 1
                if added == 0:
                    # No progress despite failures -> encoding/decode bug.
                    s = None
                    return {'status': 'error', 'iterations': it,
                            'subset_size': len(S), 'elapsed': time.time() - t0,
                            'detail': 'no new counterexamples, verification mismatch'}
        else:
            s.delete()
            return {'status': 'timeout', 'iterations': it - 1,
                    'subset_size': len(S), 'elapsed': dt}

    return {'status': 'timeout', 'iterations': max_iter, 'subset_size': len(S),
            'elapsed': time.time() - t0}

def incremental_cegis(N, k, full_care, seed_size=None, timeout=120, max_iter=200,
                      max_add=2, iter_cap=None):
    """CEGIS with a persistent solver: care points are added incrementally so
    learned clauses carry across iterations (caDiCaL auto-extends variables).

    Intended for the SAT direction (find a k-gate circuit); also yields a valid
    LB if the incremental subset ever becomes UNSAT.
    """
    if seed_size is None:
        seed_size = max(1, min(8, len(full_care) // 4))
    seed_size = min(seed_size, len(full_care))
    if iter_cap is None:
        iter_cap = max(10, timeout // 4)

    initial_idx = sorted(seed_subset(full_care, seed_size))
    added = set(initial_idx)
    base, meta, add_care_point, nvars = build_incremental(N, full_care, k,
                                                          initial_idx)

    s = Solver(name="cd153")
    for cl in base:
        s.add_clause(cl)
    nclauses = len(base)

    t0 = time.time()
    for it in range(1, max_iter + 1):
        if time.time() - t0 >= timeout:
            s.delete()
            return {'status': 'timeout', 'iterations': it - 1,
                    'subset_size': len(added), 'elapsed': time.time() - t0}

        iter_t0 = time.time()
        result = None
        while time.time() - iter_t0 < iter_cap:
            s.conf_budget(5000)
            result = s.solve_limited()
            if result is not None:
                break
        conflicts = s.accum_stats().get("conflicts", 0)
        dt = time.time() - t0
        print(f"  iter {it}: |S|={len(added):2d} clauses={nclauses:6d} "
              f"vars={nvars:4d} conflicts={conflicts:7d} "
              f"result={'T' if result is None else ('SAT' if result else 'UNSAT')} "
              f"iter={time.time()-iter_t0:5.1f}s", flush=True)

        if result is None:
            s.delete()
            return {'status': 'timeout', 'iterations': it - 1,
                    'subset_size': len(added), 'elapsed': dt}
        if result is False:
            s.delete()
            return {'status': 'unsat', 'iterations': it,
                    'subset_size': len(added), 'clauses': nclauses,
                    'vars': nvars, 'conflicts': conflicts, 'elapsed': dt}

        model = s.get_model()
        gates, outputs = decode_model(model, meta)
        correct, total, failing = verify_care(meta, gates, outputs, full_care)
        if correct == total:
            s.delete()
            return {'status': 'sat', 'iterations': it,
                    'subset_size': len(added), 'clauses': nclauses,
                    'vars': nvars, 'conflicts': conflicts, 'elapsed': dt,
                    'gates': gates, 'outputs': outputs}

        new_fail = [fi for fi in failing if fi not in added]
        n = len(new_fail)
        step = max(1, n // max_add) if (max_add and n) else 1
        added_count = 0
        for j in range(0, n, step):
            if max_add and added_count >= max_add:
                break
            fi = new_fail[j]
            x, p, q = full_care[fi]
            cc = add_care_point(x, p, q)
            nclauses += len(cc)
            for cl in cc:
                s.add_clause(cl)
            added.add(fi)
            added_count += 1
        if added_count == 0:
            s.delete()
            return {'status': 'error', 'iterations': it,
                    'subset_size': len(added), 'elapsed': time.time() - t0,
                    'detail': 'no new counterexamples, verification mismatch'}

    s.delete()
    return {'status': 'timeout', 'iterations': max_iter,
            'subset_size': len(added), 'elapsed': time.time() - t0}


def print_circuit(meta, gates, outputs):
    N = meta['N']
    k = meta['k']
    out_names = [f"p{i}" for i in range(N - 1, -1, -1)] + \
                [f"q{i}" for i in range(N - 1, -1, -1)]
    f = lambda s, inv: ("~" + s) if inv else s
    print("  Gates:")
    for g in range(k):
        print(f"    g{g} = {f(*gates[g][0])} AND {f(*gates[g][1])}")
    print("  Outputs:")
    for idx, info in enumerate(outputs):
        if info is None:
            print(f"    {out_names[idx]} = const0")
        else:
            src, inv = info
            print(f"    {out_names[idx]} = ~{src}" if inv else f"    {out_names[idx]} = {src}")

def main():
    import argparse
    p = argparse.ArgumentParser(description="CEGIS lower-bound proof for k-gate factoring circuit")
    p.add_argument("N", type=int)
    p.add_argument("ks", type=int, nargs="+", help="k values to test")
    p.add_argument("--timeout", type=int, default=120, help="wall-clock seconds per k")
    p.add_argument("--seed", type=int, default=None, help="initial care-subset size")
    p.add_argument("--max-add", type=int, default=4,
                   help="counterexamples added per iteration (0 = add all)")
    p.add_argument("--iter-cap", type=int, default=None,
                   help="per-iteration solve cap in seconds")
    args = p.parse_args()

    N = args.N
    ks = args.ks
    timeout = args.timeout
    seed = args.seed
    full_care = enumerate_care(N)
    print(f"N={N}, {len(full_care)} care points, testing k={ks}, timeout={timeout}s", flush=True)

    for k in ks:
        print(f"=== k={k} ===", flush=True)
        res = cegis_prove(N, k, full_care, seed_size=seed, timeout=timeout,
                          max_add=args.max_add, iter_cap=args.iter_cap)
        if res.get('status') == 'sat':
            print_circuit({'N': N, 'k': k}, res['gates'], res['outputs'])
        print(f"  status={res['status']}  iters={res.get('iterations')}  "
              f"subset={res.get('subset_size')}  clauses={res.get('clauses')}  "
              f"vars={res.get('vars')}  conflicts={res.get('conflicts')}  "
              f"elapsed={res.get('elapsed', 0):.1f}s", flush=True)
        if res['status'] == 'unsat':
            print(f"  ** UNSAT: no {k}-gate circuit exists -> LB >= {k+1} **")
        elif res['status'] == 'sat':
            print(f"  ** SAT: a {k}-gate circuit exists (correct on all care points) **")
        print()

if __name__ == "__main__":
    main()
