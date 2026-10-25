# Block: ExecuteController, the whole array (64 Tiles + Transposer + MeshWithDelays + execute
# control), hardened once and handed to the top as one macro. Its own sub-blocks are nested here.
include $(dir $(lastword $(MAKEFILE_LIST)))../common.mk
export DESIGN_NAME = ExecuteController
export DESIGN_NICKNAME = gemmini_ExecuteController
export SYNTH_HIERARCHICAL = 1
export BLOCKS ?= Tile AlwaysOutTransposer
export DIE_AREA = 0 0 540 540
export CORE_AREA = 2 2 538 538
export MACRO_PLACE_HALO = 6 6
export MACRO_PLACEMENT_TCL = $(CB)/flow/gemmini/ExecuteController/macro_place.tcl
export IO_CONSTRAINTS = $(CB)/flow/gemmini/ExecuteController/io_constraints.tcl
export MAX_ROUTING_LAYER = M7
export PDN_TCL = $(CB)/flow/gemmini/pdn_block_M5M6M7.tcl
# the array / scratchpad interface is 3,504 pins on one edge: 3 tracks apart fits (6 does not)
export PLACE_PINS_ARGS = -annealing -min_distance 3 -min_distance_in_tracks
