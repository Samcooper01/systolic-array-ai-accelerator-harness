# Block: StoreController (hardened once, abstract handed to the top).
include $(dir $(lastword $(MAKEFILE_LIST)))../common.mk
export DESIGN_NAME = StoreController
export DESIGN_NICKNAME = gemmini_StoreController
export CORE_UTILIZATION = 50
export MAX_ROUTING_LAYER = M7
export PDN_TCL = $(CB)/flow/gemmini/pdn_block_M5M6M7.tcl
