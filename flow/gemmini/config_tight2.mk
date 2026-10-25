# Reference top level: ExecuteController and Scratchpad opened up, so their contents (the 64 Tiles,
# the transposer, AccumulatorScale, the 8 SRAMs and the flat logic) sit at the top beside the seven
# controller blocks. Floorplan drawn by hand in a floorplan editor and exported as
# macro_place_tight2.tcl; die 821 x 765 um. Blocks are hardened from their own configs (Tile,
# AlwaysOutTransposer and AccumulatorScale are links into ExecuteController/ and Scratchpad/).
#   power grid   pdn_top_flat_M8M9.tcl: M8/M9 mesh plus local grids that reach the sub-macros' M4/M5 pins
#   placement    array_pipe_hold.tcl / array_pipe_release.tcl keep the tile channels for the array's
#                own pipeline registers during global placement
#   clock pin    io_top_clock_tight2.tcl, at the bottom edge next to the register centroid
#   constraints  constraint_drv.sdc adds a design-wide slew limit; CTS targets 3,400 ps (period_hook.tcl)
include $(dir $(lastword $(MAKEFILE_LIST)))common.mk
export DESIGN_NAME = Gemmini
export DESIGN_NICKNAME = gemmini_flat
export SYNTH_HIERARCHICAL = 1
export BLOCKS ?= Tile AlwaysOutTransposer AccumulatorScale LoopConv LoopMatmul ReservationStation LoadController StoreController FrontendTLB CounterController
export DIE_AREA = 0 0 821 765
export CORE_AREA = 2 2 819 763
export MACRO_PLACE_HALO = 6 6
export MACRO_PLACEMENT_TCL = $(CB)/flow/gemmini/macro_place_tight2.tcl
export MAX_ROUTING_LAYER = M9
export PDN_TCL = $(CB)/flow/gemmini/pdn_top_flat_M8M9.tcl
# placement density matches the editor's 60 percent logic footprint; the routability- and
# timing-driven loops stay off (they oscillated for hours on the nine-block top)
export PLACE_DENSITY = 0.60
export GPL_ROUTABILITY_DRIVEN = 0
export GPL_TIMING_DRIVEN = 0
# design-wide slew limit so long block-to-block nets get buffered (see constraint_drv.sdc)
export SDC_FILE = $(CB)/flow/gemmini/constraint_drv.sdc
# hold the pipeline registers in the array channels and block the array for everything else during
# global placement; release both afterwards
export PRE_GLOBAL_PLACE_SKIP_IO_TCL = $(CB)/flow/gemmini/array_pipe_hold.tcl
export POST_GLOBAL_PLACE_TCL = $(CB)/flow/gemmini/array_pipe_release.tcl
# sourced right before place_pins (the constraint lives in the pin placer, not in the database)
export PRE_IO_PLACEMENT_TCL = $(CB)/flow/gemmini/io_top_clock_tight2.tcl
export ARRAY_PIPE_POS = $(CB)/flow/gemmini/array_pipeline_pos_tight2.tsv
# clock tree synthesis at a 3,400 ps target so its repair works on hold, not on setup paths the
# blocks cannot meet; the declared period is searched on the finished run
export CTS_PERIOD = 3400
export PRE_CTS_TCL = $(CB)/flow/gemmini/period_hook.tcl
