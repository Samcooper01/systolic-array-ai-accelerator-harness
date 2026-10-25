# Submitting an entry

An entry is a git repository of source, with nothing built in it. The judge builds your layout from the
repository and scores what it builds, so the layout itself is never committed. It could not be anyway:
the reference result is about 2.4 GB, its top-level DEF (Design Exchange Format) file alone is 432 MB,
and GitHub refuses any file over 100 MB.

## What the repository holds

- `reproduce/Dockerfile`: the container your flow runs in, open tools, pinned
- `reproduce/run.sh`: builds the result from the pinned inputs, with no network, within the 12 hour
  chain budget on 16 threads and 64 GB
- your flow: scripts, settings, and any tools you add
- optionally, floorplan constraints: block and macro locations, pin placement, placement regions

It may not hold a finished standard-cell placement, routing, or gate netlist (see the rules recap
below). This harness's own `reproduce/` is the reference flow packaged as an entry, and it passes the
judge, so copying it and pointing `run.sh` at your flow is the quickest start.

Keep build outputs out of git. This harness's `.gitignore` already does that for a fork; a repository
of your own needs at least these lines, plus whatever directories your own flow writes to:

    /result/
    /work/
    /baseline/
    /eval_work/
    *.log

## What `run.sh` writes

The judge gives `run.sh` an empty `/result`, and `run.sh` writes the result into it:

- `top.def`: the routed top-level layout
- `top.v`: the top-level gate netlist
- `period.txt`: the clock period you declare, in picoseconds (you must pass timing at it)
- `blocks/<name>.{def,v}`: every block you hardened, layout and netlist; empty if you ran flat
- `runtime.json`: if your flow builds blocks in parallel, in the shape `run_baseline.sh` produces
  (per-step seconds and the dependency chains); the budget gate is the longest chain when you report
  one, and your wall-clock time when you do not
- optionally `top.spef`, `final.gds`, and each block's `.lef` and `.lib`; the judge extracts its own
  parasitics and streams its own layout from the DEF files, so these are for your own checks

## How the judge runs it

`judge/run_entry.sh <repository> <commit> [name]` clones your repository at the commit, builds
`reproduce/Dockerfile`, then runs `/entry/reproduce/run.sh` inside the container with your repository
mounted read-only at `/entry`, this harness's `design/` (the RTL, the SRAM macros, the activity file)
mounted read-only at `/design`, and the empty `/result` to write into; 16 threads, 64 GB, no network,
and a stop at 18 hours of wall-clock time. It then scores `/result` with the evaluator, inside the
pinned image named in `versions.lock`. So `run.sh` must read its
inputs from `/design`. The logs are kept, and a person reviews the flow of every leading entry before it
is certified.

## Test before you submit

While you work, build and score inside the pinned container, as often as you like:

    ./run_baseline.sh          # runs your flow into baseline/, as reproduce/run.sh does
    ./evaluate.sh baseline/

Once, before you submit, run your entry the way the official run will, with its own runner. Commit
first: like the official run, it builds a commit, not your working tree. Run it in a terminal on your
machine itself, outside the container, since it starts containers of its own, from your fork's
directory:

    judge/run_entry.sh

With no arguments it tests the latest commit of the repository it sits in, under the name `mine`. For
an entry that is not a fork of this harness, run it from the harness and give the entry's location and
commit: `judge/run_entry.sh <path or URL> <commit>`.

It clones the commit into `judge_work/mine/repo/`, builds your container, runs `run.sh` under the same
limits and mounts the official run uses, writes the result to `judge_work/mine/result/`, and reports the
compute-budget gate in `judge_work/mine/judge.json`. It then scores the result in the pinned image and
writes the evaluator's summary to `eval_work/mine/evaluation.json`, about a kilobyte: every gate, every
metric, and the score. This catches what building in your working container cannot: a Dockerfile that
does not build, a flow that needs the network or files you have not committed, and the budget. The run
uses about 45 GB of Docker's storage while it runs, and the evaluation about 16 GB.

## Sending it in

Open an issue on this repository with:

- the repository and the commit to judge
- your local `evaluation.json`, pasted in

The judge's own run decides the score; yours is checked against it, so a large difference is
investigated before anything is ranked.

## Rules recap

Open tools only; any partition; the design must stay Gemmini (every netlist is proven against the
pinned synthesis of its module, which the judge runs itself); synthesis is pinned, so no retiming, scan
insertion, or duplicated/merged registers beyond what it does itself; the fixed constraints stay fixed
except the clock period; no finished placement, routing, or netlist shipped in the repository or inside
the container.
