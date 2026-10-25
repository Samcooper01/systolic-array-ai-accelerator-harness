#!/usr/bin/env python3
"""Graph for the floorplan editor with the ExecuteController and Scratchpad hierarchy broken open.

Nodes:
  hard  - macros at true size: the tile array (8 x 8 Tiles as one grid), AlwaysOutTransposer,
          AccumulatorScale, the 4 scratchpad banks, the 4 accumulator half-banks, and the seven
          controller blocks (LoopConv, LoopMatmul, ReservationStation, Load/StoreController,
          FrontendTLB, CounterController), which stay hardened.
  soft  - standard-cell logic clusters by hierarchy (MeshWithDelays, execute control, the vector
          scale multiplier, DMA reader and writer, accumulator glue, queues, top glue), drawn as
          circles whose area is the cells' footprint at 60 percent utilization.
Edges: nets between two groups, counted from the flat placed netlist (img/conn_v3.tsv, written by
the connectivity extraction on the v3 flat run, which keeps the hierarchy in the cell names).
Initial positions: hard macros where the current reference puts them (block position plus the
position inside the block); soft clusters at the weighted centroid of their hard neighbours.

Usage: extract_flat_graph.py [--out flat_graph.json]
"""
import argparse, collections, json, math, re

W = "/home/sam/Geetus2.0/chipbase-ref"
R = f"{W}/flow/results/asap7"
CELL_UM2 = 0.14 / 0.60          # average cell area over target utilization
MERGE_BELOW = 300               # cells: smaller groups merge into their parent cluster


def lef_size(p):
    return tuple(float(v) for v in re.search(r"SIZE ([0-9.]+) BY ([0-9.]+)", open(p).read()).groups())


def placed(tcl):
    return {m.group(1): (float(m.group(2)), float(m.group(3)), m.group(4)) for m in re.finditer(
        r"place_macro -macro_name \{(\S+)\} -location \{([0-9.]+) ([0-9.]+)\} -orientation (\w+)", open(tcl).read())}


CONTROLLERS = {  # flat group name -> (node id, abstract)
    "MACRO:mod": ("mod", "gemmini_LoopConv/base/LoopConv.lef"),
    "mod_1": ("mod_1", "gemmini_LoopMatmul/base/LoopMatmul.lef"),
    "reservation_station": ("reservation_station", "gemmini_ReservationStation/base/ReservationStation.lef"),
    "load_controller": ("load_controller", "gemmini_LoadController/base/LoadController.lef"),
    "store_controller": ("store_controller", "gemmini_StoreController/base/StoreController.lef"),
    "tlb.tlbs_0.tlb": ("tlb", "gemmini_FrontendTLB/base/FrontendTLB.lef"),
    "counters.counterfile": ("counters", "gemmini_CounterController/base/CounterController.lef"),
}
LABEL = {"mod": "LoopConv", "mod_1": "LoopMatmul", "reservation_station": "ReservationStation",
         "load_controller": "LoadController", "store_controller": "StoreController", "tlb": "FrontendTLB",
         "counters": "CounterController"}


def node_of(g):
    """Map a flat group name to an editor node id."""
    if g.startswith("MACRO:mesh_"):
        return "tile_array"
    if g == "MACRO:ex_controller/mesh/transposer":
        return "transposer"
    if g == "MACRO:spad/acc_scale_unit":
        return "acc_scale_unit"
    m = re.match(r"MACRO:spad/spad_mems_(\d)", g)
    if m:
        return f"spad_bank_{m.group(1)}"
    m = re.match(r"MACRO:spad/acc_mems_(\d)/.*bank_(\d)", g)
    if m:
        return f"acc_bank_{m.group(1)}_{m.group(2)}"
    if g in CONTROLLERS:
        return CONTROLLERS[g][0]
    if g == "IO":
        return None
    return g


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--out", default=f"{W}/fpedit/flat_graph.json")
    a = ap.parse_args()
    groups, edges = {}, collections.Counter()
    for line in open(f"{W}/img/conn_v3.tsv"):
        p = line.rstrip("\n").split("\t")
        if p[0] == "G":
            groups[p[1]] = int(p[2])
        elif p[0] == "E":
            edges[(p[1], p[2])] += int(p[3])
    # merge tiny soft groups into their parent cluster
    alias = {}
    for g, n in groups.items():
        if g.startswith("MACRO:") or g in CONTROLLERS:
            continue
        if n < MERGE_BELOW:
            alias[g] = "spad other" if g.startswith("spad") else "top glue"
    def nid(g):
        return node_of(alias.get(g, g))

    # geometry of the current reference
    top = placed(f"{R}/gemmini/base/2_2_floorplan_macro.tcl")
    ecx, ecy, _ = top["ex_controller"]; spx, spy, _ = top["spad"]
    ec_in = placed(f"{R}/gemmini_ExecuteController/base/2_2_floorplan_macro.tcl")
    sp_in = placed(f"{R}/gemmini_Scratchpad/base/2_2_floorplan_macro.tcl")
    tile = lef_size(f"{R}/gemmini_ExecuteController_Tile/base/Tile.lef")
    tiles = [(x, y, n) for n, (x, y, o) in ec_in.items() if "mesh_" in n]
    ax0, ay0 = min(t[0] for t in tiles), min(t[1] for t in tiles)
    aw, ah = max(t[0] for t in tiles) + tile[0] - ax0, max(t[1] for t in tiles) + tile[1] - ay0
    nodes = {}
    nodes["tile_array"] = dict(kind="hard", label="Tile array\n64 Tiles, 8 x 8", w=aw, h=ah, x=ecx + ax0, y=ecy + ay0,
                               grid=[[x - ax0, y - ay0, "ex_controller/" + n] for x, y, n in tiles], tile=list(tile), parent="ExecuteController")
    tw, th = lef_size(f"{R}/gemmini_ExecuteController_AlwaysOutTransposer/base/AlwaysOutTransposer.lef")
    tx, ty, _ = next(v for k, v in ec_in.items() if k.endswith("transposer"))
    nodes["transposer"] = dict(kind="hard", inst="ex_controller/mesh/transposer", label="Transposer", w=tw, h=th, x=ecx + tx, y=ecy + ty, parent="ExecuteController")
    sw, sh = lef_size(f"{W}/srams_v2/mem_ext/mem_ext.lef"); hw, hh = lef_size(f"{W}/srams_v2/mem_0_bank_ext/mem_0_bank_ext.lef")
    aw2, ah2 = lef_size(f"{R}/gemmini_Scratchpad_AccumulatorScale/base/AccumulatorScale.lef")
    for k, (x, y, o) in sp_in.items():
        m = re.match(r"spad_mems_(\d)", k); m2 = re.match(r"acc_mems_(\d)/.*bank_(\d)", k)
        if m:
            nodes[f"spad_bank_{m.group(1)}"] = dict(kind="hard", inst="spad/" + k, label=f"spad bank {m.group(1)}\n4096 x 128", w=sw, h=sh, x=spx + x, y=spy + y, parent="Scratchpad", sram=True)
        elif m2:
            nodes[f"acc_bank_{m2.group(1)}_{m2.group(2)}"] = dict(kind="hard", inst="spad/" + k, label=f"acc {m2.group(1)} half {m2.group(2)}", w=hw, h=hh, x=spx + x, y=spy + y, parent="Scratchpad", sram=True)
        elif k == "acc_scale_unit":
            nodes["acc_scale_unit"] = dict(kind="hard", inst="spad/acc_scale_unit", label="AccumulatorScale", w=aw2, h=ah2, x=spx + x, y=spy + y, parent="Scratchpad")
    for g, (n, lef) in CONTROLLERS.items():
        w, h = lef_size(f"{R}/{lef}"); x, y, _ = top[n]
        nodes[n] = dict(kind="hard", inst=n, label=LABEL[n], w=w, h=h, x=x, y=y, parent="controllers")
    # soft clusters
    soft = collections.Counter()
    for g, n in groups.items():
        k = nid(g)
        if k and k not in nodes:
            soft[k] += n
    for k, n in soft.items():
        parent = "ExecuteController" if k.startswith("ex_controller") else "Scratchpad" if k.startswith("spad") else "top"
        nodes[k] = dict(kind="soft", label=f"{k}\n{n:,} cells", cells=n, area=n * CELL_UM2, x=0.0, y=0.0, parent=parent)
    # edges between nodes
    E = collections.Counter()
    for (g1, g2), n in edges.items():
        a1, a2 = nid(g1), nid(g2)
        if not a1 or not a2 or a1 == a2 or a1 not in nodes or a2 not in nodes:
            continue
        E[tuple(sorted((a1, a2)))] += n
    # soft cluster start positions: weighted centroid of hard neighbours (then of all neighbours)
    def center(k):
        v = nodes[k]; return (v["x"] + v.get("w", 0) / 2, v["y"] + v.get("h", 0) / 2)
    for it in range(3):
        for k, v in nodes.items():
            if v["kind"] != "soft":
                continue
            sx = sy = sw_ = 0.0
            for (p, q), n in E.items():
                o = q if p == k else p if q == k else None
                if o is None or (it == 0 and nodes[o]["kind"] == "soft"):
                    continue
                cx, cy = center(o); sx += n * cx; sy += n * cy; sw_ += n
            if sw_:
                v["x"], v["y"] = sx / sw_, sy / sw_
    die = dict(w=1352.0, h=1006.0)
    for k, v in nodes.items():  # soft x,y are centres; keep inside the die
        if v["kind"] == "soft":
            v["x"] = min(max(v["x"], 20), die["w"] - 20); v["y"] = min(max(v["y"], 20), die["h"] - 20)
    out = dict(die=die, nodes=[dict(id=k, **v) for k, v in nodes.items()],
               edges=[dict(a=p, b=q, bits=n) for (p, q), n in sorted(E.items(), key=lambda kv: -kv[1])])
    json.dump(out, open(a.out, "w"), indent=1)
    print(f"{sum(1 for v in nodes.values() if v['kind']=='hard')} hard, {len(soft)} soft, {len(E)} edges -> {a.out}")
    for (p, q), n in sorted(E.items(), key=lambda kv: -kv[1])[:15]:
        print(f"  {n:6d}  {p} <-> {q}")


if __name__ == "__main__":
    main()
