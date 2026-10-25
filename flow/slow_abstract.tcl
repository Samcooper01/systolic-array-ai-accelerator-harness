# Slow-corner timing model of a hardened block, for the slow-corner (setup) period search. Run through
# "make ... CORNER=WC open_6_final.odb" on the block, with SLOW_LIB set to the output path. The flow's
# own abstract (<block>_typ.lib) is written at the platform default corner, BC (fast).
read_spef $::env(RESULTS_DIR)/6_final.spef
set_propagated_clock [all_clocks]
set_clock_latency -source 0 [all_clocks]
write_timing_model $::env(SLOW_LIB)
puts "slow_abstract: wrote $::env(SLOW_LIB)"
exit
