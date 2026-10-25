#!/usr/bin/env python3
"""Rebuild the editor graph with every flat hierarchy broken open and each cell assigned to where it
belongs physically.

Cells (from the synthesized flat netlist, fpedit/nets_v3flat.tsv) are grouped as follows:
  hard macros         Tiles (merged into tile_array), transposer, AccumulatorScale, SRAMs, and the
                      seven controller blocks (hardened, so they stay one node each)
  array pipeline      ex_controller/mesh/mesh/*: merged into tile_array at the tile pins they serve
  MeshWithDelays      split by array edge segment (split_mwd.py): mwd_left_0..3, mwd_top_0..3, mwd_bottom_0..3, mwd_in, mwd_ctl
  named sub-blocks    a named hierarchy or a named register group keeps its own node, e.g.
                      spad/reader.beatPacker, spad/ex_read_pipe, raw_cmd_q, ex/mesh_cntl_signals_q
  generated cells     cells with generated names (_123_, placeNN) inside a flat level (the top,
                      Scratchpad, ExecuteController) carry no hierarchy. Each one is assigned to the
                      nearest named group by breadth-first search through generated cells, and
                      becomes part of a node "<level>: <that group>", placed next to that group.
Small results (under MERGE cells) merge into the group they serve.
Node area = cells x average cell area / 0.6 utilization. Positions: kept from the editor's current
layout where a node already exists; new nodes start at the group they serve.
Writes fpedit/bus_graph.json (the old one is kept as bus_graph_v1.json).
"""
import collections, json, math, os, re, shutil

HERE = "/home/sam/Geetus2.0/chipbase-ref/fpedit"
CELL_UM2 = 0.14 / 0.60
MERGE = 150

old = json.load(open(f"{HERE}/bus_graph.json"))
if not os.path.exists(f"{HERE}/bus_graph_v1.json"):
    shutil.copy(f"{HERE}/bus_graph.json", f"{HERE}/bus_graph_v1.json")
hard = {n["id"]: n for n in old["nodes"] if n["kind"] == "hard"}
grid = {name: (gx, gy) for gx, gy, name in hard["tile_array"]["grid"]}
split = json.load(open(f"{HERE}/mwd_split.json")); mwd_group, pipe_pos = split["group"], split["pipe_pos"]
lay = json.load(open(f"{HERE}/flat_graph_autosave.json")); laypos = {n["id"]: n for n in lay["nodes"]}

CTRL = {"mod_1": "mod_1", "reservation_station": "reservation_station", "load_controller": "load_controller",
        "store_controller": "store_controller", "tlb.tlbs_0.tlb": "tlb", "counters.counterfile": "counters"}
GEN = re.compile(r"^(_\d+_|(place|rebuffer|split|wire|input|output|clone|max_length|hold)\d+)$")


def macro_of(inst, master):
    if master == "Tile": return "tile_array"
    if master == "AlwaysOutTransposer": return "transposer"
    if master == "AccumulatorScale": return "acc_scale_unit"
    if master == "LoopConv": return "mod"
    m = re.match(r"spad/spad_mems_(\d)", inst)
    if master == "mem_ext_phys" and m: return f"spad_bank_{m.group(1)}"
    m = re.match(r"spad/acc_mems_(\d)/.*bank_(\d)", inst)
    if master == "mem_0_bank_ext_phys" and m: return f"acc_bank_{m.group(1)}_{m.group(2)}"
    return None


def base_name(tok):
    tok = re.sub(r"\\?\[.*", "", tok); tok = re.sub(r"\$.*", "", tok)
    return tok


def classify(inst, master):
    """(group, pool): group is a node id, or None for a generated cell in flat level `pool`."""
    m = macro_of(inst, master)
    if m: return m, None
    p = inst.split("/")
    if p[0] in CTRL or p[0].split(".")[0] in ("mod_1", "reservation_station", "load_controller", "store_controller"):
        return CTRL.get(p[0], p[0].split(".")[0]), None
    if p[0].startswith("tlb.") or p[0] == "tlb": return "tlb", None
    if p[0].startswith("counters.") or p[0] == "counters": return "counters", None
    if inst.startswith("ex_controller/mesh/mesh/"): return "tile_array", None
    if inst.startswith("ex_controller/mesh/"): return mwd_group.get(inst, "mwd_ctl"), None
    if p[0] == "ex_controller":
        if len(p) > 2: return "ex/" + p[1], None
        b = base_name(p[1])
        if GEN.match(b): return None, "ex"
        return "ex/" + re.sub(r"_\d+$", "", b.split(".")[0]), None
    if p[0] == "spad":
        if len(p) > 2:
            if p[1].startswith("acc_mems"): return "spad/acc_mems glue", None
            if p[1].startswith("spad_mems"): return "spad/spad_mems glue", None
            return "spad/" + p[1], None
        b = base_name(p[1])
        if GEN.match(b): return None, "spad"
        k = b.split(".")[0]
        if k.startswith("spad_mems"): return "spad/spad_mems glue", None
        return "spad/" + re.sub(r"_\d+$", "", k), None
    b = base_name(p[0])
    if GEN.match(b): return None, "top"
    return "top/" + re.sub(r"_\d+$", "", b.split(".")[0]), None


# ---------- read nets, classify every cell ----------
nets = []; cells = {}
for ln in open(f"{HERE}/nets_v3flat.tsv"):
    f = ln.rstrip("\n").split("\t")
    if f[0] in ("clock", "reset"): continue
    pins = [p.split("|") for p in f[1:]]
    nets.append((f[0], pins))
    for i, ms, mt, d in pins:
        if i != "IO" and i not in cells: cells[i] = (classify(i, ms), ms)
group = {i: g for i, ((g, pool), ms) in cells.items() if g}
pool_of = {i: pool for i, ((g, pool), ms) in cells.items() if not g}
# ---------- generated cells: nearest named group by breadth-first search ----------
adj = collections.defaultdict(set); seed = collections.defaultdict(collections.Counter)
for name, pins in nets:
    gen = [i for i, *_ in pins if i in pool_of]
    if not gen: continue
    named = [group[i] for i, *_ in pins if i in group]
    for a in gen:
        adj[a].update(x for x in gen if x != a)
        for g in named: seed[a][g] += 1
serves = {c: s.most_common(1)[0][0] for c, s in seed.items()}
frontier = list(serves)
while frontier:
    nxt = []
    for c in frontier:
        for n in adj[c]:
            if n not in serves: serves[n] = serves[c]; nxt.append(n)
    frontier = nxt
for c, pool in pool_of.items():
    s = serves.get(c, None)
    group[c] = f"{pool}: {s}" if s else f"{pool}: unconnected"
# ---------- merge small groups into what they serve ----------
count = collections.Counter(g for i, g in group.items() if g not in hard)
for g, n in list(count.items()):
    if n < MERGE and ": " in g:
        tgt = g.split(": ", 1)[1]
        for i, gi in group.items():
            if gi == g: group[i] = tgt
count = collections.Counter(g for i, g in group.items() if g not in hard)
for g, n in list(count.items()):   # small named groups merge into their dominant neighbour group
    if n < MERGE and g not in hard and not g.startswith("mwd_"):   # array edge segments stay separate
        nb = collections.Counter()
        for name, pins in nets:
            gs = [group.get(i) for i, *_ in pins]
            if g in gs: nb.update(x for x in gs if x and x != g)
        if nb:
            tgt = nb.most_common(1)[0][0]
            for i, gi in group.items():
                if gi == g: group[i] = tgt
count = collections.Counter(g for i, g in group.items() if g not in hard)
# glue serving another logic group belongs with it: merge "<level>: X" into X when X is logic
# (glue serving a macro stays separate, as the logic next to that macro)
for g in list(count):
    if ": " in g:
        tgt = g.split(": ", 1)[1]
        if tgt in count and tgt not in hard:
            for i, gi in group.items():
                if gi == g: group[i] = tgt
count = collections.Counter(g for i, g in group.items() if g not in hard)
# top-level glue whose connections go mostly to one logic group belongs with that group, even when it
# is named after a macro; otherwise the pair holds itself in place and neither moves toward the macro
# (block-internal glue, such as the logic beside each memory bank, stays with its macro)
nb = collections.defaultdict(collections.Counter)
for name, pins in nets:
    gs = {group.get(i) for i, *_ in pins} - {None}
    for g in gs:
        if ": " in g: nb[g].update(x for x in gs if x != g)
for g in list(count):
    if g.startswith("top: ") and nb[g]:
        tgt, n = nb[g].most_common(1)[0]
        if tgt in count and tgt not in hard and ": " not in tgt and n > sum(nb[g].values()) / 2:
            print(f"merge {g} -> {tgt} ({n} of {sum(nb[g].values())} nets)")
            for i, gi in group.items():
                if gi == g: group[i] = tgt
count = collections.Counter(g for i, g in group.items() if g not in hard)


# ---------- split the memory glue per bank macro ----------
# The glue around a set of memory banks is one group, but each bank's share of it sits beside that bank.
# Cells on a net with a bank macro's pins are seeded with that bank; the rest take the most common label
# among their neighbours in the group. A cell whose name carries a memory index (acc_mems_N) may only
# take a bank of that memory.
def split_by_bank(gname, banks, mem_of_cell, mem_of_bank):
    members = {i for i, g in group.items() if g == gname}
    if not members: return
    lab = {}; nbr = collections.defaultdict(collections.Counter); seeds = collections.defaultdict(collections.Counter)
    for name, pins in nets:
        here = [i for i, *_ in pins if i in members]
        if not here: continue
        for b in {group.get(i) for i, *_ in pins} & set(banks):
            for c in here: seeds[c][b] += 1
        if len(here) <= 32:
            for a in here: nbr[a].update(h for h in here if h != a)
    def ok(c, b):
        m = mem_of_cell(c); return m is None or m == mem_of_bank(b)
    for c, s in seeds.items():
        s = [(b, n) for b, n in s.most_common() if ok(c, b)]
        if s: lab[c] = s[0][0]
    while True:
        add = {}
        for c in members - lab.keys():
            v = collections.Counter()
            for x, n in nbr[c].items():
                if x in lab and ok(c, lab[x]): v[lab[x]] += n
            if v: add[c] = v.most_common(1)[0][0]
        if not add: break
        lab.update(add)
    for c in members:
        if c in lab: group[c] = f"{gname} {lab[c]}"   # unreachable cells stay in the shared group
    print(f"split {gname}:", dict(collections.Counter(group[c] for c in members)))


split_by_bank("spad/spad_mems glue", [f"spad_bank_{k}" for k in range(4)], lambda c: None, lambda b: None)
split_by_bank("spad/acc_mems glue", [f"acc_bank_{m}_{k}" for m in range(2) for k in range(2)],
              lambda c: (re.search(r"acc_mems_(\d+)", c) or [None, None])[1], lambda b: b.split("_")[2])
count = collections.Counter(g for i, g in group.items() if g not in hard)

# ---------- pin positions ----------
def lef_pins(path):
    t = open(path).read(); pins = {}
    for m in re.finditer(r"\n  PIN (\S+)(.*?)\n  END ", t, re.S):
        r = re.search(r"RECT\s+([0-9.]+)\s+([0-9.]+)\s+([0-9.]+)\s+([0-9.]+)", m.group(2))
        if r: pins[m.group(1)] = ((float(r.group(1)) + float(r.group(3))) / 2, (float(r.group(2)) + float(r.group(4))) / 2)
    return pins
R = "/home/sam/Geetus2.0/chipbase-ref/flow/results/asap7"
LP = {"Tile": lef_pins(f"{R}/gemmini_ExecuteController_Tile/base/Tile.lef"),
      "AlwaysOutTransposer": lef_pins(f"{R}/gemmini_ExecuteController_AlwaysOutTransposer/base/AlwaysOutTransposer.lef"),
      "AccumulatorScale": lef_pins(f"{R}/gemmini_Scratchpad_AccumulatorScale/base/AccumulatorScale.lef"),
      "LoopConv": lef_pins(f"{R}/gemmini_LoopConv/base/LoopConv.lef"),
      "mem_ext_phys": lef_pins("/home/sam/Geetus2.0/chipbase-ref/srams_v2/mem_ext/mem_ext.lef"),
      "mem_0_bank_ext_phys": lef_pins("/home/sam/Geetus2.0/chipbase-ref/srams_v2/mem_0_bank_ext/mem_0_bank_ext.lef")}
ctrl_pin = {}   # controller boundary pins, from the previous graph's buses (net-name keyed there), not
                # available per net here: controller ends are drawn at the block centre

# ---------- buses: driver node -> receiver node, per macro port or per net-name group ----------
bus = {}
for name, pins in nets:
    ends = {}
    for i, ms, mt, d in pins:
        if i == "IO": continue
        g = group.get(i)
        if g is None: continue
        p = None; port = None
        if g == "tile_array":
            if ms == "Tile" and i in grid and mt in LP["Tile"]:
                p = (grid[i][0] + LP["Tile"][mt][0], grid[i][1] + LP["Tile"][mt][1]); port = i.split("/")[-1] + "." + re.sub(r"\[\d+\]$", "", mt)
            elif i in pipe_pos:
                p = tuple(pipe_pos[i]); port = "pipeline"
        elif ms in LP and mt in LP[ms]:
            p = LP[ms][mt]; port = re.sub(r"\[\d+\]$", "", mt)
        q = ends.get(g)
        ends[g] = (p or (q[0] if q else None), (d == "OUTPUT") or (q[1] if q else False), port or (q[2] if q else None))
    if len(ends) < 2: continue
    drv = next((g for g, (p, d, pt) in ends.items() if d), sorted(ends)[0])
    base = re.sub(r"\[\d+\]$", "", name.replace("\\", ""))
    if re.match(r"^(.*/)?(_\d+_|net\d+)$", base) or "$" in base: base = "misc"
    for g, (p, d, pt) in ends.items():
        if g == drv: continue
        pa, pb = ends[drv][0], p; porta, portb = ends[drv][2], pt
        nm = f"{porta or base} -> {portb or base}" if (porta or portb) else base
        r = bus.setdefault((drv, g, nm), [0, [0.0, 0.0], 0, [0.0, 0.0], 0])
        r[0] += 1
        if pa: r[1][0] += pa[0]; r[1][1] += pa[1]; r[2] += 1
        if pb: r[3][0] += pb[0]; r[3][1] += pb[1]; r[4] += 1
buses = [dict(a=a, b=b, name=nm, bits=n, pa=[sa[0] / na, sa[1] / na] if na else None, pb=[sb[0] / nb, sb[1] / nb] if nb else None)
         for (a, b, nm), (n, sa, na, sb, nb) in bus.items()]
buses.sort(key=lambda x: -x["bits"])

# ---------- nodes ----------
def parent_of(g):
    if g.startswith(("ex/", "ex:", "mwd_")): return "ExecuteController"
    if g.startswith(("spad/", "spad:")): return "Scratchpad"
    return "top"
nodes = list(hard.values())
for g, n in count.items():
    if g in hard: continue
    nodes.append(dict(id=g, kind="soft", parent=parent_of(g), label=f"{g}\n{n:,} cells", cells=n, area=n * CELL_UM2, x=0.0, y=0.0))
# start positions: current layout if the node exists there, else next to what it serves
def pos(i):
    v = laypos.get(i)
    if v is None: return None
    h = hard.get(i)
    if h:
        w, hh = (h["h"], h["w"]) if v.get("orient") in ("R90", "R270", "MXR90", "MYR90") else (h["w"], h["h"])
        return (v["x"] + w / 2, v["y"] + hh / 2)
    return (v["x"], v["y"])
arr = laypos.get("tile_array"); ax, ay = (arr["x"], arr["y"]) if arr else (0, 0); AW, AH = hard["tile_array"]["w"], hard["tile_array"]["h"]
SEGS = 4   # array edge segments, as in split_mwd.py
edge_pos = {"mwd_ctl": (ax - 25, ay + AH - 30), "mwd_in": (ax - 25, ay + AH + 25)}
for i in range(SEGS):
    t = (i + 0.5) / SEGS
    edge_pos.update({f"mwd_left_{i}": (ax - 25, ay + AH * t), f"mwd_top_{i}": (ax + AW * t, ay + AH + 25), f"mwd_bottom_{i}": (ax + AW * t, ay - 25)})
for n in nodes:
    if n["kind"] != "soft": continue
    p = edge_pos.get(n["id"]) or pos(n["id"])
    if p is None and ": " in n["id"]: p = pos(n["id"].split(": ", 1)[1]) or edge_pos.get(n["id"].split(": ", 1)[1])
    if p is None: p = (ax - 60, ay + AH / 2)
    n["x"], n["y"] = p
json.dump(group, open(f"{HERE}/groups.json", "w"))   # cell -> cluster, for inspecting and splitting clusters
json.dump({"die": lay["die"], "nodes": nodes, "buses": buses, "ports": old.get("ports", {})}, open(f"{HERE}/bus_graph.json", "w"))
soft = sorted(((n["cells"], n["id"]) for n in nodes if n["kind"] == "soft"), reverse=True)
print(f"{len(soft)} logic nodes, {len(buses)} buses, {sum(b['bits'] for b in buses)} bit-connections")
for c, i in soft: print(f"  {c:6d}  {i}")
