#!/usr/bin/env python3
"""Pair every netlist flip-flop with an RTL register bit, and cut both out of the proof.

usage: regcut.py <gold.il> <gate.il> <gold_out.il> <gate_out.il>
                 [--probe <gold_probe.il> <gate_probe.il> <table.tsv>] [--hints <hints.tsv>]

Synthesis keeps register names: the netlist flip-flop "spad/vsm/pipe/b_index[3]$_DFFE_PP_" (flattened, its
stored value is the wire "\\spad/vsm/pipe/b_index[3]$_DFFE_PP_.Q") holds bit 3 of the RTL register
spad.vsm.pipe.b_index. Each pair is cut the way cutpoints.py cuts a black box: both flip-flops are
removed, their stored values become one shared free input "rq.<register bit>", and their next values
become compared outputs "rd.<register bit>". With every register cut, what remains on each side is
combinational, so the proof needs no initial state: for every value of the registers and the inputs, the
two designs must compute the same outputs and the same next register values. That is equivalence from
any common starting state, and it holds cycle after cycle by induction on the clock.

Pairing: by name (through any public name the RTL register bit carries); a netlist flip-flop whose
next-value net is a paired flip-flop's is that register's copy (stock ORFS Yosys clones registers to
split load). Names are not always right or enough (synthesis renumbers the columns of a narrowed memory,
keeps copies under other names, merges registers the RTL keeps apart), so the pairing can be revised by
hints from regsim.py, which simulates both sides: "unpair <gate>", "pair <gold> <gate> <inv>" (a netlist
flip-flop holding an RTL register bit, or its inverse), and "gold <gold> copy|inv|const <arg>" (an RTL
register bit synthesis merged into another, or found constant). Every pairing and relation becomes
compared outputs, so the proof checks it: a wrong hint can make the proof fail, never pass.
Any flip-flop still without a partner, on either side, becomes a free input of its own ("uq.gold.<n>",
"uq.gate.<n>"), shared with nothing, so the proof only succeeds if nothing depends on it.

Both inputs must be flattened, with enables and resets already turned into logic (dffunmap).
Prints "regcut: ..." and exits 1 only on an unsupported flip-flop type (latches, asynchronous controls).
"""
import re, sys

WIRE = re.compile(r"^\s*wire ((?:width \d+ |input \d+ |output \d+ |inout \d+ |upto |signed |offset -?\d+ )*)(\\\S+|\$\S+)$")

def parse(path):
    """Module lines, wire widths, module-level connections, and flip-flop cells of a one-module RTLIL file."""
    lines = open(path).read().split("\n")
    wires, conns, cells, max_port = {}, [], [], 0
    i = 0
    while i < len(lines):
        s = lines[i].strip()
        m = WIRE.match(lines[i])
        if m:
            opts = m.group(1)
            if "upto" in opts or re.search(r"offset -?[1-9]", opts):
                sys.exit(f"regcut: wire {m.group(2)} uses upto/offset, not supported")
            w = re.search(r"width (\d+)", opts); wires[m.group(2)] = int(w.group(1)) if w else 1
            p = re.search(r"(?:input|output|inout) (\d+)", opts)
            if p: max_port = max(max_port, int(p.group(1)))
        elif lines[i].startswith("  connect "):
            a, b = split2(lines[i][len("  connect "):]); conns.append((a, b))
        elif lines[i].startswith("  cell "):
            typ, name = s.split()[1:3]; start = i
            while start > 0 and lines[start - 1].startswith("  attribute "): start -= 1
            params, ports = {}, {}
            i += 1
            while lines[i].strip() != "end":
                t = lines[i].strip()
                if t.startswith("parameter "):
                    _, k, v = t.split(None, 2); params[k] = v
                elif t.startswith("connect "):
                    k, v = t[len("connect "):].split(None, 1); ports[k] = v
                i += 1
            cells.append(dict(type=typ, name=name, params=params, ports=ports, span=(start, i)))
        i += 1
    return lines, wires, conns, cells, max_port

def split2(text):
    """Split 'lhs rhs' of an RTLIL connect into its two sigspecs."""
    toks = tokens(text); depth = 0
    for k, t in enumerate(toks):
        if t == "{": depth += 1
        elif t == "}": depth -= 1
        if depth == 0 and not (k + 1 < len(toks) and toks[k + 1].startswith("[")):
            return " ".join(toks[:k + 1]), " ".join(toks[k + 1:])
    raise ValueError(text)

def tokens(text):
    return text.split()

def bits(sig, wires):
    """The bits of a sigspec, least significant first: ('\\wire', index) or ('const', '0'|'1'|'x'|...)."""
    toks = tokens(sig); out = []
    def atom(k):
        t = toks[k]
        if t == "{":
            parts, k = [], k + 1
            while toks[k] != "}":
                b, k = atom(k); parts.append(b)
            return [x for p in reversed(parts) for x in p], k + 1
        m = re.match(r"^(\d+)'([01xzm-]*)$", t)
        if m: return [("const", c) for c in reversed(m.group(2))], k + 1
        if re.match(r"^-?\d+$", t): return [("const", c) for c in reversed(format(int(t) & 0xffffffff, "032b"))], k + 1
        name = t; k += 1
        if k < len(toks) and toks[k].startswith("["):
            r = toks[k][1:-1].split(":"); k += 1
            hi = int(r[0]); lo = int(r[1]) if len(r) > 1 else hi
            return [(name, j) for j in range(lo, hi + 1)], k
        return [(name, j) for j in range(wires[name])], k
    k = 0
    while k < len(toks):
        b, k = atom(k); out = b + out
    return out

def bitsig(b, wires):
    if b[0] == "const": return f"1'{b[1]}"
    return b[0] if wires[b[0]] == 1 else f"{b[0]} [{b[1]}]"

class Aliases:
    def __init__(self):
        self.parent = {}
    def find(self, x):
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]; x = self.parent[x]
        return x
    def union(self, a, b):
        self.parent[self.find(a)] = self.find(b)

def flops(path):
    """The flip-flop bits of a design: (Q bit, D bit, the names it goes by, cell index)."""
    lines, wires, conns, cells, max_port = parse(path)
    al = Aliases()
    for a, b in conns:
        for x, y in zip(bits(a, wires), bits(b, wires)): al.union(x, y)
    members = {}
    for w, n in wires.items():
        if w.startswith("\\"):
            for j in range(n): members.setdefault(al.find((w, j)), []).append((w, j))
    ffs, bad = [], []
    for ci, c in enumerate(cells):
        if c["type"] == "$_DFF_P_": q, d = c["ports"]["\\Q"], c["ports"]["\\D"]
        elif c["type"] == "$dff" and c["params"].get("\\CLK_POLARITY", "1").endswith("1"): q, d = c["ports"]["\\Q"], c["ports"]["\\D"]
        elif re.match(r"^\$(_?(S?DFF|DFFE|ADFF|ALDFF|DFFSR|DLATCH|SR|FF)|(s?dff|dffe|adff|aldff|dffsr|dlatch|sr|ff|aldffe|adffe|sdffe|sdffce|dffsre|dlatchsr|adlatch)\b)", c["type"]):
            bad.append(f"{c['type']} {c['name']}"); continue
        else: continue
        for qb, db in zip(bits(q, wires), bits(d, wires)):
            names = [f"{w}[{j}]" if wires[w] > 1 else w for w, j in members.get(al.find(qb), [])]
            ffs.append(dict(q=qb, d=db, names=names, cell=ci))
    for f in ffs: f["dnet"] = al.find(f["d"]) if f["d"][0] != "const" else f["d"]
    return dict(lines=lines, wires=wires, cells=cells, max_port=max_port, ffs=ffs, bad=bad)

def norm(name):
    return name.lstrip("\\").replace("\\", "").replace("/", ".")

def gate_key(names):
    """The RTL register bit a netlist flip-flop holds, from its stored-value wire '<path>[<bit>]$<suffix>.Q'."""
    for n in names:
        m = re.match(r"^(.*?)(\$[^.]*)?\.Q(\[0\])?$", n.lstrip("\\"))
        if m and m.group(2):
            return norm(m.group(1))
    for n in names:
        m = re.match(r"^(.*)\.Q(\[0\])?$", n.lstrip("\\"))
        if m: return norm(m.group(1))
    return None

def write(design, path, cuts, extra_ports):
    """Remove the paired flip-flop cells; add the rq inputs and rd outputs."""
    lines = design["lines"]; wires = design["wires"]
    drop = set()
    for ci in {f["cell"] for f in design["ffs"]}:
        a, b = design["cells"][ci]["span"]; drop.update(range(a, b + 1))
    out = [l for k, l in enumerate(lines) if k not in drop]
    end = max(k for k, l in enumerate(out) if l.rstrip() == "end")
    add, port = [], design["max_port"]
    for name, direction in extra_ports:
        port += 1; add.append(f"  wire {direction} {port} {name}")
    add.extend(cuts)
    out[end:end] = add
    open(path, "w").write("\n".join(privatize(out)))

def privatize(lines):
    """Leave the ports as the only public names, and drive every output through an internal net.

    eqy pairs the two designs at every net whose name matches and splits the proof there. Names inside
    the logic are not a promise that the nets are equal (synthesis reuses and renames them freely), so
    only the ports stay public: the design's ports and the register and black-box cut points. Outputs
    are driven through an internal net so that logic reading an output reads that net, not the port."""
    ports, rename, extra = {}, {}, []
    for l in lines:
        m = WIRE.match(l)
        if not m: continue
        opts, name = m.group(1), m.group(2)
        if not name.startswith("\\"): continue
        d = re.search(r"(input|output|inout) (\d+)", opts)
        if d is None: rename[name] = "$pub$" + name[1:]
        elif d.group(1) == "output":
            rename[name] = "$out$" + name[1:]; ports[name] = opts
    out = []
    for l in lines:
        m = WIRE.match(l)
        if m and m.group(2) in ports:
            w = re.search(r"width (\d+)", m.group(1))
            out.append(f"  wire {'width ' + w.group(1) + ' ' if w else ''}{rename[m.group(2)]}")
            extra += [f"  wire {m.group(1)}{m.group(2)}", f"  connect {m.group(2)} {rename[m.group(2)]}"]
            continue
        if l.lstrip().startswith("attribute "): out.append(l); continue
        out.append(re.sub(r"(?<![^\s{])(\\\S+)", lambda t: rename.get(t.group(1), t.group(1)), l))
    end = max(k for k, l in enumerate(out) if l.rstrip() == "end")
    out[end:end] = extra
    return out

def inverter(cuts, sig, tag):
    """Append a $not cell driven by sig; return its output wire."""
    y = f"$regcut$inv${tag}"
    cuts += [f"  wire {y}", f"  cell $not $regcut$not${tag}", "    parameter \\A_SIGNED 0", "    parameter \\A_WIDTH 1",
             "    parameter \\Y_WIDTH 1", f"    connect \\A {sig}", f"    connect \\Y {y}", "  end"]
    return y

def main():
    args = sys.argv[1:]
    probe = hints_path = None
    if "--probe" in args:
        i = args.index("--probe"); probe = args[i + 1:i + 4]; del args[i:i + 4]
    if "--hints" in args:
        i = args.index("--hints"); hints_path = args[i + 1]; del args[i:i + 2]
    gold_in, gate_in, gold_out, gate_out = args[:4]
    gold, gate = flops(gold_in), flops(gate_in)
    problems = [f"gold: unsupported flip-flop {b}" for b in gold["bad"]] + [f"gate: unsupported flip-flop {b}" for b in gate["bad"]]
    by_name = {}
    for gi, f in enumerate(gold["ffs"]):
        for n in f["names"]:
            by_name.setdefault(norm(n), gi)
            k = gate_key([n])                        # a golden side that is itself a netlist: same naming as the gate
            if k: by_name.setdefault(k, gi)
    pair = {}                                       # gate index -> (gold index, inverted)
    owner, rest = {}, []
    named = {}                                      # gate index -> its partner by name, kept for regsim.py
    for ti, f in enumerate(gate["ffs"]):
        key = gate_key(f["names"])
        gi = by_name.get(key) if key else None
        if gi is None: rest.append(ti); continue
        pair[ti] = (gi, False); owner.setdefault(f["dnet"], gi); named[ti] = gi
    for ti in rest:                                 # unnamed copies of a paired register
        gi = owner.get(gate["ffs"][ti]["dnet"])
        if gi is not None: pair[ti] = (gi, False)
    rel = {}                                        # gold index -> (copy|inv|const, arg)
    gconst = {}                                     # gate index -> constant it always holds
    changed = 0
    if hints_path:
        for line in open(hints_path):
            f = line.split()
            if not f: continue
            if f[0] == "unpair": pair.pop(int(f[1]), None); changed += 1
            elif f[0] == "pair": pair[int(f[2])] = (int(f[1]), f[3] == "1"); changed += 1
            elif f[0] == "gold": rel[int(f[1])] = (f[2], int(f[3])); changed += 1
            elif f[0] == "gate": gconst[int(f[1])] = int(f[3]); pair.pop(int(f[1]), None); changed += 1
            elif f[0] == "drop": (rel if f[1] == "gold" else gconst).pop(int(f[2]), None); changed += 1
    groups = {}
    for ti, (gi, inv) in sorted(pair.items()): groups.setdefault(gi, []).append((ti, inv))
    rel = {gi: r for gi, r in rel.items() if gi not in groups and (r[0] == "const" or r[1] in groups)}
    free_gold = [gi for gi in range(len(gold["ffs"])) if gi not in groups and gi not in rel]
    gconst = {ti: c for ti, c in gconst.items() if ti not in pair}
    free_gate = [ti for ti in range(len(gate["ffs"])) if ti not in pair and ti not in gconst]
    gold_cuts, gate_cuts, ports = [], [], []
    keys, used = {}, set()
    for gi in groups:
        g = gold["ffs"][gi]
        k = (gate_key(g["names"][:1]) or norm(g["names"][0])) if g["names"] else f"g{gi}"   # register-bit name without a netlist suffix
        if k in used: k = f"{k}.g{gi}"
        used.add(k); keys[gi] = k
    gin, tin = {}, {}                               # the input each register reads its stored value from
    for gi, lst in sorted(groups.items()):
        g = gold["ffs"][gi]; rq = f"\\rq.{keys[gi]}"; gin[gi] = rq[1:]
        ports.append((rq, "input"))
        gold_cuts.append(f"  connect {bitsig(g['q'], gold['wires'])} {rq}")
        for k, (ti, inv) in enumerate(lst):
            t = gate["ffs"][ti]; rd = f"\\rd.{keys[gi]}" + (f".copy{k}" if k else "")
            ports.append((rd, "output")); tin[ti] = ("~" if inv else "") + rq[1:]
            gold_cuts.append(f"  connect {rd} {bitsig(g['d'], gold['wires'])}")
            tq, td = bitsig(t["q"], gate["wires"]), bitsig(t["d"], gate["wires"])
            gate_cuts.append(f"  connect {tq} {inverter(gate_cuts, rq, f'q{ti}') if inv else rq}")
            gate_cuts.append(f"  connect {rd} {inverter(gate_cuts, td, f'd{ti}') if inv else td}")
    for n, (gi, (kind, arg)) in enumerate(sorted(rel.items())):
        g = gold["ffs"][gi]; q, d = bitsig(g["q"], gold["wires"]), bitsig(g["d"], gold["wires"])
        if kind == "const":
            rd = f"\\rd.const{n}"; gin[gi] = f"={arg}"
            gold_cuts.append(f"  connect {q} 1'{arg}")
            ports.append((rd, "output"))
            gold_cuts.append(f"  connect {rd} {d}"); gate_cuts.append(f"  connect {rd} 1'{arg}")
        else:
            rq = f"\\rq.{keys[arg]}"; rd = f"\\rd.{keys[arg]}.{kind}{n}"; gin[gi] = ("~" if kind == "inv" else "") + rq[1:]
            ti0, inv0 = groups[arg][0]; td = bitsig(gate["ffs"][ti0]["d"], gate["wires"])
            gold_cuts.append(f"  connect {q} {rq if kind == 'copy' else inverter(gold_cuts, rq, f'g{gi}')}")
            ports.append((rd, "output"))
            gold_cuts.append(f"  connect {rd} {d}")
            flip = (kind == "inv") != inv0         # the partner's gate flip-flop may itself hold the inverse
            gate_cuts.append(f"  connect {rd} {inverter(gate_cuts, td, f'r{gi}') if flip else td}")
    # a netlist flip-flop that always holds a constant (the RTL side had optimized the register away): it
    # reads the constant, and its next value is compared with the constant
    for n, (ti, c) in enumerate(sorted(gconst.items())):
        t = gate["ffs"][ti]; rd = f"\\rd.gconst{n}"; tin[ti] = f"={c}"
        ports.append((rd, "output"))
        gate_cuts.append(f"  connect {bitsig(t['q'], gate['wires'])} 1'{c}")
        gate_cuts.append(f"  connect {rd} {bitsig(t['d'], gate['wires'])}"); gold_cuts.append(f"  connect {rd} 1'{c}")
    # eqy pairs the two designs port by port, so each free input exists on both sides; the side without
    # the register leaves it unread
    for side, design, idx, cuts, table in (("gold", gold, free_gold, gold_cuts, gin), ("gate", gate, free_gate, gate_cuts, tin)):
        for n, i in enumerate(idx):
            uq = f"\\uq.{side}.{n}"; table[i] = uq[1:]
            ports.append((uq, "input"))
            cuts.append(f"  connect {bitsig(design['ffs'][i]['q'], design['wires'])} {uq}")
    write(gold, gold_out, gold_cuts, ports)
    write(gate, gate_out, gate_cuts, ports)
    if probe:
        # each side alone, every register's next value as an output "pd.<index>", for regsim.py
        for design, path, cuts in ((gold, probe[0], gold_cuts), (gate, probe[1], gate_cuts)):
            pc, pp = list(cuts), list(ports)
            for i, f in enumerate(design["ffs"]):
                pp.append((f"\\pd.{i}", "output")); pc.append(f"  connect \\pd.{i} {bitsig(f['d'], design['wires'])}")
            write(design, path, pc, pp)
        with open(probe[2], "w") as f:              # side, index, state, where its stored value comes from,
            for gi in range(len(gold["ffs"])):     # and for a netlist flip-flop its partner by name (-1: none)
                f.write(f"gold\t{gi}\t{'paired' if gi in groups else 'related' if gi in rel else 'free'}\t{gin[gi]}\n")
            for ti in range(len(gate["ffs"])):
                f.write(f"gate\t{ti}\t{'paired' if ti in pair else 'related' if ti in gconst else 'free'}\t{tin[ti]}\t{named.get(ti, -1)}\n")
    npaired = len(pair)
    print(f"regcut: {npaired}/{len(gate['ffs'])} netlist flip-flops paired with {len(groups)}/{len(gold['ffs'])} RTL register bits"
          f" ({changed} pairing hints; {len(rel)} RTL bits related to a paired register or a constant, {len(gconst)} netlist flip-flops constant); unpaired, left free:"
          f" {len(free_gate)} netlist, {len(free_gold)} RTL")
    def names(design, idx):
        return ", ".join(sorted((norm(design["ffs"][i]["names"][0]) if design["ffs"][i]["names"] else str(design["ffs"][i]["q"])) for i in idx)[:12]) + (" ..." if len(idx) > 12 else "")
    if free_gate: print(f"regcut: unpaired netlist flip-flops: {names(gate, free_gate)}")
    if free_gold: print(f"regcut: unpaired RTL register bits: {names(gold, free_gold)}")
    for p in problems: print(f"regcut: {p}")
    sys.exit(1 if problems else 0)

if __name__ == "__main__":
    main()
