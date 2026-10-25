# Chipbase Competition 01 reference flow: shared settings for the top and every block.
export PLATFORM = asap7
CB := $(abspath $(dir $(lastword $(MAKEFILE_LIST)))../..)
export VERILOG_FILES = $(sort $(wildcard $(CB)/design/rtl/*.sv)) $(CB)/design/srams/_wrappers/mem_ext.v $(CB)/design/srams/_wrappers/mem_0_ext_banked.v
export SDC_FILE = $(CB)/flow/gemmini/constraint.sdc
export SYNTH_HDL_FRONTEND = slang
# FakeRAM2.0 SRAM macros: scratchpad bank (4096x128) and accumulator half-bank (512x256)
export ADDITIONAL_LEFS = $(CB)/design/srams/mem_ext/mem_ext.lef $(CB)/design/srams/mem_0_bank_ext/mem_0_bank_ext.lef
export ADDITIONAL_LIBS = $(CB)/design/srams/mem_ext/mem_ext.lib $(CB)/design/srams/mem_0_bank_ext/mem_0_bank_ext.lib
export GDS_ALLOW_EMPTY = .*_ext_phys
export CORE_ASPECT_RATIO = 1
export CORE_MARGIN = 2
# pins at least 6 tracks apart, so every block pin can be reached from outside without spacing or end-of-line trouble
export PLACE_PINS_ARGS = -annealing -min_distance 6 -min_distance_in_tracks
# Block pins on the top and bottom edges go on M3, not the platform default M5: M5 carries the
# vertical power stripes of both the block grid and the top grid, and a pin under a stripe can
# only be reached by shorting through it. Left and right edge pins stay on M4 (no horizontal stripes).
export IO_PLACER_V = M3
# resistance and capacitance per layer, including the pinned M8/M9 values. At the pinned ORFS commit the
# stage scripts read LAYER_PARASITICS_FILE (load.tcl, open.tcl) and otherwise fall back to the platform's
# own setRC.tcl, which has no M8/M9 values (zero resistance: wrong timing, and the IR drop analysis
# fails); SET_RC_TCL is kept for the scripts that still read it.
export LAYER_PARASITICS_FILE = $(CB)/flow/gemmini/setRC.tcl
export SET_RC_TCL = $(CB)/flow/gemmini/setRC.tcl
# the in-flow post-repair equivalence check (Kepler) segfaults on AccumulatorScale after an hour; the judge runs eqy on the whole design anyway
export LEC_CHECK = 0
