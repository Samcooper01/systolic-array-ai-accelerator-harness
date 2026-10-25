# Hold ECO from a routed run: repair hold with the run's extracted parasitics (6_final.spef), legalize
# the new buffers, strip the signal routing, and write the result as a post-CTS database to re-route
# from. Run through "make ... FLOW_VARIANT=<routed variant> open_5_route.odb" with ECO_OUT set
# (ECO_MARGIN, ps, defaults to 15). run_baseline.sh loops this until hold is met.
# Reason: the post-GRT hold repair works from global-route estimates, which missed the routed hold
# slack by up to 33 ps on the paths into AccumulatorScale and ReservationStation; a global margin big
# enough to cover that pulls in thousands of endpoints (hours of repair), this fixes only the few.
read_spef $::env(RESULTS_DIR)/6_final.spef
set_propagated_clock [all_clocks]
puts "eco_hold: before, worst hold [format %.1f [sta::worst_slack -min]] ps"
repair_timing -hold -hold_margin [expr {[info exists ::env(ECO_MARGIN)] ? $::env(ECO_MARGIN) : 15}] -verbose
remove_fillers   ;# the routed database is already filled; the finish stage refills
detailed_placement
check_placement -verbose
set block [ord::get_db_block]; set n 0
foreach net [$block getNets] {
  if {[$net getSigType] in {POWER GROUND}} continue
  set w [$net getWire]
  if {$w ne "NULL"} { odb::dbWire_destroy $w; incr n }
}
puts "eco_hold: stripped routing from $n signal nets"
write_db $::env(ECO_OUT)
puts "eco_hold: wrote $::env(ECO_OUT)"
exit
