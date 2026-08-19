from math import isqrt
import time
from pysat.solvers import Solver

N = 6
MAX_K = 90

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
print("Care points:")
for x, p, q in care:
    print(f"  {x:2d} -> {p:2d} * {q:2d}")
print(f"  ({C} care points out of {1 << N} inputs)")


def build_and_solve(k, solver_name="cd153"):
    next_var = 1
    def new_var():
        nonlocal next_var
        v = next_var
        next_var += 1
        return v

    s = Solver(name=solver_name)

    sig = [[new_var() for _ in care] for _ in range(k)]

    gate_info = []
    for g in range(k):
        available = ["const0"] + [f"in{i}" for i in range(N)] + [
            f"g{i}" for i in range(g)
        ]
        gate_inputs = []
        input_info = []
        for input_num in range(2):
            selectors = [new_var() for _ in available]
            inv = new_var()
            selected = [new_var() for _ in care]
            s.add_clause(selectors)
            for i in range(len(selectors)):
                for j in range(i + 1, len(selectors)):
                    s.add_clause([-selectors[i], -selectors[j]])
            for si, source in enumerate(available):
                sel = selectors[si]
                for t, (x, _, _) in enumerate(care):
                    a = selected[t]
                    if source == "const0":
                        s.add_clause([-sel, -inv, a])
                        s.add_clause([-sel, inv, -a])
                    elif source.startswith("in"):
                        bit = int(source[2:])
                        value = (x >> bit) & 1
                        if value == 0:
                            s.add_clause([-sel, -inv, a])
                            s.add_clause([-sel, inv, -a])
                        else:
                            s.add_clause([-sel, -inv, -a])
                            s.add_clause([-sel, inv, a])
                    else:
                        pg = int(source[1:])
                        v = sig[pg][t]
                        s.add_clause([-sel, -v, -inv, -a])
                        s.add_clause([-sel, v, inv, -a])
                        s.add_clause([-sel, -v, inv, a])
                        s.add_clause([-sel, v, -inv, a])
            gate_inputs.append(selected)
            input_info.append((available, selectors, inv))
        a, b = gate_inputs
        for t in range(C):
            z = sig[g][t]
            s.add_clause([-z, a[t]])
            s.add_clause([-z, b[t]])
            s.add_clause([z, -a[t], -b[t]])
        gate_info.append(input_info)

    available_out = ["const0"] + [f"in{i}" for i in range(N)] + [
        f"g{i}" for i in range(k)
    ]
    output_info = []
    for out_index in range(2 * N):
        selectors = [new_var() for _ in available_out]
        inv = new_var()
        s.add_clause(selectors)
        for i in range(len(selectors)):
            for j in range(i + 1, len(selectors)):
                s.add_clause([-selectors[i], -selectors[j]])
        is_p = out_index < N
        bit = N - 1 - (out_index % N)
        for si, source in enumerate(available_out):
            sel = selectors[si]
            for t, (x, p, q) in enumerate(care):
                required = ((p if is_p else q) >> bit) & 1
                if source == "const0":
                    if required:
                        s.add_clause([-sel, inv])
                    else:
                        s.add_clause([-sel, -inv])
                elif source.startswith("in"):
                    source_value = (x >> int(source[2:])) & 1
                    if source_value == required:
                        s.add_clause([-sel, -inv])
                    else:
                        s.add_clause([-sel, inv])
                else:
                    source_value = sig[int(source[1:])][t]
                    if required:
                        s.add_clause([-sel, source_value, inv])
                        s.add_clause([-sel, -source_value, -inv])
                    else:
                        s.add_clause([-sel, -source_value, inv])
                        s.add_clause([-sel, source_value, -inv])
        output_info.append((available_out, selectors, inv))

    sat = s.solve()
    stats = s.accum_stats()
    conflicts = stats.get("conflicts", 0)
    nvars = next_var - 1
    nclauses = stats.get("nof_clauses", 0)

    result = {
        "sat": sat,
        "conflicts": conflicts,
        "vars": nvars,
        "clauses": nclauses,
        "gate_info": gate_info,
        "output_info": output_info,
        "sig": sig,
    }

    if sat:
        model = set(v for v in s.get_model() if v > 0)
        result["model"] = model

    s.delete()
    return result


def decode_and_verify(result):
    model = result["model"]
    gate_info = result["gate_info"]
    output_info = result["output_info"]
    sig = result["sig"]
    available_out = ["const0"] + [f"in{i}" for i in range(N)] + [
        f"g{i}" for i in range(len(gate_info))
    ]

    print("\n--- MODEL ---")
    for g, inputs in enumerate(gate_info):
        print(f"Gate {g}:")
        for input_num, (available, selectors, inv) in enumerate(inputs):
            selected = [
                source for source, var in zip(available, selectors) if var in model
            ]
            inversion = inv in model
            print(
                f"  input {input_num}: "
                f"{selected[0] if selected else '???'}"
                f"{' NOT' if inversion else ''}"
            )
        values = [int(sig[g][t] in model) for t in range(C)]
        print(f"  values: {values}")

    print("\nOutputs:")
    for out_index, (available, selectors, inv) in enumerate(output_info):
        selected = [
            source for source, var in zip(available, selectors) if var in model
        ]
        inversion = inv in model
        print(
            f"  output {out_index}: "
            f"{selected[0] if selected else '???'}"
            f"{' NOT' if inversion else ''}"
        )

    print("\nDecoded results:")
    all_correct = True
    for t, (x, p, q) in enumerate(care):
        out_bits = []
        for out_index, (available, selectors, inv) in enumerate(output_info):
            selected_index = next(
                i for i, var in enumerate(selectors) if var in model
            )
            source = available[selected_index]
            if source == "const0":
                value = 0
            elif source.startswith("in"):
                value = (x >> int(source[2:])) & 1
            else:
                value = int(sig[int(source[1:])][t] in model)
            if inv in model:
                value ^= 1
            out_bits.append(value)
        p_out = sum(out_bits[i] << (N - 1 - i) for i in range(N))
        q_out = sum(out_bits[N + i] << (N - 1 - i) for i in range(N))
        ok = (p_out == p and q_out == q)
        all_correct = all_correct and ok
        print(
            f"  {x:2d}: expected {p:2d} * {q:2d}, "
            f"got {p_out:2d} * {q_out:2d}  {'OK' if ok else 'FAIL'}"
        )
    print(f"\nAll correct: {all_correct}")
    print("--- END MODEL ---\n")


print(f"\nSearching for minimum AIG (N={N}, {C} care points)...")
print(f"Solver: cd153 (CaDiCaL), max_k={MAX_K}\n")

total_time = 0.0
results = {}

for k in range(MAX_K + 1):
    t0 = time.time()
    result = build_and_solve(k)
    dt = time.time() - t0
    total_time += dt
    results[k] = result

    status = "SAT" if result["sat"] else "UNSAT"
    print(
        f"k={k:2d}: {status:>4}  conflicts={result['conflicts']:>8}  "
        f"vars={result['vars']:>5}  clauses={result['clauses']:>6}  "
        f"time={dt:7.1f}s  cumulative={total_time:8.1f}s"
    )

    if result["sat"]:
        print(f"\n*** OPTIMUM: {k} AND gates ***")
        decode_and_verify(result)
        break
else:
    print(f"\nNo solution found up to k={MAX_K}")
