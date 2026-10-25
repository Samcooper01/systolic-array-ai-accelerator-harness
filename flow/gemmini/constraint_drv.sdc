# The reference constraints (constraint.sdc, inlined) plus a design-wide maximum slew. The hardened blocks' timing
# libraries give their output pins no slew or capacitance limit, so without this the resizer never
# buffers a net that runs from one block's output to another block's input, however long it is
# (on the opened top, ReservationStation -> LoopConv had an 8.8 ns slew and 2.8 ns of wire delay).
# 320 ps is the ASAP7 standard cells' own max_transition.
set clk_name clock
set clk_port_name clock
set clk_period 1000
set in2reg_max  [expr { $clk_period * 0.8 }]
set reg2out_max [expr { $clk_period * 0.8 }]
set in2out_max  [expr { $clk_period * 0.6 }]
source $::env(PLATFORM_DIR)/constraints.sdc
set_max_transition 320 [current_design]
