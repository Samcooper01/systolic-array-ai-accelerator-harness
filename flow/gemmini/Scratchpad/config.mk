# Block: Scratchpad, the whole memory subsystem (8 SRAM macros, AccumulatorScale, the vector
# scale multiplier, DMA reader and writer, accumulator adders), hardened once as one macro.
include $(dir $(lastword $(MAKEFILE_LIST)))../common.mk
export DESIGN_NAME = Scratchpad
export DESIGN_NICKNAME = gemmini_Scratchpad
export SYNTH_HIERARCHICAL = 1
export BLOCKS ?= AccumulatorScale
export CORE_UTILIZATION = 30
export MACRO_PLACEMENT_TCL = $(CB)/flow/gemmini/Scratchpad/macro_place.tcl
export MACRO_PLACE_HALO = 6 6
export IO_CONSTRAINTS = $(CB)/flow/gemmini/Scratchpad/io_constraints.tcl
export MAX_ROUTING_LAYER = M7
export PDN_TCL = $(CB)/flow/gemmini/pdn_block_M5M6M7.tcl
# the array / scratchpad interface is 3,504 pins on one edge: 3 tracks apart fits (6 does not)
export PLACE_PINS_ARGS = -annealing -min_distance 3 -min_distance_in_tracks
# OpenROAD segfaults in repair_timing after global route on this block (float multiply pipelines); the CTS-stage repair already ran
export SKIP_INCREMENTAL_REPAIR = 1
