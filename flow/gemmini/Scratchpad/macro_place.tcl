# Macro placement inside the Scratchpad block. The array interface (1,400 pins) is on the right
# edge and the DMA / TileLink interface on the top edge, so the memories are pushed to the left
# and the whole right and center is left open for the 200k cells of glue, queues, and the vector
# scale multiplier. SRAM pins are on the macro's left edge in R0, so the banks are mirrored (MY) to face the logic on the right.
# Die is set by CORE_UTILIZATION = 30 (about 727 um square); coordinates assume at least 720.
set core [ord::get_core_area]
lassign $core lx ly ux uy
set bank_w 265.43; set bank_h 84.0
set half_w 132.81; set half_h 42.0
set x_bank [expr {$lx + 10.0}]
# four scratchpad banks stacked on the left edge, from the bottom
set y 20.0
foreach b {0 1 2 3} {
  place_macro -macro_name "spad_mems_${b}.mem.mem_ext/phys" -location [list $x_bank $y] -orientation MY
  set y [expr {$y + $bank_h + 10.0}]
}
# accumulator half-banks in two columns above the scratchpad stack
set y_acc [expr {$y + 20.0}]
set x_acc1 $x_bank; set x_acc2 [expr {$x_bank + $half_w + 8.0}]
place_macro -macro_name {acc_mems_0/mem.mem.mem_0_ext/bank_0} -location [list $x_acc1 $y_acc] -orientation R0
place_macro -macro_name {acc_mems_0/mem.mem.mem_0_ext/bank_1} -location [list $x_acc2 $y_acc] -orientation R0
place_macro -macro_name {acc_mems_1/mem.mem.mem_0_ext/bank_0} -location [list $x_acc1 [expr {$y_acc + $half_h + 8.0}]] -orientation R0
place_macro -macro_name {acc_mems_1/mem.mem.mem_0_ext/bank_1} -location [list $x_acc2 [expr {$y_acc + $half_h + 8.0}]] -orientation R0
# AccumulatorScale in the top-left corner, above the accumulator banks
place_macro -macro_name {acc_scale_unit} -location [list [expr {$lx + 10.0}] [expr {$uy - 10.0 - 166.421}]] -orientation R0
