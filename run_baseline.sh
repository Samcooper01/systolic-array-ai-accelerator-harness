#!/usr/bin/env bash
# The reference flow. Ten block types are hardened in parallel (the 64 Tiles share one), then the top
# level (flow/gemmini/config_tight2.mk: ExecuteController and Scratchpad opened, a hand floorplan) runs
# to a finished layout. Two steps follow that the stock flow does not do:
#   hold loop     the post-global-route hold repair works from estimated parasitics, so the routed
#                 layout can miss hold by a few tens of ps. While the worst hold slack is negative,
#                 flow/eco_hold.tcl repairs hold on the extracted parasitics, and the top is routed again
#                 from that database in a fresh variant (eco1, eco2, ...).
#   two corners   the flow runs at the platform default corner, BC (fast: FF libraries), which is the
#                 hold corner. Setup is judged at the slow corner, so each block also gets a slow-corner
#                 timing model and the declared period comes from a slow-corner setup search.
# Runtime is measured the way the compute-budget gate measures it: each block, then the top, and the
# gate is the longest block plus the top (every top stage, hold loop included).
set -uo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
[ -d "$HERE/orfs" ] || { echo "run ./setup.sh first"; exit 1; }
# shellcheck disable=SC1091
source "$HERE/orfs/env.sh"
export WORK_HOME="$HERE/work"
mkdir -p "$WORK_HOME" "$HERE/baseline/blocks"
BIG=${BIG_CORES:-8}; SMALL=${SMALL_CORES:-4}; TOP_CORES=${TOP_CORES:-16}; HOLD_ROUNDS=${HOLD_ROUNDS:-3}
LOG="$WORK_HOME/runtimes.log"; : > "$LOG"
FLOW="$HERE/orfs/flow"; G="$HERE/flow/gemmini"; TOP_CFG="$G/config_tight2.mk"; TOP=gemmini_flat
BLOCKS="Tile AlwaysOutTransposer AccumulatorScale LoopConv LoopMatmul ReservationStation LoadController StoreController FrontendTLB CounterController"

cfg(){ case $1 in Tile|AlwaysOutTransposer) echo ExecuteController/$1;; AccumulatorScale) echo Scratchpad/$1;; *) echo $1;; esac; }
timed(){ # timed <name> <make args...>: run make, log "<name> <rc> <seconds> <peak kB>"
  local name=$1; shift; local t0; t0=$(date +%s)
  /usr/bin/time -v -o "$WORK_HOME/time_$name.txt" make -C "$FLOW" "$@" > "$WORK_HOME/log_$name.txt" 2>&1
  local rc=$?
  echo "$name $rc $(( $(date +%s) - t0 )) $(grep 'Maximum resident' "$WORK_HOME/time_$name.txt" | awk '{print $NF}')" >> "$LOG"
  return $rc
}
block(){ # the top expects each block under results/asap7/<top nickname>_<block>/base
  local B=$1 cores=$2
  timed "$B" DESIGN_CONFIG="$G/$(cfg $B)/config.mk" DESIGN_NICKNAME=${TOP}_$B NUM_CORES=$cores generate_abstract \
    || { echo "block $B failed, see work/log_$B.txt"; exit 1; }
}
link_blocks(){ # blocks are built once, in base; a top variant finds them under its own variant name
  local v=$1
  for B in $BLOCKS; do for d in results logs reports objects; do
    [ -e "$WORK_HOME/$d/asap7/${TOP}_$B/base" ] && ln -sfn base "$WORK_HOME/$d/asap7/${TOP}_$B/$v"
  done; done
}
res(){ echo "$WORK_HOME/results/asap7/$TOP/$1"; }

echo "== blocks (parallel) =="
for B in $BLOCKS; do
  case $B in LoopConv|AccumulatorScale|ReservationStation) block $B $BIG & ;; *) block $B $SMALL & ;; esac
done
wait
for B in $BLOCKS; do
  [ -f "$WORK_HOME/results/asap7/${TOP}_$B/base/$B.lef" ] || { echo "block $B has no abstract"; exit 1; }
done

echo "== top ($TOP_CORES threads) =="
timed top DESIGN_CONFIG="$TOP_CFG" NUM_CORES=$TOP_CORES || { echo "top failed, see work/log_top.txt"; exit 1; }

echo "== hold loop =="
V=base
for i in $(seq 1 "$HOLD_ROUNDS"); do
  make -C "$FLOW" DESIGN_CONFIG="$TOP_CFG" FLOW_VARIANT=$V open_6_final.odb < "$HERE/flow/hold_check.tcl" > "$WORK_HOME/log_hold_$V.txt" 2>&1
  wh=$(awk '/^WORST_HOLD/{print $2}' "$WORK_HOME/log_hold_$V.txt"); echo "$V: worst hold ${wh:-?} ps"
  [ -n "$wh" ] || { echo "hold check failed, see work/log_hold_$V.txt"; exit 1; }
  awk -v w="$wh" 'BEGIN{exit !(w >= 0)}' && break
  N=eco$i; margin=$([ "$i" = 1 ] && echo 15 || echo 25)
  for d in results logs reports objects; do
    mkdir -p "$WORK_HOME/$d/asap7/$TOP/$N"
    for f in "$WORK_HOME/$d/asap7/$TOP/$V"/{1_,2_,3_}* "$WORK_HOME/$d/asap7/$TOP/$V"/{clock_period.txt,mem.json}; do
      [ -e "$f" ] && cp -a "$f" "$WORK_HOME/$d/asap7/$TOP/$N/"
    done
  done
  link_blocks $N
  cp "$(res $V)/5_route.sdc" "$(res $N)/4_cts.sdc"
  t0=$(date +%s)
  echo "source $HERE/flow/eco_hold.tcl" | ECO_MARGIN=$margin ECO_OUT="$(res $N)/4_cts.odb" \
    make -C "$FLOW" DESIGN_CONFIG="$TOP_CFG" FLOW_VARIANT=$V open_5_route.odb > "$WORK_HOME/log_eco_$N.txt" 2>&1
  [ -f "$(res $N)/4_cts.odb" ] || { echo "hold ECO failed, see work/log_eco_$N.txt"; exit 1; }
  cp -a "$(res $N)/4_cts.odb" "$(res $N)/4_1_cts.odb"; touch -r "$(res $N)/4_cts.odb" "$(res $N)/4_1_cts.odb" "$(res $N)/4_cts.sdc"
  echo "eco_$N 0 $(( $(date +%s) - t0 )) 0" >> "$LOG"
  timed "top_$N" DESIGN_CONFIG="$TOP_CFG" FLOW_VARIANT=$N NUM_CORES=$TOP_CORES finish \
    || { echo "top re-route $N failed, see work/log_top_$N.txt"; exit 1; }
  V=$N
done
awk -v w="$wh" 'BEGIN{exit !(w >= 0)}' || { echo "hold not met after $HOLD_ROUNDS rounds (worst $wh ps)"; exit 1; }
RES=$(res $V); echo "final layout: $V"

echo "== slow-corner block models =="
for B in $BLOCKS; do
  BR="$WORK_HOME/results/asap7/${TOP}_$B/base"
  SLOW_LIB="$BR/${B}_slow.lib" make -C "$FLOW" DESIGN_CONFIG="$G/$(cfg $B)/config.mk" DESIGN_NICKNAME=${TOP}_$B CORNER=WC \
    open_6_final.odb < "$HERE/flow/slow_abstract.tcl" > "$WORK_HOME/log_slow_$B.txt" 2>&1 &
done
wait
for B in $BLOCKS; do
  D="$WORK_HOME/results/asap7/${TOP}_$B"; [ -f "$D/base/${B}_slow.lib" ] || { echo "no slow model for $B"; exit 1; }
  mkdir -p "$D/slow"; ln -sfn "../base/${B}_slow.lib" "$D/slow/${B}_typ.lib"; ln -sfn "../base/$B.lef" "$D/slow/$B.lef"
  ln -sfn ../base/6_final.gds "$D/slow/6_final.gds"
  for d in logs reports objects; do [ -e "$WORK_HOME/$d/asap7/${TOP}_$B/base" ] && ln -sfn base "$WORK_HOME/$d/asap7/${TOP}_$B/slow"; done
done
for d in results logs reports objects; do mkdir -p "$WORK_HOME/$d/asap7/$TOP/slow"; done
for f in 6_final.odb 6_final.sdc 6_final.spef; do ln -sfn "../$V/$f" "$(res slow)/$f"; done

echo "== declared period: slow-corner setup; fast-corner hold checked at that period =="
make -C "$FLOW" DESIGN_CONFIG="$TOP_CFG" FLOW_VARIANT=slow CORNER=WC SETUP_ONLY=1 run RUN_SCRIPT="$HERE/flow/time_at_period.tcl" SEARCH=1 \
  > "$WORK_HOME/log_period_slow.txt" 2>&1 || { echo "slow-corner period search failed, see work/log_period_slow.txt"; exit 1; }
P=$(cat "$(res slow)/declared_period.txt")
make -C "$FLOW" DESIGN_CONFIG="$TOP_CFG" FLOW_VARIANT=$V run RUN_SCRIPT="$HERE/flow/time_at_period.tcl" PERIODS="$P" \
  > "$WORK_HOME/log_period_fast.txt" 2>&1
grep -E "^PERIOD" "$WORK_HOME/log_period_fast.txt" | awk '{ if ($6 < 0) { print "fast-corner hold fails at the declared period: " $0; exit 1 } }' || exit 1
echo "declared period $P ps"; echo "$P" > "$RES/declared_period.txt"

cp "$RES/6_final.def" "$HERE/baseline/top.def"; cp "$RES/6_final.v" "$HERE/baseline/top.v"
cp "$RES/6_final.spef" "$HERE/baseline/top.spef"; cp "$RES/6_final.gds" "$HERE/baseline/final.gds"
cp "$RES/declared_period.txt" "$HERE/baseline/period.txt"
for B in $BLOCKS; do
  BR="$WORK_HOME/results/asap7/${TOP}_$B/base"
  cp "$BR/6_final.def" "$HERE/baseline/blocks/$B.def"; cp "$BR/6_final.v" "$HERE/baseline/blocks/$B.v"
  cp "$BR/$B.lef" "$HERE/baseline/blocks/$B.lef"; cp "$BR/${B}_typ.lib" "$HERE/baseline/blocks/$B.fast.lib"
  cp "$BR/${B}_slow.lib" "$HERE/baseline/blocks/$B.slow.lib"
done
WORK_HOME="$WORK_HOME" python3 "$HERE/flow/metrics.py" $TOP $V > "$HERE/baseline/metrics.json"
python3 - "$LOG" "$HERE/baseline/runtime.json" "$BLOCKS" <<'PY'
import sys,json
t={}
for l in open(sys.argv[1]):
    f=l.split()
    if len(f)>=3: t[f[0]]=(int(f[2]),int(f[3]) if len(f)>3 and f[3].isdigit() else 0)
blocks=sys.argv[3].split()
top=sum(v[0] for k,v in t.items() if k=="top" or k.startswith("top_") or k.startswith("eco_"))
chains={b:t[b][0]+top for b in blocks if b in t}
crit=max(chains,key=chains.get)
out={"per_step_s":{k:v[0] for k,v in t.items()},"top_total_s":top,"chains_s":chains,"critical_path":f"{crit}>top",
     "critical_path_s":chains[crit],"peak_kb_any":max(v[1] for v in t.values())}
json.dump(out,open(sys.argv[2],"w"),indent=1); print(f"critical path {crit} then top: {chains[crit]/3600:.2f} h; peak {out['peak_kb_any']/1e6:.1f} GB")
PY
echo "Reference done. Artifacts in baseline/, metrics in baseline/metrics.json, runtime in baseline/runtime.json."
