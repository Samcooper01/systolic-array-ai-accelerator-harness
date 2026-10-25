#!/usr/bin/env python3
"""Random-vector check of one equivalence partition the prover could not settle.

usage: vecsim.py <partition.aag> [vectors]

The partition's miter (equiv.py, the same one ABC is given: registers and black boxes already cut, so
its inputs are the design's inputs and every register's stored value) is combinational, with one output
that is 1 when gold and gate differ. This evaluates it on random input vectors, 65,536 at a time as
the bits of Python integers. Because the registers are inputs, every register state is reached directly;
nothing depends on a reset sequence driving the design into it.
Rounds alternate uniform random inputs with sparse and dense ones (each input mostly 0, or mostly 1), which
reach the carry chains and wide comparisons that uniform values rarely exercise.
Prints "vecsim: PASS <n> vectors" or "vecsim: FAIL ..."; it is evidence, not a proof.
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

aag = sys.argv[1]
TOTAL = int(sys.argv[2]) if len(sys.argv) > 2 else 2_000_000
W = 65536; MASK = (1 << W) - 1
rng = random.Random(3)

lines = open(aag).read().split("\n")
m, i, l, o = map(int, lines[0].split()[1:5])
if l: sys.exit(f"vecsim: {aag} has {l} latches; expected a combinational miter")
if o < 1: sys.exit("vecsim: the miter has no output")
ins = [int(lines[1 + j]) >> 1 for j in range(i)]
outs = [int(lines[1 + i + j]) for j in range(o)]
ands = topo([tuple(map(int, t.split())) for t in lines[1 + i + o:] if re.match(r"^\d+ \d+ \d+$", t)])

val = [0] * (m + 1)
def lit(x):
    v = val[x >> 1]
    return v ^ MASK if x & 1 else v
rounds = max(3, -(-TOTAL // W))
for r in range(rounds):
    kind = r % 3
    for v in ins:
        a = rng.getrandbits(W)
        if kind == 1: a &= rng.getrandbits(W) & rng.getrandbits(W)            # mostly 0
        elif kind == 2: a |= rng.getrandbits(W) | rng.getrandbits(W)          # mostly 1
        val[v] = a
    for lhs, r0, r1 in ands: val[lhs >> 1] = lit(r0) & lit(r1)
    bad = 0
    for x in outs: bad |= lit(x)
    if bad:
        print(f"vecsim: FAIL gold and gate differ (round {r}, {bin(bad).count('1')} of {W} vectors)")
        sys.exit(0)
print(f"vecsim: PASS {rounds * W} vectors, {i} inputs, {len(ands)} gates")
