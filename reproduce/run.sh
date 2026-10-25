#!/usr/bin/env bash
# The reference as an entry, under the judge's contract (judge/run_entry.sh): the repository is mounted
# read-only at /entry, the pinned inputs at /design, and the result goes to /result. The flow needs a
# writable tree, so it works on a copy, with the pinned inputs linked in; there is no network, so the
# optional equivalence tool is not built here (the judge has its own).
set -euo pipefail
rm -rf /tmp/entry; cp -r /entry /tmp/entry; cd /tmp/entry
rm -rf design; ln -s /design design
SKIP_EQY=1 ./setup.sh
./run_baseline.sh
cp -r baseline/. /result/
