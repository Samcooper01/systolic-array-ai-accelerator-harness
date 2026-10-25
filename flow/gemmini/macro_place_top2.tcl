# Two-block top: Scratchpad on the left, ExecuteController on the right with the 3,504-pin interface
# edges facing across a 40 um channel, the array centered vertically on the memory block. Everything
# else (the seven controllers, command queues, arbiters) is flat standard-cell logic placed by the
# global placer in the band above the blocks and around them. The channel between the two blocks
# carries only the 3,504-bit interface: it is 60 um wide and blocked for standard cells, because
# a first run with a 40 um open channel failed global route there (flat logic plus wire jogs).
proc size_of {inst_name} {
  set inst [[ord::get_db_block] findInst $inst_name]
  if { $inst eq "NULL" } { error "macro_place_top2: instance $inst_name not found" }
  set m [$inst getMaster]
  return [list [ord::dbu_to_microns [$m getWidth]] [ord::dbu_to_microns [$m getHeight]]]
}
set margin 20.0
set gap 60.0
lassign [size_of spad] sw sh
lassign [size_of ex_controller] ew eh
place_macro -macro_name spad -location [list $margin $margin] -orientation R0
place_macro -macro_name ex_controller -location [list [expr {$margin + $sw + $gap}] [expr {$margin + ($sh - $eh) / 2.0}]] -orientation R0

