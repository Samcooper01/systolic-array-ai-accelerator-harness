# PRE_GLOBAL_PLACE_SKIP_IO hook: keep the tile array's channels for the array's own pipeline registers
# during global placement. The pipeline registers (standard cells under ex_controller/mesh/mesh/) are
# put at the positions they reached in the unconstrained gemmini5 placement, where they already sit
# between the tiles next to the pins they serve, and marked FIRM so the global placer treats them as
# fixed; a hard placement blockage over the array outline then keeps every other cell out. (A fence
# region did the same job but runs a second Nesterov placer whose early convergence trips the
# divergence check, GPL-0307.) array_pipe_release.tcl undoes both after global placement.
set block [ord::get_db_block]
# positions file: ARRAY_PIPE_POS if set (a floorplan whose array moved needs its own), else the default
set pos_file [expr {[info exists ::env(ARRAY_PIPE_POS)] ? $::env(ARRAY_PIPE_POS) : [file join [file dirname [info script]] array_pipeline_pos.tsv]}]
set f [open $pos_file]
set n 0; set miss 0
while {[gets $f line] >= 0} {
  lassign [split $line "\t"] name x y orient
  set inst [$block findInst $name]
  if {$inst == "NULL"} { incr miss; continue }
  $inst setOrient $orient
  $inst setLocation $x $y
  $inst setPlacementStatus FIRM
  incr n
}
close $f
set xs {}; set ys {}; set xe {}; set ye {}
foreach inst [$block getInsts] {
  if {![regexp {^ex_controller/mesh/mesh/mesh_\d+_\d+$} [$inst getName]]} continue
  set bb [$inst getBBox]
  lappend xs [$bb xMin]; lappend ys [$bb yMin]; lappend xe [$bb xMax]; lappend ye [$bb yMax]
}
set bl [odb::dbBlockage_create $block [tcl::mathfunc::min {*}$xs] [tcl::mathfunc::min {*}$ys] \
          [tcl::mathfunc::max {*}$xe] [tcl::mathfunc::max {*}$ye]]
puts "array_pipe_hold: $n pipeline cells held (FIRM), $miss not found; blockage over the array outline"
