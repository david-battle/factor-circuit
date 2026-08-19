#!/usr/bin/env python3
"""
Systematic parameter sweep for N=6 windowed resynthesis.
Tests multiple configurations to try to improve the 19-gate UB.
"""

import subprocess
import sys
import os
import time
from pathlib import Path

# Configurations to test (based on N=8 success patterns)
CONFIGS = [
    {
        "name": "C1",
        "max_in": 3,
        "max_out": 4,
        "max_gates": 15,
        "iterations": 500,
        "seed_start": 42,
    },
    {
        "name": "C2",
        "max_in": 4,
        "max_out": 4,
        "max_gates": 20,
        "iterations": 500,
        "seed_start": 123,
    },
    {
        "name": "C3",
        "max_in": 3,
        "max_out": 5,
        "max_gates": 25,
        "iterations": 500,
        "seed_start": 456,
    },
    {
        "name": "C4",
        "max_in": 5,
        "max_out": 5,
        "max_gates": 25,
        "iterations": 500,
        "seed_start": 789,
    },
]

BASE_BLIF = "factor6_opt_final_opt.blif"  # 19 gates
N = 6
TIMEOUT_PER_CONFIG = 7200  # 2 hours per config

def run_config(config):
    """Run window_opt.py with given configuration."""
    name = config["name"]
    blif_path = BASE_BLIF
    
    cmd = [
        "python3", "window_opt.py", blif_path, str(N), str(config["iterations"]),
        "--max-in", str(config["max_in"]),
        "--max-out", str(config["max_out"]),
        "--max-gates", str(config["max_gates"]),
        "--seed", str(config["seed_start"]),
    ]
    
    print(f"\n{'='*60}")
    print(f"Running {name}: max_in={config['max_in']}, max_out={config['max_out']}, "
          f"max_gates={config['max_gates']}, iters={config['iterations']}")
    print(f"Command: {' '.join(cmd)}")
    print(f"{'='*60}")
    
    start = time.time()
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT_PER_CONFIG)
        elapsed = time.time() - start
        
        print(f"Completed in {elapsed:.1f}s")
        print(f"Return code: {result.returncode}")
        print("STDOUT:")
        print(result.stdout[-3000:] if len(result.stdout) > 3000 else result.stdout)
        if result.stderr:
            print("STDERR:")
            print(result.stderr[-1000:] if len(result.stderr) > 1000 else result.stderr)
        
        # Extract final gate count from output
        final_gates = None
        for line in result.stdout.split('\n'):
            if line.startswith("Final:") and "AND gates" in line:
                parts = line.split()
                for i, p in enumerate(parts):
                    if p.isdigit():
                        final_gates = int(p)
                        break
        
        return {
            "config": config,
            "returncode": result.returncode,
            "elapsed": elapsed,
            "final_gates": final_gates,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
        
    except subprocess.TimeoutExpired:
        elapsed = time.time() - start
        print(f"TIMEOUT after {elapsed:.1f}s")
        return {
            "config": config,
            "returncode": -1,
            "elapsed": elapsed,
            "final_gates": None,
            "stdout": "",
            "stderr": "TIMEOUT",
        }

def parse_best_gates(stdout):
    """Extract the best gate count from output."""
    best = None
    for line in stdout.split('\n'):
        if "Best:" in line and "AND gates" in line:
            # Format: "  [20] Best: 19 AND gates, 0 improvements so far"
            parts = line.split()
            for p in parts:
                if p.isdigit():
                    if best is None or int(p) < best:
                        best = int(p)
    return best

def main():
    print("="*70)
    print("N=6 Windowed Resynthesis Parameter Sweep")
    print(f"Starting from {BASE_BLIF} (19 gates)")
    print(f"Testing {len(CONFIGS)} configurations")
    print("="*70)
    
    results = []
    best_overall = 19
    
    for i, config in enumerate(CONFIGS):
        result = run_config(config)
        result["parsed_best"] = parse_best_gates(result["stdout"])
        results.append(result)
        
        if result["final_gates"] is not None:
            print(f"  -> Final gates reported: {result['final_gates']}")
        if result["parsed_best"] is not None:
            print(f"  -> Best gates found: {result['parsed_best']}")
            if result["parsed_best"] < best_overall:
                best_overall = result["parsed_best"]
                print(f"  *** NEW BEST: {best_overall} gates ***")
        
        # Log to NOTES.md incrementally
        log_result(result)
    
    # Summary
    print("\n" + "="*70)
    print("SWEEP SUMMARY")
    print("="*70)
    for r in results:
        c = r["config"]
        print(f"{c['name']}: max_in={c['max_in']} max_out={c['max_out']} "
              f"max_gates={c['max_gates']} -> best={r['parsed_best']} "
              f"(final={r['final_gates']}) time={r['elapsed']:.0f}s")
    
    print(f"\nBest overall: {best_overall} gates")
    if best_overall < 19:
        print(f"IMPROVEMENT FOUND: {19 - best_overall} gates saved!")
    else:
        print("No improvement over 19 gates found.")
    
    return results

def log_result(result):
    """Append result to NOTES.md incrementally."""
    c = result["config"]
    with open("NOTES.md", "a") as f:
        f.write(f"\n### N=6 Sweep Config {c['name']}\n")
        f.write(f"- Parameters: max_in={c['max_in']}, max_out={c['max_out']}, "
                f"max_gates={c['max_gates']}, iterations={c['iterations']}\n")
        f.write(f"- Seed: {c['seed_start']}\n")
        f.write(f"- Time: {result['elapsed']:.0f}s\n")
        f.write(f"- Best gates found: {result['parsed_best']}\n")
        f.write(f"- Final gates reported: {result['final_gates']}\n")
        f.write(f"- Return code: {result['returncode']}\n")

if __name__ == "__main__":
    results = main()
    # Save results to JSON for later analysis
    import json
    with open("n6_sweep_results.json", "w") as f:
        json.dump(results, f, indent=2)