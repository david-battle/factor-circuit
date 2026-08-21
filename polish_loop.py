#!/usr/bin/env python3
"""Overnight polish-loop driver.

Alternates ABC structural polish (compress2rs; fraig; balance) with SAT
windowed resynthesis (window_opt.py), verifying care-correctness after every
pass. Keeps the canonical factor{N}_opt_final_opt.blif monotonic. Stops after
a wall-clock budget or plateau.

Usage: polish_loop.py N BUDGET_MIN [--no-window] [--no-abc]
"""

import os
import shutil
import subprocess
import sys
import time

from window_opt import (
    parse_blif,
    count_and_gates,
    verify_circuit,
    enumerate_care,
)

ABC = os.path.expanduser("~/factor-circuit/abc/abc")
ABC_WORKDIR = os.path.expanduser("~/factor-circuit/abc")


def gates_and_verify(path, N):
    aig = parse_blif(path)
    care = enumerate_care(N)
    correct, total = verify_circuit(aig, care, N)
    return count_and_gates(aig), correct, total


def abc_polish(in_path, out_path, timeout):
    cmd = (
        f"read_blif {in_path}; strash; compress2rs; fraig; balance; "
        f"write_blif {out_path}; print_stats"
    )
    return subprocess.run(
        [ABC, "-c", cmd], capture_output=True, text=True,
        timeout=timeout, cwd=ABC_WORKDIR,
    )


def window_resynth(in_path, out_path, N, seed, max_out, max_gates,
                   iterations, timeout):
    return subprocess.run(
        [sys.executable, "window_opt.py", in_path, str(N), str(iterations),
         "--seed", str(seed), "--max-out", str(max_out),
         "--max-gates", str(max_gates), "--out", out_path],
        capture_output=True, text=True, timeout=timeout,
    )


def main():
    N = int(sys.argv[1])
    budget_min = float(sys.argv[2])
    do_window = "--no-window" not in sys.argv
    do_abc = "--no-abc" not in sys.argv
    win_iters = 200
    max_out_list = [4, 5]
    max_gates_list = [60, 100]
    start_seed = 1000
    for flag, dest in [("--win-iters", "win_iters"),
                       ("--max-out", "max_out_list"),
                       ("--max-gates", "max_gates_list"),
                       ("--seed", "start_seed")]:
        if flag in sys.argv:
            val = sys.argv[sys.argv.index(flag) + 1]
            if flag == "--max-out":
                max_out_list = [int(x) for x in val.split(",")]
            elif flag == "--max-gates":
                max_gates_list = [int(x) for x in val.split(",")]
            elif flag == "--win-iters":
                win_iters = int(val)
            else:
                start_seed = int(val)

    canonical = os.path.abspath(f"factor{N}_opt_final_opt.blif")
    baseline = os.path.abspath(f"factor{N}_opt_final.blif")
    if not os.path.exists(canonical):
        shutil.copy(baseline, canonical)

    best, correct, total = gates_and_verify(canonical, N)
    if correct != total:
        print(f"ERROR: {canonical} fails verification ({correct}/{total})")
        sys.exit(1)
    print(f"start: {canonical} = {best} AND gates ({correct}/{total})", flush=True)

    deadline = time.time() + budget_min * 60
    plateau = 0
    round_num = 0
    seed = start_seed

    while time.time() < deadline:
        round_num += 1
        improved = False

        ops = []
        if do_abc:
            ops.append(("abc", None))
        if do_window:
            for max_out, max_gates in zip(max_out_list, max_gates_list):
                ops.append(("win", (seed, max_out, max_gates, win_iters)))
        seed += 1

        for kind, params in ops:
            if time.time() >= deadline:
                break
            tmp = f"/tmp/polish_{N}_pass.blif"
            t0 = time.time()
            try:
                if kind == "abc":
                    r = abc_polish(canonical, tmp, timeout=1800)
                    note = "abc polish"
                else:
                    s, mo, mg, it = params
                    r = window_resynth(canonical, tmp, N, s, mo, mg, it,
                                       timeout=3600)
                    note = f"window s={s} o={mo} g={mg} it={it}"
            except subprocess.TimeoutExpired:
                print(f"[r{round_num}] {note}: TIMEOUT", flush=True)
                continue
            dt = time.time() - t0

            if not os.path.exists(tmp):
                print(f"[r{round_num}] {note}: no output ({dt:.0f}s)", flush=True)
                continue
            try:
                new_gates, correct, total = gates_and_verify(tmp, N)
            except Exception as e:
                print(f"[r{round_num}] {note}: parse/verify failed ({dt:.0f}s): {e}",
                      flush=True)
                continue

            if correct != total:
                print(f"[r{round_num}] {note}: FAILED verify {correct}/{total} "
                      f"({dt:.0f}s)", flush=True)
                continue

            if new_gates < best:
                shutil.move(tmp, canonical)
                best = new_gates
                improved = True
                plateau = 0
                print(f"[r{round_num}] {note}: {best} AND gates "
                      f"({dt:.0f}s) *** NEW BEST ***", flush=True)
            else:
                plateau += 1
                print(f"[r{round_num}] {note}: {new_gates} no better "
                      f"({dt:.0f}s, best {best})", flush=True)

        if plateau >= 6:
            print("plateau reached, stopping", flush=True)
            break

    print(f"done: {canonical} = {best} AND gates", flush=True)


if __name__ == "__main__":
    main()
