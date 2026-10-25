#!/usr/bin/env python3
"""Layout-vs-netlist gate: the submitted layouts connect exactly what the proven netlists connect.

usage: lvs.py <result/> <work/>

For the top and every hardened block, the pin-level connectivity of the layout (DEF) is compared with
that of the netlist that passed the equivalence gate (Verilog), as partitions of instance pins and ports
into nets (net names do not matter). Physical cells with no logic (fill, tap, decap, tie) are left out.
This ties the equivalence proof to the layout. It does not re-extract connectivity from the metal
geometry (the pinned platform has no LVS deck); opens and shorts in the routing itself are the router's
and the DRC deck's to catch. Prints "GATE layout_vs_netlist PASS|FAIL <detail>".
"""
import os, sys, subprocess, re, glob
from concurrent.futures import ThreadPoolExecutor
RES, WORK = os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2])
HERE = os.path.dirname(os.path.abspath(__file__)); HARNESS = os.path.abspath(os.path.join(HERE, "..", ".."))
FLOW = os.path.join(os.environ.get("ORFS_HOME", os.path.join(HARNESS, "orfs")), "flow")
D = os.path.join(WORK, "lvs"); os.makedirs(D, exist_ok=True)
B = os.path.join(WORK, "blocks")
PHYSICAL = re.compile(r"^(FILLER|TAP|DECAP|PHY_EDGE|ENDCAP|TIE)", re.I)

def dump(name, src, **kw):
    out = os.path.join(D, f"{name}.{src}.tsv"); log = os.path.join(D, f"{name}.{src}.log")
    env = dict(os.environ, EVAL_WORK=WORK, WORK_HOME=os.path.join(WORK, "orfs_work"), EVAL_CONN_SRC=src, EVAL_CONN_OUT=out,
               **{k: str(v) for k, v in kw.items()})
    with open(log, "w") as f:
        subprocess.run(["make", "-C", FLOW, f"DESIGN_CONFIG={os.path.join(HERE, 'eval.mk')}", "run",
                        f"RUN_SCRIPT={os.path.join(HERE, 'conn_dump.tcl')}"], stdout=f, stderr=subprocess.STDOUT, env=env)
    return out

def partition(path):
    nets = {}
    for line in open(path):
        net, pin = line.rstrip("\n").split("\t", 1)
        inst = pin.rsplit("/", 1)[0]
        if PHYSICAL.match(inst.split("/")[-1]): continue
        nets.setdefault(net, set()).add(pin.replace("\\", ""))
    # a one-pin net connects nothing: the netlist names floating outputs (_NC...), the layout leaves them bare
    return {frozenset(p) for p in nets.values() if len(p) > 1}

def check(job):
    name, defp, vp, top, lefs = job
    a = dump(name, "def", EVAL_DEF=defp, EVAL_EXTRA_LEFS=lefs)
    b = dump(name, "verilog", EVAL_VERILOG=vp, EVAL_TOP=top, EVAL_EXTRA_LEFS=lefs)
    if not (os.path.getsize(a) and os.path.getsize(b)): return name, False, "could not read the layout or the netlist"
    pa, pb = partition(a), partition(b)
    only_a, only_b = pa - pb, pb - pa
    ok = not only_a and not only_b
    return name, ok, "match" if ok else f"{len(only_a)} layout nets and {len(only_b)} netlist nets differ"

blocks = sorted(os.path.splitext(os.path.basename(p))[0] for p in glob.glob(os.path.join(RES, "blocks", "*.def")))
alllefs = " ".join(os.path.join(B, f"{b}.lef") for b in blocks)
jobs = [(b, os.path.join(RES, "blocks", f"{b}.def"), os.path.join(RES, "blocks", f"{b}.v"), b, alllefs) for b in blocks]
jobs.append(("Gemmini", os.path.join(RES, "top.def"), os.path.join(RES, "top.v"), "Gemmini", alllefs))
with ThreadPoolExecutor(int(os.environ.get("LVS_JOBS", "6"))) as ex:
    res = list(ex.map(check, jobs))
for n, ok, why in res: print(f"   {n}: {why}")
bad = [n for n, ok, _ in res if not ok]
print(f"GATE layout_vs_netlist {'PASS' if not bad else 'FAIL'} {len(res) - len(bad)}/{len(res)} layouts match their netlists" + (f"; differ: {', '.join(bad)}" if bad else ""))
