# ExecuteController pin sides: the scratchpad / accumulator interface on the left edge, next to
# the array's A input (the Scratchpad block sits to the left of the array at the top level);
# command, im2col and completion on the top edge, toward the controllers.
proc pins {pat} { set r {}; foreach p [get_ports $pat] { lappend r [get_full_name $p] }; return $r }
set left [concat [pins io_srams_read*] [pins io_srams_write*] [pins io_acc_read*] [pins io_acc_write*]]
set top   [concat [pins io_cmd*] [pins io_im2col*] [pins io_completed*] [pins io_busy]]
set_io_pin_constraint -region left:*  -pin_names $left
set_io_pin_constraint -region top:*   -pin_names $top
