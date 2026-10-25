# Source this in the OpenROAD GUI Tcl console to color the flat logic by hierarchy group,
# so the connections between macros (which always pass through this logic) become visible.
#   source /home/sam/Geetus2.0/chipbase-ref/render/highlight_groups.tcl
gui::clear_highlights -1
select -type Inst -name "ex_controller/mesh/*"   -highlight 0   ;# MeshWithDelays: pipeline registers and delays around the array
select -type Inst -name "spad/spad_mems*"        -highlight 1   ;# scratchpad bank glue
select -type Inst -name "spad/acc_mems*"         -highlight 2   ;# accumulator bank glue
select -type Inst -name "spad/acc_adders*"       -highlight 2
select -type Inst -name "spad/norm_unit*"        -highlight 3   ;# feeds AccumulatorScale
select -type Inst -name "ex_controller/*"        -highlight 4   ;# execute controller (everything else under it)
select -type Inst -name "mod_1/*"                -highlight 5   ;# LoopMatmul
select -type Inst -name "reservation_station/*"  -highlight 6
select -type Inst -name "spad/vsm/*"             -highlight 7   ;# scratchpad read/write pipeline
gui::clear_selections
puts "highlight 0 MeshWithDelays  1 spad glue  2 acc glue+adders  3 norm_unit  4 ex_controller  5 LoopMatmul  6 reservation_station  7 spad/vsm"
