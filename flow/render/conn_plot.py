#!/usr/bin/env python3
"""Draw group-to-group net connectivity over the floorplan. Input: conn.tsv from conn.tcl."""
import re, math, sys, warnings; warnings.filterwarnings("ignore")
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Circle
W="/home/sam/Geetus2.0/chipbase-ref"; tsv=sys.argv[1]; out=sys.argv[2]; MIN_NETS=int(sys.argv[3]) if len(sys.argv)>3 else 100
DX=float(sys.argv[4]) if len(sys.argv)>4 else 896; DY=float(sys.argv[5]) if len(sys.argv)>5 else 896
sizes={}
for name,path in (("Tile",f"{W}/flow/results/asap7/gemmini_Tile/base/Tile.lef"),("AlwaysOutTransposer",f"{W}/flow/results/asap7/gemmini_AlwaysOutTransposer/base/AlwaysOutTransposer.lef"),
                  ("AccumulatorScale",f"{W}/flow/results/asap7/gemmini_AccumulatorScale/base/AccumulatorScale.lef"),("LoopConv",f"{W}/flow/results/asap7/gemmini_LoopConv/base/LoopConv.lef"),
                  ("mem_ext_phys",f"{W}/srams_v2/mem_ext/mem_ext.lef"),("mem_0_bank_ext_phys",f"{W}/srams_v2/mem_0_bank_ext/mem_0_bank_ext.lef")):
    m=re.search(r"SIZE ([0-9.]+) BY ([0-9.]+)",open(path).read()); sizes[name]=(float(m.group(1)),float(m.group(2)))
def master(inst):
    if "/mesh/mesh/" in inst or inst.startswith("mesh_"): return "Tile"
    if inst.endswith("transposer"): return "AlwaysOutTransposer"
    if inst=="mod": return "LoopConv"
    if inst.endswith("acc_scale_unit"): return "AccumulatorScale"
    if "mem_0_ext" in inst: return "mem_0_bank_ext_phys"
    return "mem_ext_phys"
col={"Tile":"#4c9be8","AlwaysOutTransposer":"#f0c419","AccumulatorScale":"#e8734c","LoopConv":"#b07ce8","mem_ext_phys":"#5fd18a","mem_0_bank_ext_phys":"#3fb59e"}
insts={}
for m in re.finditer(r"place_macro -macro_name \{(\S+)\} -location \{([0-9.]+) ([0-9.]+)\} -orientation (\w+)",open(f"{W}/flow/results/asap7/gemmini/base/2_2_floorplan_macro.tcl").read()):
    insts[m.group(1)]=(float(m.group(2)),float(m.group(3)))
# groups and edges
G={}; E={}
for line in open(tsv):
    p=line.rstrip("\n").split("\t")
    if p[0]=="G": G[p[1]]=(int(p[2]),float(p[3]),float(p[4]))
    elif p[0]=="E": E[(p[1],p[2])]=int(p[3])
# node keys: macros by instance name (tiles merged into one node), big flat groups, rest merged
def node(g):
    if g.startswith("MACRO:mesh_"): return "Tile array (64)"
    if g.startswith("MACRO:"): return g[6:]
    if g=="IO": return "IO"
    if G.get(g,(0,))[0]>=3000: return g
    return "spad other" if g.startswith("spad/") else "other small groups"
nodes={}
for g,(n,x,y) in G.items():
    k=node(g); c=nodes.setdefault(k,[0,0.0,0.0]); c[0]+=n; c[1]+=n*x; c[2]+=n*y
pos={}
for k,(n,sx,sy) in nodes.items(): pos[k]=(sx/n,sy/n)
# macro nodes: rectangle centers
for inst,(x,y) in insts.items():
    mst=master(inst); w,h=sizes[mst]
    if mst!="Tile": pos[inst]=(x+w/2,y+h/2)
tiles=[(x,y) for i,(x,y) in insts.items() if master(i)=="Tile"]
pos["Tile array (64)"]=(sum(t[0] for t in tiles)/64+sizes["Tile"][0]/2, sum(t[1] for t in tiles)/64+sizes["Tile"][1]/2)
pos["IO"]=(DX/2,-40)
edges={}
for (a,b),n in E.items():
    ka,kb=node(a),node(b)
    if ka==kb: continue
    key=tuple(sorted((ka,kb))); edges[key]=edges.get(key,0)+n
fig,ax=plt.subplots(figsize=(15,15),facecolor="black"); ax.set_facecolor("black")
ax.add_patch(Rectangle((0,0),DX,DY,fill=False,ec="#777",lw=1.2))
for inst,(x,y) in insts.items():
    mst=master(inst); w,h=sizes[mst]; ax.add_patch(Rectangle((x,y),w,h,color=col[mst],alpha=0.35,lw=0))
for k,(x,y) in pos.items():
    if k in insts or k in ("Tile array (64)","IO"): continue
    n=nodes[k][0]; r=4+math.sqrt(n)/6
    ax.add_patch(Circle((x,y),r,color="#dddddd",alpha=0.25,lw=0)); ax.add_patch(Circle((x,y),r,fill=False,ec="#eeeeee",lw=0.8))
    ax.text(x,y+r+4,f"{k}\n{n:,} cells",ha="center",va="bottom",fontsize=7.5,color="white")
for (a,b),n in sorted(edges.items(),key=lambda kv:kv[1]):
    if n<MIN_NETS: continue
    (x1,y1),(x2,y2)=pos[a],pos[b]; lw=0.6*math.log2(n/MIN_NETS+1)+0.4
    c="#ff5f5f" if n>=1000 else "#ffb347" if n>=300 else "#9ad1ff"
    ax.plot([x1,x2],[y1,y2],color=c,lw=lw,alpha=0.85,solid_capstyle="round")
    ax.text((x1+x2)/2,(y1+y2)/2,f"{n}",fontsize=6.5,color=c,ha="center",va="center",bbox=dict(boxstyle="round,pad=0.15",fc="black",ec="none",alpha=0.7))
for inst,(x,y) in insts.items():
    mst=master(inst)
    if mst=="Tile": continue
    w,h=sizes[mst]; short={"LoopConv":"LoopConv (mod)","AccumulatorScale":"AccumulatorScale","AlwaysOutTransposer":"Transposer"}.get(mst)
    if not short: short=("spad bank "+re.search(r"spad_mems_(\d)",inst).group(1)) if mst=="mem_ext_phys" else "acc %s/%s"%re.search(r"acc_mems_(\d).*bank_(\d)",inst).groups()
    ax.text(x+w/2,y+h/2,short,ha="center",va="center",fontsize=8,color="white",alpha=0.9)
ax.text(*pos["Tile array (64)"],"Tile array\n64 macros",ha="center",va="center",fontsize=10,color="white")
ax.text(DX/2,-40,"top-level IO pins",ha="center",va="center",fontsize=9,color="white")
ax.set_xlim(-10,DX+10); ax.set_ylim(-70,DY+10); ax.set_aspect("equal"); ax.tick_params(colors="white"); [s.set_color("#555") for s in ax.spines.values()]
ax.set_title(f"Connectivity over the placed floorplan: line = nets joining two groups (label = net count, only >= {MIN_NETS} shown).\n"
             "Macros drawn at their placed outline; flat logic drawn as a circle at its placed centroid (area ~ cell count). Clock and power nets excluded.",color="white",fontsize=10.5)
plt.tight_layout(); plt.savefig(out,dpi=110,facecolor="black"); print("saved",out)
