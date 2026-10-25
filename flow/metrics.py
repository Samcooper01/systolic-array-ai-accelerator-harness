#!/usr/bin/env python3
"""Extract reference metrics for one ORFS design run. Usage: metrics.py <nickname> <variant> [time_file]"""
import json,glob,os,re,sys
import os
W=os.environ.get("WORK_HOME", os.path.join(os.path.dirname(os.path.abspath(__file__)),"..","work")); nick,var=sys.argv[1],sys.argv[2]; tf=sys.argv[3] if len(sys.argv)>3 else None
L=f"{W}/logs/asap7/{nick}/{var}"; R=f"{W}/reports/asap7/{nick}/{var}"; S=f"{W}/results/asap7/{nick}/{var}"
m={}
for f in sorted(glob.glob(f"{L}/6_*.json")):
    try: m.update(json.load(open(f)))
    except Exception: pass
def g(k,d=None): return m.get(k,d)
out={"design":nick,"variant":var}
rpt=f"{R}/6_finish.rpt"
if os.path.exists(rpt):
    t=open(rpt).read(); mm=re.search(r"period_min = ([0-9.]+)",t); out["period_min_ps"]=float(mm.group(1)) if mm else None
dp=f"{S}/declared_period.txt"; out["declared_period_ps"]=float(open(dp).read().split()[0]) if os.path.exists(dp) else None
_cp=open(f"{S}/clock_period.txt").read().split() if os.path.exists(f"{S}/clock_period.txt") else []
out["clock_ps"]=float(_cp[0]) if _cp else None
out["setup_ws_ps"]=g("finish__timing__setup__ws"); out["hold_ws_ps"]=g("finish__timing__hold__ws")
out["setup_tns"]=g("finish__timing__setup__tns"); out["hold_viol"]=g("finish__timing__drv__hold_violation_count"); out["setup_viol"]=g("finish__timing__drv__setup_violation_count")
out["die_area_um2"]=g("finish__design__die__area"); out["core_area_um2"]=g("finish__design__core__area"); out["stdcell_area_um2"]=g("finish__design__instance__area__stdcell")
out["stdcells"]=g("finish__design__instance__count__stdcell"); out["macros"]=g("finish__design__instance__count__macros")
out["power_w"]=g("finish__power__total"); out["leak_w"]=g("finish__power__leakage__total"); out["util_pct"]=g("finish__design__instance__utilization")
drc=f"{R}/5_route_drc.rpt"; out["drc"]=sum(1 for _ in open(drc)) if os.path.exists(drc) else None
out["routed"]=os.path.exists(f"{S}/6_final.def")
if tf and os.path.exists(tf):
    t=open(tf).read(); e=re.search(r"Elapsed.*?([0-9:.]+)$",t,re.M); p=re.search(r"Maximum resident.*?(\d+)",t)
    if e:
        parts=[float(x) for x in e.group(1).split(":")]; out["runtime_s"]=parts[0]*3600+parts[1]*60+parts[2] if len(parts)==3 else parts[0]*60+parts[1]
    if p: out["peak_mem_kb"]=int(p.group(1))

# Chip power is the sum over the hierarchy: a block abstract carries timing but no power, so each
# run reports only its own cells. Roll up each block's own finish power times its instance count.
def _own_power(n):
    f=f"{W}/logs/asap7/{n}/base/6_report.json"
    try: return json.load(open(f)).get("finish__power__total")
    except Exception: return None
L1={"gemmini_ExecuteController_Tile":64,"gemmini_ExecuteController_AlwaysOutTransposer":1,"gemmini_Scratchpad_AccumulatorScale":1,"gemmini_ExecuteController":1,"gemmini_Scratchpad":1}
L2={"gemmini_LoopConv":1,"gemmini_LoopMatmul":1,"gemmini_ReservationStation":1,"gemmini_LoadController":1,"gemmini_StoreController":1,"gemmini_FrontendTLB":1,"gemmini_CounterController":1}
# the reference top (config_tight2.mk): ExecuteController and Scratchpad opened, ten block types below
L3={f"gemmini_flat_{b}":n for b,n in (("Tile",64),("AlwaysOutTransposer",1),("AccumulatorScale",1),("LoopConv",1),
    ("LoopMatmul",1),("ReservationStation",1),("LoadController",1),("StoreController",1),("FrontendTLB",1),("CounterController",1))}
if nick in ("gemmini","gemmini2","gemmini_flat") and out.get("power_w") is not None:
    blocks=L3 if nick=="gemmini_flat" else dict(L1)
    if nick=="gemmini": blocks.update(L2)
    parts={b:_own_power(b) for b in blocks}
    if all(v is not None for v in parts.values()):
        out["power_rollup_w"]=out["power_w"]+sum(parts[b]*n for b,n in blocks.items())
print(json.dumps(out))
