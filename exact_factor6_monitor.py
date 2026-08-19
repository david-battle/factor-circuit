from math import isqrt
import time, sys
from pysat.solvers import Solver

N = 6

def is_prime(n):
    if n < 2: return False
    for p in range(2, isqrt(n) + 1):
        if n % p == 0: return False
    return True

def factor_semiprime(n):
    for p in range(2, isqrt(n) + 1):
        if n % p == 0:
            q = n // p
            if p != q and is_prime(p) and is_prime(q): return p, q
    return None

care = []
for x in range(1 << N):
    f = factor_semiprime(x)
    if f: care.append((x, f[0], f[1]))
C = len(care)

ks = [int(x) for x in sys.argv[1:]] if len(sys.argv) > 1 else [11]

def build_cnf(k):
    nv = 1
    clauses = []
    def nv_():
        nonlocal nv; v = nv; nv += 1; return v
    sig = [[nv_() for _ in care] for _ in range(k)]
    for g in range(k):
        avail = ["const0"] + [f"in{i}" for i in range(N)] + [f"g{i}" for i in range(g)]
        for _ in range(2):
            sel = [nv_() for _ in avail]
            inv = nv_()
            sel_t = [nv_() for _ in care]
            clauses.append(sel)
            for i in range(len(sel)):
                for j in range(i+1, len(sel)):
                    clauses.append([-sel[i], -sel[j]])
            for si, src in enumerate(avail):
                for t, (x, _, _) in enumerate(care):
                    a = sel_t[t]
                    if src == "const0":
                        clauses.extend([[-sel[si], -inv, a], [-sel[si], inv, -a]])
                    elif src.startswith("in"):
                        v = (x >> int(src[2:])) & 1
                        if v == 0:
                            clauses.extend([[-sel[si], -inv, a], [-sel[si], inv, -a]])
                        else:
                            clauses.extend([[-sel[si], -inv, -a], [-sel[si], inv, a]])
                    else:
                        vv = sig[int(src[1:])][t]
                        clauses.extend([[-sel[si], -vv, -inv, -a], [-sel[si], vv, inv, -a],
                                        [-sel[si], -vv, inv, a], [-sel[si], vv, -inv, a]])
    for g in range(k):
        avail = ["const0"] + [f"in{i}" for i in range(N)] + [f"g{i}" for i in range(g)]
        inp_sel = []
        for _ in range(2):
            sel = [nv_() for _ in avail]
            inv = nv_()
            sel_t = [nv_() for _ in care]
            clauses.append(sel)
            for i in range(len(sel)):
                for j in range(i+1, len(sel)):
                    clauses.append([-sel[i], -sel[j]])
            for si, src in enumerate(avail):
                for t, (x, _, _) in enumerate(care):
                    a = sel_t[t]
                    if src == "const0":
                        clauses.extend([[-sel[si], -inv, a], [-sel[si], inv, -a]])
                    elif src.startswith("in"):
                        v = (x >> int(src[2:])) & 1
                        if v == 0:
                            clauses.extend([[-sel[si], -inv, a], [-sel[si], inv, -a]])
                        else:
                            clauses.extend([[-sel[si], -inv, -a], [-sel[si], inv, a]])
                    else:
                        vv = sig[int(src[1:])][t]
                        clauses.extend([[-sel[si], -vv, -inv, -a], [-sel[si], vv, inv, -a],
                                        [-sel[si], -vv, inv, a], [-sel[si], vv, -inv, a]])
            inp_sel.append((sel_t, inv))
        (a, _), (b, _) = inp_sel
        for t in range(C):
            z = sig[g][t]
            clauses.extend([[-z, a[t]], [-z, b[t]], [z, -a[t], -b[t]]])

    avail_out = ["const0"] + [f"in{i}" for i in range(N)] + [f"g{i}" for i in range(k)]
    for oi in range(2*N):
        sel = [nv_() for _ in avail_out]
        inv = nv_()
        clauses.append(sel)
        for i in range(len(sel)):
            for j in range(i+1, len(sel)):
                clauses.append([-sel[i], -sel[j]])
        is_p = oi < N
        bit = N - 1 - (oi % N)
        for si, src in enumerate(avail_out):
            for t, (x, p, q) in enumerate(care):
                req = ((p if is_p else q) >> bit) & 1
                if src == "const0":
                    clauses.append([-sel[si], inv]) if req else clauses.append([-sel[si], -inv])
                elif src.startswith("in"):
                    sv = (x >> int(src[2:])) & 1
                    clauses.append([-sel[si], -inv]) if sv == req else clauses.append([-sel[si], inv])
                else:
                    sv = sig[int(src[1:])][t]
                    if req:
                        clauses.extend([[-sel[si], sv, inv], [-sel[si], -sv, -inv]])
                    else:
                        clauses.extend([[-sel[si], -sv, inv], [-sel[si], sv, -inv]])

    return clauses, nv - 1


KNOWN_UNSAT = 10
KNOWN_SAT = 20
PREV_UNTIMED = {10: 405, 20: 50, 30: 31, 50: 47}

for k in ks:
    clauses, nvars = build_cnf(k)
    nclauses = len(clauses)

    s = Solver(name="cd153")
    s.append_formula(clauses)

    BUDGET = 5000
    t0 = time.time()
    snapshots = []
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
        dec = stats.get("decisions", 0)
        prop = stats.get("propagations", 0)

        rate = conf / dt if dt > 0 else 0

        snapshots.append((dt, conf, dec, prop, rate))

        # Print summary every ~30s worth of snapshots
        if len(snapshots) % 6 == 0:
            # Compute trend: are we speeding up or slowing down?
            if len(snapshots) >= 12:
                recent_rate = snapshots[-1][4]
                older_rate = snapshots[-6][4]
                trend = "slowing" if recent_rate < older_rate * 0.8 else (
                    "speeding up" if recent_rate > older_rate * 1.2 else "steady")
            else:
                trend = "..."

            # Estimate based on known results for similar k
            est = "unknown"
            if k == KNOWN_UNSAT:
                est = f"(known UNSAT, prev took {PREV_UNTIMED.get(k, '?')}s)"
            elif k == KNOWN_SAT:
                est = f"(known SAT, prev took {PREV_UNTIMED.get(k, '?')}s)"
            elif k - 1 in PREV_UNTIMED and k + 1 in PREV_UNTIMED:
                est = f"(between {PREV_UNTIMED[k-1]}s and {PREV_UNTIMED[k+1]}s est)"

            print(
                f"  k={k}: {dt:6.0f}s | {conf:>10} conflicts | "
                f"{rate:>7.0f} c/s | trend: {trend:>10} | "
                f"learned ~{stats.get('learned_clauses', 0):>6} clauses | "
                f"{est}",
                flush=True,
            )

    dt = time.time() - t0
    stats = s.accum_stats()
    total_conf = stats.get("conflicts", 0)
    learned = stats.get("learned_clauses", 0)

    print(f"\nk={k}: {'SAT' if result else 'UNSAT'}  "
          f"conflicts={total_conf}  learned={learned}  "
          f"time={dt:.1f}s  rate={total_conf/dt:.0f} c/s\n")
    s.delete()
    if result:
        break
