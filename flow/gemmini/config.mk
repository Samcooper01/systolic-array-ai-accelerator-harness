# Top level: Gemmini, with nine blocks hardened first (the reference partition).
include $(dir $(lastword $(MAKEFILE_LIST)))common.mk
export DESIGN_NAME = Gemmini
export DESIGN_NICKNAME = gemmini
export SYNTH_HIERARCHICAL = 1
export BLOCKS ?= ExecuteController Scratchpad LoopMatmul ReservationStation LoadController StoreController LoopConv FrontendTLB CounterController
export DIE_AREA = 0 0 1352 1006
export CORE_AREA = 2 2 1350 1004
export MACRO_PLACE_HALO = 6 6
export MACRO_PLACEMENT_TCL = $(CB)/flow/gemmini/macro_place_top.tcl
export MAX_ROUTING_LAYER = M9
export PDN_TCL = $(CB)/flow/gemmini/pdn_top_M8M9.tcl
# the top is 0.25 percent utilization: a few thousand glue cells and the pin buffers of the 3,504-bit
# block interface. Let them cluster (density 0.9) and skip the routability and timing loops of the
# global placer, which oscillate for hours at this utilization; repair_design and CTS still run.
export PLACE_DENSITY = 0.90
export GPL_ROUTABILITY_DRIVEN = 0
export GPL_TIMING_DRIVEN = 0
