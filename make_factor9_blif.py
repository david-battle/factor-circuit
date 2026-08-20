#!/usr/bin/env python3
"""Build N=9 ABC baseline BLIF with persistence (fixes survey.py's missing artifact).

Runs the same ABC strategy battery as survey.py's run_abc_optimize, but
writes each candidate circuit with write_blif and keeps the best one as
factor9_opt_final.blif.
"""

import os
import shutil
import subprocess
import sys
import tempfile

from survey import count_abc_gates_from_output, enumerate_care, generate_blif

ABC_BIN = os.path.expanduser("~/factor-circuit/abc/abc")
N = 9
OUT = "factor9_opt_final.blif"

STRATEGIES = [
    "strash; rewrite; refactor; balance",
    "strash; rewrite; refactor; balance; resub",
    "strash; rewrite; refactor; balance; resub -K 8",
    "strash; rewrite; refactor; balance; resub -K 16",
    "strash; rewrite; refactor; balance; resub -K 32",
    "strash; rewrite; refactor; balance; resub -K 64",
    "strash; rewrite -K 6; refactor -K 6; balance; resub -K 16",
    "strash; rewrite -K 8; refactor -K 8; balance; resub -K 32",
    "strash; rewrite; refactor; balance; resub; resub -K 16",
    "strash; rewrite; refactor; balance; resub; resub -K 32",
    "strash; rewrite -K 4; refactor; balance; resub -K 8",
    "strash; rewrite -K 10; refactor -K 10; balance; resub",
    "strash; dc2; rewrite; refactor; balance",
    "strash; dc2; rewrite; refactor; balance; resub",
    "strash; dc2; dc2; rewrite; refactor; balance",
    "strash; dc2; dc2; rewrite; refactor; balance; resub",
    "strash; dc2; mfs2; rewrite; refactor; balance",
    "strash; dc2; mfs2; rewrite; refactor; balance; resub",
    "strash; dc2; dc2; mfs2; rewrite; refactor; balance",
    "strash; dc2; dc2; mfs2; rewrite; refactor; balance; resub",
    "strash; dch; rewrite; refactor; balance",
    "strash; dch; rewrite; refactor; balance; resub",
    "strash; dch; dc2; rewrite; refactor; balance",
    "strash; dch; dc2; rewrite; refactor; balance; resub",
]

SINGLE_PIPELINES = [
    ("dc2; rewrite; refactor; balance; resub", 8),
    ("dch; dc2; rewrite; refactor; balance; resub", 10),
]

ALT_PIPELINES = [
    "dch; dc2; rewrite; refactor; balance; resub",
    "dc2; rewrite; refactor; balance; resub",
]


def main():
    care = enumerate_care(N)
    with tempfile.NamedTemporaryFile(suffix=".blif", delete=False, dir="/tmp") as f:
        raw = f.name
    generate_blif(N, care, raw)

    best = None
    best_blif = None

    # Phase 1: one-shot strategies
    for strat in STRATEGIES:
        with tempfile.NamedTemporaryFile(suffix=".blif", delete=False, dir="/tmp") as f:
            tmp = f.name
        cmd = f"read_blif {raw}; {strat}; write_blif {tmp}; print_stats"
        result = subprocess.run(
            [ABC_BIN, "-c", cmd], capture_output=True, text=True, timeout=120
        )
        gates = count_abc_gates_from_output(result.stdout)
        if gates is not None and (best is None or gates < best):
            if best_blif is not None:
                os.unlink(best_blif)
            best = gates
            best_blif = tmp
            print(f"  new best: {gates} AND gates")
        else:
            os.unlink(tmp)

    # Phase 2: iterated single pipelines
    for pipeline, max_passes in SINGLE_PIPELINES:
        current = raw
        no_improve = 0
        for _ in range(max_passes):
            with tempfile.NamedTemporaryFile(suffix=".blif", delete=False, dir="/tmp") as f:
                tmp = f.name
            cmd = f"read_blif {current}; strash; {pipeline}; write_blif {tmp}; print_stats"
            result = subprocess.run(
                [ABC_BIN, "-c", cmd], capture_output=True, text=True, timeout=120
            )
            gates = count_abc_gates_from_output(result.stdout)
            if gates is None:
                os.unlink(tmp)
                break
            if best is None or gates < best:
                if best_blif is not None:
                    os.unlink(best_blif)
                best = gates
                best_blif = tmp
                no_improve = 0
                print(f"  new best: {gates} AND gates")
            else:
                no_improve += 1
            if no_improve >= 2:
                os.unlink(tmp)
                break
            current = tmp

    # Phase 3: alternating pipelines
    current = raw
    no_improve = 0
    for pass_num in range(30):
        pipeline = ALT_PIPELINES[pass_num % 2]
        with tempfile.NamedTemporaryFile(suffix=".blif", delete=False, dir="/tmp") as f:
            tmp = f.name
        cmd = f"read_blif {current}; strash; {pipeline}; write_blif {tmp}; print_stats"
        result = subprocess.run(
            [ABC_BIN, "-c", cmd], capture_output=True, text=True, timeout=120
        )
        gates = count_abc_gates_from_output(result.stdout)
        if gates is None:
            os.unlink(tmp)
            break
        if best is None or gates < best:
            if best_blif is not None:
                os.unlink(best_blif)
            best = gates
            best_blif = tmp
            no_improve = 0
            print(f"  new best: {gates} AND gates")
        else:
            no_improve += 1
        if no_improve >= 8:
            os.unlink(tmp)
            break
        current = tmp

    print(f"\nBest: {best} AND gates")
    if best_blif is not None:
        shutil.copy(best_blif, OUT)
        print(f"Wrote {OUT}")
    else:
        print("No BLIF produced!", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
