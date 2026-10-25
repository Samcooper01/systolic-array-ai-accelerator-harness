#!/usr/bin/env bash
# Validate the harness the way a new user meets it: a fresh clone of this repository at the current
# commit, the pinned container image, and exactly the README's commands, with nothing from this
# checkout's own flow or work directories. About 6 hours (5 for the flow, 1 for the evaluator), peak
# about 30 GB.
#
#   judge/validate_reference.sh [work dir]      default: ../harness-validate next to this checkout
#
# Writes <work dir>/harness (the clone, with baseline/ and eval_work/ inside), <work dir>/validate.log,
# and the container's exit code. Expected end: "ALL GATES PASS" and "FOM 1.000".
set -uo pipefail
HERE=$(cd "$(dirname "$0")/.." && pwd)
V=${1:-"$HERE/../harness-validate"}; mkdir -p "$V"; V=$(cd "$V" && pwd)
IMAGE=$(awk -F'= *' '/^container /{print $2}' "$HERE/versions.lock" | awk '{print $1}')
[ -n "$IMAGE" ] || { echo "no container pin in versions.lock"; exit 1; }
rm -rf "$V/harness"
git clone -q "$HERE" "$V/harness" || { echo "clone failed"; exit 1; }
echo "$(date +%T) start (commit $(git -C "$V/harness" log --oneline -1); image $IMAGE)" > "$V/validate.log"
docker run --rm --name chipbase_validate -v "$V/harness:/work" -w /work "$IMAGE" bash -c '
  set -o pipefail
  ./setup.sh 2>&1 | tee setup.log || exit 11
  /usr/bin/time -v -o baseline_time.txt ./run_baseline.sh 2>&1 | tee baseline.log || exit 12
  /usr/bin/time -v -o evaluate_time.txt ./evaluate.sh baseline/ 2>&1 | tee evaluate.log || exit 13
' >> "$V/validate.log" 2>&1
rc=$?
echo "$(date +%T) container exit $rc" >> "$V/validate.log"
grep -E "GATE|FOM|ALL GATES|declared period|critical path" "$V/validate.log" | cut -c1-200
exit $rc
