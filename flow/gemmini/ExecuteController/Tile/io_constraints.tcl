# Pin sides for the Tile block, so that tiles abut cleanly when the top places them as a grid.
# A flows left to right; B, D (accumulator input), and the control, id, last, and valid
# signals flow top to bottom, C leaves at the bottom. Each output is mirrored with the input
# it feeds on the next tile: same coordinate on the opposite edge, so a column of tiles has
# every bus running straight down and a row has A running straight across.
set top_in    [list]
set bottom_out [list]
foreach k {0 1} {
  for {set i 0} {$i < 20} {incr i} { lappend top_in "io_in_b_${k}\[$i\]" "io_in_d_${k}\[$i\]"; lappend bottom_out "io_out_b_${k}\[$i\]" "io_out_c_${k}\[$i\]" }
  for {set i 0} {$i < 5} {incr i}  { lappend top_in "io_in_control_${k}_shift\[$i\]"; lappend bottom_out "io_out_control_${k}_shift\[$i\]" }
  for {set i 0} {$i < 3} {incr i}  { lappend top_in "io_in_id_${k}\[$i\]"; lappend bottom_out "io_out_id_${k}\[$i\]" }
  lappend top_in io_in_control_${k}_dataflow io_in_control_${k}_propagate io_in_last_${k} io_in_valid_${k}
  lappend bottom_out io_out_control_${k}_dataflow io_out_control_${k}_propagate io_out_last_${k} io_out_valid_${k}
}
set left_in [list]; set right_out [list]
foreach k {0 1} { for {set i 0} {$i < 8} {incr i} { lappend left_in "io_in_a_${k}\[$i\]"; lappend right_out "io_out_a_${k}\[$i\]" } }

set_io_pin_constraint -region top:*    -pin_names $top_in
set_io_pin_constraint -region bottom:* -pin_names $bottom_out
set_io_pin_constraint -region left:*   -pin_names $left_in
set_io_pin_constraint -region right:*  -pin_names $right_out
foreach a $top_in  b $bottom_out { set_io_pin_constraint -mirrored_pins [list $a $b] }
foreach a $left_in b $right_out  { set_io_pin_constraint -mirrored_pins [list $a $b] }
# clock and the bad_dataflow flag are free
