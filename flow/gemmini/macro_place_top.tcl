# Top-level floorplan for the nine hardened blocks. Sizes are read from the loaded abstracts, so
# this script does not need editing when a block changes size; the die (DIE_AREA in config.mk)
# is set to match: width = Scratchpad + 40 + ExecuteController + 40, height = Scratchpad + 40 +
# LoopConv + 40.
#
#   Scratchpad on the left, ExecuteController on the right, their 3,504-pin interface edges facing
#   each other across a 40 um channel, the array centered vertically on the memory block.
#   A band above holds the controllers: above the Scratchpad the DMA-side blocks (LoadController,
#   StoreController, FrontendTLB, CounterController), above the array the command-side blocks
#   (ReservationStation, LoopMatmul, LoopConv). Entrants may replace all of this.
set block [ord::get_db_block]
proc size_of {inst_name} {
  set inst [[ord::get_db_block] findInst $inst_name]
  if { $inst eq "NULL" } { error "macro_place_top: instance $inst_name not found" }
  set m [$inst getMaster]
  return [list [ord::dbu_to_microns [$m getWidth]] [ord::dbu_to_microns [$m getHeight]]]
}
proc put {inst x y} { place_macro -macro_name $inst -location [list $x $y] -orientation R0 }
set margin 20.0
set gap 40.0
lassign [size_of spad] sw sh
lassign [size_of ex_controller] ew eh
lassign [size_of mod] lw lh

# memory block and array
put spad $margin $margin
set ex_x [expr {$margin + $sw + $gap}]
set ex_y [expr {$margin + ($sh - $eh) / 2.0}]
put ex_controller $ex_x $ex_y

# controller band, placed by partner: the Scratchpad's DMA, TLB and counter pins sit in the
# middle-left of its top edge (about x 250 to 400 on the die), the array's command pins at about
# x 1005 to 1080. TLB, Load and Store go over the DMA pins, CounterController and the
# ReservationStation (which talks to Load, Store, Counter and the array) over the gap between the
# two big blocks, LoopMatmul and LoopConv toward the array's command pins.
set band_y [expr {$margin + $sh + $gap}]
set x [expr {$margin + 260.0}]
foreach inst {tlb load_controller store_controller counters reservation_station mod_1 mod} {
  lassign [size_of $inst] w h
  put $inst $x $band_y
  set x [expr {$x + $w + 12.0}]
}
puts "macro_place_top: die should be [expr {$margin + $sw + $gap + $ew + $margin}] x [expr {$band_y + $lh + $margin}] um"
