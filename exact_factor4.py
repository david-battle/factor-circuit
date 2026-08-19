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


def solve_k(k):
    next_var = 1

    def new_var():
        nonlocal next_var
        v = next_var
        next_var += 1
        return v

    s = Solver(name="glucose4")

    # sig[g][t] = value of AND gate g on care point t
    sig = [
        [new_var() for _ in care]
        for _ in range(k)
    ]

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

            # Exactly one selector.
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

        for t in range(len(care)):
            z = sig[g][t]
            s.add_clause([-z, a[t]])
            s.add_clause([-z, b[t]])
            s.add_clause([z, -a[t], -b[t]])

        gate_info.append(input_info)

    # Outputs.
    available = ["const0"] + [f"in{i}" for i in range(N)] + [
        f"g{i}" for i in range(k)
    ]

    output_info = []

    for out_index in range(2 * N):
        selectors = [new_var() for _ in available]
        inv = new_var()

        s.add_clause(selectors)
        for i in range(len(selectors)):
            for j in range(i + 1, len(selectors)):
                s.add_clause([-selectors[i], -selectors[j]])

        is_p = out_index < N
        bit = N - 1 - (out_index % N)

        for si, source in enumerate(available):
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

        output_info.append((available, selectors, inv))

    sat = s.solve()
    conflicts = s.accum_stats().get("conflicts", 0)

    if sat and k == 1:
        model = set(v for v in s.get_model() if v > 0)

        print("\n--- k=1 MODEL ---")

        # Decode gate inputs.
        for g, inputs in enumerate(gate_info):
            print(f"Gate {g}:")
            for input_num, (available, selectors, inv) in enumerate(inputs):
                selected = [
                    source
                    for source, var in zip(available, selectors)
                    if var in model
                ]
                inversion = inv in model
                print(
                    f"  input {input_num}: "
                    f"{selected[0] if selected else '???'}"
                    f"{' NOT' if inversion else ''}"
                )

            values = [
                int(sig[g][t] in model)
                for t in range(len(care))
            ]
            print(f"  values: {values}")

        # Decode outputs.
        print("\nOutputs:")
        for out_index, (available, selectors, inv) in enumerate(output_info):
            selected = [
                source
                for source, var in zip(available, selectors)
                if var in model
            ]
            inversion = inv in model

            print(
                f"  output {out_index}: "
                f"{selected[0] if selected else '???'}"
                f"{' NOT' if inversion else ''}"
            )

        # Evaluate the decoded outputs on every care point.
        print("\nDecoded results:")
        for t, (x, p, q) in enumerate(care):
            out_bits = []

            for out_index, (available, selectors, inv) in enumerate(output_info):
                selected_index = next(
                    i for i, var in enumerate(selectors)
                    if var in model
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

            p_out = sum(
                out_bits[i] << (N - 1 - i)
                for i in range(N)
            )
            q_out = sum(
                out_bits[N + i] << (N - 1 - i)
                for i in range(N)
            )

            print(
                f"  {x:2d}: expected {p:2d} * {q:2d}, "
                f"got {p_out:2d} * {q_out:2d}"
            )

        print("\n--- END MODEL ---\n")

    s.delete()
    return sat, conflicts


print("Care points:")
for x, p, q in care:
    print(f"  {x:2d} -> {p:2d} * {q:2d}")

import time as _time

print("\nSearching for minimum AIG...\n")

_cumulative = 0.0
for k in range(15):
    _t0 = _time.time()
    sat, conflicts = solve_k(k)
    _dt = _time.time() - _t0
    _cumulative += _dt
    print(f"k={k:2d}: {'SAT' if sat else 'UNSAT'}  conflicts={conflicts:>8}  time={_dt:6.1f}s  cumulative={_cumulative:6.1f}s")
    if sat:
        print(f"\nOPTIMUM: {k} AND gates")
        break
