#!/usr/bin/env python3
"""Give the two cut designs the same ports, so the miter can pair them.

usage: align_cuts.py <gold.cut.il> <gate.cut.il>   (both rewritten in place)

cutpoints.py creates a port only for each black-box pin a design actually connects. A pin one side
leaves open (an unused block output the RTL does not wire up, but the netlist ties to a no-connect net)
therefore exists on one side only. The missing side gets the same port unconnected: a free input for a
block output (harmless when unused, and a failed proof if the other side really reads it), an undriven
output for a block input (x on the gold side is a don't-care; on the gate side it fails the proof).
"""
import sys, re

def ports(path):
    out = {}
    for line in open(path):
        m = re.match(r"\s*wire width (\d+) (input|output) \d+ (\\bbo?\.\S+)$", line)
        if m: out[m.group(3)] = (int(m.group(1)), m.group(2))
    return out

def add(path, missing):
    lines = open(path).read().split("\n")
    idx = max((int(m.group(1)) for l in lines for m in [re.match(r"\s*wire .*\b(?:input|output|inout) (\d+) ", l)] if m), default=0)
    extra = []
    for k, (name, (w, d)) in enumerate(sorted(missing.items()), start=idx + 1):
        extra.append(f"  wire width {w} {d} {k} {name}")
    for i in range(len(lines) - 1, -1, -1):          # insert before the module's own end
        if lines[i].rstrip() == "end": lines[i:i] = extra; break
    open(path, "w").write("\n".join(lines))

a, b = sys.argv[1], sys.argv[2]
pa, pb = ports(a), ports(b)
add(a, {n: v for n, v in pb.items() if n not in pa})
add(b, {n: v for n, v in pa.items() if n not in pb})
diff = [n for n in pa if n in pb and pa[n] != pb[n]]
print(f"aligned: {len(pb) - len(set(pa) & set(pb))} ports added to gold, {len(pa) - len(set(pa) & set(pb))} to gate, {len(diff)} width/direction mismatches")
for n in diff[:5]: print("  mismatch", n, pa[n], pb[n])
