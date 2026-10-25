#!/usr/bin/env bash
# Pin the flow. Inside the pinned container image (see README: openroad/flow-ubuntu22.04-builder at a
# fixed digest) OpenROAD-flow-scripts is already built at /OpenROAD-flow-scripts, at the pinned commit:
# link it. Anywhere else, clone OpenROAD-flow-scripts at the pinned commit; its tools (OpenROAD, Yosys
# with the slang plugin, KLayout) must then be built or installed per the ORFS docs.
set -euo pipefail
ORFS_COMMIT=bde10c79a2389ffe9c5d73445f177f81262059f9
ORFS_REPO=https://github.com/The-OpenROAD-Project/OpenROAD-flow-scripts
HERE=$(cd "$(dirname "$0")" && pwd)
if [ -e "$HERE/orfs" ]; then
  echo "orfs already present: $(readlink -f "$HERE/orfs")"
elif [ -x /OpenROAD-flow-scripts/tools/install/OpenROAD/bin/openroad ]; then
  ln -s /OpenROAD-flow-scripts "$HERE/orfs"
  echo "Linked the container's OpenROAD-flow-scripts (built at $ORFS_COMMIT)."
else
  git clone "$ORFS_REPO" "$HERE/orfs"
  git -C "$HERE/orfs" checkout "$ORFS_COMMIT"
  git -C "$HERE/orfs" submodule update --init --recursive
  echo "Cloned ORFS at $ORFS_COMMIT. Build its tools per the ORFS docs (or use the container, see README)."
fi
# shellcheck disable=SC1091
source "$HERE/orfs/env.sh" > /dev/null 2>&1 || true
for t in openroad yosys klayout; do command -v $t > /dev/null || { echo "missing tool: $t"; exit 1; }; done
# The equivalence gate uses eqy (YosysHQ's equivalence checker) and its sby dependency, which the container
# does not carry. Build both at pinned commits into tools/eqy, with eqy's Yosys plugins compiled against the
# flow's own Yosys (yosys-config), so they load into exactly that Yosys.
EQY_COMMIT=7a92d8441aa442dd1b5543458d6f1060a8f85dd1
SBY_COMMIT=b1a1e98cba941ec8433f8dc27f416cd7bb7f14be
TOOLS="$HERE/tools"
if [ "${SKIP_EQY:-0}" = 1 ]; then
  echo "eqy build skipped (SKIP_EQY=1): the equivalence gate's optional RTL-side check needs it, the flow does not."
elif [ ! -x "$TOOLS/eqy/bin/eqy" ]; then
  mkdir -p "$TOOLS/src"
  for r in eqy:$EQY_COMMIT sby:$SBY_COMMIT; do
    n=${r%%:*}; c=${r#*:}
    [ -d "$TOOLS/src/$n" ] || git clone -q "https://github.com/YosysHQ/$n" "$TOOLS/src/$n"
    git -C "$TOOLS/src/$n" checkout -q "$c"
  done
  make -s -C "$TOOLS/src/sby" install PREFIX="$TOOLS/eqy" > /dev/null
  make -s -C "$TOOLS/src/eqy" install PREFIX="$TOOLS/eqy" YOSYS_CONFIG="$(command -v yosys-config)" > /dev/null
fi
[ "${SKIP_EQY:-0}" = 1 ] || "$TOOLS/eqy/bin/eqy" --version > /dev/null || { echo "eqy did not build (see tools/src/eqy)"; exit 1; }
echo "Tools: $(openroad -version 2>/dev/null | head -1), $(yosys -V | cut -d' ' -f1-2), $(klayout -v)$([ "${SKIP_EQY:-0}" = 1 ] || echo ", eqy ${EQY_COMMIT:0:7}")"
echo "Next: ./run_baseline.sh   then   ./evaluate.sh baseline/"
