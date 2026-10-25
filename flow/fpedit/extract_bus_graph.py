#!/usr/bin/env python3
"""Every net at the editor's level of hierarchy, grouped into buses, with pin-accurate endpoints.

Inputs
  fpedit/nets_v3flat.tsv   every signal net of the flat v3 synthesis (dumpnets.tcl): pins as
                           inst|master|mterm|direction. ExecuteController and Scratchpad contents
                           keep their hierarchy in the instance names.
  fpedit/flat_graph.json   the editor's nodes (macros and logic clusters) and their positions.
  current LEF abstracts    pin locations of the Tile, transposer, AccumulatorScale, SRAMs, and
                           the controller blocks.
  gemmini/base/1_2_yosys.v the nine-block top netlist: maps a boundary net to the controller port
                           it lands on (the controllers are flat in the v3 netlist).

Each net becomes driver-node -> sink-node connections. Nets whose name differs only in the bit index
form a bus; nets with generated names (_123_, net456) are grouped as "misc" per node pair. Every bus
records its bit count and, on each macro end, the average pin position relative to the macro origin
(unrotated); logic-cluster ends have no pin (drawn at the cluster centre).

Output: fpedit/bus_graph.json = flat_graph.json nodes + "buses" list.
"""
import collections, json, re, sys

W = "/home/sam/Geetus2.0/chipbase-ref"
R = f"{W}/flow/results/asap7"
HERE = f"{W}/fpedit"
MERGE_BELOW = 300

LEFS = {
    "Tile": f"{R}/gemmini_ExecuteController_Tile/base/Tile.lef",
    "AlwaysOutTransposer": f"{R}/gemmini_ExecuteController_AlwaysOutTransposer/base/AlwaysOutTransposer.lef",
    "AccumulatorScale": f"{R}/gemmini_Scratchpad_AccumulatorScale/base/AccumulatorScale.lef",
    "LoopConv": f"{R}/gemmini_LoopConv/base/LoopConv.lef",
    "mem_ext_phys": f"{W}/srams_v2/mem_ext/mem_ext.lef",
    "mem_0_bank_ext_phys": f"{W}/srams_v2/mem_0_bank_ext/mem_0_bank_ext.lef",
    "LoopMatmul": f"{R}/gemmini_LoopMatmul/base/LoopMatmul.lef",
    "ReservationStation": f"{R}/gemmini_ReservationStation/base/ReservationStation.lef",
    "LoadController": f"{R}/gemmini_LoadController/base/LoadController.lef",
    "StoreController": f"{R}/gemmini_StoreController/base/StoreController.lef",
    "FrontendTLB": f"{R}/gemmini_FrontendTLB/base/FrontendTLB.lef",
    "CounterController": f"{R}/gemmini_CounterController/base/CounterController.lef",
}
CTRL_GROUP = {"mod_1": ("mod_1", "LoopMatmul"), "reservation_station": ("reservation_station", "ReservationStation"),
              "load_controller": ("load_controller", "LoadController"), "store_controller": ("store_controller", "StoreController"),
              "tlb.tlbs_0.tlb": ("tlb", "FrontendTLB"), "counters.counterfile": ("counters", "CounterController")}
CTRL_INST = {"mod_1": "LoopMatmul", "reservation_station": "ReservationStation", "load_controller": "LoadController",
             "store_controller": "StoreController", "tlb": "FrontendTLB", "counters": "CounterController"}


def lef_pins(path):
    t = open(path).read(); pins = {}
    for m in re.finditer(r"\n  PIN (\S+)(.*?)\n  END ", t, re.S):
        r = re.search(r"RECT\s+([0-9.]+)\s+([0-9.]+)\s+([0-9.]+)\s+([0-9.]+)", m.group(2))
        if r:
            pins[m.group(1)] = ((float(r.group(1)) + float(r.group(3))) / 2, (float(r.group(2)) + float(r.group(4))) / 2)
    return pins


def clean(n):
    return n.replace("\\", "")


def group_of(inst, master):
    """Same grouping as the connectivity extraction the editor was built from."""
    if master in ("Tile", "AlwaysOutTransposer", "AccumulatorScale", "LoopConv", "mem_ext_phys", "mem_0_bank_ext_phys"):
        return "MACRO:" + inst
    p = inst.split("/"); a = p[0]
    if a == "ex_controller":
        return "ex_controller/mesh (MeshWithDelays)" if len(p) > 1 and p[1] == "mesh" else "ex_controller"
    if a == "spad":
        b = p[1] if len(p) > 1 else ""
        if b.startswith("acc_mems"): return "spad/acc_mems glue"
        if b.startswith("spad_mems"): return "spad/spad_mems glue"
        return "spad/" + b
    if len(p) == 1:
        return "top glue"
    return a


def node_of(g):
    if g.startswith("MACRO:ex_controller/mesh/mesh/mesh_"): return "tile_array"
    if g == "MACRO:ex_controller/mesh/transposer": return "transposer"
    if g == "MACRO:spad/acc_scale_unit": return "acc_scale_unit"
    m = re.match(r"MACRO:spad/spad_mems_(\d)", g)
    if m: return f"spad_bank_{m.group(1)}"
    m = re.match(r"MACRO:spad/acc_mems_(\d)/.*bank_(\d)", g)
    if m: return f"acc_bank_{m.group(1)}_{m.group(2)}"
    if g == "MACRO:mod": return "mod"
    if g in CTRL_GROUP: return CTRL_GROUP[g][0]
    return g


def expand(expr):
    """Port-connection expression -> bit nets, MSB first (the order Verilog concatenation uses)."""
    expr = expr.strip()
    if not expr or re.match(r"^\d+'", expr): return [None] if expr else []
    if expr.startswith("{"):
        out = []
        for part in re.split(r",(?![^\[]*\])", expr.strip("{} ")):
            out += expand(part)
        return out
    m = re.match(r"^(\\?\S+?)\s*\[(\d+):(\d+)\]$", expr)
    if m:
        a, b = int(m.group(2)), int(m.group(3)); step = -1 if a >= b else 1
        return [clean(f"{m.group(1)}[{i}]") for i in range(a, b + step, step)]
    return [clean(expr)]


def main():
    graph = json.load(open(f"{HERE}/flat_graph.json"))
    nodes = {n["id"]: n for n in graph["nodes"]}
    pins = {m: lef_pins(p) for m, p in LEFS.items()}
    grid = {name: (gx, gy) for gx, gy, name in nodes["tile_array"]["grid"]}

    # boundary net -> (controller inst, LEF pin) from the nine-block top netlist
    top = open(f"{R}/gemmini/base/1_2_yosys.v").read()
    ctrl_pin = collections.defaultdict(dict)
    for m in re.finditer(r"^\s+(\w+)\s+(\\?\S+?)\s*\((.*?)\);", top, re.S | re.M):
        master, inst, body = m.group(1), clean(m.group(2)), m.group(3)
        if inst not in CTRL_INST: continue
        lp = pins[master]
        for port, e in re.findall(r"\.(\S+?)\s*\(\s*((?:[^()]|\([^()]*\))*?)\s*\)", body):
            bl = expand(e); w = len(bl)
            for k, net in enumerate(bl):
                if net is None: continue
                pname = port if (w == 1 and port in lp) else f"{port}[{w - 1 - k}]"
                if pname in lp: ctrl_pin[net][inst] = (lp[pname], pname)

    # first pass: group sizes, to merge tiny groups as the editor graph does
    lines = open(f"{HERE}/nets_v3flat.tsv").read().splitlines()
    members = collections.defaultdict(set)
    for ln in lines:
        for pin in ln.split("\t")[1:]:
            inst, master, _, _ = pin.split("|")
            if inst != "IO": members[group_of(inst, master)].add(inst)
    alias = {g: ("spad other" if g.startswith("spad") else "top glue") for g, s in members.items()
             if not g.startswith("MACRO:") and g not in CTRL_GROUP and len(s) < MERGE_BELOW}

    def nid(g):
        return node_of(alias.get(g, g))

    bus = {}   # (a, b, busname) -> [bits, sum_pa, n_pa, sum_pb, n_pb]
    skipped = 0
    for ln in lines:
        f = ln.split("\t"); net = clean(f[0])
        if net in ("clock", "reset") or len(f) < 3: continue
        ends = []   # (node, pin or None, is_driver)
        for pin in f[1:]:
            inst, master, mterm, io = pin.split("|")
            if inst == "IO":
                continue
            n = nid(group_of(inst, master))
            if n not in nodes: skipped += 1; continue
            p = None; port = None
            pb_ = re.sub(r"\[\d+\]$", "", mterm)
            if n == "tile_array":
                g = grid.get(inst); lp = pins["Tile"].get(mterm)
                if g and lp: p = (g[0] + lp[0], g[1] + lp[1])
                port = inst.split("/")[-1] + "." + pb_
            elif master in pins and master not in ("LoopMatmul",):
                p = pins[master].get(mterm); port = pb_
            ends.append((n, p, io == "OUTPUT", port))
        for n in set(e[0] for e in ends):   # controller ends: port pin from the hierarchical netlist
            if n in CTRL_INST and n in ctrl_pin.get(net, {}):
                pp, pname = ctrl_pin[net][n]
                ends = [(a, pp if a == n else p, d, re.sub(r"\[\d+\]$", "", pname) if a == n else pt) for a, p, d, pt in ends]
        nodeset = {}
        for n, p, d, pt in ends:   # one endpoint per node: prefer a pin position, remember driver and port
            q = nodeset.get(n)
            nodeset[n] = (p if p is not None else (q[0] if q else None), d or (q[1] if q else False), pt or (q[2] if q else None))
        if len(nodeset) < 2: continue
        drv = next((n for n, (p, d, pt) in nodeset.items() if d), sorted(nodeset)[0])
        base = re.sub(r"\[\d+\]$", "", net)
        if re.match(r"^(.*/)?(_\d+_|net\d+)$", base) or "$" in base: base = "misc"
        for n, (p, d, pt) in nodeset.items():
            if n == drv: continue
            a, b = drv, n; pa, pb = nodeset[drv][0], p
            porta, portb = nodeset[drv][2], pt
            # a bus is one port on each macro end; between two logic clusters it is the net-name group
            name = f"{porta or base} -> {portb or base}" if (porta or portb) else base
            key = (a, b, name)
            r = bus.setdefault(key, [0, [0.0, 0.0], 0, [0.0, 0.0], 0])
            r[0] += 1
            if pa: r[1][0] += pa[0]; r[1][1] += pa[1]; r[2] += 1
            if pb: r[3][0] += pb[0]; r[3][1] += pb[1]; r[4] += 1
    out_buses = []
    for (a, b, name), (n, sa, na, sb, nb) in bus.items():
        out_buses.append(dict(a=a, b=b, name=name, bits=n,
                              pa=[sa[0] / na, sa[1] / na] if na else None, pb=[sb[0] / nb, sb[1] / nb] if nb else None))
    out_buses.sort(key=lambda x: -x["bits"])
    graph["buses"] = out_buses
    ports = {}
    dirs = {}
    for m, path in LEFS.items():
        tt = open(path).read()
        for mm in re.finditer(r"\n  PIN (\S+)(.*?)\n  END ", tt, re.S):
            d = re.search(r"DIRECTION (\w+)", mm.group(2)); dirs[(m, re.sub(r"\[\d+\]$", "", mm.group(1)))] = d.group(1) if d else ""
    def port_list(master, offset=(0.0, 0.0), prefix=""):
        agg = collections.defaultdict(list)
        for pn, (x, y) in pins[master].items():
            if pn in ("VDD", "VSS"): continue
            agg[re.sub(r"\[\d+\]$", "", pn)].append((x, y))
        return [dict(name=prefix + k, x=offset[0] + sum(a for a, _ in v) / len(v), y=offset[1] + sum(b for _, b in v) / len(v),
                     bits=len(v), dir=dirs.get((master, k), "")) for k, v in agg.items()]
    master_of = {"transposer": "AlwaysOutTransposer", "acc_scale_unit": "AccumulatorScale", "mod": "LoopConv"}
    master_of.update({k: v for k, v in CTRL_INST.items()})
    for k, v in nodes.items():
        if v["kind"] != "hard": continue
        if k == "tile_array":
            ports[k] = [p for gx, gy, name in v["grid"] for p in port_list("Tile", (gx, gy), name.split("/")[-1] + ".")]
        elif k.startswith("spad_bank"): ports[k] = port_list("mem_ext_phys")
        elif k.startswith("acc_bank"): ports[k] = port_list("mem_0_bank_ext_phys")
        elif k in master_of: ports[k] = port_list(master_of[k])
    graph["ports"] = ports
    json.dump(graph, open(f"{HERE}/bus_graph.json", "w"))
    pairs = collections.Counter()
    for x in out_buses: pairs[tuple(sorted((x["a"], x["b"])))] += x["bits"]
    pinned = sum(1 for x in out_buses if (x["pa"] or x["pb"]))
    print(f"{len(out_buses)} buses ({pinned} with a pin end), {sum(x['bits'] for x in out_buses)} bit-connections, "
          f"{len(pairs)} node pairs, {skipped} pins on unmapped groups")
    for x in out_buses[:12]:
        print(f"  {x['bits']:5d}  {x['a']} -> {x['b']}  {x['name'][:60]}")


if __name__ == "__main__":
    main()
