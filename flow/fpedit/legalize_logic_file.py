#!/usr/bin/env python3
"""Place the soft logic clusters sensibly around the current macros: pull each toward its
wirelength-optimal point (bit-weighted median of what it connects to), push clusters apart so they do
not overlap, push them out of macros, keep them in the die. Writes move commands to the editor."""
import json, math, os, re, sys, time, tkinter as tk
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fpedit_flat as f
f.AUTOSAVE = "/home/sam/.claude/jobs/826af8d2/tmp/t.json"
SRC = sys.argv[1] if len(sys.argv) > 1 else None
OUT = sys.argv[2] if len(sys.argv) > 2 else None
GAP = 4.0   # um between neighbouring clusters and between a cluster and a macro


def wmed(pairs):
    pairs = sorted(pairs); tot = sum(w for _, w in pairs); a = 0
    for v, w in pairs:
        a += w
        if a >= tot / 2: return v


def main():
    r = tk.Tk(); r.withdraw(); e = f.Editor(r, SRC or os.path.join(os.path.dirname(os.path.abspath(__file__)), "flat_graph_autosave.json"))
    soft = [k for k, v in e.nodes.items() if v["kind"] == "soft"]
    hard = [k for k, v in e.nodes.items() if v["kind"] == "hard"]
    rad = {k: math.sqrt(e.nodes[k]["area"] / math.pi) for k in soft}
    # the MeshWithDelays edge registers are split into segments along each array edge: pin each segment
    # to the middle of its stretch of edge, just outside the array (segments count from the bottom-left
    # corner; the array is assumed unrotated), and let everything else settle around them
    pinned = set()
    if "tile_array" in e.nodes:
        a = e.nodes["tile_array"]; aw, ah = f.dims(a)
        if a.get("orient", "R0") != "R0": print("warning: tile_array is not R0; edge segments are placed as if it were")
        for k in list(e.nodes):
            m = re.fullmatch(r"mwd_(left|top|bottom)_(\d+)", k)
            if not m: continue
            segs = 1 + max(int(re.fullmatch(r"mwd_\w+_(\d+)", j).group(1)) for j in e.nodes if re.fullmatch(r"mwd_(left|top|bottom)_\d+", j))
            t = (int(m.group(2)) + 0.5) / segs; rk = rad.get(k, 0)
            px, py = {"left": (a["x"] - rk - GAP, a["y"] + ah * t), "top": (a["x"] + aw * t, a["y"] + ah + rk + GAP),
                      "bottom": (a["x"] + aw * t, a["y"] - rk - GAP)}[m.group(1)]
            e.nodes[k]["x"], e.nodes[k]["y"] = px, py; pinned.add(k)
    # clusters placed by hand stay where they are (comma-separated ids in PIN)
    for k in filter(None, os.environ.get("PIN", "").split(",")):
        if k in e.nodes: pinned.add(k)
    soft_all = soft
    soft = [k for k in soft if k not in pinned]
    die = e.die
    for it in range(400):
        # attraction: move part way to the optimum given everything else
        step = 0.5 if it < 200 else 0.15
        for k in soft:
            xs, ys = [], []
            for b in e.buses:
                if b["a"] == k: o = e.end(b["b"], b["pb"])
                elif b["b"] == k: o = e.end(b["a"], b["pa"])
                else: continue
                xs.append((o[0], b["bits"])); ys.append((o[1], b["bits"]))
            if xs:
                v = e.nodes[k]; tx, ty = wmed(xs), wmed(ys)
                v["x"] += step * (tx - v["x"]); v["y"] += step * (ty - v["y"])
        # repulsion between clusters, and out of macros, several relaxation passes
        for _ in range(6):
            for i, a in enumerate(soft):
                va = e.nodes[a]
                for b in soft[i + 1:]:
                    vb = e.nodes[b]; dx, dy = vb["x"] - va["x"], vb["y"] - va["y"]; d = math.hypot(dx, dy) or 1e-6
                    need = rad[a] + rad[b] + GAP
                    if d < need:
                        push = (need - d) / 2; ux, uy = (dx / d, dy / d) if d > 1e-3 else (1.0, 0.0)
                        va["x"] -= ux * push; va["y"] -= uy * push; vb["x"] += ux * push; vb["y"] += uy * push
                for pk in pinned:
                    vp = e.nodes[pk]; dx, dy = va["x"] - vp["x"], va["y"] - vp["y"]; d = math.hypot(dx, dy) or 1e-6
                    need = rad[a] + rad[pk] + GAP
                    if d < need: va["x"] += dx / d * (need - d); va["y"] += dy / d * (need - d)
                for h in hard:
                    m = e.nodes[h]; w, hh = f.dims(m)
                    cx = min(max(va["x"], m["x"]), m["x"] + w); cy = min(max(va["y"], m["y"]), m["y"] + hh)
                    dx, dy = va["x"] - cx, va["y"] - cy; d = math.hypot(dx, dy)
                    inside = m["x"] < va["x"] < m["x"] + w and m["y"] < va["y"] < m["y"] + hh
                    if inside:   # jump out through the nearest side
                        opts = [(va["x"] - m["x"], -1, 0), (m["x"] + w - va["x"], 1, 0), (va["y"] - m["y"], 0, -1), (m["y"] + hh - va["y"], 0, 1)]
                        dist, sx, sy = min(opts)
                        va["x"] += sx * (dist + rad[a] + GAP); va["y"] += sy * (dist + rad[a] + GAP)
                    elif d < rad[a] + GAP:
                        push = rad[a] + GAP - d; va["x"] += dx / (d or 1e-6) * push; va["y"] += dy / (d or 1e-6) * push
                va["x"] = min(max(va["x"], rad[a] + 3), die["w"] - rad[a] - 3); va["y"] = min(max(va["y"], rad[a] + 3), die["h"] - rad[a] - 3)
    # final spreading: relaxation only (no attraction), so clusters settle without overlapping
    for _ in range(300):
        moved = False
        for i, a in enumerate(soft):
            va = e.nodes[a]
            for b in soft[i + 1:]:
                vb = e.nodes[b]; dx, dy = vb["x"] - va["x"], vb["y"] - va["y"]; d = math.hypot(dx, dy) or 1e-6
                need = rad[a] + rad[b] + GAP
                if d < need:
                    moved = True; push = (need - d) / 2; ux, uy = (dx / d, dy / d) if d > 1e-3 else (1.0, 0.0)
                    va["x"] -= ux * push; va["y"] -= uy * push; vb["x"] += ux * push; vb["y"] += uy * push
            for pk in pinned:
                vp = e.nodes[pk]; dx, dy = va["x"] - vp["x"], va["y"] - vp["y"]; d = math.hypot(dx, dy) or 1e-6
                need = rad[a] + rad[pk] + GAP
                if d < need: va["x"] += dx / d * (need - d); va["y"] += dy / d * (need - d); moved = True
            for h in hard:
                m = e.nodes[h]; w, hh = f.dims(m)
                cx = min(max(va["x"], m["x"]), m["x"] + w); cy = min(max(va["y"], m["y"]), m["y"] + hh)
                dx, dy = va["x"] - cx, va["y"] - cy; d = math.hypot(dx, dy)
                if m["x"] < va["x"] < m["x"] + w and m["y"] < va["y"] < m["y"] + hh:
                    opts = [(va["x"] - m["x"], -1, 0), (m["x"] + w - va["x"], 1, 0), (va["y"] - m["y"], 0, -1), (m["y"] + hh - va["y"], 0, 1)]
                    dist, sx, sy = min(opts); va["x"] += sx * (dist + rad[a] + GAP); va["y"] += sy * (dist + rad[a] + GAP); moved = True
                elif d < rad[a] + GAP:
                    push = rad[a] + GAP - d; va["x"] += dx / (d or 1e-6) * push; va["y"] += dy / (d or 1e-6) * push; moved = True
            va["x"] = min(max(va["x"], rad[a] + 3), die["w"] - rad[a] - 3); va["y"] = min(max(va["y"], rad[a] + 3), die["h"] - rad[a] - 3)
        if not moved: break
    # report overlaps left
    left = 0
    for i, a in enumerate(soft):
        for b in soft[i + 1:]:
            if math.hypot(e.nodes[a]["x"] - e.nodes[b]["x"], e.nodes[a]["y"] - e.nodes[b]["y"]) < rad[a] + rad[b] - 1: left += 1
    t, v, per, w = e.metrics()
    print(f"score {t / 1000:,.0f} bit-mm; cluster-cluster overlaps left {left}; warnings {[x for x in w if 'logic' in x] or 'none'}")
    if OUT:
        json.dump(e.layout(), open(OUT, "w")); print("wrote", OUT); r.destroy(); return
    cmds = [{"op": "move", "id": k, "x": round(e.nodes[k]["x"], 1), "y": round(e.nodes[k]["y"], 1)} for k in soft_all]
    cmds += [{"op": "show", "ids": soft_all}, {"op": "note", "text": "Logic placed: each cluster pulled toward its wirelength optimum, pushed apart from the others and out of the macros (circle = footprint at 60 percent utilization)."}]
    d = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cmd"); tmp = f"{d}/.{time.time_ns()}.tmp"
    json.dump(cmds, open(tmp, "w")); os.rename(tmp, f"{d}/{time.time_ns()}.json"); print("sent")
    r.destroy()


if __name__ == "__main__":
    main()
