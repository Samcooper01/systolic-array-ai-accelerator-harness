#!/usr/bin/env python3
"""Revise the register pairing by simulating both sides.

usage: regsim.py <gold.aag> <gold.map> <gate.aag> <gate.map> <table.tsv> <hints.tsv>

The probes (regcut.py --probe, then Yosys write_aiger -ascii) are the two cut designs, each with every
register's next value as an output "pd.<index>". Their inputs are named alike (the design's inputs, the
black-box outputs, "rq.*" for paired registers, "uq.gold.*" / "uq.gate.*" for unpaired ones), so both
sides are simulated on the same random values, 16384 at once as bits of Python integers.

The simulation is three-valued: an unpaired register's stored value is unknown, and a next value is
compared only on the vectors where it is known on both sides, so nothing is concluded from logic that
depends on a register not yet matched. Hints written (appended to the
existing file, which regcut.py reads):
  unpair <gate>            a name pair whose next values differ (for example a narrowed memory whose
                           columns synthesis renumbered); the flip-flop is matched again next pass
  pair <gold> <gate> <inv> a netlist flip-flop that holds an RTL register bit (inv 1: its inverse)
  gold <gold> copy|inv <g> an RTL register bit synthesis merged into paired register g (or its inverse)
  gold <gold> const <c>    an RTL register bit that is constant
  gate <gate> const <c>    a netlist flip-flop that is constant (the RTL side optimized it away)
  drop gold|gate <index>   a constant or copy guessed on an earlier pass whose next value differs; it is
                           withdrawn and not guessed again
Resolved registers read their partner's value in later rounds, so chains of merged stages resolve. The
hints are only guesses: regcut.py makes each a compared output, and the proof checks it.
"""
import os, random, re, sys

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

gold_aag, gold_map, gate_aag, gate_map, tsv, hints_path = sys.argv[1:7]
W = 16384; MASK = (1 << W) - 1
rng = random.Random(1)

def load(aag, mapf):
    lines = open(aag).read().split("\n")
    m, i, l, o = map(int, lines[0].split()[1:5])
    if l: sys.exit(f"regsim: {aag} has {l} latches; expected a combinational design")
    ins = [int(lines[1 + j]) >> 1 for j in range(i)]
    outs = [int(lines[1 + i + j]) for j in range(o)]
    # the AND lines as written (the header's AND count can exceed them), up to the symbol table
    ands = [tuple(map(int, t.split())) for t in lines[1 + i + o:] if re.match(r"^\d+ \d+ \d+$", t)]
    ands = topo(ands)
    nin, nout = {}, {}
    for line in open(mapf):
        f = line.split()
        if len(f) >= 4 and f[0] == "input": nin[int(f[1])] = (f[3].lstrip("\\"), int(f[2]))
        if len(f) >= 4 and f[0] == "output": nout[int(f[1])] = f[3].lstrip("\\")
    return dict(m=m, ins=ins, outs=outs, ands=ands, nin=nin, nout=nout)

def simulate_round(d, value, r):
    """Three-valued simulation of one round of W vectors: every signal is (value, known), one bit per
    vector. An input the caller marks unknown (an unpaired register's stored value) makes a result unknown
    only where it can matter: an AND is known 0 wherever either side is known 0."""
    V = [0] * (d["m"] + 1); K = [MASK] * (d["m"] + 1); sh = r * W
    for j, n in enumerate(d["ins"]):
        name, bit = d["nin"].get(j, (f"?{j}", 0))
        v, k = value(name, bit); k = (k >> sh) & MASK; V[n] = (v >> sh) & k; K[n] = k
    for lhs, r0, r1 in d["ands"]:
        ka = K[r0 >> 1]; va = V[r0 >> 1]
        if r0 & 1: va = ~va & ka
        kb = K[r1 >> 1]; vb = V[r1 >> 1]
        if r1 & 1: vb = ~vb & kb
        V[lhs >> 1] = va & vb
        K[lhs >> 1] = (ka & kb) | (ka & ~va) | (kb & ~vb)
    res = {}
    for j, x in enumerate(d["outs"]):
        mm = re.match(r"^pd\.(\d+)$", d["nout"].get(j, ""))
        if mm:
            k = K[x >> 1]; v = V[x >> 1]
            res[int(mm.group(1))] = ((~v & k) if x & 1 else v, k)
    return res

def simulate(d, value):
    """ROUNDS rounds, concatenated: each next value's (value, known) over ROUNDS * W vectors."""
    acc = {}
    for r in range(ROUNDS):
        for i, (v, k) in simulate_round(d, value, r).items():
            pv, pk = acc.get(i, (0, 0)); acc[i] = (pv | (v << (r * W)), pk | (k << (r * W)))
    return acc

gold, gate = load(gold_aag, gold_map), load(gate_aag, gate_map)
state, src, named = {}, {}, {}
for line in open(tsv):
    f = line.split()
    if len(f) >= 4: state[(f[0], int(f[1]))] = f[2]; src[(f[0], int(f[1]))] = f[3]
    if len(f) == 5 and f[0] == "gate" and f[4] != "-1": named[int(f[1])] = int(f[4])
old = [l.rstrip("\n") for l in open(hints_path)] if os.path.exists(hints_path) else []
dropped = {(h.split()[1], int(h.split()[2])) for h in old if h.startswith("drop ")}

# A register that only loads on a rare event (a queue's memory, written when the queue is) has a known next
# value on few vectors, so when registers are unmatched on both sides more rounds are simulated.
ROUNDS = 8 if any(st == "free" for (side, _), st in state.items() if side == "gold") and \
              any(st == "free" for (side, _), st in state.items() if side == "gate") else 1
FULL = (1 << (W * ROUNDS)) - 1
base = {}
def rand(name, bit):
    if (name, bit) not in base: base[(name, bit)] = rng.getrandbits(W * ROUNDS)
    return base[(name, bit)]
def value_of(s):
    """The stored value a table entry names: '<input>', '~<input>', or '=<constant>'."""
    if s.startswith("="): return FULL if s[1:] == "1" else 0
    if s.startswith("~"): return rand(s[1:], 0) ^ FULL
    return rand(s, 0)

gold_of_rq = {src[("gold", gi)]: gi for (side, gi), st in state.items() if side == "gold" and st == "paired"}
free_gold = [gi for (side, gi), st in state.items() if side == "gold" and st == "free"]
free_gate = [ti for (side, ti), st in state.items() if side == "gate" and st == "free"]
gold_val, gate_val = {}, {}                    # resolved free registers: the stored value they follow
new = []
ENOUGH = 32                                    # positions two signals must both be known on to be compared
def pop(x): return bin(x).count("1")
def varies(v, c):
    """Whether a signal takes both values on the positions c. A match on positions where it is constant
    says nothing (a mostly-0 signal matches every other one there), and a wrong match feeds wrong values
    into the next passes, so matches and relations need it."""
    return 0 < pop(v & c) < pop(c)

def inputs(extra=None):
    """Input values for one simulation: free registers unknown unless resolved; extra (input name -> value)
    gives stored values to try, and takes precedence."""
    over = {}
    for gi in free_gold: over[src[("gold", gi)]] = (gold_val[gi], FULL) if gi in gold_val else (0, 0)
    for ti in free_gate: over[src[("gate", ti)]] = (gate_val[ti], FULL) if ti in gate_val else (0, 0)
    over.update({n: (v, FULL) for n, v in (extra or {}).items()})
    def value(name, bit):
        if bit == 0 and name in over: return over[name]
        if name.startswith(("?", "$")) or "anyseq" in name: return (0, 0)     # an RTL x value: unknown
        return (rand(name, bit), FULL)
    return value

# name pairs restored on an earlier pass ("pair <gold> <gate> 0" with the name partner), restored only once
restored = {(int(h.split()[1]), int(h.split()[2])) for h in old if h.startswith("pair ") and named.get(int(h.split()[2])) == int(h.split()[1])}
renamed = set()
first = True
while True:
    g, t = simulate(gold, inputs()), simulate(gate, inputs())
    found = 0
    if first:
        # constants and copies guessed on earlier passes: the guess holds only if the register's next value
        # is the constant (or its partner's next value) wherever both are known. A guess made while what
        # it depends on was still unknown (a rarely written memory row whose write was never seen) can be
        # wrong, and is only seen to be once that is resolved; a wrong one left in fails the proof.
        for (side, i), st in state.items():
            if st != "related": continue
            s = src[(side, i)]; d = g if side == "gold" else t
            if i not in d: continue
            v, k = d[i]
            if s.startswith("="): ev, ek = (FULL if s[1:] == "1" else 0), FULL
            else:
                p_ = gold_of_rq.get(s.lstrip("~"))
                if p_ is None or p_ not in g: continue
                ev, ek = g[p_][0] ^ (FULL if s.startswith("~") else 0), g[p_][1]
            if (v ^ ev) & k & ek:
                new.append(f"drop {side} {i}"); dropped.add((side, i))
        # This simulation read the wrong guesses, so nothing else is concluded from it: the next pass
        # simulates without them and checks the pairs again.
        if new: break
        # name pairs: a paired flip-flop reads rq.<k> (or its inverse); its next value must match the RTL's
        # wherever both are known
        for (side, ti), st in state.items():
            if side != "gate" or st != "paired": continue
            s = src[("gate", ti)]; inv = s.startswith("~"); gi = gold_of_rq.get(s.lstrip("~"))
            if gi is None: continue
            if ti not in t or gi not in g: continue
            (tv, tk), (gv, gk) = t[ti], g[gi]
            if (tv ^ gv ^ (FULL if inv else 0)) & tk & gk:
                new.append(f"unpair {ti}"); found += 1
        first = False
    # candidates for a free netlist flip-flop: free RTL bits, then bits only related to another register
    # by an earlier guess (pairing replaces the guess, which regcut.py then drops), then paired ones
    order = [gi for st_ in ("free", "related", "paired") for gi in g if state.get(("gold", gi)) == st_]
    for ti in free_gate:
        if ti in gate_val or ti not in t: continue
        tv, tk = t[ti]
        if pop(tk) < ENOUGH: continue
        if (tv & tk == 0 or tv & tk == tk) and ("gate", ti) not in dropped:   # constant wherever known
            c = 1 if tv & tk else 0
            new.append(f"gate {ti} const {c}"); found += 1; gate_val[ti] = FULL if c else 0; continue
        hit = None
        for gi in order:
            gv, gk = g[gi]; c = tk & gk
            if pop(c) < ENOUGH or not varies(tv, c): continue
            d = (tv ^ gv) & c
            if d == 0: hit = (gi, 0); break
            if d == c: hit = (gi, 1); break
        if hit is None: continue
        gi, inv = hit
        if state[("gold", gi)] == "free" and gi not in gold_val: gold_val[gi] = rand(src[("gold", gi)], 0)
        gvv = gold_val[gi] if state[("gold", gi)] == "free" else value_of(src[("gold", gi)])
        new.append(f"pair {gi} {ti} {inv}"); found += 1
        gate_val[ti] = gvv ^ (FULL if inv else 0)
    # A name pair split on an earlier pass comes back once the simulation no longer tells the two apart:
    # the name is the default, and only a difference removes it. A split can be a false alarm, made
    # before a register it depends on was resolved (a queue that is never written, found constant only
    # on a later pass), and a memory row that is never written gives no evidence after that, so without
    # this it would stay unpaired. Restored once only, so a pair that differs again stays split.
    for ti in free_gate:
        gi = named.get(ti)
        if gi is None or ti in gate_val or state.get(("gold", gi)) != "free" or (gi, ti) in restored: continue
        if gi in gold_val and gi not in renamed: continue
        if ti in t and gi in g and (t[ti][0] ^ g[gi][0]) & t[ti][1] & g[gi][1]: continue
        if gi not in gold_val: gold_val[gi] = rand(src[("gold", gi)], 0); renamed.add(gi)
        gate_val[ti] = gold_val[gi]; new.append(f"pair {gi} {ti} 0"); found += 1
    paired = [(gi, g[gi]) for (side, gi), st in state.items() if side == "gold" and st == "paired" and gi in g]
    for gi in free_gold:
        if gi in gold_val or gi not in g or ("gold", gi) in dropped: continue
        gv, gk = g[gi]
        if pop(gk) < ENOUGH: continue
        if gv & gk == 0: h, a = "const", 0
        elif gv & gk == gk: h, a = "const", 1
        else:
            m = None
            for p_, (pv, pk) in paired:
                c = gk & pk
                if pop(c) < ENOUGH or not varies(gv, c): continue
                d = (gv ^ pv) & c
                if d == 0: m = (p_, "copy"); break
                if d == c: m = (p_, "inv"); break
            if not m: continue
            a, h = m
        new.append(f"gold {gi} {h} {a}"); found += 1
        gold_val[gi] = (FULL if a else 0) if h == "const" else value_of(src[("gold", a)]) ^ (FULL if h == "inv" else 0)
    if not found: break

# Registers that read each other (the state bits of a state machine) are never matched above: with their
# stored values unknown, their next values are known only where something forces them, such as a reset,
# and there they are constant. Simulated over several cycles instead, starting unknown and each taking
# its own next value as its stored value in the following cycle (the inputs and the paired registers
# random each cycle), they become known wherever a reset or a load has set them, and from then on a
# netlist flip-flop and the RTL bit it holds go through the same values.
withdrawn = any(h.startswith("drop ") for h in new)
seq_t = [ti for ti in free_gate if ti not in gate_val and ti in t]
seq_g = [gi for gi in free_gold if gi not in gold_val and gi in g]
if seq_t and seq_g and not withdrawn:
    STEPS = 16
    srng = random.Random(2)
    stored = {}                                # input name -> (value, known) of a register still free
    hist = {("gate", ti): [0, 0] for ti in seq_t}; hist.update({("gold", gi): [0, 0] for gi in seq_g})
    for s in range(STEPS):
        fresh, over = {}, {}
        for gi in free_gold: over[src[("gold", gi)]] = (gold_val[gi] & MASK, MASK) if gi in gold_val else (0, 0)
        for ti in free_gate: over[src[("gate", ti)]] = (gate_val[ti] & MASK, MASK) if ti in gate_val else (0, 0)
        over.update(stored)
        def value(name, bit):
            if bit == 0 and name in over: return over[name]
            if name.startswith(("?", "$")) or "anyseq" in name: return (0, 0)
            if (name, bit) not in fresh: fresh[(name, bit)] = srng.getrandbits(W)
            return (fresh[(name, bit)], MASK)
        rg, rt = simulate_round(gold, value, 0), simulate_round(gate, value, 0)
        for (side, i), h in hist.items():
            v, k = (rg if side == "gold" else rt)[i]
            h[0] |= v << (s * W); h[1] |= k << (s * W)
            stored[src[(side, i)]] = (v, k)
    for ti in seq_t:
        tv, tk = hist[("gate", ti)]
        for gi in seq_g:
            gv, gk = hist[("gold", gi)]; c = tk & gk
            if pop(c) < ENOUGH or not varies(tv, c): continue
            d = (tv ^ gv) & c
            if d not in (0, c): continue
            inv = 1 if d else 0
            if gi not in gold_val: gold_val[gi] = rand(src[("gold", gi)], 0)
            new.append(f"pair {gi} {ti} {inv}"); gate_val[ti] = gold_val[gi] ^ (FULL if inv else 0)
            break

# Constants by induction. A register that only ever loads a constant, and loads it rarely (a field tied
# off in this configuration behind a module boundary the netlist keeps, so only the RTL side folded it),
# is almost never seen loading, so the comparisons above learn nothing about it. Every register still
# free on either side is given the stored value c at once; those whose next value is c wherever it is
# known (and known often enough) stay candidates, the rest are dropped, until the set is stable. The
# candidates then hold c together, cycle after cycle. A register whose next value is its own stored
# value and nothing else (a memory row that is never written) only holds whatever it starts with, so it
# is never called constant. regcut.py makes each a compared output, so the proof checks it.
def own(d, side):
    """Registers whose next value is exactly their stored value (pure holds), on one side."""
    var = {nm: d["ins"][j] for j, (nm, bit) in d["nin"].items() if bit == 0}
    out = {int(nm[3:]): d["outs"][j] for j, nm in d["nout"].items() if nm.startswith("pd.")}
    return {i for (sd, i), st in state.items() if sd == side and st == "free" and i in out and out[i] == 2 * var.get(src[(sd, i)], -1)}
holds = {"gate": own(gate, "gate"), "gold": own(gold, "gold")}
rest_t = [ti for ti in free_gate if ti not in gate_val and ti not in holds["gate"] and ("gate", ti) not in dropped]
rest_g = [gi for gi in free_gold if gi not in gold_val and gi not in holds["gold"] and ("gold", gi) not in dropped]
nconst = 0
for c in (() if withdrawn else (0, 1)):
    C = FULL if c else 0
    ts, gs = set(rest_t), set(rest_g)
    while ts or gs:
        extra = {src[("gate", ti)]: C for ti in ts}; extra.update({src[("gold", gi)]: C for gi in gs})
        g, t = simulate(gold, inputs(extra)), simulate(gate, inputs(extra))
        steady = lambda r: r is not None and pop(r[1]) >= ENOUGH and (r[0] ^ C) & r[1] == 0
        bt = {ti for ti in ts if not steady(t.get(ti))}; bg = {gi for gi in gs if not steady(g.get(gi))}
        if not bt and not bg: break
        ts -= bt; gs -= bg
    for ti in sorted(ts): new.append(f"gate {ti} const {c}"); gate_val[ti] = C; nconst += 1
    for gi in sorted(gs): new.append(f"gold {gi} const {c}"); gold_val[gi] = C; nconst += 1
    rest_t = [ti for ti in rest_t if ti not in ts]; rest_g = [gi for gi in rest_g if gi not in gs]

with open(hints_path, "w") as f:
    for line in old + new: f.write(line + "\n")
kinds = lambda p: sum(1 for h in new if h.startswith(p))
print(f"regsim: {len(new)} new hints ({kinds('unpair')} name pairs split, {kinds('pair')} netlist flip-flops matched, "
      f"{kinds('gate')} netlist flip-flops constant, {kinds('gold')} RTL bits related, {kinds('drop')} earlier guesses withdrawn)")
