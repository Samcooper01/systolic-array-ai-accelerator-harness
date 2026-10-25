#!/usr/bin/env python3
"""Floorplan editor with the ExecuteController and Scratchpad hierarchy broken open, bus-accurate.

Nodes: hard macros (rectangles, true size): the tile array (8 x 8 Tiles, moves as one grid), the
transposer, AccumulatorScale, the 8 SRAM macros, the seven controller blocks. Soft logic clusters
(circles, area = cell footprint at 60 percent utilization).

Connectivity: every net at this level (bus_graph.json), grouped into buses by name. A bus is drawn
from the average position of the pins that carry it on each macro (so it lands on the right edge of
the right tile or SRAM), or from the centre of a logic cluster. Two views:
  buses  - one line per port: every port of every macro is its own bus, from its pin in the
           abstract, driver to receiver (arrowhead); hover for the port names and width
  pairs  - one line per node pair, all buses summed
Colors: blue = ExecuteController contents, green = Scratchpad contents, purple = controller blocks,
grey = top-level glue. Wires: red >= 1000 bits, orange >= 300, blue below (pairs view); in the bus
view the colour follows the bus width (red >= 128, orange >= 32).

Mouse: drag any node (clicks pass through wires and labels); hover a wire for its bus.
Direction (i): All / Inputs / Outputs. With a block selected: buses into it or out of it; with
nothing selected: buses arriving at or leaving hard-macro pins. Filtered wires take the pin colours
(green = input, yellow = output).
Zoom: mouse wheel (around the cursor) or + / -; f = fit the die; pan: right- or middle-drag.
Keys: e = wires on / off (off by default: the view shows blocks and logic only), arrows nudge the selected node 1 um (Shift 10), x / y / r / 0 = MX / MY / R180 / R0, w = rotate 90 (also R90, R270, MXR90, MYR90 buttons),
  h = hide the selected node and its nets, b = toggle buses / pairs, l = labels, n = names,
  s = save, Ctrl+z = undo.
Visibility panel: tick nodes on and off to floorplan a few at a time; hidden nodes and their nets are
left out of the drawing and of the "visible" score.

Score: sum of bits x Manhattan distance between the two ends of every bus (bit-mm), for everything
and for the visible part only. Positions autosave on every change; the editor starts from the last
autosave. s writes flow/gemmini/macro_place_flat_custom.tcl (every hard macro, each tile individually).

Usage: fpedit_flat.py [layout.json]
"""
import json, math, os, sys, tkinter as tk
from tkinter import ttk

HERE = os.path.dirname(os.path.abspath(__file__))
FLOW = os.path.join(HERE, "..", "flow", "gemmini")
AUTOSAVE = os.path.join(HERE, "flat_graph_autosave.json")
CMD_DIR = os.path.join(HERE, "cmd")          # control channel: JSON command files, applied in name order
CMD_LOG = os.path.join(HERE, "cmd_log.txt")
MARGIN_PX = 30
CORE = 2.0
PARENT_COLOR = {"ExecuteController": "#4c9be8", "Scratchpad": "#5fd18a", "controllers": "#9b7fd6", "top": "#9aa0a6"}
PARENT_NAME = {"ExecuteController": "ExecuteController contents", "Scratchpad": "Scratchpad contents",
               "controllers": "Controller blocks", "top": "Top-level logic"}


ORIENTS = ("R0", "MX", "MY", "R180", "R90", "R270", "MXR90", "MYR90")
ROTATED = ("R90", "R270", "MXR90", "MYR90")


def orient_point(p, w, h, o):
    """Master-relative point -> placed-relative point (LEF/DEF orientations; w, h = unrotated size,
    origin = lower-left of the placed bounding box)."""
    x, y = p
    return {"R0": (x, y), "MX": (x, h - y), "MY": (w - x, y), "R180": (w - x, h - y),
            "R90": (h - y, x), "R270": (y, w - x), "MXR90": (y, x), "MYR90": (h - y, w - x)}.get(o, (x, y))


def dims(v):
    """Placed width and height of a hard node (swapped when rotated by 90 degrees)."""
    return (v["h"], v["w"]) if v.get("orient") in ROTATED else (v["w"], v["h"])


def orient_rect(x, y, w, h, W, H, o):
    """Lower-left corner and size of a sub-rectangle (x, y, w, h) of a W x H block after orienting it."""
    xs, ys = zip(*(orient_point(c, W, H, o) for c in ((x, y), (x + w, y), (x, y + h), (x + w, y + h))))
    return min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)


def blend(c, a, bg="#0b0d10"):
    """Solid colour equal to c drawn at opacity a over the background (Tk has no alpha)."""
    f = lambda h, i: int(h[i:i + 2], 16)
    return "#%02x%02x%02x" % tuple(round(f(c, i) * a + f(bg, i) * (1 - a)) for i in (1, 3, 5))


def short(n):
    return n.replace("ex_controller/mesh (MeshWithDelays)", "MeshWithDelays")


class Editor:
    def __init__(self, root, layout_path):
        base = json.load(open(os.path.join(HERE, "bus_graph.json")))
        self.nodes = {n["id"]: n for n in base["nodes"]}
        self.die = base["die"]
        if layout_path and os.path.exists(layout_path):   # positions from the user's layout
            lay = json.load(open(layout_path)); self.die = lay.get("die", self.die)
            for n in lay["nodes"]:
                if n["id"] in self.nodes:
                    self.nodes[n["id"]].update(x=n["x"], y=n["y"], orient=n.get("orient", "R0"))
        for n in self.nodes.values():
            n.setdefault("orient", "R0")
        self.buses = [b for b in base["buses"] if b["a"] in self.nodes and b["b"] in self.nodes]
        self.ports = base.get("ports", {})
        self.show_ports = tk.BooleanVar(value=False)
        self.show_wires = tk.BooleanVar(value=False)
        self.dirf = tk.StringVar(value="all")
        self.root = root; self.sel = None; self.drag = None; self.undo = []
        self.zoom = 1.0; self.pan = [0.0, 0.0]; self.panning = None
        vis = None
        if layout_path and os.path.exists(layout_path):
            vis = json.load(open(layout_path)).get("visible")
        self.hidden = {k: tk.BooleanVar(value=(vis is None or k in vis)) for k in self.nodes}   # True = visible
        self.show_labels = tk.BooleanVar(value=True); self.show_names = tk.BooleanVar(value=True)
        self.mode = tk.StringVar(value="buses"); self.min_bits = tk.IntVar(value=1)
        self.wire_info = {}

        root.title("Gemmini floorplan editor: ExecuteController and Scratchpad broken open, every bus")
        main = ttk.Frame(root); main.pack(fill="both", expand=True)
        self.cv = tk.Canvas(main, bg="#0b0d10", highlightthickness=0); self.cv.pack(side="left", fill="both", expand=True)
        side = ttk.Frame(main, padding=6); side.pack(side="right", fill="y")

        top = ttk.Frame(side); top.pack(fill="x")
        ttk.Radiobutton(top, text="Pairs", variable=self.mode, value="pairs", command=self.on_mode).pack(side="left")
        ttk.Radiobutton(top, text="Buses (b)", variable=self.mode, value="buses", command=self.on_mode).pack(side="left")
        ttk.Checkbutton(top, text="Labels (l)", variable=self.show_labels, command=self.redraw).pack(side="left", padx=4)
        ttk.Checkbutton(top, text="Names (n)", variable=self.show_names, command=self.redraw).pack(side="left")
        ttk.Checkbutton(top, text="Ports (p)", variable=self.show_ports, command=self.redraw).pack(side="left")
        ttk.Checkbutton(top, text="Wires (e)", variable=self.show_wires, command=self.redraw).pack(side="left")
        df = ttk.Frame(side); df.pack(anchor="w")
        ttk.Label(df, text="Direction (i):").pack(side="left")
        for val, txt in (("all", "All"), ("in", "Inputs"), ("out", "Outputs")):
            ttk.Radiobutton(df, text=txt, variable=self.dirf, value=val, command=self.redraw).pack(side="left")
        self.slider_lbl = ttk.Label(side, text=""); self.slider_lbl.pack(anchor="w")
        self.slider = ttk.Scale(side, from_=1, to=2000, variable=self.min_bits, orient="horizontal", command=lambda *_: self.redraw())
        self.slider.pack(fill="x")
        f = ttk.Frame(side); f.pack(anchor="w", pady=2)
        ttk.Label(f, text="Die").pack(side="left")
        self.dw = tk.StringVar(value=f"{self.die['w']:g}"); self.dh = tk.StringVar(value=f"{self.die['h']:g}")
        ttk.Entry(f, textvariable=self.dw, width=7).pack(side="left"); ttk.Label(f, text="x").pack(side="left")
        ttk.Entry(f, textvariable=self.dh, width=7).pack(side="left")
        ttk.Button(f, text="Apply", command=self.apply_die).pack(side="left", padx=2)
        f3 = ttk.Frame(side); f3.pack(anchor="w", pady=2)
        for o in ORIENTS[:4]:
            ttk.Button(f3, text=o, width=5, command=lambda o=o: self.set_orient(o)).pack(side="left")
        f3b = ttk.Frame(side); f3b.pack(anchor="w")
        for o in ORIENTS[4:]:
            ttk.Button(f3b, text=o, width=6, command=lambda o=o: self.set_orient(o)).pack(side="left")
        self.sel_lbl = ttk.Label(side, text="(none)", width=48); self.sel_lbl.pack(anchor="w")
        self.hover = ttk.Label(side, text="hover a wire for its bus", width=48, foreground="#e0a030"); self.hover.pack(anchor="w")

        # visibility panel
        vis = ttk.LabelFrame(side, text="Visible blocks (h hides the selected one)", padding=4); vis.pack(fill="both", expand=True, pady=4)
        bf = ttk.Frame(vis); bf.pack(fill="x")
        ttk.Button(bf, text="Show all", command=lambda: self.set_all(True)).pack(side="left")
        ttk.Button(bf, text="Hide all", command=lambda: self.set_all(False)).pack(side="left", padx=2)
        ttk.Button(bf, text="Only selected + neighbours", command=self.only_neighbours).pack(side="left")
        lc = tk.Canvas(vis, width=330, height=250, bg="#1b1e24", highlightthickness=0)
        sb = ttk.Scrollbar(vis, orient="vertical", command=lc.yview); inner = ttk.Frame(lc)
        inner.bind("<Configure>", lambda e: lc.configure(scrollregion=lc.bbox("all")))
        lc.create_window((0, 0), window=inner, anchor="nw"); lc.configure(yscrollcommand=sb.set)
        lc.pack(side="left", fill="both", expand=True); sb.pack(side="right", fill="y")
        for parent in ("ExecuteController", "Scratchpad", "controllers", "top"):
            ks = sorted(k for k, v in self.nodes.items() if v["parent"] == parent)
            if not ks: continue
            row = ttk.Frame(inner); row.pack(anchor="w", pady=(4, 0))
            ttk.Label(row, text=PARENT_NAME[parent], font=("TkDefaultFont", 9, "bold")).pack(side="left")
            ttk.Button(row, text="on", width=3, command=lambda p=parent: self.set_parent(p, True)).pack(side="left", padx=2)
            ttk.Button(row, text="off", width=3, command=lambda p=parent: self.set_parent(p, False)).pack(side="left")
            for k in ks:
                ttk.Checkbutton(inner, text=short(k), variable=self.hidden[k], command=self.redraw).pack(anchor="w", padx=10)

        self.score_lbl = ttk.Label(side, text="", font=("TkDefaultFont", 10, "bold")); self.score_lbl.pack(anchor="w")
        self.detail = tk.Text(side, width=50, height=12, bg="#15181d", fg="#dddddd", relief="flat", font=("TkFixedFont", 8))
        self.detail.pack(fill="x", pady=2)
        f4 = ttk.Frame(side); f4.pack(anchor="w")
        ttk.Button(f4, text="Save (s)", command=self.save).pack(side="left")
        ttk.Button(f4, text="Undo (Ctrl+z)", command=self.do_undo).pack(side="left", padx=4)
        self.status = ttk.Label(side, text="", wraplength=330); self.status.pack(anchor="w")

        self.cv.bind("<Configure>", lambda e: self.redraw())
        self.cv.bind("<ButtonPress-1>", self.on_press); self.cv.bind("<B1-Motion>", self.on_drag)
        self.cv.bind("<ButtonRelease-1>", lambda e: setattr(self, "drag", None))
        self.cv.bind("<Motion>", self.on_motion)
        # zoom: mouse wheel (X11 buttons 4/5, or MouseWheel), + / - keys, f = fit; pan: right or middle drag
        self.cv.bind("<Button-4>", lambda e: self.zoom_at(e.x, e.y, 1.25))
        self.cv.bind("<Button-5>", lambda e: self.zoom_at(e.x, e.y, 0.8))
        self.cv.bind("<MouseWheel>", lambda e: self.zoom_at(e.x, e.y, 1.25 if e.delta > 0 else 0.8))
        for b in ("<ButtonPress-2>", "<ButtonPress-3>"):
            self.cv.bind(b, lambda e: setattr(self, "panning", (e.x, e.y)))
        for b in ("<B2-Motion>", "<B3-Motion>"):
            self.cv.bind(b, self.on_pan)
        root.bind("<Key>", self.on_key); root.bind("<Control-z>", lambda e: self.do_undo())
        self.claude = ttk.Label(side, text="", wraplength=330, foreground="#7fd1ff"); self.claude.pack(anchor="w", pady=(4, 0))
        os.makedirs(CMD_DIR, exist_ok=True)
        self.on_mode()
        self.root.after(500, self.poll_commands)

    # ---------- geometry ----------
    def scale(self):
        cw, ch = max(self.cv.winfo_width(), 200), max(self.cv.winfo_height(), 200)
        return min((cw - 2 * MARGIN_PX) / self.die["w"], (ch - 2 * MARGIN_PX) / self.die["h"]) * self.zoom

    def to_px(self, x, y):
        s = self.scale(); return MARGIN_PX + self.pan[0] + x * s, self.cv.winfo_height() - MARGIN_PX + self.pan[1] - y * s

    def to_um(self, px, py):
        s = self.scale(); return (px - MARGIN_PX - self.pan[0]) / s, (self.cv.winfo_height() - MARGIN_PX + self.pan[1] - py) / s

    def zoom_at(self, px, py, factor):
        """Zoom by factor keeping the point under the cursor fixed."""
        ux, uy = self.to_um(px, py)
        self.zoom = min(max(self.zoom * factor, 0.2), 200.0)
        nx, ny = self.to_px(ux, uy)
        self.pan[0] += px - nx; self.pan[1] += py - ny
        self.redraw()

    def fit(self):
        self.zoom = 1.0; self.pan = [0.0, 0.0]; self.redraw()

    def center(self, n):
        v = self.nodes[n]
        if v["kind"] == "soft": return (v["x"], v["y"])
        w, h = dims(v); return (v["x"] + w / 2, v["y"] + h / 2)

    def end(self, n, p):
        """Position of a bus end: the pin centroid on a macro (orientation applied) or the node centre."""
        v = self.nodes[n]
        if p is None or v["kind"] == "soft":
            return self.center(n)
        x, y = orient_point(p, v["w"], v["h"], v["orient"])
        return v["x"] + x, v["y"] + y

    def visible(self, n):
        return self.hidden[n].get()

    # ---------- connectivity views ----------
    def wires(self):
        """(a, b, bits, (xa, ya), (xb, yb), label) for the current view."""
        out = []
        if self.mode.get() == "buses":
            for b in self.buses:
                out.append((b["a"], b["b"], b["bits"], self.end(b["a"], b["pa"]), self.end(b["b"], b["pb"]), b["name"]))
        else:
            agg = {}
            for b in self.buses:
                k = tuple(sorted((b["a"], b["b"])))
                pa, pb = (self.end(b["a"], b["pa"]), self.end(b["b"], b["pb"])) if k[0] == b["a"] else (self.end(b["b"], b["pb"]), self.end(b["a"], b["pa"]))
                r = agg.setdefault(k, [0, 0.0, 0.0, 0.0, 0.0, 0])
                r[0] += b["bits"]; r[1] += pa[0] * b["bits"]; r[2] += pa[1] * b["bits"]; r[3] += pb[0] * b["bits"]; r[4] += pb[1] * b["bits"]; r[5] += 1
            for (a, c), (n, x1, y1, x2, y2, nb) in agg.items():
                out.append((a, c, n, (x1 / n, y1 / n), (x2 / n, y2 / n), f"{nb} buses"))
        return out

    def metrics(self):
        tot = vis = 0.0; per = []
        for b in self.buses:
            (x1, y1), (x2, y2) = self.end(b["a"], b["pa"]), self.end(b["b"], b["pb"])
            c = b["bits"] * (abs(x1 - x2) + abs(y1 - y2)); tot += c
            if self.visible(b["a"]) and self.visible(b["b"]):
                vis += c; per.append((c, b))
        warn = []
        hard = [k for k, v in self.nodes.items() if v["kind"] == "hard" and self.visible(k)]
        for k in hard:
            v = self.nodes[k]; w, h = dims(v)
            if v["x"] < CORE or v["y"] < CORE or v["x"] + w > self.die["w"] - CORE or v["y"] + h > self.die["h"] - CORE:
                warn.append(f"outside core: {k}")
        for i in range(len(hard)):
            for j in range(i + 1, len(hard)):
                a, b = self.nodes[hard[i]], self.nodes[hard[j]]; (aw, ah), (bw, bh) = dims(a), dims(b)
                if a["x"] < b["x"] + bw and b["x"] < a["x"] + aw and a["y"] < b["y"] + bh and b["y"] < a["y"] + ah:
                    warn.append(f"OVERLAP: {short(hard[i])} / {short(hard[j])}")
        return tot, vis, sorted(per, key=lambda t: -t[0]), warn

    # ---------- drawing ----------
    def redraw(self):
        cv = self.cv; cv.delete("all"); self.wire_info = {}
        s = self.scale()
        x0, y0 = self.to_px(0, self.die["h"]); x1, y1 = self.to_px(self.die["w"], 0)
        cv.create_rectangle(x0, y0, x1, y1, outline="#888888", width=2)
        for k, v in self.nodes.items():
            if not self.visible(k): continue
            col = PARENT_COLOR.get(v["parent"], "#9aa0a6")
            if v["kind"] == "hard":
                vw, vh = dims(v)
                ax, ay = self.to_px(v["x"], v["y"] + vh); bx, by = self.to_px(v["x"] + vw, v["y"])
                cv.create_rectangle(ax, ay, bx, by, fill=blend(col, 0.25 if "grid" in v else 0.5),
                                    outline="#ffffff" if k == self.sel else col, width=3 if k == self.sel else 1, tags=("node", k))
                if "grid" in v:
                    tw, th = v["tile"]
                    for gx, gy, _ in v["grid"]:
                        px, py, rw, rh = orient_rect(gx, gy, tw, th, v["w"], v["h"], v["orient"])
                        tx, ty = self.to_px(v["x"] + px, v["y"] + py + rh); ux, uy = self.to_px(v["x"] + px + rw, v["y"] + py)
                        cv.create_rectangle(tx, ty, ux, uy, fill=blend(col, 0.85), outline="", tags=("node", k))
                if self.show_names.get():
                    cv.create_text((ax + bx) / 2, (ay + by) / 2, text=v["label"] + ("" if v["orient"] == "R0" else f"  [{v['orient']}]"),
                                   fill="#ffffff", font=("TkDefaultFont", 8), tags=("node", k))
            else:
                r = math.sqrt(v["area"] / math.pi) * s; cx, cy = self.to_px(v["x"], v["y"])
                cv.create_oval(cx - r, cy - r, cx + r, cy + r, fill=blend(col, 0.4),
                               outline="#ffffff", width=3 if k == self.sel else 0.6, tags=("node", k))
                if self.show_names.get():
                    cv.create_text(cx, cy, text=short(v["label"]), fill="#ffffff", font=("TkDefaultFont", 7), tags=("node", k))
        if self.show_ports.get():
            for k, plist in self.ports.items():
                if not self.visible(k): continue
                v = self.nodes[k]
                dsel = self.dirf.get()
                if self.sel and k != self.sel and dsel != "all": continue
                for pt in plist:
                    if (dsel == "in" and pt["dir"] == "OUTPUT") or (dsel == "out" and pt["dir"] != "OUTPUT"): continue
                    x, y = orient_point((pt["x"], pt["y"]), v["w"], v["h"], v["orient"])
                    px, py = self.to_px(v["x"] + x, v["y"] + y)
                    c = "#ffd24d" if pt["dir"] == "OUTPUT" else "#7ee0a1"
                    pid = cv.create_rectangle(px - 2, py - 2, px + 2, py + 2, fill=c, outline="", tags=("wire",))
                    self.wire_info[pid] = f"port {short(k)}.{pt['name']}  ({pt['dir'].lower()}, {pt['bits']} bits)"
        mb = int(self.min_bits.get()); buses = self.mode.get() == "buses"
        dsel = self.dirf.get()
        hard = lambda x: self.nodes[x]["kind"] == "hard"
        for a, b, n, pa, pb, name in (sorted(self.wires(), key=lambda w: w[2]) if self.show_wires.get() else []):
            if n < mb or not (self.visible(a) and self.visible(b)): continue
            if dsel != "all" and buses:
                if self.sel:
                    if (dsel == "in" and b != self.sel) or (dsel == "out" and a != self.sel): continue
                else:
                    if (dsel == "in" and not hard(b)) or (dsel == "out" and not hard(a)): continue
            (xa, ya), (xb, yb) = self.to_px(*pa), self.to_px(*pb)
            if buses:
                col = "#ff5f5f" if n >= 128 else "#ffb347" if n >= 32 else "#9ad1ff"; w = 0.5 + 0.7 * math.log10(n + 1)
                if dsel == "in": col = "#7ee0a1"
                elif dsel == "out": col = "#ffd24d"
            else:
                col = "#ff5f5f" if n >= 1000 else "#ffb347" if n >= 300 else "#9ad1ff"; w = 0.6 + 1.1 * math.log10(n)
            wid = cv.create_line(xa, ya, xb, yb, fill=col, width=w, capstyle="round", tags=("wire",),
                                 arrow="last" if buses else "none", arrowshape=(7, 8, 3))
            self.wire_info[wid] = f"{short(a)} -> {short(b)}: {name}  ({n} bits)"
            cv.create_oval(xa - 2, ya - 2, xa + 2, ya + 2, fill=col, outline="", tags=("wire",))
            cv.create_oval(xb - 2, yb - 2, xb + 2, yb + 2, fill=col, outline="", tags=("wire",))
            if self.show_labels.get() and (not buses or n >= 16):
                tid = cv.create_text((xa + xb) / 2, (ya + yb) / 2, text=str(n), fill=col, font=("TkDefaultFont", 12 if not buses else 10, "bold"), tags=("wire",))
                self.wire_info[tid] = self.wire_info[wid]
                bx0, by0, bx1, by1 = cv.bbox(tid)
                cv.tag_lower(cv.create_rectangle(bx0 - 2, by0 - 1, bx1 + 2, by1 + 1, fill="#0b0d10", outline="", tags=("wire",)), tid)
        tot, vis, per, warn = self.metrics()
        self.score_lbl.config(text=f"Wirelength: {vis / 1000:,.0f} bit-mm visible  /  {tot / 1000:,.0f} total")
        t = self.detail; t.delete("1.0", "end")
        if warn:
            t.insert("end", "WARNINGS\n" + "\n".join(warn[:8]) + "\n\n")
        t.insert("end", "largest visible buses (bit-mm, bits):\n")
        for c, b in per[:12]:
            t.insert("end", f"{c / 1000:6.0f} {b['bits']:5d} {short(b['a'])[:14]}>{short(b['b'])[:14]} {b['name'][-22:]}\n")
        self.sel_lbl.config(text=f"selected: {short(self.sel)}  ({self.nodes[self.sel]['kind']})" if self.sel else "(none)")
        self.autosave()

    # ---------- interaction ----------
    def on_mode(self):
        if self.mode.get() == "buses":
            self.slider.configure(to=256); self.min_bits.set(min(self.min_bits.get(), 32))
            self.slider_lbl.config(text="Hide buses narrower than N bits")
        else:
            self.slider.configure(to=2000); self.min_bits.set(max(self.min_bits.get(), 1))
            self.slider_lbl.config(text="Hide node pairs with fewer than N bits")
        self.redraw()

    def on_pan(self, ev):
        if self.panning:
            self.pan[0] += ev.x - self.panning[0]; self.pan[1] += ev.y - self.panning[1]
            self.panning = (ev.x, ev.y); self.redraw()

    def on_motion(self, ev):
        for item in reversed(self.cv.find_overlapping(ev.x - 3, ev.y - 3, ev.x + 3, ev.y + 3)):
            if item in self.wire_info:
                self.hover.config(text=self.wire_info[item]); return
        self.hover.config(text="")

    def set_all(self, on):
        for v in self.hidden.values(): v.set(on)
        self.redraw()

    def set_parent(self, parent, on):
        for k, v in self.nodes.items():
            if v["parent"] == parent: self.hidden[k].set(on)
        self.redraw()

    def only_neighbours(self):
        if not self.sel: return
        keep = {self.sel} | {b["b"] for b in self.buses if b["a"] == self.sel} | {b["a"] for b in self.buses if b["b"] == self.sel}
        for k, v in self.hidden.items(): v.set(k in keep)
        self.redraw()

    def snapshot(self):
        self.undo.append({k: (v["x"], v["y"], v["orient"]) for k, v in self.nodes.items()}); self.undo = self.undo[-100:]

    def do_undo(self):
        if self.undo:
            for k, (x, y, o) in self.undo.pop().items():
                self.nodes[k].update(x=x, y=y, orient=o)
            self.redraw()

    def on_press(self, ev):
        tags = []
        for item in reversed(self.cv.find_overlapping(ev.x - 1, ev.y - 1, ev.x + 1, ev.y + 1)):
            it = self.cv.gettags(item)
            if "node" in it:
                tags = [t for t in it if t not in ("node", "current")]; break
        if tags and tags[0] in self.nodes:
            self.sel = tags[0]; self.snapshot()
            if self.dirf.get() != "all" and self.mode.get() != "buses":
                self.mode.set("buses"); self.on_mode()
            ux, uy = self.to_um(ev.x, ev.y); v = self.nodes[self.sel]
            self.drag = (ux - v["x"], uy - v["y"])
        else:
            self.sel = None; self.drag = None
        self.redraw()

    def on_drag(self, ev):
        if self.sel and self.drag:
            ux, uy = self.to_um(ev.x, ev.y); v = self.nodes[self.sel]
            v["x"] = round(ux - self.drag[0], 1); v["y"] = round(uy - self.drag[1], 1); self.redraw()

    def on_key(self, ev):
        k = ev.keysym
        if isinstance(ev.widget, (tk.Entry, ttk.Entry)): return
        if k == "l": self.show_labels.set(not self.show_labels.get()); self.redraw(); return
        if k == "n": self.show_names.set(not self.show_names.get()); self.redraw(); return
        if k == "p": self.show_ports.set(not self.show_ports.get()); self.redraw(); return
        if k == "e": self.show_wires.set(not self.show_wires.get()); self.redraw(); return
        if k == "i": self.dirf.set({"all": "in", "in": "out", "out": "all"}[self.dirf.get()]); self.redraw(); return
        if k in ("plus", "equal", "KP_Add"): self.zoom_at(self.cv.winfo_width() / 2, self.cv.winfo_height() / 2, 1.25); return
        if k in ("minus", "KP_Subtract"): self.zoom_at(self.cv.winfo_width() / 2, self.cv.winfo_height() / 2, 0.8); return
        if k == "f": self.fit(); return
        if k == "b": self.mode.set("pairs" if self.mode.get() == "buses" else "buses"); self.on_mode(); return
        if k == "s": self.save(); return
        if not self.sel: return
        if k == "h":
            self.hidden[self.sel].set(False); self.sel = None; self.redraw(); return
        v = self.nodes[self.sel]; step = 10.0 if ev.state & 0x1 else 1.0
        mv = {"Left": (-step, 0), "Right": (step, 0), "Up": (0, step), "Down": (0, -step)}
        if k in mv:
            self.snapshot(); v["x"] = round(v["x"] + mv[k][0], 1); v["y"] = round(v["y"] + mv[k][1], 1); self.redraw()
        elif k in ("x", "y", "r", "0"):
            self.set_orient({"x": "MX", "y": "MY", "r": "R180", "0": "R0"}[k])
        elif k == "w":   # rotate by 90 degrees counter-clockwise, keeping any mirror
            nxt = {"R0": "R90", "R90": "R180", "R180": "R270", "R270": "R0",
                   "MX": "MXR90", "MXR90": "MY", "MY": "MYR90", "MYR90": "MX"}
            self.set_orient(nxt.get(v["orient"], "R0"))

    def set_orient(self, o):
        if self.sel and self.nodes[self.sel]["kind"] == "hard":
            self.snapshot(); self.nodes[self.sel]["orient"] = o
            msg = ""
            if self.sel == "tile_array" and o != "R0":
                msg = "Mirroring or rotating the tile array puts Tile pins off the routing grid; keep it R0."
            elif o in ROTATED:
                msg = ("Rotated macro: its pins change layer direction (horizontal pins become vertical), so check "
                       "the pins still land on routing tracks; the flow could not snap rotated SRAMs earlier.")
            self.status.config(text=msg)
            self.redraw()

    def apply_die(self):
        try:
            self.die = {"w": float(self.dw.get()), "h": float(self.dh.get())}
        except ValueError:
            return
        self.redraw()

    def poll_commands(self):
        """Apply command files dropped in fpedit/cmd/ (written by fpctl.py), then delete them.
        Ops: show / hide {ids}, only {ids}, move {id, x, y}, nudge {id, dx, dy}, orient {id, o},
        die {w, h}, mode {m}, select {id}, min_bits {n}, note {text}."""
        try:
            files = sorted(f for f in os.listdir(CMD_DIR) if f.endswith(".json"))
        except OSError:
            files = []
        changed = False
        for fn in files:
            path = os.path.join(CMD_DIR, fn)
            try:
                cmds = json.load(open(path)); os.remove(path)
            except (OSError, ValueError):
                continue
            if isinstance(cmds, dict): cmds = [cmds]
            for c in cmds:
                msg = self.apply_command(c); changed = True
                with open(CMD_LOG, "a") as lg:
                    lg.write(json.dumps(c) + "  ->  " + msg + "\n")
        if changed:
            self.redraw()
        self.root.after(500, self.poll_commands)

    def apply_command(self, c):
        op = c.get("op"); ids = c.get("ids", [])
        bad = [i for i in ids + ([c["id"]] if "id" in c else []) if i not in self.nodes]
        if bad:
            return f"unknown ids {bad}"
        if op in ("show", "hide"):
            for i in ids: self.hidden[i].set(op == "show")
        elif op == "only":
            for k, v in self.hidden.items(): v.set(k in ids)
        elif op == "move":
            self.snapshot(); self.nodes[c["id"]].update(x=float(c["x"]), y=float(c["y"]))
        elif op == "nudge":
            self.snapshot(); v = self.nodes[c["id"]]; v["x"] += float(c.get("dx", 0)); v["y"] += float(c.get("dy", 0))
        elif op == "orient":
            self.snapshot(); self.nodes[c["id"]]["orient"] = c["o"]
        elif op == "die":
            self.die = {"w": float(c["w"]), "h": float(c["h"])}; self.dw.set(f"{c['w']:g}"); self.dh.set(f"{c['h']:g}")
        elif op == "mode":
            self.mode.set(c["m"]); self.on_mode()
        elif op == "select":
            self.sel = c["id"]
        elif op == "min_bits":
            self.min_bits.set(int(c["n"]))
        elif op == "note":
            pass
        elif op == "snapshot":   # write what the canvas shows, for Claude to look at
            self.redraw(); self.cv.update()
            self.cv.postscript(file=os.path.join(HERE, "gui_snapshot.ps"), colormode="color")
        else:
            return "unknown op"
        if c.get("text") or op == "note":
            self.claude.config(text="Claude: " + c.get("text", ""))
        return "ok"

    def layout(self):
        return {"die": self.die, "nodes": [{"id": k, "x": v["x"], "y": v["y"], "orient": v["orient"]} for k, v in self.nodes.items()],
                "visible": [k for k, v in self.hidden.items() if v.get()], "selected": self.sel,
                "mode": self.mode.get(), "min_bits": int(self.min_bits.get())}

    def autosave(self):
        try:
            json.dump(self.layout(), open(AUTOSAVE, "w"))
        except OSError:
            pass

    def save(self):
        tot, _, _, warn = self.metrics()
        tcl = os.path.normpath(os.path.join(FLOW, "macro_place_flat_custom.tcl"))
        with open(tcl, "w") as f:
            f.write(f"# Floorplan written by fpedit_flat.py for a top level where ExecuteController and Scratchpad are not\n"
                    f"# hardened. Die {self.die['w']:g} x {self.die['h']:g} um. Bus wirelength {tot / 1000:,.0f} bit-mm.\n")
            if warn:
                f.write("# WARNINGS at save time: " + "; ".join(warn[:20]) + "\n")
            for k, v in sorted(self.nodes.items()):
                if v["kind"] != "hard": continue
                if "grid" in v:
                    tw, th = v["tile"]
                    for gx, gy, name in v["grid"]:
                        px, py, _, _ = orient_rect(gx, gy, tw, th, v["w"], v["h"], v["orient"])
                        f.write(f"place_macro -macro_name {{{name}}} -location {{{v['x'] + px:.3f} {v['y'] + py:.3f}}} -orientation {v['orient']}\n")
                else:
                    f.write(f"place_macro -macro_name {{{v['inst']}}} -location {{{v['x']:.3f} {v['y']:.3f}}} -orientation {v['orient']}\n")
        js = os.path.join(HERE, "flat_graph_edited.json"); json.dump(self.layout(), open(js, "w"), indent=1)
        self.status.config(text=f"Saved {tcl}\nand {js}" + ("\n(with warnings)" if warn else ""))


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else (AUTOSAVE if os.path.exists(AUTOSAVE) else None)
    print("layout from", path)
    root = tk.Tk(); root.geometry("1750x1000"); Editor(root, path); root.mainloop()


if __name__ == "__main__":
    main()
