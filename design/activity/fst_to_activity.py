#!/usr/bin/env python3
"""Switching activity of Gemmini over the workload's multiply window, from the simulation trace.

usage: fst2vcd -f trace.fst | fst_to_activity.py <scope-name> <out.tsv>
       fst_to_activity.py <scope-name> <out.tsv> --vcd <file.vcd>     (reuse a VCD already on disk)

The window is set by the accelerator itself: it opens at the first command Gemmini accepts (io_cmd_valid
and io_cmd_ready high) in the final burst of commands (commands less than 50,000 Gemmini cycles apart;
an isolated configuration command earlier in the program is not part of the workload) and closes when
io_busy last falls. The clock period is measured from Gemmini's own clock (it runs slower than the
harness clock). Over that window every bit of every signal
under the Gemmini scope gets a toggle count and a time at logic 1. Output, one line per signal:
    path  width  toggles_per_cycle(bit0,bit1,...)  duty(bit0,bit1,...)
path is relative to the Gemmini instance, with "/" between scopes. A header line records the window.
Two passes over the VCD text: the first finds the window, the second accumulates (the VCD is spooled to
a temporary file so the trace is converted once).
"""
import sys, os, tempfile, shutil, re

scope_name, out_path = sys.argv[1], sys.argv[2]
if "--vcd" in sys.argv:
    vcd_path = sys.argv[sys.argv.index("--vcd") + 1]; keep_vcd = True
else:
    tmp = tempfile.NamedTemporaryFile("w", delete=False, dir=os.path.dirname(os.path.abspath(out_path)), suffix=".vcd")
    shutil.copyfileobj(sys.stdin, tmp); tmp.close(); vcd_path = tmp.name; keep_vcd = False

# ---- header: variables under the Gemmini scope ----
ids = {}          # id -> list of (path, width)
stack, in_scope_depth = [], None
top_ids = {}      # names directly in the Gemmini scope -> id (for the window signals)
with open(vcd_path) as f:
    for line in f:
        if line.startswith("$scope"):
            name = line.split()[2]; stack.append(name)
            if in_scope_depth is None and name == scope_name: in_scope_depth = len(stack)
        elif line.startswith("$upscope"):
            if in_scope_depth is not None and len(stack) == in_scope_depth: in_scope_depth = -1   # left it
            stack.pop()
        elif line.startswith("$var") and in_scope_depth not in (None, -1):
            p = line.split(); width, code, name = int(p[2]), p[3], p[4]
            rel = "/".join(stack[in_scope_depth:] + [name])
            ids.setdefault(code, []).append((rel, width))
            if len(stack) == in_scope_depth: top_ids[name] = code
        elif line.startswith("$enddefinitions"):
            break
need = ("clock", "io_cmd_valid", "io_cmd_ready", "io_busy")
assert all(n in top_ids for n in need), f"window signals not found in scope {scope_name}: {[n for n in need if n not in top_ids]}"
clk, cv, cr, busy = (top_ids[n] for n in need)
print(f"scope {scope_name}: {sum(len(v) for v in ids.values())} signals, {len(ids)} trace ids", file=sys.stderr)

def changes(path):
    t = 0
    with open(path) as f:
        for line in f:
            if line.startswith("$enddefinitions"): break
        for line in f:
            c = line[0]
            if c == "#": t = int(line[1:]); continue
            if c in "01xzXZ": yield t, line[1:].strip(), line[0]
            elif c in "bB":
                v, code = line[1:].split(); yield t, code, v
            elif c in "rR": pass

# ---- pass 1: the window and Gemmini's clock period ----
val = {cv: "0", cr: "0", busy: "0"}; fires = []; falls = []; clk_edges = []
for t, code, v in changes(vcd_path):
    if code == clk:
        if v == "1" and len(clk_edges) < 3: clk_edges.append(t)
        continue
    if code in val:
        val[code] = v
        if code in (cv, cr) and val[cv] == "1" and val[cr] == "1": fires.append(t)
        if code == busy and v == "0": falls.append(t)
assert len(clk_edges) >= 2 and fires and falls, "clock, commands or busy not found"
period = clk_edges[1] - clk_edges[0]
gap = 50000 * period
t_open = fires[-1]
for t in reversed(fires):      # walk back through the final burst
    if t_open - t > gap: break
    t_open = t
t_close = falls[-1]
assert t_close > t_open, "window not found"
cycles = (t_close - t_open) / period
print(f"window {t_open} .. {t_close} ({cycles:.0f} cycles at period {period}); {len(fires)} commands in trace", file=sys.stderr)

# ---- pass 2: toggles and time at 1, per bit, inside the window ----
def to_int(v):
    v = v.lower().replace("x", "0").replace("z", "0"); return int(v, 2) if v else 0
cur = {code: 0 for code in ids}; width = {code: ids[code][0][1] for code in ids}
tog = {code: [0] * width[code] for code in ids}; one = {code: [0] * width[code] for code in ids}
since = {code: t_open for code in ids}
def settle(code, t):   # credit time at 1 for bits that are 1, from since[code] to t
    v = cur[code]; dt = t - since[code]
    if v and dt > 0:
        o = one[code]; b = 0
        while v:
            if v & 1: o[b] += dt
            v >>= 1; b += 1
    since[code] = t
for t, code, v in changes(vcd_path):
    if t > t_close: break
    if code not in cur: continue
    new = to_int(v)
    if t <= t_open: cur[code] = new; continue
    settle(code, t)
    x = cur[code] ^ new; b = 0; tg = tog[code]
    while x:
        if x & 1: tg[b] += 1
        x >>= 1; b += 1
    cur[code] = new
for code in ids: settle(code, t_close)
span = t_close - t_open
with open(out_path, "w") as out:
    out.write(f"# window {t_open} {t_close} cycles {cycles:.0f} period {period} scope {scope_name}\n")
    for code, names in ids.items():
        tr = ",".join(f"{n / cycles:.5g}" for n in tog[code]); du = ",".join(f"{o / span:.4g}" for o in one[code])
        for rel, w in names: out.write(f"{rel}\t{w}\t{tr}\t{du}\n")
keep_vcd or os.unlink(vcd_path)
print(f"wrote {out_path}", file=sys.stderr)
