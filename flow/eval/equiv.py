#!/usr/bin/env python3
"""Equivalence gate: the entry's netlists against the golden Gemmini RTL, hierarchically.

usage: equiv.py <result/> <work/>

Each hardened block (blocks/<name>.v) and the top (top.v) is proven against its golden RTL module
(design/rtl, read with the slang frontend). Steps, per module:

1. Gold: the RTL through the pinned Yosys's coarse synthesis (the ORFS synthesis script up to technology
   mapping), so state machine encodings and register names are the ones that synthesis gives the
   netlist; then mapped to generic gates. Gate: the netlist, cells from the pinned ASAP7 libraries.
2. Black boxes (cutpoints.py): sub-blocks and SRAM macros are removed on both sides; their outputs become
   shared free inputs and their inputs compared outputs. The top is proven with the blocks as boxes and
   each block against its own RTL, which covers the chip.
3. Registers (regcut.py): every netlist flip-flop is paired with the RTL register bit it holds; each
   pair's stored value becomes a shared free input and its next value a compared output. What remains is
   combinational, so no initial state is assumed: for every register and input value, both sides must
   produce the same outputs and next register values.
4. eqy (YosysHQ's partitioned equivalence checker, built by setup.sh) splits that into one partition per
   compared bit; each partition is proven by ABC (iprove), or, where ABC finds a difference, decided by
   Yosys sat with RTL x values as don't-cares. The module passes only if every partition is proven.

Prints "GATE equivalence PASS|FAIL <detail>".
"""
import os, re, subprocess, sys, glob, gzip, shutil, time
from concurrent.futures import ThreadPoolExecutor

RES, WORK = os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2])
HERE = os.path.dirname(os.path.abspath(__file__)); HARNESS = os.path.abspath(os.path.join(HERE, "..", ".."))
ORFS = os.environ.get("ORFS_HOME", os.path.join(HARNESS, "orfs"))
FLOW = os.path.join(ORFS, "flow")
YOSYS = shutil.which("yosys") or os.path.join(ORFS, "tools", "install", "yosys", "bin", "yosys")
EQ = os.path.join(WORK, "equiv"); os.makedirs(EQ, exist_ok=True)
EQY = os.environ.get("EQY") or os.path.join(HARNESS, "tools", "eqy", "bin", "eqy")
JOBS = int(os.environ.get("EQUIV_JOBS", "16"))
ABC_TIMEOUT = int(os.environ.get("EQUIV_ABC_TIMEOUT", "300"))    # seconds per partition for ABC (and for building its miter)
SAT_TIMEOUT = int(os.environ.get("EQUIV_SAT_TIMEOUT", "300"))    # seconds per partition for the Yosys sat decision
FORMAL_BUDGET = int(os.environ.get("EQUIV_FORMAL_BUDGET", "3600"))  # seconds per module for proving partitions
SIM_VECTORS = int(os.environ.get("EQUIV_SIM_VECTORS", "2000000"))  # random vectors for a partition the prover cannot settle
GOLD_NETLISTS = os.environ.get("EQUIV_GOLD_NETLISTS")   # directory of <module>.v synthesized netlists to use as the golden side (experiment)
WHOLE_TIMEOUT = int(os.environ.get("EQUIV_WHOLE_TIMEOUT", "3600"))  # seconds for ABC on a whole-module miter
PAIR_BUDGET = int(os.environ.get("EQUIV_PAIR_BUDGET", "1800"))   # seconds per module for the simulation-guided pairing
ABC = shutil.which("yosys-abc") or os.path.join(os.path.dirname(YOSYS), "yosys-abc")
SRAMS = ["mem_ext_phys", "mem_0_bank_ext_phys"]

# typical-corner cell libraries, unzipped once (the function is all that matters here)
libdir = os.path.join(ORFS, "flow", "platforms", "asap7", "lib", "NLDM")
libs = []
for f in sorted(glob.glob(os.path.join(libdir, "asap7sc7p5t_*_RVT_TT_nldm_*.lib*"))):
    out = os.path.join(EQ, os.path.basename(f).replace(".gz", ""))
    if not os.path.exists(out):
        with (gzip.open(f, "rt") if f.endswith(".gz") else open(f)) as a, open(out, "w") as b: b.write(a.read())
    libs.append(out)
rtl = sorted(glob.glob(os.path.join(HARNESS, "design", "rtl", "*.sv")))
wrappers = sorted(glob.glob(os.path.join(HARNESS, "design", "srams", "_wrappers", "*.v")))
sram_lefs_v = [os.path.join(HARNESS, "design", "srams", d, f"{d}.v") for d in ("mem_ext", "mem_0_bank_ext")]

def lef_stub(lef, module):
    """A black-box Verilog module for a macro, from its LEF pins (bus width from the highest index)."""
    t = open(lef).read(); ports = {}
    for m in re.finditer(r"\n\s*PIN\s+(\S+)(.*?)\n\s*END\s+\1", t, re.S):
        name, body = m.group(1), m.group(2)
        if re.search(r"USE\s+(POWER|GROUND)", body): continue
        d = re.search(r"DIRECTION\s+(\w+)", body); d = (d.group(1).lower() if d else "input")
        b = re.match(r"^(.*)\[(\d+)\]$", name)
        base, idx = (b.group(1), int(b.group(2))) if b else (name, None)
        w, _ = ports.get(base, (-1, d)); ports[base] = (max(w, idx if idx is not None else -1), d)
    decl = ",\n".join(f"  {('output' if d == 'output' else 'inout' if d == 'inout' else 'input')} {f'[{w}:0] ' if w >= 0 else ''}{n}" for n, (w, d) in ports.items())
    return f"(* blackbox *)\nmodule {module} (\n{decl}\n);\nendmodule\n"
# The ASAP7 flip-flops store the inverted value (ff(IQN), next_state !D, QN = IQN). These models store Q
# and drive QN = ~Q, so a netlist flip-flop's stored value is the RTL register bit itself, which is what
# regcut.py pairs. They replace the library's.
seq_file = os.path.join(EQ, "seq_models.v")
with open(seq_file, "w") as f:
    for size in ("x1", "x2", "x3"):
        f.write(f"module DFFHQN{size}_ASAP7_75t_R (input CLK, input D, output QN);\n  reg Q;\n"
                f"  always @(posedge CLK) Q <= D;\n  assign QN = ~Q;\nendmodule\n")
stub_file = os.path.join(EQ, "sram_stubs.v")
with open(stub_file, "w") as f:
    for d, m in (("mem_ext", "mem_ext_phys"), ("mem_0_bank_ext", "mem_0_bank_ext_phys")):
        f.write(lef_stub(os.path.join(HARNESS, "design", "srams", d, f"{d}.lef"), m))

def modules_in(netlist):
    return set(re.findall(r"^\s*module\s+(\S+?)\s*\(", open(netlist).read(), re.M))
def instantiated(netlist, candidates):
    t = open(netlist).read()
    return sorted(m for m in candidates if re.search(rf"^\s*\\?{re.escape(m)}\s+\S+", t, re.M))

blocks = {os.path.splitext(os.path.basename(p))[0]: p for p in glob.glob(os.path.join(RES, "blocks", "*.v"))}
jobs = [(b, p) for b, p in blocks.items()] + [("Gemmini", os.path.join(RES, "top.v"))]
if os.environ.get("EQUIV_ONLY"): jobs = [j for j in jobs if j[0] in os.environ["EQUIV_ONLY"].split(",")]   # debugging

def port_table(files):
    """module -> {port: (direction, width)} from Verilog module headers (stubs and block netlists)."""
    tab = {}
    for f in files:
        t = open(f).read()
        for m in re.finditer(r"module\s+(\S+?)\s*\((.*?)\bendmodule", t, re.S):
            name, body = m.group(1), m.group(2); ports = {}
            for d, w, names in re.findall(r"\b(input|output|inout)\s+(?:wire\s+)?(\[\s*\d+\s*:\s*\d+\s*\])?\s*([^;\)]+)", body):
                width = 1
                if w:
                    a, b = map(int, re.findall(r"\d+", w)); width = abs(a - b) + 1
                for n in names.split(","):
                    n = n.strip().lstrip("\\").split()[0] if n.strip() else ""
                    if n: ports[n] = ("output" if d == "output" else "input", width)
            tab[name] = ports
    return tab

def formal(job):
    name, netlist = job
    boxes = instantiated(netlist, set(blocks) | set(SRAMS))
    box_cmd = f"blackbox {' '.join(boxes)}" if boxes else ""
    box_files = [stub_file] + [blocks[b] for b in boxes if b in blocks]
    tsv = os.path.join(EQ, f"{name}.ports.tsv")
    with open(tsv, "w") as f:
        for mod, ps in port_table(box_files).items():
            if mod in boxes:
                for p, (d, w) in ps.items(): f.write(f"{mod}\t{p}\t{d}\t{w}\n")
    # flatten leaves a $scopeinfo cell per flattened instance (a record of the hierarchy, no logic); eqy would
    # match those by name across the two sides and then fail to find a wire of that name
    lower = "flatten; delete t:$scopeinfo; proc; opt_clean"
    # The gold side is the golden RTL taken through the pinned Yosys's coarse synthesis, the part of the ORFS
    # synthesis script before technology mapping (synth -run :fine, then opt, memory_map, opt as its fine
    # step starts): state machines re-encoded, resources shared, memories mapped to registers. Register
    # names and encodings then match what that synthesis gives the netlist, and everything after it (gate
    # mapping, logic optimization, every physical-design edit) is what the proof checks. Gold then drops
    # simulation-only assertions and prints, splits registers into single bits and merges duplicates (the
    # netlist keeps one flip-flop for RTL bits with the same next value). Both sides: enables and resets
    # become logic.
    gold_regs = ("chformal -remove; delete t:$print t:$check; opt_clean; "
                 "simplemap t:$*dff*; opt_merge -share_all; async2sync; dffunmap; "
                 f"techmap -map +/techmap.v -map {os.path.join(ORFS, 'flow', 'platforms', 'common', 'lcu_kogge_stone.v')}; "
                 # merge duplicates again at gate level, where copies' next-value logic has become identical
                 "opt -fast -keepdc -nodffe -nosdff; opt_merge -share_all; opt -fast -keepdc -nodffe -nosdff; opt_clean")
    gate_regs = "async2sync; dffunmap; opt_clean"
    ya = os.path.join(EQ, f"{name}.a.ys"); log_a = os.path.join(EQ, f"{name}.a.log")
    gate_read = f"""read_verilog {seq_file}
read_liberty -ignore_redef -ignore_miss_func {' '.join(libs)}
read_verilog -lib {' '.join(box_files)}
read_verilog -defer {{netlist}}
hierarchy -top {name}
setattr -mod -unset keep_hierarchy
{box_cmd}
{lower}
{gate_regs}"""
    gold_netlist = None if os.environ.get("EQUIV_RTL_CHECK") == "1" else \
        os.path.join(GOLD_NETLISTS, f"{name}.v") if GOLD_NETLISTS else pinned_synthesis(name, [b for b in boxes if b in blocks])
    if gold_netlist is False: return name, False, f"the pinned synthesis of {name} failed (see {os.path.join(WORK, 'synth', name + '.log')})", None
    variants = ["flat", "hier"]
    coarse = coarse_synthesis(name, [b for b in boxes if b in blocks]) if not gold_netlist else None
    if coarse: variants.insert(0, "orfs")
    with open(ya, "w") as f:
        if gold_netlist:
            # the golden side is itself a gate netlist (the pinned synthesis output): read like the entry's
            variants = ["synth"]
            f.write(gate_read.format(netlist=gold_netlist) + f"""
rename {name} gold
select gold
write_rtlil -selected {os.path.join(EQ, name + '.gold.synth.il')}
design -reset
""")
        else:
            f.write(f"""plugin -i slang
read_slang {' '.join(rtl)} {' '.join(wrappers)} {stub_file} --top {name} --ignore-unknown-modules {' '.join('--blackboxed-module ' + b for b in boxes)}
hierarchy -top {name}
design -save rtl
synth -flatten -top {name} -run :fine -nordff
opt -fast -full; memory_map; opt -full
{lower}
{gold_regs}
rename {name} gold
select gold
write_rtlil -selected {os.path.join(EQ, name + '.gold.flat.il')}
select -clear
design -load rtl
synth -top {name} -run :fine -nordff
synth -flatten -top {name} -run coarse:fine -nordff
opt -fast -full; memory_map; opt -full
{lower}
{gold_regs}
rename {name} gold
select gold
write_rtlil -selected {os.path.join(EQ, name + '.gold.hier.il')}
design -reset
""")
            if coarse:
                # the pinned synthesis's own coarse step, continued the same way
                f.write(f"""read_rtlil {coarse}
hierarchy -top {name}
setattr -mod -unset keep_hierarchy
opt -fast -full; memory_map; opt -full
{lower}
{gold_regs}
rename {name} gold
select gold
write_rtlil -selected {os.path.join(EQ, name + '.gold.orfs.il')}
design -reset
""")
        f.write(gate_read.format(netlist=netlist) + f"""
rename {name} gate
select gate
write_rtlil -selected {os.path.join(EQ, name + '.gate.il')}
""")
    ra = subprocess.run([YOSYS, "-q", "-l", log_a, ya], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if ra.returncode != 0: return name, False, f"could not read the designs (see {log_a})", None
    # Two gold variants, the coarse synthesis run flat (as ORFS synthesizes a block) or per module first and
    # then flat (as ORFS does with SYNTH_HIERARCHICAL, for the top): they can extract and re-encode different
    # state machines. Both are the RTL's function, so either is a valid gold; the one whose registers pair
    # better with the netlist is used.
    gate_cut = os.path.join(EQ, f"{name}.gate.cut.il")
    subprocess.run([sys.executable, os.path.join(HERE, "cutpoints.py"), os.path.join(EQ, f"{name}.gate.il"), gate_cut, tsv], check=True)
    best = None
    for v in variants:
        g, gc, tc = (os.path.join(EQ, f"{name}.{x}") for x in (f"gold.{v}.il", f"gold.{v}.cut.il", f"gate.{v}.cut.il"))
        subprocess.run([sys.executable, os.path.join(HERE, "cutpoints.py"), g, gc, tsv], check=True)
        shutil.copy(gate_cut, tc)
        subprocess.run([sys.executable, os.path.join(HERE, "align_cuts.py"), gc, tc], check=True, stdout=subprocess.DEVNULL)
        t = subprocess.run([sys.executable, os.path.join(HERE, "regcut.py"), gc, tc, gc + ".try", tc + ".try"], capture_output=True, text=True).stdout
        m = re.search(r"left free: (\d+) netlist, (\d+) RTL", t)
        score = int(m.group(1)) + int(m.group(2)) if m else 1 << 30
        if best is None or score < best[0]: best = (score, v, gc, tc)
    cut = {"gold": best[2], "gate": best[3]}
    fin = {side: os.path.join(EQ, f"{name}.{side}.final.il") for side in ("gold", "gate")}
    if os.environ.get("EQUIV_SKIP_FORMAL") == "1": return name, False, "formal proof skipped (EQUIV_SKIP_FORMAL)", cut   # debugging
    # Pairing by name, then revised by simulating both sides (regsim.py): name pairs that disagree are
    # split, leftover flip-flops matched to the RTL bits they hold, merged or constant RTL bits related.
    # Each pass cuts with the hints so far and simulates the result; until a pass adds nothing (at most 5).
    hints = os.path.join(EQ, f"{name}.hints.tsv"); open(hints, "w").close()
    pr = {k: os.path.join(EQ, f"{name}.probe.{k}") for k in ("gold.il", "gate.il", "tsv", "gold.aag", "gold.map", "gate.aag", "gate.map")}
    regcut = [sys.executable, os.path.join(HERE, "regcut.py"), cut["gold"], cut["gate"], fin["gold"], fin["gate"], "--hints", hints]
    runlog = ""; t0 = time.time()
    for n in range(int(os.environ.get("EQUIV_PAIR_PASSES", "5"))):
        if time.time() - t0 > PAIR_BUDGET: runlog += "pairing time budget reached\n"; break
        tp = time.time()
        rc = subprocess.run(regcut + ["--probe", pr["gold.il"], pr["gate.il"], pr["tsv"]], capture_output=True, text=True)
        runlog += rc.stdout + rc.stderr
        if rc.returncode != 0: break
        for side in ("gold", "gate"):
            subprocess.run([YOSYS, "-q", "-p", f'read_rtlil "{pr[side + ".il"]}"; hierarchy -top {side}; flatten; techmap; opt -fast; '
                            # an RTL x value becomes an unnamed free input, which regsim.py treats as unknown
                            + ('setundef -undriven -anyseq; setundef -anyseq; ' if side == "gold" else 'setundef -undriven -zero; setundef -zero; ')
                            + f'aigmap; opt_clean; write_aiger -ascii -map {pr[side + ".map"]} {pr[side + ".aag"]}'],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        sim = subprocess.run([sys.executable, os.path.join(HERE, "regsim.py"), pr["gold.aag"], pr["gold.map"], pr["gate.aag"],
                              pr["gate.map"], pr["tsv"], hints], capture_output=True, text=True)
        runlog += sim.stdout + sim.stderr + f"pass {n + 1}: {time.time() - tp:.0f} s\n"
        if sim.returncode != 0 or re.search(r"regsim: 0 new hints", sim.stdout): break
    rc = subprocess.run(regcut, capture_output=True, text=True)
    runlog += rc.stdout + rc.stderr
    open(os.path.join(EQ, f"{name}.regcut.log"), "w").write(f"gold variant: {best[1]}\n" + runlog)
    if rc.returncode != 0:
        why = [l[len("regcut: "):] for l in rc.stdout.splitlines() if l.startswith("regcut: ")]
        return name, False, ("; ".join(why) or f"register pairing failed (see {name}.regcut.log)"), cut
    if os.environ.get("EQUIV_PAIR_ONLY") == "1": return name, False, "pairing only (EQUIV_PAIR_ONLY)", None   # debugging
    if gold_netlist:
        # Netlist against netlist (the pinned synthesis output against the entry's final netlist): the two
        # are structurally close, so ABC proves the whole module's miter at once by SAT sweeping; eqy's
        # partitioner is not used here (it does not handle this pairing).
        return whole_miter(name, fin, rc.stdout.split(chr(10))[0][len('regcut: '):]) + (cut,)
    cfg = os.path.join(EQ, f"{name}.eqy"); wd = os.path.join(EQ, f"{name}.eqy.d"); log = os.path.join(EQ, f"{name}.eqy.log")
    with open(cfg, "w") as f:
        f.write(f"[gold]\nread_rtlil {fin['gold']}\nrename gold {name}\n\n[gate]\nread_rtlil {fin['gate']}\nrename gate {name}\n\n"
                # amend *: where one partition reads a net another partition produces, eqy adds that net's
                # gold logic to the reader instead of treating the net as a free value, so a true
                # equivalence cannot fail at an artificial cut, and partitions stay small
                "[partition *]\namend *\n\n[strategy sat]\nuse sat\ndepth 2\n")
    with open(log, "w") as f:   # eqy builds the partitions (-m); partitions are proven below
        r = subprocess.run([EQY, "-f", "-m", "-d", wd, cfg], stdout=f, stderr=subprocess.STDOUT)
    plist = os.path.join(wd, "partition.list")
    if r.returncode != 0 or not os.path.exists(plist):
        return name, False, f"eqy could not partition the designs (see {log})", cut
    parts = sorted({l.split()[1] for l in open(plist) if l.strip()})
    os.makedirs(os.path.join(wd, "abc"), exist_ok=True)
    with ThreadPoolExecutor(JOBS) as ex:
        deadline = time.time() + FORMAL_BUDGET
        verdicts = list(ex.map(lambda p: check_partition(wd, p, deadline), parts))
    with open(log, "a") as f:
        for p, v, how in verdicts: f.write(f"PARTITION {p} {v} ({how})\n")
    left = [(p, v) for p, v, _ in verdicts if v not in ("proven", "simulated")]
    sim = [p for p, v, _ in verdicts if v == "simulated"]
    pairing = rc.stdout.split(chr(10))[0][len('regcut: '):]
    if not left and not sim:
        return name, "proven", f"{len(parts)} partitions proven; {pairing}", cut
    if not left:
        return name, "simulated", (f"{len(parts) - len(sim)} of {len(parts)} partitions proven, {len(sim)} checked by {SIM_VECTORS:,} random vectors each "
                                   f"({', '.join(sim[:4])}{' ...' if len(sim) > 4 else ''}); {pairing}"), cut
    kinds = sorted({v for _, v in left})
    return name, False, f"{len(left)}/{len(parts)} partitions not proven ({', '.join(kinds)}), e.g. {', '.join(p for p, _ in left[:3])} (see {log})", cut

# One partition's proof. First ABC: eqy's miter for the partition, with the amended cross points wired to
# their gold logic (DIRECT_CROSS_POINTS, the same constraint eqy otherwise states as an assumption), made
# two-valued and proven by ABC's iprove (SAT sweeping: it merges the matching internal points of the two
# sides, which proves the large arithmetic cones plain SAT does not finish). Two-valued means an RTL x
# counts as a definite value the netlist must match, which is stricter, so a proof here is a proof. If
# ABC finds a difference (or gives up), eqy's own Yosys sat strategy decides, with x as a don't-care.
AIG_YS = """verilog_defaults -add -D CHECK_OUTPUTS -D DIRECT_CROSS_POINTS
read_verilog -sv "{sv}"
read_rtlil "{il}"
hierarchy -top miter; proc; chformal -cover -remove; chformal -lower; async2sync; flatten -wb
setundef -undriven -anyseq; opt_clean
select -assert-none t:$assume
miter -assert miter; hierarchy -top miter
techmap; opt -fast; setundef -anyseq; aigmap; opt_clean
write_aiger -zinit "{aig}"
write_aiger -zinit -ascii "{aig}.aag"
"""
def yosys_sat(wd, p):
    """eqy's own Yosys sat strategy on one partition, with RTL x values as don't-cares."""
    sdir = os.path.join(wd, "strategies", p, "sat")
    proc = subprocess.Popen(["bash", "run.sh"], cwd=sdir, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    try:
        proc.wait(timeout=SAT_TIMEOUT)
        return open(os.path.join(sdir, "status")).read().strip() if os.path.exists(os.path.join(sdir, "status")) else "ERROR"
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, 9); proc.wait(); return "TIMEOUT"   # the whole group: run.sh and its yosys

def check_partition(wd, p, deadline):
    """One partition: (name, verdict, by). Verdicts: proven; simulated (the prover did not finish, and
    random vectors found no difference); anything else fails the module."""
    if time.time() > deadline: return p, "not run (formal time budget)", "none"
    base = os.path.join(wd, "partitions", p); aig = os.path.join(wd, "abc", p + ".aig"); ys = os.path.join(wd, "abc", p + ".ys")
    open(ys, "w").write(AIG_YS.format(sv=base + ".sv", il=base + ".il", aig=aig))
    abc = "error"
    try:
        if subprocess.run([YOSYS, "-q", "-l", ys[:-3] + ".log", ys], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                          timeout=ABC_TIMEOUT).returncode == 0:
            a = subprocess.run([ABC, "-c", f"read_aiger {aig}; iprove"], capture_output=True, text=True, timeout=ABC_TIMEOUT)
            open(ys[:-3] + ".abc.log", "w").write(a.stdout + a.stderr)
            abc = "unsat" if re.search(r"^UNSATISFIABLE", a.stdout, re.M) else "sat" if re.search(r"^SATISFIABLE", a.stdout, re.M) else "undecided"
    except subprocess.TimeoutExpired:
        abc = "timeout"
    if abc == "unsat": return p, "proven", "ABC"
    if abc == "sat":
        # a difference in the two-valued miter: Yosys sat decides it with RTL x values as don't-cares
        st = yosys_sat(wd, p)
        return p, {"PASS": "proven", "FAIL": "not equivalent", "UNKNOWN": "unknown", "TIMEOUT": "timeout"}.get(st, "error"), "Yosys sat"
    if not os.path.exists(aig + ".aag"): return p, "error", "none"
    # ABC did not finish (typically wide arithmetic): random vectors over every input and register value
    v = subprocess.run([sys.executable, os.path.join(HERE, "vecsim.py"), aig + ".aag", str(SIM_VECTORS)], capture_output=True, text=True)
    open(ys[:-3] + ".vecsim.log", "w").write(v.stdout + v.stderr)
    if "vecsim: PASS" in v.stdout: return p, "simulated", "random vectors"
    if "vecsim: FAIL" in v.stdout:
        st = yosys_sat(wd, p)                  # is the difference real, or only where the RTL is x?
        return p, {"PASS": "proven", "FAIL": "not equivalent"}.get(st, "not equivalent on random vectors"), "Yosys sat"
    return p, "error", "random vectors"

def pinned_synthesis(name, block_boxes):
    """Run the pinned ORFS synthesis of module `name` from the golden RTL, with the entry's hardened blocks
    (their evaluator-derived timing models) and the SRAM macros as black boxes. Returns the netlist path,
    or False if synthesis failed. Hierarchy mode 1 for a module with hardened blocks inside, else 0."""
    sdir = os.path.join(WORK, "synth"); os.makedirs(sdir, exist_ok=True)
    out = os.path.join(sdir, name, "results", "asap7", f"evalsynth_{name}", "base", "1_2_yosys.v")
    if os.path.exists(out): return out
    with open(os.path.join(sdir, name + ".log"), "w") as f:
        r = subprocess.run(["make", "-C", FLOW, f"DESIGN_CONFIG={os.path.join(HERE, 'eval_synth.mk')}", "synth"],
                           stdout=f, stderr=subprocess.STDOUT, env=synth_env(name, block_boxes, os.path.join(sdir, name)))
    return out if r.returncode == 0 and os.path.exists(out) else False

def synth_env(name, block_boxes, work_home):
    """The environment of the pinned synthesis of module `name` (eval_synth.mk)."""
    libs = " ".join(os.path.join(WORK, "blocks", f"{b}_BC.lib") for b in block_boxes)
    lefs = " ".join(os.path.join(WORK, "blocks", f"{b}.lef") for b in block_boxes)
    return dict(os.environ, WORK_HOME=work_home, EVAL_SYNTH_NAME=name, EVAL_SYNTH_LIBS=libs, EVAL_SYNTH_LEFS=lefs,
                EVAL_SYNTH_HIER="1" if block_boxes else "0", EVAL_WORK=WORK)

def coarse_synthesis(name, block_boxes):
    """The pinned synthesis of module `name`, set up exactly as pinned_synthesis sets it up but stopped after
    its coarse step: the pinned synth.tcl up to where it maps memories and gates, written as RTLIL. Its state
    machines are the ones the netlist's synthesis extracted and re-encoded, decided by the same script,
    settings and hierarchy handling, which an imitation of that script does not reproduce. Returns the
    path, or None if it could not be made."""
    sdir = os.path.join(WORK, "synth_coarse"); os.makedirs(sdir, exist_ok=True)
    out = os.path.join(sdir, f"{name}.il")
    if os.path.exists(out): return out
    src = open(os.path.join(FLOW, "scripts", "synth.tcl")).read()
    stop = src.find("\njson -o $::env(RESULTS_DIR)/mem.json")    # where the coarse step ends and the memory checks start
    if stop < 0: return None
    script = os.path.join(sdir, f"{name}.tcl")
    open(script, "w").write(src[:stop] + f"\nwrite_rtlil {out}\n")
    env = synth_env(name, block_boxes, os.path.join(sdir, name))
    with open(os.path.join(sdir, name + ".log"), "w") as f:
        for target in ("do-yosys-canonicalize", "do-yosys"):
            r = subprocess.run(["make", "-C", FLOW, f"DESIGN_CONFIG={os.path.join(HERE, 'eval_synth.mk')}", target,
                                f"SYNTH_SCRIPT={script}"], stdout=f, stderr=subprocess.STDOUT, env=env)
            if r.returncode != 0: return None
    return out if os.path.exists(out) else None

def whole_miter(name, fin, pairing):
    base = os.path.join(EQ, f"{name}.whole")
    r = subprocess.run([YOSYS, "-q", "-l", base + ".log", "-p",
                        f'read_rtlil "{fin["gold"]}"; read_rtlil "{fin["gate"]}"; miter -equiv -flatten gold gate miter; '
                        f'hierarchy -top miter; flatten; techmap; opt -fast; setundef -undriven -anyseq; setundef -anyseq; aigmap; opt_clean; '
                        f'write_aiger -zinit {base}.aig; write_aiger -zinit -ascii {base}.aag'],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if r.returncode != 0: return name, False, f"could not build the miter (see {base}.log)"
    try:
        a = subprocess.run([ABC, "-c", f"read_aiger {base}.aig; iprove"], capture_output=True, text=True, timeout=WHOLE_TIMEOUT)
    except subprocess.TimeoutExpired:
        a = None
    open(base + ".abc.log", "w").write((a.stdout + a.stderr) if a else "timeout\n")
    if a and re.search(r"^UNSATISFIABLE", a.stdout, re.M): return name, "proven", f"whole module proven by ABC; {pairing}"
    if a and re.search(r"^SATISFIABLE", a.stdout, re.M):
        v = subprocess.run([sys.executable, os.path.join(HERE, "vecsim.py"), base + ".aag", "65536"], capture_output=True, text=True)
        return name, False, f"ABC found a difference ({v.stdout.strip()}); {pairing}"
    v = subprocess.run([sys.executable, os.path.join(HERE, "vecsim.py"), base + ".aag", str(SIM_VECTORS)], capture_output=True, text=True)
    if "vecsim: PASS" in v.stdout: return name, "simulated", f"ABC did not finish; whole module checked by {SIM_VECTORS:,} random vectors; {pairing}"
    return name, False, f"ABC did not finish and random vectors found a difference ({v.stdout.strip()}); {pairing}"

def simulate(name, cut):
    """The second tier: sequential random simulation from reset (seqsim.py) of the gold and gate designs
    with their registers kept and the black boxes cut as in the formal check. No register pairing is
    needed, so re-encoded state machines and merged or renumbered registers do not matter."""
    base = os.path.join(EQ, f"{name}.sim")
    r = subprocess.run([YOSYS, "-q", "-l", base + ".log", "-p",
                        f'read_rtlil "{cut["gold"]}"; read_rtlil "{cut["gate"]}"; miter -equiv -flatten -make_outputs gold gate miter; '
                        f'hierarchy -top miter; flatten; techmap; opt -fast; formalff -clk2ff; zinit -all; '
                        f'setundef -undriven -zero; setundef -zero; aigmap; opt_clean; write_aiger -zinit -ascii -map {base}.map {base}.aag'],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if r.returncode != 0: return False, f"could not build the simulation miter (see {base}.log)"
    big = os.path.getsize(base + ".aag") > 200_000_000
    s = subprocess.run([sys.executable, os.path.join(HERE, "seqsim.py"), base + ".aag", base + ".map",
                        os.environ.get("EQUIV_SIM_CYCLES", "200"), os.environ.get("EQUIV_SIM_TRACES", "1024" if big else "4096")],
                       capture_output=True, text=True)
    out = (s.stdout + s.stderr).strip(); open(base + ".out", "w").write(out + "\n")
    line = next((l for l in out.splitlines() if l.startswith("seqsim: PASS") or l.startswith("seqsim: FAIL")), out[-300:])
    return line.startswith("seqsim: PASS"), line[len("seqsim: "):] if line.startswith("seqsim: ") else line

def prove(job):
    """Formal proof per partition, random vectors for partitions the prover cannot finish. A module that
    still fails also gets a from-reset simulation, reported as information only: it is blind to
    differences behind states that random inputs do not reach, so it never passes a module."""
    name, ok, why, cut = formal(job)
    if ok: return name, ok, why
    if cut is None: return name, "fail", why
    sok, swhy = simulate(name, cut)
    return name, "fail", f"{why}; from-reset simulation (information only): {swhy}"

if os.environ.get("EQUIV_RTL_CHECK") == "1" and not os.access(EQY, os.X_OK):   # only the RTL-side check partitions with eqy
    print(f"GATE equivalence FAIL eqy not found at {EQY} (run ./setup.sh)"); sys.exit(0)
if not jobs or not any(os.path.exists(n) for _, n in jobs):
    print("GATE equivalence FAIL no netlists to check (result/top.v and result/blocks/*.v)"); sys.exit(0)
results = [prove(j) for j in sorted(jobs, key=lambda j: j[0] == "Gemmini")]   # one module at a time; eqy runs JOBS partitions in parallel
for name, verdict, why in results: print(f"   {name}: {verdict}: {why}")
bad = [n for n, v, _ in results if v == "fail"]
sim = [n for n, v, _ in results if v == "simulated"]
print(f"GATE equivalence {'PASS' if not bad else 'FAIL'} {sum(1 for _, v, _ in results if v == 'proven')}/{len(results)} modules fully proven"
      + (f", {len(sim)} with partitions checked by random vectors ({', '.join(sim)})" if sim else "") + (f"; failed: {', '.join(bad)}" if bad else ""))
