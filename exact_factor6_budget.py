from math import isqrt
import time, sys
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

ks = [int(x) for x in sys.argv[1:]] if len(sys.argv) > 1 else list(range(11, 21))


def build_cnf(k):
    next_var = 1
    clauses = []

    def new_var():
        nonlocal next_var
        v = next_var
        next_var += 1
        return v

    sig = [[new_var() for _ in care] for _ in range(k)]

    gate_inputs_all = []
    for g in range(k):
        available = ["const0"] + [f"in{i}" for i in range(N)] + [
            f"g{i}" for i in range(g)
        ]
        gate_inputs = []
        for input_num in range(2):
            selectors = [new_var() for _ in available]
            inv = new_var()
            selected = [new_var() for _ in care]
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
            gate_inputs.append(selected)
        a, b = gate_inputs
        for t in range(C):
            z = sig[g][t]
            clauses.append([-z, a[t]])
            clauses.append([-z, b[t]])
            clauses.append([z, -a[t], -b[t]])
        gate_inputs_all.append(gate_inputs)

    available_out = ["const0"] + [f"in{i}" for i in range(N)] + [
        f"g{i}" for i in range(k)
    ]
    out_info = []
    for out_index in range(2 * N):
        selectors = [new_var() for _ in available_out]
        inv = new_var()
        clauses.append(selectors)
        for i in range(len(selectors)):
            for j in range(i + 1, len(selectors)):
                clauses.append([-selectors[i], -selectors[j]])
        is_p = out_index < N
        bit = N - 1 - (out_index % N)
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
        out_info.append((selectors, inv))

    return clauses, next_var - 1, sig, gate_inputs_all, out_info, available_out


for k in ks:
    clauses, nvars, sig, gate_inputs_all, out_info, available_out = build_cnf(k)
    nclauses = len(clauses)

    s = Solver(name="cd153")
    s.append_formula(clauses)

    BUDGET = 5000
    total_conflicts = 0
    total_propagations = 0
    t0 = time.time()
    result = None

    while True:
        s.conf_budget(BUDGET)
        outcome = s.solve_limited()
        dt = time.time() - t0

        if outcome is not None:
            result = outcome
            break

        stats = s.accum_stats()
        conf = stats.get("conflicts", 0)
        prop = stats.get("propagations", 0)
        dec = stats.get("decisions", 0)
        total_conflicts = conf
        total_propagations = prop

        rate = total_conflicts / dt if dt > 0 else 0
        print(
            f"k={k:2d}: {dt:6.0f}s  conflicts={total_conflicts:>10}  "
            f"decisions={dec:>10}  props={total_propagations:>12}  "
            f"({rate:.0f} conf/s)  vars={nvars}  clauses={nclauses}",
            flush=True,
        )

    dt = time.time() - t0
    stats = s.accum_stats()
    total_conflicts = stats.get("conflicts", 0)
    rate = total_conflicts / dt if dt > 0 else 0

    print(
        f"k={k:2d}: {'SAT' if result else 'UNSAT'}  "
        f"conflicts={total_conflicts:>10}  time={dt:7.1f}s  "
        f"({rate:.0f} conf/s)  vars={nvars}  clauses={nclauses}",
        flush=True,
    )
    s.delete()

    if result:
        break
