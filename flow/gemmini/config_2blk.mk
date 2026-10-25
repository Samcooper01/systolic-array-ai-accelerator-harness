# Top level, two-block variant: only ExecuteController and Scratchpad are hardened; the seven
# controllers (about 120k cells) run flat at the top. Separate nickname so results sit beside the
# nine-block reference. Block configs are found next to this file (ExecuteController/, Scratchpad/).
include $(dir $(lastword $(MAKEFILE_LIST)))common.mk
export DESIGN_NAME = Gemmini
export DESIGN_NICKNAME = gemmini2
export SYNTH_HIERARCHICAL = 1
export BLOCKS ?= ExecuteController Scratchpad
export DIE_AREA = 0 0 1372 940
export CORE_AREA = 2 2 1370 938
export MACRO_PLACE_HALO = 6 6
export MACRO_PLACEMENT_TCL = $(CB)/flow/gemmini/macro_place_top2.tcl
export MAX_ROUTING_LAYER = M9
export PDN_TCL = $(CB)/flow/gemmini/pdn_top_M8M9.tcl
# 120k flat cells: normal placer settings (unlike the nine-block top, which is 0.25 percent utilization)
export PLACE_DENSITY = 0.60
# cells that global placement leaves in the (row-less) channel need a legalization search wider
# than the 27 um default; 200 x 40 um is enough and keeps legalization fast (a 1500 um window ran for hours)
export DETAIL_PLACEMENT_ARGS = -max_displacement {200 40}
# keep standard cells out of the 60 um channel (see channel_blockage.tcl)
export POST_TAPCELL_TCL = $(CB)/flow/gemmini/channel_blockage.tcl
