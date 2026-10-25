# PRE_CTS hook: re-apply the reference constraints at clock period CTS_PERIOD (default 2,500 ps) before clock tree synthesis, so
# the timing repair works toward a period the hardened blocks allow (AccumulatorScale alone needs
# 2,414 ps of setup on its scale input; at 1,000 ps every repair is wasted on paths that cannot close).
# Placement is not timing-driven, so it is unaffected. write_sdc after CTS carries the period forward.
set clk_name clock
set clk_port_name clock
set clk_period [expr {[info exists ::env(CTS_PERIOD)] ? $::env(CTS_PERIOD) : 2500}]
set in2reg_max  [expr { $clk_period * 0.8 }]
set reg2out_max [expr { $clk_period * 0.8 }]
set in2out_max  [expr { $clk_period * 0.6 }]
source $::env(PLATFORM_DIR)/constraints.sdc
set_max_transition 320 [current_design]
puts "period hook: clock period now [get_property [get_clocks clock] period] ps"
