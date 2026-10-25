# Block: Tile (hardened once, abstract handed to the top).
include $(dir $(lastword $(MAKEFILE_LIST)))../../common.mk
export DESIGN_NAME = Tile
export DESIGN_NICKNAME = gemmini_ExecuteController_Tile
export CORE_UTILIZATION = 50
export MAX_ROUTING_LAYER = M5
export PDN_TCL = $(PLATFORM_DIR)/openRoad/pdn/BLOCK_grid_strategy.tcl
export IO_CONSTRAINTS = $(CB)/flow/gemmini/ExecuteController/Tile/io_constraints.tcl
