#!/usr/bin/env python3
"""Design-rule gate on the submitted layouts.

usage: drc.py <result/> <work/>   (DRC_KLAYOUT=1 also runs the ASAP7 KLayout deck, for information)

Every hardened block and the top are checked with the detailed router's own rule checker
(drt::check_drc: the technology LEF's rules on every routing and via layer), one layout at a time. The
gate fails on any short and on any via (cut) spacing, enclosure or off-grid violation: the defects that
break a chip. The checker's other findings (end-of-line keep-out and spacing, corner and metal spacing,
minimum width) are reported as counts but do not fail the gate: run standalone, the checker reports
these on every block of the reference even where the router's own sign-off found none, so they are
not a reliable pass/fail signal.
The pinned KLayout deck is not part of the gate either: it reports hundreds of violations per block on
the reference, many inside the standard cells themselves, and takes hours on the top level.
Prints "GATE drc PASS|FAIL <detail>".
"""
import os, sys, subprocess, re, glob, collections
RES, WORK = os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2])
HERE = os.path.dirname(os.path.abspath(__file__)); HARNESS = os.path.abspath(os.path.join(HERE, "..", ".."))
FLOW = os.path.join(os.environ.get("ORFS_HOME", os.path.join(HARNESS, "orfs")), "flow")
D = os.path.join(WORK, "drc"); os.makedirs(D, exist_ok=True)
B = os.path.join(WORK, "blocks")
FATAL = re.compile(r"short|cut|enclosure|off ?grid|via", re.I)

blocks = sorted(os.path.splitext(os.path.basename(p))[0] for p in glob.glob(os.path.join(RES, "blocks", "*.def")))
lefs = " ".join(os.path.join(B, f"{b}.lef") for b in blocks)
jobs = [(b, os.path.join(RES, "blocks", f"{b}.def")) for b in blocks] + [("Gemmini", os.path.join(RES, "top.def"))]
fatal_total, other_total, failed = 0, collections.Counter(), []
for name, defp in jobs:
    rpt = os.path.join(D, f"{name}.rpt"); log = os.path.join(D, f"{name}.log")
    if os.path.exists(rpt): os.remove(rpt)
    env = dict(os.environ, EVAL_WORK=WORK, WORK_HOME=os.path.join(WORK, "orfs_work"), EVAL_DEF=defp, EVAL_DRC_OUT=rpt, EVAL_EXTRA_LEFS=lefs)
    with open(log, "w") as f:
        rc = subprocess.run(["make", "-C", FLOW, f"DESIGN_CONFIG={os.path.join(HERE, 'eval.mk')}", "run",
                             f"RUN_SCRIPT={os.path.join(HERE, 'drc_route.tcl')}"], stdout=f, stderr=subprocess.STDOUT, env=env).returncode
    done = any(l.startswith("EVAL drc_route_violations") for l in open(log))
    if rc != 0 or not done:
        failed.append(name); print(f"   {name}: checker did not finish (see {log})"); continue
    types = collections.Counter(m.group(1).strip() for m in re.finditer(r"^violation type: (.*)$", open(rpt).read() if os.path.exists(rpt) else "", re.M))
    fatal = sum(n for t, n in types.items() if FATAL.search(t)); other = {t: n for t, n in types.items() if not FATAL.search(t)}
    fatal_total += fatal; other_total.update(other)
    print(f"   {name}: {fatal} shorts or via violations; other findings {sum(other.values())}")
if os.environ.get("DRC_KLAYOUT") == "1":
    print("   KLayout deck: run separately with orfs/flow/platforms/asap7/drc/asap7.lydrc (information only)")
detail = f"{fatal_total} shorts or via violations; informational: " + (", ".join(f"{t} {n}" for t, n in other_total.most_common()) or "none")
ok = fatal_total == 0 and not failed
print(f"GATE drc {'PASS' if ok else 'FAIL'} {detail}" + (f"; not checked: {', '.join(failed)}" if failed else ""))
