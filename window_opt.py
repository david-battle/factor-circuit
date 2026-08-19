#!/usr/bin/env python3
"""SAT-based windowed resynthesis for factoring circuits.

Loads an ABC-optimized BLIF, selects random windows, computes ODC care sets,
uses SAT to find optimal replacements, and splices them back in.
"""

import sys
import os
import copy
import random
import time
from math import isqrt
from collections import defaultdict
from pysat.solvers import Solver


# ── AIG Class ─────────────────────────────────────────────────────────

class AIG:
    def __init__(self):
        self.inputs = []
        self.outputs = []
        self.nodes = {}
        # Types:
        #   'PI': Primary Input
        #   'CONST0': Constant 0
        #   'CONST1': Constant 1
        #   'BUF': (source,)
        #   'NOT': (source,)
        #   'AND': (src1, inv1, src2, inv2, inv_out)

    def eval_node(self, node, values, _visited=None):
        if node in values:
            return values[node]
        if _visited is None:
            _visited = set()
        if node in _visited:
            raise RuntimeError(f"Cycle detected at node {node}")
        _visited.add(node)
        if node not in self.nodes:
            raise ValueError(f"Node '{node}' not in AIG")
        typ, args = self.nodes[node]
        if typ == 'PI':
            raise ValueError(f"PI {node} not in values")
        elif typ == 'CONST0':
            val = 0
        elif typ == 'CONST1':
            val = 1
        elif typ == 'BUF':
            val = self.eval_node(args[0], values, _visited)
        elif typ == 'NOT':
            val = 1 - self.eval_node(args[0], values, _visited)
        elif typ == 'AND':
            src1, inv1, src2, inv2, inv_out = args
            v1 = self.eval_node(src1, values, _visited)
            v2 = self.eval_node(src2, values, _visited)
            if inv1:
                v1 = 1 - v1
            if inv2:
                v2 = 1 - v2
            val = v1 & v2
            if inv_out:
                val = 1 - val
        else:
            raise ValueError(f"Unknown type {typ} for node {node}")
        values[node] = val
        return val

    def simulate(self, input_vals):
        values = input_vals.copy()
        for node in self.toposort():
            self.eval_node(node, values)
        return values

    def toposort(self):
        visited = set()
        order = []

        def visit(n):
            if n in visited:
                return
            visited.add(n)
            if n not in self.nodes:
                return
            typ, args = self.nodes[n]
            if typ == 'PI':
                pass
            elif typ in ('CONST0', 'CONST1'):
                pass
            elif typ in ('BUF', 'NOT'):
                visit(args[0])
            elif typ == 'AND':
                visit(args[0])
                visit(args[2])
            order.append(n)

        for out in self.outputs:
            visit(out)
        return order

    def compute_fanout(self):
        """Returns dict: node -> list of nodes that consume it."""
        fanout = defaultdict(list)
        for name, (typ, args) in self.nodes.items():
            if typ == 'AND':
                fanout[args[0]].append(name)
                fanout[args[2]].append(name)
            elif typ in ('BUF', 'NOT'):
                fanout[args[0]].append(name)
        return fanout

    def and_gate_names(self):
        """List of node names that are AND gates."""
        return [n for n, (typ, _) in self.nodes.items() if typ == 'AND']

    def clone(self):
        """Deep copy of the AIG."""
        new = AIG()
        new.inputs = list(self.inputs)
        new.outputs = list(self.outputs)
        new.nodes = {}
        for name, (typ, args) in self.nodes.items():
            new.nodes[name] = (typ, list(args) if isinstance(args, list) else args)
        return new

    def prune(self):
        """Remove nodes not reachable from outputs or inputs."""
        reachable = set(self.inputs)
        for out in self.outputs:
            self._mark_reachable(out, reachable)
        removed = [n for n in self.nodes if n not in reachable]
        for n in removed:
            del self.nodes[n]
        return len(removed)

    def _mark_reachable(self, node, visited):
        if node in visited or node not in self.nodes:
            return
        visited.add(node)
        typ, args = self.nodes[node]
        if typ in ('BUF', 'NOT'):
            self._mark_reachable(args[0], visited)
        elif typ == 'AND':
            self._mark_reachable(args[0], visited)
            self._mark_reachable(args[2], visited)

    def has_cycle(self):
        """Detect cycles in the AIG using DFS coloring."""
        WHITE, GRAY, BLACK = 0, 1, 2
        color = {n: WHITE for n in self.nodes}

        def dfs(n, path):
            if n not in self.nodes:
                return False
            if color.get(n, WHITE) == GRAY:
                return True
            if color.get(n, WHITE) == BLACK:
                return False
            color[n] = GRAY
            path.append(n)
            typ, args = self.nodes[n]
            found = False
            if typ in ('BUF', 'NOT'):
                found = dfs(args[0], path)
            elif typ == 'AND':
                found = dfs(args[0], path) or dfs(args[2], path)
            path.pop()
            color[n] = BLACK
            return found

        for n in self.nodes:
            if color.get(n, WHITE) == WHITE:
                if dfs(n, []):
                    return True
        return False

    def to_blif(self, filepath):
        with open(filepath, 'w') as f:
            f.write(f".model factor\n")
            f.write(f".inputs {' '.join(self.inputs)}\n")
            f.write(f".outputs {' '.join(self.outputs)}\n")
            for node in self.toposort():
                if node in self.inputs:
                    continue
                typ, args = self.nodes[node]
                if typ == 'CONST0':
                    f.write(f".names {node}\n0\n")
                elif typ == 'CONST1':
                    f.write(f".names {node}\n1\n")
                elif typ == 'BUF':
                    f.write(f".names {args[0]} {node}\n1 1\n")
                elif typ == 'NOT':
                    f.write(f".names {args[0]} {node}\n0 1\n")
                elif typ == 'AND':
                    src1, inv1, src2, inv2, inv_out = args
                    f.write(f".names {src1} {src2} {node}\n")
                    p1 = '0' if inv1 else '1'
                    p2 = '0' if inv2 else '1'
                    v = '0' if inv_out else '1'
                    f.write(f"{p1}{p2} {v}\n")
            f.write(".end\n")


# ── BLIF Parser ───────────────────────────────────────────────────────

def parse_blif(filepath):
    aig = AIG()
    with open(filepath, 'r') as f:
        lines = f.read().splitlines()

    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line or line.startswith('#'):
            i += 1
            continue

        if line.startswith('.inputs'):
            aig.inputs = line.split()[1:]
            for pi in aig.inputs:
                aig.nodes[pi] = ('PI', [])
        elif line.startswith('.outputs'):
            aig.outputs = line.split()[1:]
        elif line.startswith('.names'):
            parts = line.split()
            out_node = parts[-1]
            in_nodes = parts[1:-1]

            tt = []
            i += 1
            while i < len(lines) and lines[i].strip() and not lines[i].startswith('.'):
                tt.append(lines[i].strip())
                i += 1

            if len(in_nodes) == 0:
                if len(tt) == 0 or tt[0].strip() == '0':
                    aig.nodes[out_node] = ('CONST0', [])
                elif tt[0].strip() == '1':
                    aig.nodes[out_node] = ('CONST1', [])
            elif len(in_nodes) == 1:
                if tt == ['1 1']:
                    aig.nodes[out_node] = ('BUF', [in_nodes[0]])
                elif tt == ['0 1']:
                    aig.nodes[out_node] = ('NOT', [in_nodes[0]])
                elif tt == ['0 0']:
                    aig.nodes[out_node] = ('BUF', [in_nodes[0]])
                elif tt == ['1 0']:
                    aig.nodes[out_node] = ('NOT', [in_nodes[0]])
                elif tt == [] or tt == ['0']:
                    aig.nodes[out_node] = ('CONST0', [])
                else:
                    raise ValueError(f"Unknown 1-input TT for {out_node}: {tt}")
            elif len(in_nodes) == 2:
                if len(tt) == 1:
                    pattern, out_val = tt[0].split()
                    inv1 = (pattern[0] == '0')
                    inv2 = (pattern[1] == '0')
                    inv_out = (out_val == '0')
                    aig.nodes[out_node] = ('AND', [in_nodes[0], inv1, in_nodes[1], inv2, inv_out])
                elif len(tt) == 0:
                    aig.nodes[out_node] = ('CONST0', [])
                else:
                    raise ValueError(f"Unknown 2-input TT for {out_node}: {tt}")
            else:
                raise ValueError(f"Node {out_node} has {len(in_nodes)} inputs")
            continue
        i += 1

    return aig


# ── ODC Extraction ────────────────────────────────────────────────────

def get_window_care_set(aig, W_in, W_out, W_gates, care_points, N, use_odc=True):
    """Care set extraction for a window.

    Returns dict: tuple(in_vals) -> set of tuple(out_vals).

    SDC (Level 1): each in_pattern maps to the single out_pattern the original circuit produces.
    ODC (Level 2): for each in_pattern, try all 2^|W_out| out patterns and keep
    those that still produce correct global outputs.
    """
    care_set = defaultdict(set)

    if not use_odc:
        # SDC only: record what the original circuit produces
        for (x, p, q) in care_points:
            input_vals = {f"x{i}": (x >> i) & 1 for i in range(N)}
            values = aig.simulate(input_vals)
            in_pattern = tuple(values[n] for n in W_in)
            out_pattern = tuple(values[n] for n in W_out)
            care_set[in_pattern].add(out_pattern)
        return care_set

    # ODC (Level 2): try all W_out patterns and keep those that still work
    topo = aig.toposort()

    # Find the fanout cone of W_out: nodes that depend on W_out
    fanout_cone = set()
    for n in W_out:
        fanout_cone.add(n)
    for n in topo:
        if n in fanout_cone or n in aig.inputs:
            continue
        typ, args = aig.nodes[n]
        if typ in ('BUF', 'NOT') and args[0] in fanout_cone:
            fanout_cone.add(n)
        elif typ == 'AND' and (args[0] in fanout_cone or args[2] in fanout_cone):
            fanout_cone.add(n)

    # Nodes to re-simulate: fanout cone minus W_out (W_gates are included
    # so they re-evaluate with new W_out values, giving correct inputs to
    # downstream nodes that depend on both W_out and W_gates).
    eval_order = [n for n in topo if n in fanout_cone and n not in W_out]

    for (x, p, q) in care_points:
        input_vals = {f"x{i}": (x >> i) & 1 for i in range(N)}
        base_vals = aig.simulate(input_vals)
        in_pattern = tuple(base_vals[n] for n in W_in)

        req = {}
        for i in range(N):
            req[f"p{i}"] = (p >> i) & 1
            req[f"q{i}"] = (q >> i) & 1

        O_size = len(W_out)
        for i in range(1 << O_size):
            out_pattern = tuple((i >> j) & 1 for j in range(O_size))
            test_vals = base_vals.copy()
            for j, out_node in enumerate(W_out):
                test_vals[out_node] = out_pattern[j]

            for n in eval_order:
                if n in test_vals:
                    del test_vals[n]
                aig.eval_node(n, test_vals)

            ok = True
            for out_node, required_val in req.items():
                if out_node in aig.outputs and test_vals.get(out_node) != required_val:
                    ok = False
                    break

            if ok:
                care_set[in_pattern].add(out_pattern)

    return care_set


# ── Window Selection ──────────────────────────────────────────────────

def trace_to_source(aig, node):
    """Trace through BUF/NOT to find the AND gate or PI source."""
    while True:
        typ, args = aig.nodes[node]
        if typ in ('PI', 'AND', 'CONST0', 'CONST1'):
            return node
        elif typ in ('BUF', 'NOT'):
            node = args[0]
        else:
            return node


def select_window(aig, max_inputs=6, max_outputs=3, max_gates=15):
    """Select a window by topological growth from a random seed.

    Returns (W_in, W_out, W_gates) or None if no valid window found.
    """
    and_gates = aig.and_gate_names()
    if not and_gates:
        return None

    fanout = aig.compute_fanout()
    seed = random.choice(and_gates)
    W_gates = {seed}

    for _ in range(max_gates - 1):
        candidates = set()
        for g in W_gates:
            typ, args = aig.nodes[g]
            if typ == 'AND':
                # Fanin: trace through BUF/NOT to find source
                src0 = trace_to_source(aig, args[0])
                src2 = trace_to_source(aig, args[2])
                if src0 not in W_gates and aig.nodes[src0][0] == 'AND':
                    candidates.add(src0)
                if src2 not in W_gates and aig.nodes[src2][0] == 'AND':
                    candidates.add(src2)
                # Fanout
                for consumer in fanout.get(g, []):
                    if consumer not in W_gates and aig.nodes[consumer][0] == 'AND':
                        candidates.add(consumer)

        if not candidates:
            break

        cand_list = list(candidates)
        random.shuffle(cand_list)

        added = False
        for cand in cand_list:
            test_gates = W_gates | {cand}
            w_in, w_out = compute_window_boundaries(aig, test_gates)
            if len(w_in) <= max_inputs and len(w_out) <= max_outputs:
                W_gates = test_gates
                added = True
                break

        if not added:
            break

    W_in, W_out = compute_window_boundaries(aig, W_gates)
    if not W_in or not W_out:
        return None
    # Sort consistently — order must match between ODC extraction, SAT encoding, and splicing
    W_in = sorted(W_in, key=lambda n: (n not in aig.inputs, n))
    W_out = sorted(W_out, key=lambda n: (n not in aig.outputs, n))
    return W_in, W_out, W_gates


def compute_window_boundaries(aig, W_gates):
    """Compute W_in and W_out for a set of window gates."""
    W_in = set()
    W_out = set()

    for g in W_gates:
        typ, args = aig.nodes[g]
        if typ == 'AND':
            for src_idx in [0, 2]:
                src = trace_to_source(aig, args[src_idx])
                if src not in W_gates:
                    W_in.add(src)

    # W_out: nodes in W_gates whose output is consumed outside W_gates or is a PO
    fanout = aig.compute_fanout()
    for g in W_gates:
        consumers = fanout.get(g, [])
        is_po = g in aig.outputs
        consumed_outside = any(c not in W_gates for c in consumers)
        if is_po or consumed_outside:
            W_out.add(g)

    return W_in, W_out


# ── SAT Encoder ───────────────────────────────────────────────────────

def build_window_cnf(I, O, care_list, k):
    """Build CNF for a window with I inputs, O outputs, k AND gates.

    care_list: list of (in_pattern_tuple, allowed_out_patterns_set).
    Returns (clauses, nvars, sig, gate_inputs_all, out_info, available_out).
    """
    C = len(care_list)
    next_var = 1
    clauses = []

    def new_var():
        nonlocal next_var
        v = next_var
        next_var += 1
        return v

    sig = [[new_var() for _ in range(C)] for _ in range(k)]

    gate_inputs_all = []
    for g in range(k):
        available = ["const0"] + [f"in{i}" for i in range(I)] + [
            f"g{i}" for i in range(g)
        ]
        gate_inputs = []
        for input_num in range(2):
            selectors = [new_var() for _ in available]
            inv = new_var()
            selected = [new_var() for _ in range(C)]

            # At-least-one
            clauses.append(selectors)
            # At-most-one (pairwise)
            for i in range(len(selectors)):
                for j in range(i + 1, len(selectors)):
                    clauses.append([-selectors[i], -selectors[j]])

            for si, source in enumerate(available):
                sel = selectors[si]
                for t, (in_pat, _) in enumerate(care_list):
                    a = selected[t]
                    if source == "const0":
                        clauses.append([-sel, -inv, a])
                        clauses.append([-sel, inv, -a])
                    elif source.startswith("in"):
                        bit = int(source[2:])
                        value = in_pat[bit]
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

        # Symmetry breaking: source(input0) <= source(input1)
        sel0_vars = []
        sel1_vars = []
        for input_num in range(2):
            available = ["const0"] + [f"in{i}" for i in range(I)] + [
                f"g{i}" for i in range(g)
            ]
            # We need the actual selector variables — they were created above
            # Reconstruct: the selectors were created in order for each input_num
            # Actually we need to track them. Let's use a different approach.
            pass

        # Gate output: sig[g][t] = gate_sel[g][0][t] AND gate_sel[g][1][t]
        a, b = gate_inputs
        for t in range(C):
            z = sig[g][t]
            clauses.append([-z, a[t]])
            clauses.append([-z, b[t]])
            clauses.append([z, -a[t], -b[t]])

        gate_inputs_all.append(gate_inputs)

    # Output encoding
    available_out = ["const0"] + [f"in{i}" for i in range(I)] + [
        f"g{i}" for i in range(k)
    ]
    out_info = []
    for j in range(O):
        selectors = [new_var() for _ in available_out]
        inv = new_var()

        # At-least-one
        clauses.append(selectors)
        # At-most-one
        for i in range(len(selectors)):
            for si in range(i + 1, len(selectors)):
                clauses.append([-selectors[i], -selectors[si]])

        for si, source in enumerate(available_out):
            sel = selectors[si]
            for t, (in_pat, allowed_outs) in enumerate(care_list):
                # out_val[j][t] auxiliary variable
                pass  # handled below

        out_info.append((selectors, inv))

    # Output value + ODC constraints
    # For each output j, care point t: out_val[j][t] is the actual output value
    out_val = [[new_var() for _ in range(C)] for _ in range(O)]

    for j in range(O):
        selectors, inv = out_info[j]
        for si, source in enumerate(available_out):
            sel = selectors[si]
            for t, (in_pat, allowed_outs) in enumerate(care_list):
                ov = out_val[j][t]
                if source == "const0":
                    # sel AND inv => ov=1; sel AND ~inv => ov=0
                    clauses.append([-sel, -inv, ov])
                    clauses.append([-sel, inv, -ov])
                elif source.startswith("in"):
                    bit = int(source[2:])
                    value = in_pat[bit]
                    if value == 0:
                        clauses.append([-sel, -inv, ov])
                        clauses.append([-sel, inv, -ov])
                    else:
                        clauses.append([-sel, -inv, -ov])
                        clauses.append([-sel, inv, ov])
                else:
                    pg = int(source[1:])
                    v = sig[pg][t]
                    # ov = v XOR inv
                    # If inv=0: ov=v; If inv=1: ov=~v
                    # Clause: sel => (ov == v XOR inv)
                    # Expand: 4 clauses for the 2x2 cases
                    clauses.append([-sel, -v, -inv, -ov])
                    clauses.append([-sel, v, inv, -ov])
                    clauses.append([-sel, -v, inv, ov])
                    clauses.append([-sel, v, -inv, ov])

    # ODC disallowed pattern constraints
    for t, (in_pat, allowed_outs) in enumerate(care_list):
        all_patterns = set()
        for o in range(1 << O):
            p = tuple((o >> j) & 1 for j in range(O))
            all_patterns.add(p)
        disallowed = all_patterns - allowed_outs
        for p in disallowed:
            # Not all output bits simultaneously match p
            clause = []
            for j in range(O):
                ov = out_val[j][t]
                if p[j] == 0:
                    clause.append(ov)   # ~out_val[j] means out_val[j] must be 0, so we negate: need ov to NOT be 0 => use ~ov
                else:
                    clause.append(-ov)
            clauses.append(clause)

    return clauses, next_var - 1, sig, gate_inputs_all, out_info, available_out, out_val


# ── Decoder ───────────────────────────────────────────────────────────

def decode_window_model(model, I, O, k, care_list, sig, gate_inputs_all, out_info, available_out):
    """Extract gate and output definitions from SAT model.

    Returns (gates, outputs) where:
    - gates: list of (src1, inv1, src2, inv2) for each of k AND gates
    - outputs: list of (src, inv) for each of O outputs
    """
    model_set = set(model)

    def is_true(v):
        return v in model_set

    gates = []
    for g in range(k):
        src1 = src2 = None
        inv1 = inv2 = False

        for input_num in range(2):
            available = ["const0"] + [f"in{i}" for i in range(I)] + [
                f"g{i}" for i in range(g)
            ]
            # Find which source is selected
            # We need to reconstruct the variable assignments
            # The selectors were created sequentially in build_window_cnf
            # We need to figure out which variable corresponds to what
            # This requires knowing the variable numbering

            # Actually, we need to pass the variable info through
            # For now, let's use a simpler approach: check the model
            # against the care list to determine what each gate does
            pass

        gates.append((src1, inv1, src2, inv2))

    outputs = []
    for j in range(O):
        src = None
        inv = False
        outputs.append((src, inv))

    return gates, outputs


def decode_window_model_v2(model, I, O, k, care_list, sig, gate_inputs_all, out_info, available_out, next_var_start):
    """Decode SAT model by inspecting selector variable assignments."""
    model_set = set(model)
    is_true = lambda v: v in model_set

    gates = []
    for g in range(k):
        available = ["const0"] + [f"in{i}" for i in range(I)] + [
            f"g{i}" for i in range(g)
        ]
        gate_def = []
        for input_num in range(2):
            src_name = None
            inv_val = False
            # The selectors for this gate/input_num were created as a block
            # We need to find them by checking the model
            for si, source in enumerate(available):
                # Variable numbering: we need to know which var is selectors[si]
                # This is tricky without tracking. Let's use a different approach.
                pass
            gate_def.append((src_name, inv_val))
        gates.append(gate_def)

    return gates


# ── Better approach: track variables during encoding ──────────────────

def build_window_cnf_tracked(I, O, care_list, k):
    """Build CNF with full variable tracking for decoding."""
    C = len(care_list)
    next_var = 1
    clauses = []

    def new_var():
        nonlocal next_var
        v = next_var
        next_var += 1
        return v

    sig = [[new_var() for _ in range(C)] for _ in range(k)]

    # Track gate selectors: gate_sel[g][input_num] = list of (source_name, sel_var)
    # Track gate inversions: gate_inv[g][input_num] = inv_var
    gate_sel = [[[] for _ in range(2)] for _ in range(k)]
    gate_inv = [[None for _ in range(2)] for _ in range(k)]
    gate_selected = [[None for _ in range(2)] for _ in range(k)]

    for g in range(k):
        available = ["const0"] + [f"in{i}" for i in range(I)] + [
            f"g{i}" for i in range(g)
        ]
        for input_num in range(2):
            selectors = [new_var() for _ in available]
            inv = new_var()
            selected = [new_var() for _ in range(C)]

            gate_sel[g][input_num] = list(zip(available, selectors))
            gate_inv[g][input_num] = inv
            gate_selected[g][input_num] = selected

            clauses.append(selectors)
            for i in range(len(selectors)):
                for j in range(i + 1, len(selectors)):
                    clauses.append([-selectors[i], -selectors[j]])

            for si, source in enumerate(available):
                sel = selectors[si]
                for t, (in_pat, _) in enumerate(care_list):
                    a = selected[t]
                    if source == "const0":
                        clauses.append([-sel, -inv, a])
                        clauses.append([-sel, inv, -a])
                    elif source.startswith("in"):
                        bit = int(source[2:])
                        value = in_pat[bit]
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

        # Symmetry breaking
        sel0 = [s for _, s in gate_sel[g][0]]
        sel1 = [s for _, s in gate_sel[g][1]]
        for i in range(len(sel0)):
            for j in range(i):
                clauses.append([-sel0[i], -sel1[j]])

        # Gate output
        a, b = gate_selected[g]
        for t in range(C):
            z = sig[g][t]
            clauses.append([-z, a[t]])
            clauses.append([-z, b[t]])
            clauses.append([z, -a[t], -b[t]])

    # Output encoding
    available_out = ["const0"] + [f"in{i}" for i in range(I)] + [
        f"g{i}" for i in range(k)
    ]
    out_sel = []
    out_inv_vars = []
    for j in range(O):
        selectors = [new_var() for _ in available_out]
        inv = new_var()
        out_sel.append(list(zip(available_out, selectors)))
        out_inv_vars.append(inv)

        clauses.append(selectors)
        for i in range(len(selectors)):
            for si in range(i + 1, len(selectors)):
                clauses.append([-selectors[i], -selectors[si]])

    # Output value + ODC constraints
    out_val = [[new_var() for _ in range(C)] for _ in range(O)]

    for j in range(O):
        for si, source in enumerate(available_out):
            sel = out_sel[j][si][1]
            inv = out_inv_vars[j]
            for t, (in_pat, _) in enumerate(care_list):
                ov = out_val[j][t]
                if source == "const0":
                    clauses.append([-sel, -inv, ov])
                    clauses.append([-sel, inv, -ov])
                elif source.startswith("in"):
                    bit = int(source[2:])
                    value = in_pat[bit]
                    if value == 0:
                        clauses.append([-sel, -inv, ov])
                        clauses.append([-sel, inv, -ov])
                    else:
                        clauses.append([-sel, -inv, -ov])
                        clauses.append([-sel, inv, ov])
                else:
                    pg = int(source[1:])
                    v = sig[pg][t]
                    clauses.append([-sel, -v, -inv, -ov])
                    clauses.append([-sel, v, inv, -ov])
                    clauses.append([-sel, -v, inv, ov])
                    clauses.append([-sel, v, -inv, ov])

    # ODC disallowed pattern constraints
    for t, (in_pat, allowed_outs) in enumerate(care_list):
        all_patterns = set()
        for o in range(1 << O):
            p = tuple((o >> j) & 1 for j in range(O))
            all_patterns.add(p)
        disallowed = all_patterns - allowed_outs
        for p in disallowed:
            clause = []
            for j in range(O):
                ov = out_val[j][t]
                if p[j] == 0:
                    clause.append(ov)
                else:
                    clause.append(-ov)
            clauses.append(clause)

    tracking = {
        'gate_sel': gate_sel,
        'gate_inv': gate_inv,
        'out_sel': out_sel,
        'out_inv': out_inv_vars,
        'sig': sig,
        'available_out': available_out,
    }
    return clauses, next_var - 1, tracking


def decode_model(model, I, O, k, tracking):
    """Decode SAT model using tracked variables."""
    model_set = set(model)

    gates = []
    for g in range(k):
        gate_def = []
        for input_num in range(2):
            src_name = None
            for source_name, sel_var in tracking['gate_sel'][g][input_num]:
                if sel_var in model_set:
                    src_name = source_name
                    break
            inv_var = tracking['gate_inv'][g][input_num]
            inv_val = inv_var in model_set
            gate_def.append((src_name, inv_val))
        gates.append(gate_def)

    outputs = []
    for j in range(O):
        src_name = None
        for source_name, sel_var in tracking['out_sel'][j]:
            if sel_var in model_set:
                src_name = source_name
                break
        inv_var = tracking['out_inv'][j]
        inv_val = inv_var in model_set
        outputs.append((src_name, inv_val))

    return gates, outputs


# ── Splice Window ─────────────────────────────────────────────────────

def source_to_node(source, W_in_list, prefix=""):
    """Convert a source name to a node reference."""
    if source == "const0":
        return None  # handled specially
    elif source.startswith("in"):
        return W_in_list[int(source[2:])]
    elif source.startswith("g"):
        return f"{prefix}_g{source[1:]}"
    return source


def splice_window(aig, W_in, W_out, W_gates, gates, outputs, prefix):
    """Replace window gates with new SAT-synthesized gates.

    gates: list of (src1, inv1, src2, inv2) for each internal gate
    outputs: list of (src, inv) for each W_out node
    """
    W_in_list = list(W_in)  # Already sorted by select_window

    # Remove old window gates
    for g in W_gates:
        if g in aig.nodes:
            del aig.nodes[g]

    # Add new internal gates
    for i, (src1_def, src2_def) in enumerate(gates):
        node_name = f"{prefix}_g{i}"
        s1_name = source_to_node(src1_def[0], W_in_list, prefix)
        s2_name = source_to_node(src2_def[0], W_in_list, prefix)

        if s1_name is None:
            s1_name = "__const0__"
            aig.nodes[s1_name] = ('CONST0', [])
        if s2_name is None:
            s2_name = "__const0__"
            if "__const0__" not in aig.nodes:
                aig.nodes["__const0__"] = ('CONST0', [])

        aig.nodes[node_name] = ('AND', [
            s1_name, src1_def[1],
            s2_name, src2_def[1],
            False
        ])

    # Rewrite W_out nodes
    for j, out_node in enumerate(W_out):
        src_name, inv = outputs[j]
        if src_name is None:
            aig.nodes[out_node] = ('CONST0', [])
        elif source_to_node(src_name, W_in_list, prefix) is None:
            # const0 source
            if inv:
                aig.nodes[out_node] = ('CONST1', [])
            else:
                aig.nodes[out_node] = ('CONST0', [])
        else:
            resolved = source_to_node(src_name, W_in_list, prefix)
            if inv:
                aig.nodes[out_node] = ('NOT', [resolved])
            else:
                aig.nodes[out_node] = ('BUF', [resolved])


# ── Verification ──────────────────────────────────────────────────────

def verify_circuit(aig, care_points, N):
    """Simulate and check all care points. Returns (correct, total).
    
    BLIF convention: p5 = bit 5 (MSB), p0 = bit 0 (LSB).
    """
    correct = 0
    for x, p, q in care_points:
        input_vals = {f"x{i}": (x >> i) & 1 for i in range(N)}
        values = aig.simulate(input_vals)

        ok = True
        for i in range(N):
            if values.get(f"p{i}") != ((p >> i) & 1):
                ok = False
                break
            if values.get(f"q{i}") != ((q >> i) & 1):
                ok = False
                break
        if ok:
            correct += 1
    return correct, len(care_points)


def count_and_gates(aig):
    return sum(1 for _, (typ, _) in aig.nodes.items() if typ == 'AND')


# ── Main Optimization Loop ───────────────────────────────────────────

def enumerate_care(N):
    """Returns list of (input_val, p, q) for all N-bit semiprimes."""
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
    return care


def optimize_circuit(aig, care_points, N, num_iterations=200, seed=42,
                     max_inputs=6, max_outputs=3, max_gates=15, verbose=True,
                     use_odc=True):
    """Main optimization loop."""
    random.seed(seed)
    initial_gates = count_and_gates(aig)
    best_gates = initial_gates
    total_improvements = 0

    print(f"Initial circuit: {initial_gates} AND gates, {len(care_points)} care points")

    for iteration in range(num_iterations):
        # Select random window
        result = select_window(aig, max_inputs, max_outputs, max_gates)
        if result is None:
            if verbose:
                print(f"  [{iteration}] No valid window found, skipping")
            continue

        W_in, W_out, W_gates = result
        old_gate_count = len(W_gates)

        # Compute ODC care set
        care_set = get_window_care_set(aig, W_in, W_out, W_gates, care_points, N, use_odc=use_odc)
        care_list = [(in_pat, allowed) for in_pat, allowed in care_set.items()]

        if not care_list:
            continue

        I = len(W_in)
        O = len(W_out)

        # Try to find smaller replacement
        found_better = False
        for k in range(0, old_gate_count):
            clauses, nvars, tracking = build_window_cnf_tracked(I, O, care_list, k)
            nclauses = len(clauses)

            s = Solver(name="cd153")
            for cl in clauses:
                s.add_clause(cl)

            # Use budget-based solving
            budget = 5000
            t0 = time.time()
            result_sat = None
            while True:
                s.conf_budget(budget)
                outcome = s.solve_limited()
                dt = time.time() - t0
                if outcome is not None:
                    result_sat = outcome
                    break
                if dt > 10:
                    break

            if result_sat:
                model = s.get_model()
                s.delete()

                # Decode and splice
                gates, outputs = decode_model(model, I, O, k, tracking)
                prefix = f"win_{iteration}"
                saved_aig = aig.clone()
                splice_window(aig, W_in, W_out, W_gates, gates, outputs, prefix)
                aig.prune()  # Remove disconnected nodes

                # Quick cycle check
                if aig.has_cycle():
                    aig.nodes = saved_aig.nodes
                    aig.inputs = saved_aig.inputs
                    aig.outputs = saved_aig.outputs
                    if verbose:
                        print(f"  [{iteration}] Cycle detected after splice, reverting")
                    continue

                # Verify
                correct, total = verify_circuit(aig, care_points, N)
                if correct == total:
                    new_gates = count_and_gates(aig)
                    improvement = old_gate_count - k
                    total_improvements += 1
                    if verbose:
                        print(f"  [{iteration}] Window: {I}in/{O}out/{old_gate_count}gates "
                              f"-> {k} gates (saved {improvement}), "
                              f"total: {new_gates} AND gates")
                    found_better = True
                    best_gates = min(best_gates, new_gates)
                    break
                else:
                    # Revert: restore the clone
                    aig.nodes = saved_aig.nodes
                    aig.inputs = saved_aig.inputs
                    aig.outputs = saved_aig.outputs
                    if verbose:
                        print(f"  [{iteration}] Verification failed for k={k} "
                              f"({correct}/{total} correct), reverting")
            else:
                s.delete()

        if iteration % 20 == 0 and iteration > 0:
            if verbose:
                print(f"  [{iteration}] Best: {best_gates} AND gates, "
                      f"{total_improvements} improvements so far")

    print(f"\nFinal: {best_gates} AND gates ({initial_gates - best_gates} saved, "
          f"{total_improvements} improvements)")
    return aig, True


# ── CLI ───────────────────────────────────────────────────────────────

def parse_flag(argv, flag, default=None):
    for i, arg in enumerate(argv):
        if arg == flag and i + 1 < len(argv):
            return argv[i + 1]
    return default


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <blif_file> [N] [num_iterations] [--seed S] [--max-in I] [--max-out O] [--max-gates G]")
        sys.exit(1)

    blif_path = sys.argv[1]
    N = int(sys.argv[2]) if len(sys.argv) > 2 and not sys.argv[2].startswith('-') else 6
    num_iterations = int(sys.argv[3]) if len(sys.argv) > 3 and not sys.argv[3].startswith('-') else 200

    seed = 42
    use_odc = True
    max_inputs = 6
    max_outputs = 3
    max_gates = 15
    for i, arg in enumerate(sys.argv):
        if arg == '--seed' and i + 1 < len(sys.argv):
            seed = int(sys.argv[i + 1])
        if arg in ('--sdc', '--no-odc'):
            use_odc = False
        if arg == '--max-in' and i + 1 < len(sys.argv):
            max_inputs = int(sys.argv[i + 1])
        if arg == '--max-out' and i + 1 < len(sys.argv):
            max_outputs = int(sys.argv[i + 1])
        if arg == '--max-gates' and i + 1 < len(sys.argv):
            max_gates = int(sys.argv[i + 1])

    print(f"Loading {blif_path}...")
    aig = parse_blif(blif_path)
    print(f"  Inputs: {aig.inputs}")
    print(f"  Outputs: {aig.outputs}")
    print(f"  Nodes: {len(aig.nodes)}")
    print(f"  AND gates: {count_and_gates(aig)}")

    care_points = enumerate_care(N)
    print(f"  Care points: {len(care_points)}")
    print(f"  Window params: max_inputs={max_inputs}, max_outputs={max_outputs}, max_gates={max_gates}")

    result_aig, success = optimize_circuit(
        aig, care_points, N,
        num_iterations=num_iterations,
        seed=seed,
        use_odc=use_odc,
        max_inputs=max_inputs,
        max_outputs=max_outputs,
        max_gates=max_gates
    )

    if success and result_aig is not None:
        out_path = blif_path.replace('.blif', '_opt.blif')
        result_aig.to_blif(out_path)
        print(f"\nOptimized circuit written to {out_path}")

        # Verify on care points (CEC checks ALL inputs, but we have don't-cares)
        correct, total = verify_circuit(result_aig, care_points, N)
        print(f"Care-point verification: {correct}/{total} correct")
        if correct == total:
            print("PASS: all care points satisfied")
        else:
            print("FAIL: some care points violated")
