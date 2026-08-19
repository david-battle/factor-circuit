from math import isqrt
import time, sys, signal, os
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

ks = [int(x) for x in sys.argv[1:]] if len(sys.argv) > 1 else list(range(15, 20))

for k in ks:
    next_var = 1
    def new_var():
        global next_var
        v = next_var
        next_var += 1
        return v

    s = Solver(name="cd153")
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

    nvars = next_var - 1
    t0 = time.time()

    pid = os.fork()
    if pid == 0:
        sat = s.solve()
        s.delete()
        os._exit(0 if sat else 1)
    else:
        elapsed_printed = 0
        while True:
            try:
                wpid, status = os.waitpid(pid, os.WNOHANG)
            except ChildProcessError:
                break
            if wpid != 0:
                break
            elapsed = time.time() - t0
            if elapsed - elapsed_printed >= 30:
                print(f"    ... k={k}: {elapsed:.0f}s elapsed, vars={nvars}", flush=True)
                elapsed_printed = elapsed
            time.sleep(1)

        dt = time.time() - t0
        try:
            _, status = os.waitpid(pid, 0)
        except ChildProcessError:
            pass
        sat = os.WIFEXITED(status) and os.WEXITSTATUS(status) == 0

    print(f"k={k:2d}: {'SAT' if sat else 'UNSAT'}  vars={nvars:>5}  time={dt:7.1f}s", flush=True)
    s.delete()
    if sat:
        break
