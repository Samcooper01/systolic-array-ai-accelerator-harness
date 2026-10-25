#!/usr/bin/env python3
"""Top-level floorplan editor for the Gemmini reference.

Drag the hardened blocks around the die and watch their connectivity. Every block pair that shares
nets is drawn as a line between the centroids of the pins that carry those nets (so flipping or
moving a block moves the line ends correctly); the line width and label are the number of bits.

Mouse: drag a block to move it; click empty space to deselect.
Keys (on the selected block): arrows nudge 1 um (Shift: 10 um), x = mirror top/bottom (MX),
  y = mirror left/right (MY), r = rotate 180 (R180), 0 = back to R0.
Keys (global): l = toggle bit labels, g = toggle glue counts, s = save, Ctrl+z = undo.

Score: sum over block pairs of bits x Manhattan distance between the two pin centroids (bit-mm),
the same quantity global placement minimizes, restricted to block-to-block nets. Lower is better.
Warnings: overlaps, blocks outside the core, and pairs of blocks closer than the minimum channel.

Save writes flow/gemmini/macro_place_top_custom.tcl (place_macro lines, readable by the flow as
MACRO_PLACEMENT_TCL) and fpedit/top_graph_edited.json.

Usage: fpedit.py [top_graph.json]
"""
import json, math, os, sys, tkinter as tk
from tkinter import ttk

HERE = os.path.dirname(os.path.abspath(__file__))
FLOW = os.path.join(HERE, "..", "flow", "gemmini")
MARGIN_PX = 30
CORE_OFFSET = 2.0            # core inset from the die edge, um
MIN_CHANNEL = 10.0           # warn when two blocks are closer than this, um

COLORS = {"ExecuteController": "#4c9be8", "Scratchpad": "#5fd18a"}
DEFAULT_BLOCK = "#9b7fd6"


def orient_point(p, w, h, o):
    x, y = p
    return {"R0": (x, y), "MX": (x, h - y), "MY": (w - x, y), "R180": (w - x, h - y)}.get(o, (x, y))


class Editor:
    def __init__(self, root, path):
        self.root = root
        self.path = path
        g = json.load(open(path))
        self.die = g["die"]
        self.blocks = {b["inst"]: b for b in g["blocks"]}
        self.edges = g["edges"]
        self.glue = {e["inst"]: e for e in g["glue"]}
        self.sel = None
        self.drag = None
        self.undo = []
        self.show_labels = tk.BooleanVar(value=True)
        self.show_glue = tk.BooleanVar(value=True)
        self.min_bits = tk.IntVar(value=1)

        root.title("Gemmini top-level floorplan editor")
        main = ttk.Frame(root); main.pack(fill="both", expand=True)
        self.cv = tk.Canvas(main, bg="#0b0d10", highlightthickness=0)
        self.cv.pack(side="left", fill="both", expand=True)
        side = ttk.Frame(main, padding=8); side.pack(side="right", fill="y")

        ttk.Label(side, text="Die (um)").pack(anchor="w")
        f = ttk.Frame(side); f.pack(anchor="w")
        self.die_w = tk.StringVar(value=f"{self.die['w']:g}"); self.die_h = tk.StringVar(value=f"{self.die['h']:g}")
        ttk.Entry(f, textvariable=self.die_w, width=8).pack(side="left")
        ttk.Label(f, text=" x ").pack(side="left")
        ttk.Entry(f, textvariable=self.die_h, width=8).pack(side="left")
        ttk.Button(side, text="Apply die size", command=self.apply_die).pack(anchor="w", pady=(2, 8))

        ttk.Label(side, text="Hide pairs under N bits").pack(anchor="w")
        ttk.Scale(side, from_=1, to=500, variable=self.min_bits, orient="horizontal", command=lambda *_: self.redraw()).pack(fill="x")
        ttk.Checkbutton(side, text="Bit labels (l)", variable=self.show_labels, command=self.redraw).pack(anchor="w")
        ttk.Checkbutton(side, text="Glue / die-pin counts (g)", variable=self.show_glue, command=self.redraw).pack(anchor="w", pady=(0, 8))

        ttk.Label(side, text="Selected").pack(anchor="w")
        self.sel_lbl = ttk.Label(side, text="(none)", width=34); self.sel_lbl.pack(anchor="w")
        f2 = ttk.Frame(side); f2.pack(anchor="w", pady=2)
        self.ex = tk.StringVar(); self.ey = tk.StringVar()
        ttk.Label(f2, text="x").pack(side="left"); ttk.Entry(f2, textvariable=self.ex, width=8).pack(side="left")
        ttk.Label(f2, text=" y").pack(side="left"); ttk.Entry(f2, textvariable=self.ey, width=8).pack(side="left")
        ttk.Button(side, text="Set position", command=self.set_pos).pack(anchor="w")
        f3 = ttk.Frame(side); f3.pack(anchor="w", pady=4)
        for o in ("R0", "MX", "MY", "R180"):
            ttk.Button(f3, text=o, width=5, command=lambda o=o: self.set_orient(o)).pack(side="left")

        ttk.Separator(side).pack(fill="x", pady=8)
        self.score_lbl = ttk.Label(side, text="", font=("TkDefaultFont", 11, "bold")); self.score_lbl.pack(anchor="w")
        self.detail = tk.Text(side, width=40, height=22, bg="#15181d", fg="#dddddd", relief="flat", font=("TkFixedFont", 9))
        self.detail.pack(fill="y", expand=True, pady=4)
        f4 = ttk.Frame(side); f4.pack(anchor="w", pady=4)
        ttk.Button(f4, text="Save (s)", command=self.save).pack(side="left")
        ttk.Button(f4, text="Undo (Ctrl+z)", command=self.do_undo).pack(side="left", padx=4)
        self.status = ttk.Label(side, text="", wraplength=280); self.status.pack(anchor="w")

        self.cv.bind("<Configure>", lambda e: self.redraw())
        self.cv.bind("<ButtonPress-1>", self.on_press)
        self.cv.bind("<B1-Motion>", self.on_drag)
        self.cv.bind("<ButtonRelease-1>", self.on_release)
        root.bind("<Key>", self.on_key)
        root.bind("<Control-z>", lambda e: self.do_undo())

    # ---------- geometry ----------
    def scale(self):
        cw, ch = max(self.cv.winfo_width(), 200), max(self.cv.winfo_height(), 200)
        return min((cw - 2 * MARGIN_PX) / self.die["w"], (ch - 2 * MARGIN_PX) / self.die["h"])

    def to_px(self, x, y):
        s = self.scale(); return MARGIN_PX + x * s, self.cv.winfo_height() - MARGIN_PX - y * s

    def to_um(self, px, py):
        s = self.scale(); return (px - MARGIN_PX) / s, (self.cv.winfo_height() - MARGIN_PX - py) / s

    def pin(self, inst, p):
        b = self.blocks[inst]
        x, y = orient_point(p, b["w"], b["h"], b["orient"])
        return b["x"] + x, b["y"] + y

    # ---------- metrics ----------
    def metrics(self):
        wl = 0.0; per = []
        for e in self.edges:
            (x1, y1), (x2, y2) = self.pin(e["a"], e["pa"]), self.pin(e["b"], e["pb"])
            d = abs(x1 - x2) + abs(y1 - y2); wl += e["bits"] * d; per.append((e["bits"] * d, e))
        warn = []
        lo, hx, hy = CORE_OFFSET, self.die["w"] - CORE_OFFSET, self.die["h"] - CORE_OFFSET
        names = sorted(self.blocks)
        for n in names:
            b = self.blocks[n]
            if b["x"] < lo or b["y"] < lo or b["x"] + b["w"] > hx or b["y"] + b["h"] > hy:
                warn.append(f"outside core: {n}")
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                a, c = self.blocks[names[i]], self.blocks[names[j]]
                gx = max(c["x"] - (a["x"] + a["w"]), a["x"] - (c["x"] + c["w"]))
                gy = max(c["y"] - (a["y"] + a["h"]), a["y"] - (c["y"] + c["h"]))
                if gx < 0 and gy < 0:
                    warn.append(f"OVERLAP: {names[i]} / {names[j]}")
                elif max(gx, gy) < MIN_CHANNEL:
                    warn.append(f"channel {max(gx, gy):.1f} um: {names[i]} / {names[j]}")
        return wl, sorted(per, key=lambda t: -t[0]), warn

    # ---------- drawing ----------
    def redraw(self):
        cv = self.cv; cv.delete("all")
        x0, y0 = self.to_px(0, self.die["h"]); x1, y1 = self.to_px(self.die["w"], 0)
        cv.create_rectangle(x0, y0, x1, y1, outline="#888888", width=2)
        for n, b in self.blocks.items():
            ax, ay = self.to_px(b["x"], b["y"] + b["h"]); bx, by = self.to_px(b["x"] + b["w"], b["y"])
            fill = COLORS.get(b["master"], DEFAULT_BLOCK)
            cv.create_rectangle(ax, ay, bx, by, fill=fill, stipple="gray50", outline="#ffffff" if n == self.sel else fill,
                                width=3 if n == self.sel else 1, tags=("block", n))
            label = f"{b['master']}\n{b['w']:.0f} x {b['h']:.0f}  {b['orient']}"
            if self.show_glue.get() and n in self.glue:
                label += f"\n+{self.glue[n]['bits']} b to top logic / pins"
            cv.create_text((ax + bx) / 2, (ay + by) / 2, text=label, fill="#ffffff", font=("TkDefaultFont", 9), tags=("block", n))
        mb = int(self.min_bits.get())
        for e in sorted(self.edges, key=lambda e: e["bits"]):
            if e["bits"] < mb:
                continue
            (xa, ya), (xb, yb) = self.to_px(*self.pin(e["a"], e["pa"])), self.to_px(*self.pin(e["b"], e["pb"]))
            w = 1 + 2.5 * math.log10(e["bits"])
            col = "#ff5f5f" if e["bits"] >= 1000 else "#ffb347" if e["bits"] >= 200 else "#9ad1ff"
            cv.create_line(xa, ya, xb, yb, fill=col, width=w, capstyle="round")
            cv.create_oval(xa - 3, ya - 3, xa + 3, ya + 3, fill=col, outline="")
            cv.create_oval(xb - 3, yb - 3, xb + 3, yb + 3, fill=col, outline="")
            if self.show_labels.get():
                cv.create_text((xa + xb) / 2, (ya + yb) / 2, text=str(e["bits"]), fill=col, font=("TkDefaultFont", 9, "bold"))
        wl, per, warn = self.metrics()
        self.score_lbl.config(text=f"Weighted wirelength: {wl / 1000:,.1f} bit-mm")
        t = self.detail; t.delete("1.0", "end")
        if warn:
            t.insert("end", "WARNINGS\n" + "\n".join(warn) + "\n\n")
        t.insert("end", "largest contributors (bit-mm):\n")
        for c, e in per[:14]:
            t.insert("end", f"{c / 1000:8.1f}  {e['bits']:5d}b  {e['a']} - {e['b']}\n")
        if self.sel:
            b = self.blocks[self.sel]
            self.sel_lbl.config(text=f"{self.sel} ({b['master']})")
            self.ex.set(f"{b['x']:.3f}"); self.ey.set(f"{b['y']:.3f}")
        else:
            self.sel_lbl.config(text="(none)")

    # ---------- interaction ----------
    def snapshot(self):
        self.undo.append({n: (b["x"], b["y"], b["orient"]) for n, b in self.blocks.items()})
        self.undo = self.undo[-100:]

    def do_undo(self):
        if not self.undo:
            return
        for n, (x, y, o) in self.undo.pop().items():
            self.blocks[n].update(x=x, y=y, orient=o)
        self.redraw()

    def on_press(self, ev):
        hit = [t for t in self.cv.gettags(self.cv.find_withtag("current")) if t not in ("block", "current")] if self.cv.find_withtag("current") else []
        if hit and hit[0] in self.blocks:
            self.sel = hit[0]; self.snapshot()
            ux, uy = self.to_um(ev.x, ev.y); b = self.blocks[self.sel]
            self.drag = (ux - b["x"], uy - b["y"])
        else:
            self.sel = None; self.drag = None
        self.redraw()

    def on_drag(self, ev):
        if not (self.sel and self.drag):
            return
        ux, uy = self.to_um(ev.x, ev.y); b = self.blocks[self.sel]
        b["x"] = round(ux - self.drag[0], 1); b["y"] = round(uy - self.drag[1], 1)
        self.redraw()

    def on_release(self, ev):
        self.drag = None

    def on_key(self, ev):
        k = ev.keysym
        if k == "l":
            self.show_labels.set(not self.show_labels.get()); self.redraw(); return
        if k == "g":
            self.show_glue.set(not self.show_glue.get()); self.redraw(); return
        if k == "s" and not (ev.state & 0x4):
            self.save(); return
        if not self.sel or isinstance(ev.widget, (tk.Entry, ttk.Entry)):
            return
        b = self.blocks[self.sel]; step = 10.0 if ev.state & 0x1 else 1.0
        moves = {"Left": (-step, 0), "Right": (step, 0), "Up": (0, step), "Down": (0, -step)}
        if k in moves:
            self.snapshot(); b["x"] = round(b["x"] + moves[k][0], 1); b["y"] = round(b["y"] + moves[k][1], 1)
        elif k in ("x", "y", "r", "0"):
            self.set_orient({"x": "MX", "y": "MY", "r": "R180", "0": "R0"}[k]); return
        self.redraw()

    def set_orient(self, o):
        if not self.sel:
            return
        self.snapshot(); self.blocks[self.sel]["orient"] = o
        self.status.config(text="Note: mirrored blocks put pins off the routing grid unless the block's width "
                                "(MY) or height (MX) is a multiple of the track pitch; check before using." if o != "R0" else "")
        self.redraw()

    def set_pos(self):
        if not self.sel:
            return
        try:
            x, y = float(self.ex.get()), float(self.ey.get())
        except ValueError:
            return
        self.snapshot(); self.blocks[self.sel].update(x=x, y=y); self.redraw()

    def apply_die(self):
        try:
            self.die = {"w": float(self.die_w.get()), "h": float(self.die_h.get())}
        except ValueError:
            return
        self.redraw()

    def save(self):
        wl, _, warn = self.metrics()
        tcl = os.path.normpath(os.path.join(FLOW, "macro_place_top_custom.tcl"))
        with open(tcl, "w") as f:
            f.write(f"# Top-level floorplan written by fpedit.py. Die {self.die['w']:g} x {self.die['h']:g} um "
                    f"(set DIE_AREA to match). Weighted block-to-block wirelength {wl / 1000:,.1f} bit-mm.\n")
            if warn:
                f.write("# WARNINGS at save time: " + "; ".join(warn) + "\n")
            for n, b in sorted(self.blocks.items()):
                f.write(f"place_macro -macro_name {{{n}}} -location {{{b['x']:.3f} {b['y']:.3f}}} -orientation {b['orient']}\n")
        js = os.path.join(HERE, "top_graph_edited.json")
        json.dump({"die": self.die, "blocks": list(self.blocks.values()), "edges": self.edges, "glue": list(self.glue.values())},
                  open(js, "w"), indent=1)
        self.status.config(text=f"Saved {tcl}\nand {js}" + ("\n(with warnings)" if warn else ""))


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "top_graph.json")
    root = tk.Tk(); root.geometry("1500x950")
    Editor(root, path)
    root.mainloop()


if __name__ == "__main__":
    main()
