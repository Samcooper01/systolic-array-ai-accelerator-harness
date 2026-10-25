# Handoff: state of the harness and what remains

Written 2026-10-15 for whoever (person or agent session) continues this work on another machine. The
repository holds everything needed to run the flow and the judge; this file holds what is not in the
code: what has been validated and how, why the gates are designed as they are, what was tried and
abandoned, and what is still open. Read it before changing anything in `flow/eval/`.

On 2026-10-21 the repository moved to `Samcooper01/systolic-array-ai-accelerator-harness`, with its full
history, and the challenge page was retitled "Systolic Array AI Accelerator". The earlier repository,
`Samcooper01/ChipBase-CVA6-Challenge-Harness`, is no longer updated.

## Where things stand

The harness does what it was built to do: clone it, follow the README inside the pinned container, run
the reference flow and the evaluator, and get the reference score. This was validated five times:

| run | what | result |
|---|---|---|
| development machine | `run_baseline.sh` then `evaluate.sh` | 6,391 ps, 628,065 um2, 1.3455 W, every gate pass |
| fresh clone, pinned container (2026-10-05) | same commands, nothing from the host | identical numbers, every gate pass, 1.000 |
| `judge/run_entry.sh` on this repository as the entry (2026-10-06) | `reproduce/Dockerfile` on the published OpenROAD-flow-scripts image, no network, 16 processors, 64 GB | identical numbers, every gate pass, 1.000; chain 5.65 h |
| the evaluator alone inside the published image (2026-10-23) | fresh clone at 5c57f62, `./evaluate.sh judge_work/mine/result/` on the 2026-10-06 judge result, mounted read-only, 34 GB memory cap | every gate pass, 1.000, 57 minutes |
| `judge/run_entry.sh` end to end, scoring in the pinned image (2026-10-23) | a test entry whose `run.sh` copies the 2026-10-06 result, so the runner's own steps are tested: clone, Dockerfile build, no-network run, budget, then the evaluator in the pinned image | every gate pass, 1.000; budget pass; 60 minutes |

The flow has reproduced bit for bit across those runs (the same hold slack after each repair round,
down to 0.01 ps). Multithreaded routing is not guaranteed identical on different hardware, so a small
difference elsewhere is possible but has not been seen.

Hardware used: 32 threads, 62 GB. The top's detailed routing peaks at about 27 GB; the evaluator at
about 30 GB (top-level parasitic extraction). A judge run is capped at 16 processors and 64 GB.

## Decisions and their reasons

- Gemmini replaced CVA6 (an open 64-bit application processor core) on 2026-09-27 because it is flat and closes too easily; the competition is
  meant to be floorplanning-heavy but low-barrier. The compact nine-block-plus-flat-logic partition is
  the only reference (an earlier three-level hierarchy and a two-block variant were dropped).
- The clock period is the entrant's lever: the reference declares the slowest clock that passes setup
  at the slow corner (6,391 ps), and the score rewards a faster one. Hold must be met; setup is handled
  by the declared period. The reference does not try to be fast.
- RTL (Register Transfer Level) changes and retiming are not allowed; the gate is physical design only, which is why synthesis
  is pinned and the equivalence gate compares against it. An entrant can change any partition,
  floorplan, pin placement, clock tree, power grid, cell choice or tool setting.
- Runtime is a gate (12 hours on 16 threads, 64 GB), not part of the cost, measured along the
  dependency chain so a hierarchical flow is not penalized for building blocks in parallel. Sam
  raised it from 6 to 12 hours on 2026-10-22, so the reference chain (5.1 to 5.7 hours) no longer
  sits close to the limit; `judge/run_entry.sh` reads it from `scoring.yaml`.
- Power is measured at a fixed 1,000 ps clock with pinned activity, so slowing the clock does not
  lower the power score; the IR (current times resistance) drop limit (110 mV) is the reference's 84 mV with margin.
- Cost weights are fixed up front: speed 0.30, area 0.50, power 0.20, decided 2026-10-22. Area leads
  because the competition is meant to be floorplanning-heavy and die area is the floorplan's number
  (standard cells are about 6% of the die, the rest is macros and the space between them). Speed is
  won mostly by re-hardening blocks, and the 73 block instances draw 88% of the power, so the
  floorplan moves those two less. Equal weights (1/3 each) were set earlier the same day and
  replaced. The plan before that was a 50/30/20 split (speed first) corrected by the measured
  spread of each axis over reference variants. It was dropped: the spread came from our own
  variants rather than from entrants, it gave the largest weight to the axis that moves least (so
  routing noise could decide rankings), and it needed several 6 hour runs. `flow/calibrate.py` was
  removed with it.
- The reference flow runs at the fast corner, the default libraries of ASAP7 (Arizona State University 7 nm predictive process); setup is judged at the slow
  corner on per-block slow models, which is why the declared period is found by a separate search.

## Flow landmines (each cost hours; do not rediscover them)

- Global placement over the tile array: a fence region for the array's pipeline registers made the
  placer diverge (`GPL-0307`). The working method is `array_pipe_hold.tcl`: hold the registers as `FIRM`
  with a placement blockage over the array, then `array_pipe_release.tcl`.
- Clock tree synthesis runs at a 3,400 ps period set by `period_hook.tcl` (`PRE_CTS`); at 1,000 or
  2,500 ps the setup repair after CTS (Clock Tree Synthesis) never converges.
- LoopConv needs a strip at least 28 um wide on its LEFT (287 of its pins face left); an 8 um strip
  jammed with hold buffers and detailed placement failed.
- The Tile is 39.046 um wide, which is off the 48 nm track grid when mirrored: tiles are placed R0 only.
- Macros with pins on M5 need local M6/M7 power grids and the memories (M4 pins) M5 to M7
  (`pdn_top_flat_M8M9.tcl`); a direct M2 to M9 stack fails in pdngen (`PDN-0233`).
- The block timing models give their output pins no slew limit, so without `set_max_transition 320`
  in the constraints the long block-to-block nets were never buffered.
- Hold repair before routing works from estimated wires and misses by tens of ps; the ECO (Engineering Change Order) loop on
  extracted parasitics (`eco_hold.tcl`, margins 15 then 25 ps) is what closes it. Global hold margins
  made the repair fail outright.
- The OpenROAD-flow-scripts in-flow equivalence check (`LEC_CHECK`) segfaults on AccumulatorScale after an hour; it is
  off, the judge's gate covers it.
- `drt::check_drc` crashes when several run at once (memory); `drc.py` runs the layouts one at a time.
  It also reports end-of-line and spacing findings the router's own sign-off does not, hence the
  shorts-and-vias gate.
- `write_aiger -map` does not strip quotes from its filename; `setattr -mod -unset keep_hierarchy`
  before flattening a netlist OpenROAD-flow-scripts wrote hierarchically; the platform config overrides `SET_RC_TCL`.

## How the pieces fit

- `run_baseline.sh`: the reference flow. Ten blocks in parallel, then the top, then the hold loop (repair
  on extracted parasitics and re-route until hold is met: two rounds on the reference), slow-corner block
  models, the declared-period search, `baseline/` and `baseline/runtime.json`.
- `evaluate.sh result/` (`flow/eval/evaluate.py`): the judge. Re-derives everything from the layouts and
  netlists in `result/`; nothing the entry reports is used. Steps: read, blocks, top (timing both
  corners, legality, routing, area), power, IR (current times resistance) drop, design rules, equivalence, layout versus netlist,
  score. `--skip blocks,drc,equiv,lvs` skips steps for debugging.
- `judge/run_entry.sh [<repo> <commit> [name]]`: the judge's side of a submission (no arguments: this
  repository at its latest commit, named `mine`). Builds the entry's
  `reproduce/Dockerfile`, runs `reproduce/run.sh` with `design/` mounted read-only at `/design`, the
  repository at `/entry`, output at `/result`, no network, 16 processors, 64 GB, an 18 hour wall-clock stop;
  gates the budget on the dependency chain the entry reports in `result/runtime.json` (wall clock if it
  reports none); then runs the evaluator inside the pinned image named in `versions.lock`, whatever tools
  the machine itself has, writing `eval_work/<name>/evaluation.json`. An entrant runs the same command on
  their own commit to test it. `reproduce/` in this repository is the reference as an entry.
- `flow/render/`: the scripts that rendered the page's layout images; `flow/fpedit/`: the floorplan editor
  the reference floorplan was drawn with (both carry development-machine paths; see their READMEs).
- `setup.sh`: links the container's ORFS (or clones it at the pinned commit elsewhere) and builds eqy
  into `tools/eqy` (skipped with `SKIP_EQY=1`; needed only by the equivalence check against the RTL (Register Transfer Level)).
- `scoring.yaml`: gates, weights, reference values. `versions.lock`: every pin.

## The equivalence gate: design and why

What is proven: for every module the entry submits (each hardened block and the top), the final netlist
is equivalent to the pinned synthesis of that module, which the evaluator runs itself
(`flow/eval/eval_synth.mk`: golden RTL (Register Transfer Level), pinned Yosys settings, the entry's other hardened blocks and
the SRAM (Static Random-Access Memory) macros as black boxes, hierarchy mode 1 for a module that instantiates hardened blocks and 0
for a leaf, as the reference flow did). Synthesis is pinned by rule; everything after it is what an
entrant changes and what the gate checks.

How (`flow/eval/equiv.py`, `cutpoints.py`, `align_cuts.py`, `regcut.py`):
1. Both sides are read as netlists (ASAP7 (Arizona State University 7 nm predictive process) liberty cells; the flip-flops replaced by `seq_models.v`,
   which store Q, since the real cells store the inverted value), flattened.
2. Black boxes are cut: each box's outputs become shared free inputs, its inputs compared outputs.
3. Every register is cut: each netlist flip-flop is paired with the synthesized register of the same
   name (synthesis copies, which carry no name, by their shared next-value net); the pair's stored value
   becomes a shared free input and its next value a compared output. The remainder is combinational,
   so no initial state is assumed and the check holds for every reachable and unreachable state alike.
4. ABC (`iprove`) proves the whole module's miter in one go; the two netlists are structurally close,
   so this takes seconds to a few minutes (the top: about 7 minutes). If ABC (Berkeley's logic synthesis and verification tool) cannot finish, the module
   is checked with 2,000,000 random vectors (`vecsim.py`) and reported as "checked by random vectors",
   never "proven". A difference fails the entry.

Result on the reference: 11 of 11 modules proven, 35,608 of 35,608 top-level flip-flops paired, 35
minutes, 9 GB. Planted bugs fail (see the regression test below).

The check on the RTL (Register Transfer Level) side (`EQUIV_RTL_CHECK=1`): the pinned synthesis against the source itself, which is the
harness's responsibility rather than the entrant's. Its golden side is the source after the coarse part
of the pinned synthesis script itself (everything before technology mapping, with the same hierarchy
and FSM (finite-state machine) steps), so register names line up; what it checks is the fine synthesis,
technology mapping and ABC (Berkeley's logic synthesis and verification tool) optimization, and it trusts
Yosys's coarse passes. It uses eqy's partitioner, simulation-guided register pairing (`regsim.py`) and
per-partition ABC (Berkeley's logic synthesis and verification tool) with a Yosys sat fallback. The pairing compares one cycle at a time,
and also simulates several cycles from an unknown state, which is what matches the bits of a state
machine: one cycle cannot, because a state register's next value depends on its own unknown value. On
the reference top, all 48,477 partitions prove, with all 35,608 flip-flops accounted for (35,605 paired,
3 constant), in 42 minutes. Of the ten blocks (68 minutes for all), nine prove fully; LoopConv proves
4,812 of 4,864 partitions, and the other 52 (address arithmetic in its command pipeline) run out of time
and pass 2,000,000 random vectors each. It is information, not a gate.

Dead ends, so nobody repeats them:
- Yosys `sat -tempinduct` on a whole-module miter from an all-zero state: unsound here; it passed a
  deliberately broken Tile.
- eqy with its default name matching, RTL (Register Transfer Level) against netlist: false failures at internal nets that
  synthesis reuses under other names.
- eqy `bind *`: one giant partition that never proves. eqy `amend *` plus per-partition ABC (Berkeley's logic synthesis and verification tool): works for
  blocks; eqy's partitioner segfaults when both sides are netlists.
- From-reset random simulation as a fallback: missed a planted AND-to-OR change in StoreController
  (the broken logic sits behind a state random inputs rarely reach). Kept as information only.
- Imitating the hierarchical synthesis of OpenROAD-flow-scripts by hand (keep_hierarchy by size, FSM (finite-state machine) re-encoding) on the RTL (Register Transfer Level) side
  to make names match: no gain. Running the pinned script's own coarse step does it (see above).
- eqy's partitioner crashes (a segmentation fault in its partition merge) when matched names belong to
  the `$scopeinfo` cells that Yosys's flatten leaves behind; they carry no logic and are deleted right
  after flattening, on both sides.

## Other gates, briefly

- Design rules: `drt::check_drc` on every layout; shorts and via (cut, enclosure, off-grid) violations
  fail; end-of-line, spacing and minimum-width findings are reported only, because the standalone
  checker reports them on every reference block where the router's own sign-off found none. The
  KLayout deck is not a gate (hundreds of findings per block, many inside standard cells).
- Layout versus netlist: pin-level connectivity, single-pin nets ignored. No open transistor-level deck.
- IR (current times resistance) drop: the evaluator's own static analysis with the pinned activity, limit 110 mV (reference
  84.4 mV). The layer resistances are loaded by path from `flow/gemmini/setRC.tcl` because the
  platform config overrides `SET_RC_TCL` after the evaluator's settings load, and the platform file has
  no M8/M9 values; the same reason the flow exports `LAYER_PARASITICS_FILE`.
- Timing: setup at the slow, worst-case corner (0.63 V, 100 C) at the declared period on per-block slow models;
  hold at the fast corner; power at the typical corner with a fixed 1,000 ps clock. The reference passes
  hold at 0.0 ps in the evaluator, identical in three runs; thin, but it reproduces.

## Problems found only on a clean machine (keep testing that way)

- The container image first pinned had been built locally and never published; a fresh machine could
  not pull it. Now `openroad/orfs@sha256:6bc088ee...` (the OpenROAD-flow-scripts project's image of the pinned commit).
- M8/M9 resistances: the flow and the evaluator each read the platform's `setRC.tcl` on a clean machine
  (the development host had M8/M9 added by hand), so the top routed with zero resistance on those
  layers and the IR (current times resistance) analysis failed. Fixed in `flow/gemmini/common.mk` and `flow/eval/common.tcl`.
- The budget gate was on wall-clock time; under the judge's cap of 16 processors on a shared machine the
  reference finished 8 minutes inside 6 hours. The gate now reads the dependency chain.

## Open items, with recommendations

1. Non-reference partition test. Every evaluator test so far used the reference partition. Build a
   variant and evaluate it: the reference with LoopConv left flat is the lowest-risk choice (reuses the
   proven floorplan; changes the synthesis black-box set and the hierarchy). `flow/gemmini/config_2blk.mk`
   is a two-block variant from earlier work that was never shown to converge.
2. Hold margin: the reference passes hold at 0.0 ps. Raising the repair margins (eco_hold.tcl, the
   15 and 25 ps in run_baseline.sh) would give slack but changes the pinned power and needs a rerun.
3. Entries are sent in by an issue on this repository (the challenge page and `submission/README.md`
   agree), which needs the repository to be public.

## The site

The Chipbase site (the challenge page, the games, the algorithm and education content, the browser
grader, the static freeze) has its own repository, https://github.com/Samcooper01/chipbase, and is
published from it with GitHub Pages at https://samcooper01.github.io/chipbase/ (live since
2026-10-25). It lived in this repository as `site/` from 2026-10-15 until then, and that history stays
in this repository's log. The challenge page's content is in `app/challenge_content.py` and
`app/templates/challenge.html` there. Its judging section, rules and reference numbers must stay in
step with `README.md` and `scoring.yaml` here, so a change to the gates, the weights or the reference
results is a change in both repositories. The site's own README says how to run it, add to it and
publish it.

The directory `PD-Leet/` on the development machine is a stale copy of the site; work in the chipbase
repository.

## What is not in the repository

- Regenerating the RTL (Register Transfer Level) or the switching-activity file needs Chipyard 1.11.0 with the pinned Gemmini
  commit (`design/generator/README.md` says how the RTL (Register Transfer Level) was made; `design/activity/` has the workload
  program and the converter from FST (Fast Signal Trace) waveforms to activity). The Verilator simulation that produced the activity ran
  on the development machine (`/home/sam/chipyard`, Chipyard 1.11.0 at ac58f38d, Gemmini 8c8b38b,
  firtool 1.61.0) with two local fixes: `RISCV=/home/sam/chipyard/.conda-env/riscv-tools` for the fesvr
  version mismatch, and Verilator 5.020's empty `VerilatedTraceSigType::` in the FST (Fast Signal Trace) waveform writer patched to
  `LOGIC` (plus deleting a stale generated `.debug` makefile). The activity window is found from Gemmini's
  own 2,000 ps clock and the final command burst; the full check on the host processor timed out, so the program checks 4
  sampled rows. Both files are pinned in the repository, so this matters
  only if the workload or the design changes.
- The reference run's own artifacts (layouts, logs, the evaluator's work directories, the judge test's
  result) stay on the development machine; `run_baseline.sh` regenerates them with the same numbers.
- The earlier partitions that were tried and abandoned (three-level hierarchy, two-block variant) and
  their results stay there too; `flow/gemmini/config_2blk.mk` and the block configs are in the
  repository, their runs are not.
- The full-size renders behind the page images (`chipbase-ref/img/`, 260 MB) are not; the page's
  WebP files are, and `flow/render/` has the scripts that made them.

## Regression test for the equivalence gate

`flow/eval/tests/planted_bugs.sh baseline/` makes two deliberately broken netlists from the reference
(Tile: the D inputs of two flip-flops swapped; StoreController: one AND2 cell changed to OR2), runs the
gate on them and on the originals, and reports whether the broken ones fail and the originals pass.
Run it after any change to `flow/eval/`.

## Setting up a new machine

Nothing in the repository installs itself; the host needs these before the resume commands work.

- Linux on x86-64, 16 or more threads, 64 GB of memory (the top's routing peaks at 27 GB, the
  evaluator at 30 GB, and the judge caps an entry at 64 GB), about 120 GB of free disk, counting Docker's
  storage: the image (6.5 GB), a reference run (about 40 GB with its work directory), a self-test with
  `judge/run_entry.sh` (about 45 GB in Docker's storage while it runs, 2.4 GB after) and each
  evaluation (about 16 GB).
- Docker, with the user in the `docker` group (or run through `sudo`). Everything that touches the
  flow runs inside the pinned image; the first `docker run` pulls it. The judge runner also needs
  `docker build`, `timeout` and `python3` on the host.
- git, and an SSH (Secure Shell) key registered with GitHub for pushing to `Samcooper01/systolic-array-ai-accelerator-harness`
  (clone over HTTPS (Hypertext Transfer Protocol Secure) works without one). The GitHub command-line tool is optional.
- Python 3.10 or newer on the host for the judge runner's bookkeeping.
- Nothing from the development host's own OpenROAD-flow-scripts build is needed: the harness was validated in the
  pinned image. If you want to run `evaluate.sh` or the regression test outside Docker, `setup.sh`
  clones OpenROAD-flow-scripts at the pinned commit and you build its tools yourself (hours); running inside the
  image instead is simpler: `docker run --rm -it -v "$PWD":/work -w /work <image> bash`, then the
  README's commands.
- Development inside the container keeps `tools/`, `work/`, `baseline/`, `eval_work/` and
  `judge_work/` in the mounted checkout; they are ignored by git. Files the container writes are owned
  by root on the host; remove them with a throwaway `docker run ... rm -rf` if a plain `rm` is refused.
- Regenerating the pinned RTL (Register Transfer Level) or activity needs Chipyard as well (see "What is not in the repository").

## Resuming on another machine

    git clone https://github.com/Samcooper01/systolic-array-ai-accelerator-harness && cd systolic-array-ai-accelerator-harness
    judge/validate_reference.sh              # fresh clone + pinned container: flow, evaluator, score (about 6 h)
    # or step by step, as the README says: docker run ... ; ./setup.sh ; ./run_baseline.sh ; ./evaluate.sh baseline/

Expected: every gate passes and the score is 1.000 with the reference numbers above.
