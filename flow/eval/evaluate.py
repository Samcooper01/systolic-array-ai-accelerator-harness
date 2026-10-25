#!/usr/bin/env python3
"""The judge: takes an entry's result/ and re-derives every number with the pinned tools.

usage: evaluate.py <result/> [--work DIR] [--jobs N] [--skip STEP,...]

Everything is measured from the submitted layouts (DEF) and the pinned inputs; the entry's own SPEF,
timing models, abstracts and reports are ignored. Steps (each prints PASS/FAIL or a number):
  1  read          top.def, top.v, period.txt, blocks/<name>.def for every block the layouts use
  2  blocks        per block: extract parasitics, write the evaluator's abstract and timing models
                   (fast BC, slow WC), check placement legality and unrouted nets
  3  top           parasitics; setup at the slow corner at the declared period (WC); hold at the fast
                   corner (BC); placement legality; unrouted nets; die area
  4  power         pinned switching activity (design/activity/) at the typical corner (TC) and the
                   fixed reference clock, top plus every block instance with its own activity
  5  IR drop       static, VDD and VSS, against the pinned limit
  6  DRC           the ASAP7 KLayout deck on the merged layout                   (drc.py)
  7  equivalence   each block and the top against the golden RTL, with eqy       (equiv.py)
  8  layout vs netlist                                                            (lvs.py)
  9  score         FOM from scoring.yaml
Results go to <work>/evaluation.json and a summary on stdout. Exit status 0 only if every gate passes.
"""
import argparse, json, os, re, subprocess, sys, gzip, shutil
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
HARNESS = os.path.abspath(os.path.join(HERE, "..", ".."))
ORFS = os.environ.get("ORFS_HOME", os.path.join(HARNESS, "orfs"))
FLOW = os.path.join(ORFS, "flow")
EVAL_MK = os.path.join(HERE, "eval.mk")
ACTIVITY = os.path.join(HARNESS, "design", "activity", "chipbase_matmul_activity.tsv.gz")

ap = argparse.ArgumentParser()
ap.add_argument("result"); ap.add_argument("--work"); ap.add_argument("--jobs", type=int, default=8)
ap.add_argument("--skip", default="")
args = ap.parse_args()
RES = os.path.abspath(args.result)
WORK = os.path.abspath(args.work or os.path.join(RES, "..", "eval_work"))
SKIP = set(s for s in args.skip.split(",") if s)
os.makedirs(os.path.join(WORK, "blocks"), exist_ok=True)
out = {"gates": {}, "metrics": {}, "notes": []}

def say(msg): print(msg, flush=True)
def gate(name, ok, detail=""):
    out["gates"][name] = {"pass": bool(ok), "detail": detail}
    say(f"   {'PASS' if ok else 'FAIL'}  {name}{('  ' + detail) if detail else ''}")

def run(script, log, corner, env):
    """Run one evaluator Tcl script through the flow's make environment; return its EVAL lines."""
    e = dict(os.environ); e.update({k: str(v) for k, v in env.items()})
    e["EVAL_WORK"] = WORK; e["WORK_HOME"] = os.path.join(WORK, "orfs_work")
    cmd = ["make", "-C", FLOW, f"DESIGN_CONFIG={EVAL_MK}", f"CORNER={corner}", "run", f"RUN_SCRIPT={os.path.join(HERE, script)}"]
    with open(log, "w") as f:
        rc = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT, env=e).returncode
    vals = {}
    for line in open(log):
        if line.startswith("EVAL "):
            _, k, v = line.rstrip("\n").split(" ", 2); vals[k] = v
    return rc, vals

# ---- 1 read ----
say("1  read")
for f in ("top.def", "top.v", "period.txt"):
    if not os.path.exists(os.path.join(RES, f)): say(f"FAIL: missing {f}"); sys.exit(2)
period = float(open(os.path.join(RES, "period.txt")).read().strip())
def components(defpath):
    """(instance, master) pairs from a DEF's COMPONENTS section."""
    comps, on = [], False
    with open(defpath) as f:
        for line in f:
            if line.startswith("COMPONENTS"): on = True; continue
            if line.startswith("END COMPONENTS"): break
            if on:
                m = re.match(r"\s*-\s+(\S+)\s+(\S+)", line)
                if m: comps.append((m.group(1).replace("\\", ""), m.group(2)))
    return comps
blockdir = os.path.join(RES, "blocks")
block_defs = {os.path.splitext(f)[0]: os.path.join(blockdir, f) for f in (os.listdir(blockdir) if os.path.isdir(blockdir) else []) if f.endswith(".def")}
children = {b: sorted({m for _, m in components(p) if m in block_defs}) for b, p in block_defs.items()}
top_comps = components(os.path.join(RES, "top.def"))
used = {m for _, m in top_comps if m in block_defs}
order, seen = [], set()
def visit(b):
    if b in seen: return
    seen.add(b)
    for c in children[b]: visit(c)
    order.append(b)
for b in sorted(used): visit(b)
say(f"   period {period:g} ps; blocks used: {len(order)} ({', '.join(order)})")
out["metrics"]["declared_period_ps"] = period

# block instances with their full paths in Gemmini (nested blocks prefix their parent's path)
def instances(defpath, prefix):
    for inst, master in components(defpath):
        if master in block_defs:
            path = prefix + inst
            yield path, master
            yield from instances(block_defs[master], path + "/")
all_insts = list(instances(os.path.join(RES, "top.def"), ""))

B = os.path.join(WORK, "blocks")
def lefs_of(b): return " ".join(os.path.join(B, f"{c}.lef") for c in children[b])
def libs_of(b, corner): return " ".join(os.path.join(B, f"{c}_{corner}.lib") for c in children[b])

# ---- 2 blocks (children before parents; same-depth blocks in parallel) ----
say("2  blocks: parasitics, abstracts, fast and slow timing models, legality, routing")
depth = {}
def d(b): depth.setdefault(b, 1 + max((d(c) for c in children[b]), default=0)); return depth[b]
for b in order: d(b)
block_ok = True
if "blocks" not in SKIP:
    for lvl in sorted(set(depth.values())):
      for c_phase in ("BC", "WC"):     # BC first: it extracts the parasitics that WC then reuses
        todo = [(b, c_phase) for b in order if depth[b] == lvl]
        def one(bc):
            b, c = bc
            return b, c, run("block.tcl", os.path.join(WORK, f"block_{b}_{c}.log"), c,
                             {"EVAL_BLOCK": b, "EVAL_DEF": block_defs[b], "EVAL_OUT": B,
                              "EVAL_EXTRA_LEFS": lefs_of(b), "EVAL_EXTRA_LIBS": libs_of(b, c)})
        with ThreadPoolExecutor(args.jobs) as ex:
          for b, c, (rc, v) in ex.map(one, todo):
                if rc != 0 or v.get(f"block_{b}.model_{c}") != "ok":
                    block_ok = False; say(f"   block {b} {c} failed (see {WORK}/block_{b}_{c}.log)")
                if c == "BC":
                    legal = v.get(f"block_{b}.placement_legal") == "1"; unr = int(v.get(f"block_{b}.unrouted_nets", "-1"))
                    if not legal or unr != 0: block_ok = False
                    say(f"   {b}: legal {legal}, unrouted nets {unr}")
    gate("blocks legal and routed", block_ok)

top_lefs = " ".join(os.path.join(B, f"{b}.lef") for b in sorted(used))
def top_libs(corner): return " ".join(os.path.join(B, f"{b}_{corner}.lib") for b in sorted(used))
tdef = os.path.join(RES, "top.def")

# ---- 3 top: setup (slow) and hold / legality / routing / area (fast), in parallel ----
say("3  top: timing at both corners, legality, routing, area")
# hold first: it extracts the top's parasitics and lists the flip-flops; setup then reuses them
rh, vh = run("top.tcl", os.path.join(WORK, "top_hold_BC.log"), "BC",
             {"EVAL_MODE": "hold", "EVAL_DEF": tdef, "EVAL_PERIOD": period, "EVAL_EXTRA_LEFS": top_lefs, "EVAL_EXTRA_LIBS": top_libs("BC")})
fs_executor = ThreadPoolExecutor(1)
fs = fs_executor.submit(run, "top.tcl", os.path.join(WORK, "top_setup_WC.log"), "WC",
                        {"EVAL_MODE": "setup", "EVAL_DEF": tdef, "EVAL_PERIOD": period, "EVAL_EXTRA_LEFS": top_lefs, "EVAL_EXTRA_LIBS": top_libs("WC")})
hold = float(vh.get("hold_wns_ps", "nan"))
gate("hold (fast corner)", rh == 0 and hold >= 0, f"worst slack {hold:.1f} ps")
gate("placement legal", vh.get("placement_legal") == "1")
gate("routing complete", vh.get("unrouted_nets") == "0", f"unrouted nets {vh.get('unrouted_nets')}")
area = float(vh.get("die_area_um2", "nan")); out["metrics"]["die_area_um2"] = area
say(f"   die area {area:.0f} um2")

# ---- 4 power and 5 IR drop ----
say("4  power: pinned switching activity, typical corner, fixed 1,000 ps reference clock")
if not os.path.exists(ACTIVITY): say(f"FAIL: missing pinned activity {ACTIVITY}"); sys.exit(2)
act_tsv = ACTIVITY
def annotate(flops, ports, prefix, tcl):
    r = subprocess.run([sys.executable, os.path.join(HERE, "activity.py"), act_tsv, flops, ports, prefix, tcl], capture_output=True, text=True)
    m = re.search(r"flops (\d+)/(\d+)", r.stdout); return (int(m.group(1)), int(m.group(2))) if m else (0, 0)
cov = [0, 0]
h, n = annotate(os.path.join(WORK, "top.flops.tsv"), os.path.join(WORK, "top.ports.tsv"), "", os.path.join(WORK, "top.activity.tcl")); cov[0] += h; cov[1] += n
per_block = {}
for path, master in all_insts:
    tcl = os.path.join(WORK, "act_" + path.replace("/", "__") + ".tcl")
    h, n = annotate(os.path.join(B, f"{master}.flops.tsv"), os.path.join(B, f"{master}.ports.tsv"), path + "/", tcl)
    cov[0] += h; cov[1] += n; per_block.setdefault(master, []).append(f"{path}={tcl}")
def power_block(master):
    return run("block_power.tcl", os.path.join(WORK, f"power_{master}.log"), "TC",
               {"EVAL_BLOCK": master, "EVAL_DEF": block_defs[master], "EVAL_SPEF": os.path.join(B, f"{master}.spef"),
                "EVAL_INSTANCES": " ".join(per_block[master]), "EVAL_EXTRA_LEFS": lefs_of(master), "EVAL_EXTRA_LIBS": libs_of(master, "BC")})
with ThreadPoolExecutor(args.jobs) as ex:
    ftop = ex.submit(run, "top.tcl", os.path.join(WORK, "top_power_TC.log"), "TC",
                     {"EVAL_MODE": "power", "EVAL_DEF": tdef, "EVAL_PERIOD": period, "EVAL_EXTRA_LEFS": top_lefs,
                      "EVAL_EXTRA_LIBS": top_libs("BC"), "EVAL_ACTIVITY_TCL": os.path.join(WORK, "top.activity.tcl")})
    fbl = {m: ex.submit(power_block, m) for m in per_block}
    rt, vt = ftop.result(); blocks_w = 0.0; nb = 0
    for m, f in fbl.items():
        rc, v = f.result()
        for k, val in v.items():
            if k.startswith("block_power."): blocks_w += float(val); nb += 1
rs, vs = fs.result(); setup = float(vs.get("setup_wns_ps", "nan"))
gate("setup (slow corner, declared period)", rs == 0 and setup >= 0, f"worst slack {setup:.1f} ps")
top_w = float(vt.get("top_power_w", "nan")); total = top_w + blocks_w
out["metrics"].update({"power_w": total, "power_top_w": top_w, "power_blocks_w": blocks_w, "block_instances": nb,
                       "activity_coverage_flops": f"{cov[0]}/{cov[1]}"})
say(f"   power {total:.4f} W (top {top_w:.4f} W + {nb} block instances {blocks_w:.4f} W); activity on {cov[0]}/{cov[1]} flip-flops ({100.0 * cov[0] / max(cov[1], 1):.2f}%)")

say("5  IR drop")
ir = {}
for line in open(os.path.join(WORK, "top_power_TC.log")):
    m = re.search(r"Worstcase IR drop:\s*([0-9.eE+-]+)\s*V", line)
    if m: ir[len(ir)] = float(m.group(1)) * 1000.0
limit = None
for line in open(os.path.join(HARNESS, "scoring.yaml")):
    m = re.match(r"\s*ir_drop_limit_mv:\s*([0-9.]+)", line)
    if m: limit = float(m.group(1))
worst = max(ir.values()) if ir else float("nan")
out["metrics"]["ir_drop_mv"] = worst
gate("IR drop", ir and limit is not None and worst <= limit, f"worst {worst:.1f} mV (limit {limit} mV)")

# ---- 6-8: DRC, equivalence, layout vs netlist (separate scripts) ----
for step, script in (("6  DRC", "drc.py"), ("7  equivalence", "equiv.py"), ("8  layout vs netlist", "lvs.py")):
    say(step)
    key = script[:-3]
    if key in SKIP: say("   skipped"); continue
    p = os.path.join(HERE, script)
    if not os.path.exists(p): gate(step.split("  ")[1], False, "not implemented"); continue
    r = subprocess.run([sys.executable, p, RES, WORK], capture_output=True, text=True)
    sys.stdout.write(r.stdout)
    for line in r.stdout.splitlines():
        m = re.match(r"GATE (\S+) (PASS|FAIL) ?(.*)", line)
        if m: out["gates"][m.group(1)] = {"pass": m.group(2) == "PASS", "detail": m.group(3)}

# ---- 9 score ----
say("9  score")
sc = open(os.path.join(HARNESS, "scoring.yaml")).read()
def num(k):  # a plain number, or a fraction such as 1/3
    m = re.search(rf"^\s*{k}:\s*([0-9.eE+-]+)(?:\s*/\s*([0-9.eE+-]+))?", sc, re.M)
    return None if not m else float(m.group(1)) / (float(m.group(2)) if m.group(2) else 1.0)
T0, A0, P0 = num("T_base_ps"), num("A_base_um2"), num("P_base_w")
a, b_, g = num("a"), num("b"), num("g")
if None in (T0, A0, P0, a, b_, g):
    say("   not scored: scoring.yaml reference values or weights are not set")
else:
    fom = (T0 / period) ** a * (A0 / area) ** b_ * (P0 / total) ** g
    out["metrics"]["fom"] = fom; say(f"   FOM {fom:.3f}  (T {period:g} ps, A {area:.0f} um2, P {total:.4f} W)")
allpass = all(v["pass"] for v in out["gates"].values())
out["all_gates_pass"] = allpass
json.dump(out, open(os.path.join(WORK, "evaluation.json"), "w"), indent=1)
say(f"== {'ALL GATES PASS' if allpass else 'SOME GATES FAIL'}; details in {WORK}/evaluation.json")
sys.exit(0 if allpass else 1)
