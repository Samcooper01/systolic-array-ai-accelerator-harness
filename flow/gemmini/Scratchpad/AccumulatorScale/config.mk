# Block: AccumulatorScale (hardened once, abstract handed to the top).
include $(dir $(lastword $(MAKEFILE_LIST)))../../common.mk
export DESIGN_NAME = AccumulatorScale
export DESIGN_NICKNAME = gemmini_Scratchpad_AccumulatorScale
export CORE_UTILIZATION = 50
export MAX_ROUTING_LAYER = M5
export PDN_TCL = $(PLATFORM_DIR)/openRoad/pdn/BLOCK_grid_strategy.tcl
# OpenROAD segfaults in repair_timing after global route on this block (float multiply pipelines); the CTS-stage repair already ran
export SKIP_INCREMENTAL_REPAIR = 1
