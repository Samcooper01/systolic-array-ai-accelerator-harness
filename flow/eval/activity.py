#!/usr/bin/env python3
"""Annotate a design with the pinned switching activity.

usage: activity.py <activity.tsv[.gz]> <flops.tsv> <ports.tsv> <prefix> <out.tcl>

activity.tsv  the pinned table (design/activity/): per Gemmini signal, per bit, toggles per clock cycle
              and duty, measured on the golden RTL running the fixed workload
flops.tsv     the design's flip-flops: instance name, master, output pins (written by flops.tcl)
ports.tsv     the design's input ports (written by flops.tcl)
prefix        where this design sits in Gemmini ("" for the top; "ex_controller/mesh/mesh/mesh_3_5/" for
              one Tile instance), so each block instance gets its own activity
out.tcl       set_power_activity commands on every matched flip-flop output and input port

Matching is by register name, which synthesis keeps: a flip-flop called
"spad/norm_unit_passthru_q.wrap_1$_SDFFE_PP0P_" or "tile_0_0.c1[3]$_DFFE_PP_" is the RTL register
spad/norm_unit_passthru_q/wrap_1 (bit 0) or tile_0_0/c1 (bit 3). Internal wire names are not used:
they differ between elaborations and between entrants' syntheses. Activity through the combinational
logic is propagated by OpenSTA from the annotated registers and inputs. A QN output gets duty 1 - d.
Coverage (matched / all flip-flops) is printed so the approximation stays visible.
"""
import sys, re, gzip

act_path, flops_path, ports_path, prefix, out_path = sys.argv[1:6]
op = gzip.open if act_path.endswith(".gz") else open
act = {}
with op(act_path, "rt") as f:
    for line in f:
        if line.startswith("#"): continue
        p, w, tr, du = line.rstrip("\n").split("\t")
        act[p] = (tr.split(","), du.split(","))

def lookup(name):
    base = name.replace("\\", "").split("$")[0]
    m = re.match(r"^(.*)\[(\d+)\]$", base); bit = 0
    if m: base, bit = m.group(1), int(m.group(2))
    rec = act.get(prefix + base.replace(".", "/"))
    if rec and bit < len(rec[0]): return float(rec[0][bit]), float(rec[1][bit])
    return None

def tcl_name(s): return "{" + s + "}"

lines = []; n = hit = 0
for line in open(flops_path):
    inst, master, outs = line.rstrip("\n").split("\t"); n += 1
    a = lookup(inst)
    if a is None: continue
    hit += 1; tr, du = a
    for pin in outs.split(","):
        d = 1.0 - du if pin.upper().startswith("QN") else du
        lines.append(f"set_power_activity -pins [get_pins {tcl_name(inst + '/' + pin)}] -activity {tr:.6g} -duty {min(max(d, 0.0), 1.0):.4g} -clock [get_clocks clock]")
np = hp = 0
for line in open(ports_path):
    port = line.strip()
    if not port or port in ("clock", "reset"): continue
    np += 1; a = lookup(port)
    if a is None: continue
    hp += 1; tr, du = a
    lines.append(f"set_power_activity -input_ports [get_ports {tcl_name(port)}] -activity {tr:.6g} -duty {min(max(du, 0.0), 1.0):.4g} -clock [get_clocks clock]")
with open(out_path, "w") as f:
    f.write(f"# pinned switching activity for prefix '{prefix}': {hit}/{n} flip-flops, {hp}/{np} input ports\n")
    f.write("\n".join(lines) + "\n")
print(f"ACTIVITY_COVERAGE flops {hit}/{n} inputs {hp}/{np}")
