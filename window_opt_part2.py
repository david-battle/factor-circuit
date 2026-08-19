    def toposort(self):
        visited = set()
        order = []
        def visit(n):
            if n in visited: return
            visited.add(n)
            typ, args = self.nodes[n]
            if typ in ('BUF', 'NOT'):
                visit(args[0])
            elif typ in ('AND', 'XOR', 'XNOR'):
                visit(args[0])
                visit(args[2] if typ == 'AND' else args[1])
            order.append(n)
        for out in self.outputs:
            visit(out)
        return order

    def to_blif(self, filepath):
        with open(filepath, 'w') as f:
            f.write(f".model factor\n")
            f.write(f".inputs {' '.join(self.inputs)}\n")
            f.write(f".outputs {' '.join(self.outputs)}\n")
            for node in self.toposort():
                if node in self.inputs: continue
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
                elif typ == 'XOR':
                    f.write(f".names {args[0]} {args[1]} {node}\n01 1\n10 1\n")
                elif typ == 'XNOR':
                    f.write(f".names {args[0]} {args[1]} {node}\n00 1\n11 1\n")
            f.write(".end\n")

def get_window_care_set(aig, W_in, W_out, care_points, N):
    """
    Extracts ODC care set for a window.
    care_points is a list of (x, p, q).
    Returns a dict: tuple(W_in_vals) -> set of tuple(W_out_vals)
    """
    topo = aig.toposort()
    # Find all nodes that depend on W_out
    depends_on = {n: False for n in aig.nodes}
    for n in W_out:
        depends_on[n] = True
    
    for n in topo:
        if n in aig.inputs or n in W_out:
            continue
        typ, args = aig.nodes[n]
        if typ in ('BUF', 'NOT') and depends_on[args[0]]:
            depends_on[n] = True
        elif typ in ('AND', 'XOR', 'XNOR') and (depends_on[args[0]] or depends_on[args[2] if typ=='AND' else args[1]]):
            depends_on[n] = True

    eval_order = [n for n in topo if depends_on[n] and n not in W_out]
    
    care_set = defaultdict(set)
    for (x, p, q) in care_points:
        input_vals = {f"x{i}": (x >> i) & 1 for i in range(N)}
        # Baseline simulation
        base_vals = aig.simulate(input_vals)
        
        in_pattern = tuple(base_vals[n] for n in W_in)
        
        # Required outputs for this care point
        req = {}
        for i in range(N):
            req[f"p{i}"] = (p >> i) & 1
            req[f"q{i}"] = (q >> i) & 1
            
        # Try all 2^|W_out| combinations
        O_size = len(W_out)
        for i in range(1 << O_size):
            out_pattern = tuple((i >> j) & 1 for j in range(O_size))
            
            # Fast re-simulate the dependent cone
            test_vals = base_vals.copy()
            for j, out_node in enumerate(W_out):
                test_vals[out_node] = out_pattern[j]
                
            for n in eval_order:
                # Remove cached val so eval_node recomputes
                if n in test_vals:
                    del test_vals[n]
                aig.eval_node(n, test_vals)
                
            # Check if global outputs still match
            ok = True
            for out_node, required_val in req.items():
                if out_node in aig.outputs and test_vals[out_node] != required_val:
                    ok = False
                    break
            
            if ok:
                care_set[in_pattern].add(out_pattern)
                
    return care_set
