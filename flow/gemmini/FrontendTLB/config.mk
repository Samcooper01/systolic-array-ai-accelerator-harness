# Block: FrontendTLB (hardened once, abstract handed to the top).
include $(dir $(lastword $(MAKEFILE_LIST)))../common.mk
export DESIGN_NAME = FrontendTLB
export DESIGN_NICKNAME = gemmini_FrontendTLB
# pin-bound: 801 pins need about 230 um of perimeter at 6-track spacing
export CORE_UTILIZATION = 20
export MAX_ROUTING_LAYER = M7
export PDN_TCL = $(CB)/flow/gemmini/pdn_block_M5M6M7.tcl
