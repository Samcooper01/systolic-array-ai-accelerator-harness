#!/usr/bin/env bash
# The judge's side of a submission: build the entry's container, run its flow under the budget with no
# network, then evaluate what it produced.
#
#   judge/run_entry.sh                                  # this repository at its latest commit, as "mine"
#   judge/run_entry.sh <repository url or path> <commit> [name]
#
# Writes judge_work/<name>/: repo/ (the clone at the commit), result/ (what the entry's flow produced),
# run.log, judge.json (wall-clock time, exit code, the entry's own runtime.json chain if it wrote one),
# and the evaluator's report under eval_work/<name>/ (evaluation.json). The evaluator runs in the pinned
# image, so an entrant can run this on their own latest commit (judge/run_entry.sh, no arguments) and get
# exactly what the official run does. Only committed work is tested: the entry is cloned at the commit.
#
# Contract for the entry (see submission/README.md): reproduce/Dockerfile builds its container; inside
# it, /entry/reproduce/run.sh regenerates the result from the pinned inputs mounted read-only at /design (this
# harness's design/: RTL, SRAM macros, activity) and writes /result (top.def, top.v, period.txt,
# blocks/<name>.{def,v}). It gets 16 threads, 64 GB and no network, with the budget in scoring.yaml (12 hours); the
# compute-budget gate is the longest dependency chain, so a flow that parallelizes its blocks may also
# write /result/runtime.json (as run_baseline.sh does) for the chain to be read; the logs are kept and a
# person reviews the flow of every leading entry.
set -uo pipefail
HERE=$(cd "$(dirname "$0")/.." && pwd)
# with no arguments: this repository (an entry forked from the harness) at its latest commit, named mine
REPO=${1:-$HERE}; COMMIT=${2:-$(git -C "$REPO" rev-parse HEAD 2>/dev/null)}; NAME=${3:-mine}
[ -n "$COMMIT" ] || { echo "usage: judge/run_entry.sh [<repository url or path> <commit> [name]]"; exit 1; }
if [ -d "$REPO/.git" ] && [ -n "$(git -C "$REPO" status --porcelain --untracked-files=no)" ]; then
  echo "note: $REPO has uncommitted changes; only commit $COMMIT is tested"
fi
J="$HERE/judge_work/$NAME"; mkdir -p "$J/result"
# the budget in hours comes from scoring.yaml (compute_budget: hours), so the two cannot drift apart
BUDGET_H=${BUDGET_H:-$(awk '/^ *hours:/ {print $2; exit}' "$HERE/scoring.yaml")}; CPUS=${CPUS:-16}; MEM=${MEM:-64g}
[ -n "$BUDGET_H" ] || { echo "no compute_budget hours in scoring.yaml"; exit 1; }
# The gate is the longest dependency chain (block, then its parent, then the top), which a flow that
# builds blocks in parallel reports in /result/runtime.json. The wall clock is only a safety stop, at 1.5
# times the budget: a flow with no runtime.json is judged on wall-clock time instead.
WALL_CAP_H=$(python3 -c "print($BUDGET_H * 1.5)")

if [ ! -d "$J/repo/.git" ]; then git clone -q "$REPO" "$J/repo" || { echo "clone failed"; exit 1; }; fi
git -C "$J/repo" fetch -q origin 2>/dev/null; git -C "$J/repo" checkout -q "$COMMIT" || { echo "commit $COMMIT not found"; exit 1; }
echo "entry $NAME at $(git -C "$J/repo" rev-parse HEAD)"
[ -f "$J/repo/reproduce/Dockerfile" ] || { echo "no reproduce/Dockerfile in the entry"; exit 1; }

IMG="chipbase-entry-$NAME"
docker build -q -t "$IMG" "$J/repo/reproduce" > "$J/build.log" 2>&1 || { echo "container build failed, see $J/build.log"; exit 1; }
# an empty /result, even when this name was run before: the container writes as root, so clear it there
docker run --rm -v "$J/result:/result" "$IMG" find /result -mindepth 1 -delete

echo "running the entry's flow: $CPUS threads, $MEM, no network, $BUDGET_H h budget on the dependency chain ($WALL_CAP_H h wall-clock stop)"
t0=$(date +%s)
timeout "${WALL_CAP_H}h" docker run --rm --name "judge_$NAME" --network none --cpus "$CPUS" --memory "$MEM" --memory-swap "$MEM" \
  -v "$HERE/design:/design:ro" -v "$J/repo:/entry:ro" -v "$J/result:/result" -w /entry "$IMG" bash /entry/reproduce/run.sh > "$J/run.log" 2>&1
rc=$?; wall=$(( $(date +%s) - t0 ))
echo "flow exit $rc after $wall s"

python3 - "$J" "$rc" "$wall" "$BUDGET_H" <<'PY'
import json, os, sys
j, rc, wall, budget = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), float(sys.argv[4])
out = {"exit": rc, "wall_s": wall, "budget_s": int(budget * 3600), "timed_out": rc == 124}
rt = os.path.join(j, "result", "runtime.json")
if os.path.exists(rt):
    try:
        r = json.load(open(rt)); chains = r.get("chains_s", {})
        out["entry_runtime_json"] = {"critical_chain_s": max(chains.values()) if chains else None, "chains_s": chains}
    except Exception as e:
        out["entry_runtime_json"] = f"unreadable: {e}"
chain = out["entry_runtime_json"]["critical_chain_s"] if isinstance(out.get("entry_runtime_json"), dict) else None
measured = chain if chain is not None else wall
out["budget_measure"] = "dependency chain from the entry's runtime.json" if chain is not None else "wall clock (no runtime.json)"
out["budget_gate"] = "PASS" if rc == 0 and measured <= budget * 3600 else "FAIL"
json.dump(out, open(os.path.join(j, "judge.json"), "w"), indent=1)
print(f"compute budget: {out['budget_gate']} ({out['budget_measure']}: {measured} s of {int(budget*3600)} s; wall clock {wall} s)")
PY
[ $rc -eq 0 ] || exit 1
# Scored in the pinned image (versions.lock) with the image's own tools, whatever this machine has
# installed, so every entry, and an entrant's own test, is scored by the same evaluator in the same image.
EVAL_IMG=$(awk '$1 == "container" {print $3}' "$HERE/versions.lock")
[ -n "$EVAL_IMG" ] || { echo "no container in versions.lock"; exit 1; }
echo "evaluating in $EVAL_IMG"
docker run --rm --name "eval_$NAME" -v "$HERE:/harness" -w /harness -e ORFS_HOME=/OpenROAD-flow-scripts "$EVAL_IMG" \
  ./evaluate.sh "judge_work/$NAME/result" --work "/harness/eval_work/$NAME"
