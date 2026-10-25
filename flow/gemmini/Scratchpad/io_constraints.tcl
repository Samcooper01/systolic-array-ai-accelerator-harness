# Scratchpad pin sides: the ExecuteController interface on the right edge (the array sits to the
# right at the top level); DMA and TileLink toward the load/store controllers and the memory port
# on the top edge. TLB, counter and busy pins are left free.
proc pins {pat} { set r {}; foreach p [get_ports $pat] { lappend r [get_full_name $p] }; return $r }
set right [concat [pins io_srams_read*] [pins io_srams_write*] [pins io_acc_read*] [pins io_acc_write*]]
set top  [concat [pins io_dma_read*] [pins io_dma_write*] [pins auto_id_out*]]
set_io_pin_constraint -region right:* -pin_names $right
set_io_pin_constraint -region top:*  -pin_names $top
