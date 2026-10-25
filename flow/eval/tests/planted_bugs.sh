#!/usr/bin/env bash
# Regression test for the equivalence gate: two deliberately broken netlists made from a reference
# result must fail, and the untouched originals must pass. Run after any change under flow/eval/.
#
#   flow/eval/tests/planted_bugs.sh <result dir>     e.g. baseline/ after run_baseline.sh
#
# Tile: the D inputs of the flip-flops tile_0_0.c1[10] and tile_0_0.c1[11] are swapped (a wrong wire).
# StoreController: the 40th AND2x2 cell becomes an OR2x2 (a wrong gate). The gate must report both as
# failed, with the originals proven. About 5 minutes.
set -uo pipefail
RES=$(cd "${1:?usage: planted_bugs.sh <result dir>}" && pwd)
HERE=$(cd "$(dirname "$0")/../../.." && pwd)
# shellcheck disable=SC1091
source "$HERE/orfs/env.sh" > /dev/null 2>&1
for f in Tile.v Tile.def StoreController.v StoreController.def; do
  [ -f "$RES/blocks/$f" ] || { echo "planted_bugs: $RES/blocks/$f is missing; pass a complete result directory"; exit 2; }
done
T="$HERE/eval_work/planted_bugs"; rm -rf "$T"; mkdir -p "$T/tile/blocks" "$T/sc/blocks"
cp "$RES/blocks/Tile.v" "$RES/blocks/Tile.def" "$T/tile/blocks/"
cp "$RES/blocks/StoreController.v" "$RES/blocks/StoreController.def" "$T/sc/blocks/"
python3 - "$T" <<'PY'
import re, sys
t = sys.argv[1]
p = f"{t}/tile/blocks/Tile.v"; s = open(p).read()
pat = lambda n: re.compile(r"(DFFHQNx\d_ASAP7_75t_R \\tile_0_0\.c1\[" + str(n) + r"\]\$\S+\s+\(\.CLK\(\S+\),\s+\.D\()(\S+?)(\))")
a, b = pat(10).search(s), pat(11).search(s)
if not (a and b): sys.exit("planted_bugs: tile_0_0.c1[10] or [11] not found in Tile.v")
da, db = a.group(2), b.group(2)
s = s[:a.start(2)] + db + s[a.end(2):]
b = pat(11).search(s); s = s[:b.start(2)] + da + s[b.end(2):]
open(p, "w").write(s); print(f"planted_bugs: Tile: swapped D of c1[10] ({da}) and c1[11] ({db})")
p = f"{t}/sc/blocks/StoreController.v"; L = open(p).read().split("\n")
idx = [i for i, l in enumerate(L) if l.startswith(" AND2x2_ASAP7_75t_R")]
if len(idx) < 40: sys.exit("planted_bugs: fewer than 40 AND2x2 cells in StoreController.v")
L[idx[39]] = L[idx[39]].replace("AND2x2_ASAP7_75t_R", "OR2x2_ASAP7_75t_R")
open(p, "w").write("\n".join(L)); print(f"planted_bugs: StoreController: AND2x2 at line {idx[39] + 1} changed to OR2x2")
PY
ok=0; bad=0
check() { # check <label> <module> <result dir> <expect: PASS|FAIL>
  local label=$1 mod=$2 res=$3 expect=$4 out
  out=$(EQUIV_ONLY=$mod EQUIV_JOBS=${EQUIV_JOBS:-8} python3 "$HERE/flow/eval/equiv.py" "$res" "$T/work_$label" 2>&1 | grep "^GATE equivalence" | cut -c1-120)
  if echo "$out" | grep -q "GATE equivalence $expect" && ! echo "$out" | grep -q " 0/0 "; then echo "ok    $label: $out"; ok=$((ok+1)); else echo "WRONG $label (expected $expect): $out"; bad=$((bad+1)); fi
}
check tile_original Tile "$RES" PASS
check tile_broken Tile "$T/tile" FAIL
check storecontroller_original StoreController "$RES" PASS
check storecontroller_broken StoreController "$T/sc" FAIL
echo "planted_bugs: $ok right, $bad wrong"
[ $bad -eq 0 ]
