#!/usr/bin/env python3
"""Cut black-box instances out of a flattened RTLIL module, for a hierarchical equivalence proof.

usage: cutpoints.py <in.il> <out.il> <ports.tsv>

ports.tsv lists every black-box module's ports: "module<TAB>port<TAB>input|output<TAB>width".
Each black-box cell is removed. Its output ports become new module inputs named
"bb.<instance>.<port>" (so gold and gate see the same free value), and its input ports become new module
outputs named "bbo.<instance>.<port>" (so the miter compares what each design feeds the box). Instance
names are normalized ("/" becomes ".", escapes dropped) so the two designs' names line up.
"""
import sys, re

src, dst, ports_path = sys.argv[1:4]
ports = {}
for line in open(ports_path):
    m, p, d, w = line.rstrip("\n").split("\t"); ports.setdefault(m, {})[p] = (d, int(w))

def sig_width(sig, wires):
    """Width of an RTLIL sigspec: wires, bit and range selects, constants, and { } concatenations."""
    sig = sig.strip()
    if sig.startswith("{"):
        inner = sig[1:sig.rindex("}")]
        return sum(sig_width(t, wires) for t in re.findall(r"\S+ \[\d+(?::\d+)?\]|\{[^}]*\}|\S+", inner))
    m = re.match(r"^(\d+)'[01xzm-]*$", sig)
    if m: return int(m.group(1))
    m = re.match(r"^(\S+) \[(\d+)(?::(\d+))?\]$", sig)
    if m: return abs(int(m.group(2)) - int(m.group(3))) + 1 if m.group(3) else 1
    return wires.get(sig, 1)

def norm(name):
    return name.lstrip("\\").replace("\\", "").replace("/", ".")

lines = open(src).read().split("\n")
out, pend_attr = [], []
new_ports, new_conns = [], []
i = 0; in_module = False; max_port = 0; wires = {}
while i < len(lines):
    line = lines[i]; s = line.strip()
    if s.startswith("module "): in_module = True
    if in_module:
        m = re.match(r"wire .*\b(?:input|output|inout) (\d+)\b", s)
        if m: max_port = max(max_port, int(m.group(1)))
        m = re.match(r"wire (?:width (\d+) )?.*?(\S+)$", s)
        if m and s.startswith("wire"): wires[m.group(2)] = int(m.group(1) or 1)
    if s.startswith("attribute "):
        pend_attr.append(line); i += 1; continue
    m = re.match(r"cell (\S+) (\S+)$", s)
    if m and m.group(1).lstrip("\\") in ports:
        typ, inst = m.group(1).lstrip("\\"), norm(m.group(2))
        i += 1
        while lines[i].strip() != "end":
            c = re.match(r"\s*connect (\S+) (.*)$", lines[i])
            if c:
                p = c.group(1).lstrip("\\"); sig = c.group(2)
                d, _ = ports[typ].get(p, ("input", 1)); w = sig_width(sig, wires)
                if d == "output":
                    nm = f"\\bb.{inst}.{p}"; new_ports.append((nm, w, "input")); new_conns.append(f"  connect {sig} {nm}")
                else:
                    nm = f"\\bbo.{inst}.{p}"; new_ports.append((nm, w, "output")); new_conns.append(f"  connect {nm} {sig}")
            i += 1
        i += 1; pend_attr = []; continue          # drop the cell and its attributes
    if line.rstrip() == "end" and in_module:        # the module's own end (cell and process ends are indented)
        for k, (nm, w, d) in enumerate(new_ports, start=max_port + 1):
            out.append(f"  wire width {w} {d} {k} {nm}")
        out.extend(new_conns)
        new_ports, new_conns = [], []; in_module = False
    out.extend(pend_attr); pend_attr = []
    out.append(line); i += 1
open(dst, "w").write("\n".join(out))
