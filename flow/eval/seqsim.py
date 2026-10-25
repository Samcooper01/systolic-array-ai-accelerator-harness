#!/usr/bin/env python3
"""Sequential random simulation of a gold/gate miter, from reset: the equivalence gate's second tier.

usage: seqsim.py <miter.aag> <miter.map> [cycles] [traces] [reset_cycles]

The miter (equiv.py: Yosys miter -equiv -make_outputs of the gold and gate designs, black boxes cut as
in the formal check, registers kept, written with write_aiger -zinit) starts with every register at 0
(the netlist flip-flops are modelled storing Q, so 0 means the same on both sides). Each cycle every
input gets a fresh random value, except "reset", which is held at 1 for the first reset_cycles cycles
and 0 after; that many traces run at once, as the bits of Python integers. From the first cycle after
reset, the miter's "trigger" output must stay 0: any gold output that differs from its gate output is a
difference in function.
Prints "seqsim: PASS ..." or "seqsim: FAIL ..." with the first differing outputs, the cycle and the trace.
"""
import random, re, sys

def topo(ands):
    """AND gates in dependency order (ASCII AIGER does not require the file order to be one)."""
    by = {lhs >> 1: (lhs, r0, r1) for lhs, r0, r1 in ands}
    done, order = set(), []
    for root in by:
        if root in done: continue
        stack = [(root, False)]
        while stack:
            v, expanded = stack.pop()
            if v in done or v not in by: continue
            if expanded: done.add(v); order.append(by[v]); continue
            stack.append((v, True))
            for r in by[v][1:]:
                if (r >> 1) in by and (r >> 1) not in done: stack.append((r >> 1, False))
    return order

aag, mapf = sys.argv[1:3]
CYCLES = int(sys.argv[3]) if len(sys.argv) > 3 else 200
W = int(sys.argv[4]) if len(sys.argv) > 4 else 4096
RESET = int(sys.argv[5]) if len(sys.argv) > 5 else 5
MASK = (1 << W) - 1
rng = random.Random(2)

lines = open(aag).read().split("\n")
m, i, l, o = map(int, lines[0].split()[1:5])
ins = [int(lines[1 + j]) >> 1 for j in range(i)]
latches = []
for j in range(l):
    f = lines[1 + i + j].split()
    latches.append((int(f[0]) >> 1, int(f[1]), int(f[2]) if len(f) > 2 else 0))
outs = [int(lines[1 + i + l + j]) for j in range(o)]
ands = [tuple(map(int, t.split())) for t in lines[1 + i + l + o:] if re.match(r"^\d+ \d+ \d+$", t)]
ands = topo(ands)
nin, nout = {}, {}
for line in open(mapf):
    f = line.split()
    if len(f) >= 4 and f[0] == "input": nin[int(f[1])] = f[3].lstrip("\\")
    if len(f) >= 4 and f[0] == "output": nout[int(f[1])] = (f[3].lstrip("\\"), int(f[2]))
if any(init not in (0,) for _, _, init in latches):
    sys.exit("seqsim: expected every register to start at 0 (write_aiger -zinit)")
reset_in = {j for j, n in nin.items() if n == "in_reset" or n == "reset"}
trig = [j for j, (n, b) in nout.items() if n == "trigger"]
if not trig: sys.exit("seqsim: the miter has no trigger output")
if not reset_in: print("seqsim: note: no reset input found; comparing from the first cycle")

val = [0] * (m + 1)
def lit(x):
    v = val[x >> 1]
    return v ^ MASK if x & 1 else v
for cyc in range(CYCLES):
    for j, v in enumerate(ins):
        val[v] = (MASK if cyc < RESET else 0) if j in reset_in else rng.getrandbits(W)
    for lhs, r0, r1 in ands: val[lhs >> 1] = lit(r0) & lit(r1)
    if cyc >= RESET or not reset_in:
        t = lit(outs[trig[0]])
        if t:
            trace = (t & -t).bit_length() - 1
            pairs = {}
            for j, (n, b) in nout.items():
                mm = re.match(r"^(gold|gate)_(.*)$", n)
                if mm: pairs.setdefault((mm.group(2), b), {})[mm.group(1)] = (lit(outs[j]) >> trace) & 1
            diff = [f"{n}[{b}]" for (n, b), s in sorted(pairs.items()) if len(s) == 2 and s["gold"] != s["gate"]]
            print(f"seqsim: FAIL at cycle {cyc} (trace {trace} of {W}): {len(diff)} outputs differ, e.g. {', '.join(diff[:8])}")
            sys.exit(0)
    nxt = [lit(nx) for _, nx, _ in latches]
    for (q, _, _), v in zip(latches, nxt): val[q] = v
print(f"seqsim: PASS {W} random traces x {CYCLES} cycles after {RESET if reset_in else 0} reset cycles, no output differs")
