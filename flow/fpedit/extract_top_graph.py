#!/usr/bin/env python3
"""Extract the top-level block graph for the floorplan editor.

Reads the synthesized top netlist (block instances and the nets on their ports), each block's LEF
(size and pin locations), the current macro placement, and the die size, and writes a JSON file:

  blocks:  inst, master, w, h, x, y, orient
  edges:   a, b, bits, pa, pb   (pa/pb: centroid, in block-local microns, of the pins carrying
                                  those bits on block a and block b, before orientation)
  glue:    inst, bits, p        (bits from the block to top-level logic or die pins)
  die:     w, h

Usage: extract_top_graph.py [--variant base] [--out top_graph.json]
"""
import argparse, collections, json, os, re

W = "/home/sam/Geetus2.0/chipbase-ref"
R = f"{W}/flow/results/asap7"
LEF = {  # master -> abstract
    "ExecuteController": f"{R}/gemmini_ExecuteController/base/ExecuteController.lef",
    "Scratchpad": f"{R}/gemmini_Scratchpad/base/Scratchpad.lef",
    "LoopConv": f"{R}/gemmini_LoopConv/base/LoopConv.lef",
    "LoopMatmul": f"{R}/gemmini_LoopMatmul/base/LoopMatmul.lef",
    "ReservationStation": f"{R}/gemmini_ReservationStation/base/ReservationStation.lef",
    "LoadController": f"{R}/gemmini_LoadController/base/LoadController.lef",
    "StoreController": f"{R}/gemmini_StoreController/base/StoreController.lef",
    "FrontendTLB": f"{R}/gemmini_FrontendTLB/base/FrontendTLB.lef",
    "CounterController": f"{R}/gemmini_CounterController/base/CounterController.lef",
}


def read_lef(path):
    t = open(path).read()
    w, h = (float(v) for v in re.search(r"SIZE ([0-9.]+) BY ([0-9.]+)", t).groups())
    ports = collections.defaultdict(list)  # port base name -> pin centers
    for m in re.finditer(r"\n  PIN (\S+)(.*?)\n  END ", t, re.S):
        r = re.search(r"RECT\s+([0-9.]+)\s+([0-9.]+)\s+([0-9.]+)\s+([0-9.]+)", m.group(2))
        if not r:
            continue
        x = (float(r.group(1)) + float(r.group(3))) / 2
        y = (float(r.group(2)) + float(r.group(4))) / 2
        ports[re.sub(r"\[\d+\]$", "", m.group(1))].append((x, y))
    cent = {p: (sum(x for x, _ in v) / len(v), sum(y for _, y in v) / len(v)) for p, v in ports.items()}
    return w, h, cent


def bits(expr):
    """Expand a port-connection expression into bit-level net names."""
    expr = expr.strip()
    if not expr:
        return []
    if expr.startswith("{"):
        out = []
        for part in re.split(r",(?![^\[]*\])", expr.strip("{}")):
            out += bits(part)
        return out
    if re.match(r"^\d+'", expr):
        return []
    m = re.match(r"^(\\?\S+?)\s*\[(\d+):(\d+)\]$", expr)
    if m:
        a, b = int(m.group(2)), int(m.group(3))
        return [f"{m.group(1)}[{i}]" for i in range(min(a, b), max(a, b) + 1)]
    return [expr]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", default="base")
    ap.add_argument("--out", default=f"{W}/fpedit/top_graph.json")
    a = ap.parse_args()
    res = f"{R}/gemmini/{a.variant}"
    net = open(f"{res}/1_2_yosys.v").read()
    lefs = {m: read_lef(p) for m, p in LEF.items()}

    # nets on block ports: net bit -> list of (inst, port)
    on = collections.defaultdict(list)
    inst_master = {}
    for m in re.finditer(r"^\s+(\w+)\s+(\\?\S+?)\s*\((.*?)\);", net, re.S | re.M):
        master, inst, body = m.group(1), m.group(2).lstrip("\\"), m.group(3)
        if master not in LEF:
            continue
        inst_master[inst] = master
        for port, expr in re.findall(r"\.(\S+?)\s*\(\s*((?:[^()]|\([^()]*\))*?)\s*\)", body):
            if port not in lefs[master][2]:
                continue
            for b in bits(expr):
                on[b].append((inst, port))

    pair = collections.defaultdict(lambda: [0, [0.0, 0.0], [0.0, 0.0]])
    glue = collections.defaultdict(lambda: [0, [0.0, 0.0]])
    for b, ends in on.items():
        insts = sorted(set(i for i, _ in ends))
        port_of = {i: p for i, p in ends}
        if len(insts) == 1:
            i = insts[0]; c = lefs[inst_master[i]][2][port_of[i]]
            g = glue[i]; g[0] += 1; g[1][0] += c[0]; g[1][1] += c[1]
            continue
        for x in range(len(insts)):
            for y in range(x + 1, len(insts)):
                i, j = insts[x], insts[y]
                ci = lefs[inst_master[i]][2][port_of[i]]; cj = lefs[inst_master[j]][2][port_of[j]]
                e = pair[(i, j)]; e[0] += 1
                e[1][0] += ci[0]; e[1][1] += ci[1]; e[2][0] += cj[0]; e[2][1] += cj[1]

    # current placement and die
    place = {}
    tcl = f"{res}/2_2_floorplan_macro.tcl"
    if os.path.exists(tcl):
        for m in re.finditer(r"place_macro -macro_name \{(\S+)\} -location \{([0-9.]+) ([0-9.]+)\} -orientation (\w+)", open(tcl).read()):
            place[m.group(1)] = (float(m.group(2)), float(m.group(3)), m.group(4))
    cfg = open(f"{W}/flow/gemmini/config.mk").read()
    d = re.search(r"DIE_AREA = 0 0 ([0-9.]+) ([0-9.]+)", cfg)
    die = {"w": float(d.group(1)), "h": float(d.group(2))} if d else {"w": 1400.0, "h": 1000.0}

    out = {"die": die, "blocks": [], "edges": [], "glue": []}
    for i, master in sorted(inst_master.items()):
        w, h, _ = lefs[master]
        x, y, o = place.get(i, (0.0, 0.0, "R0"))
        out["blocks"].append({"inst": i, "master": master, "w": w, "h": h, "x": x, "y": y, "orient": o})
    for (i, j), (n, si, sj) in sorted(pair.items(), key=lambda kv: -kv[1][0]):
        out["edges"].append({"a": i, "b": j, "bits": n, "pa": [si[0] / n, si[1] / n], "pb": [sj[0] / n, sj[1] / n]})
    for i, (n, s) in sorted(glue.items(), key=lambda kv: -kv[1][0]):
        out["glue"].append({"inst": i, "bits": n, "p": [s[0] / n, s[1] / n]})
    json.dump(out, open(a.out, "w"), indent=1)
    print(f"{len(out['blocks'])} blocks, {len(out['edges'])} block pairs, die {die['w']} x {die['h']} -> {a.out}")
    for e in out["edges"][:12]:
        print(f"  {e['bits']:5d}  {e['a']} <-> {e['b']}")


if __name__ == "__main__":
    main()
