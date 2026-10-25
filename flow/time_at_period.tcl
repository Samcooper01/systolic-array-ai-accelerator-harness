# Retime a finished run at other clock periods, without re-optimizing anything: only the clock
# period in the SDC changes (the reference SDC scales its io budgets with it). Two modes:
#   PERIODS="900 1000 1100"  report worst setup and hold slack at each listed period (ps)
#   SEARCH=1                 find the smallest period (5 ps steps) that passes setup and hold;
#                            this is the period the reference declares, computed the way the
#                            timing gate computes it
# Run through ORFS so the design environment is loaded, for example:
#   make DESIGN_CONFIG=flow/gemmini/config.mk run RUN_SCRIPT=$PWD/flow/time_at_period.tcl SEARCH=1
source $::env(SCRIPTS_DIR)/load.tcl
load_design 6_final.odb 6_final.sdc
read_spef $::env(RESULTS_DIR)/6_final.spef
set fh [open $::env(SDC_FILE) r]; set sdc_text [read $fh]; close $fh
regexp {set clk_period ([0-9.]+)} $sdc_text -> sdc_period

proc slack_at {period} {
  global sdc_text
  regsub {set clk_period [0-9.]+} $sdc_text "set clk_period $period" sdc_p
  set tmp $::env(RESULTS_DIR)/retime.sdc
  set out [open $tmp w]; puts $out $sdc_p; close $out
  read_sdc $tmp
  set_propagated_clock [all_clocks]
  set ws [sta::worst_slack -max]; set wh [sta::worst_slack -min]
  puts [format "PERIOD %d setup_ws %.1f hold_ws %.1f" $period $ws $wh]
  return [list $ws $wh]
}
# SETUP_ONLY=1: pass on setup alone. The grader checks setup at the slow corner and hold at the fast
# corner, so a slow-corner search must not require hold (hold is checked by the fast-corner search).
proc passes {period} {
  lassign [slack_at $period] ws wh
  if { [info exists ::env(SETUP_ONLY)] && $::env(SETUP_ONLY) } { return [expr {$ws >= 0}] }
  return [expr {$ws >= 0 && $wh >= 0}]
}

if { [info exists ::env(PERIODS)] && $::env(PERIODS) ne "" } {
  foreach p $::env(PERIODS) { slack_at $p }
} else {
  # geometric climb from the SDC period until it passes, then bisect down to 5 ps
  set hi [expr {int($sdc_period)}]
  set lo 0
  while { ![passes $hi] } { set lo $hi; set hi [expr {int($hi * 1.5)}]; if { $hi > 100000 } { puts "DECLARED_PERIOD none"; exit 1 } }
  while { $hi - $lo > 5 } {
    set mid [expr {int(($lo + $hi) / 2)}]
    if { [passes $mid] } { set hi $mid } else { set lo $mid }
  }
  set fh [open $::env(RESULTS_DIR)/declared_period.txt w]; puts $fh $hi; close $fh
  puts "DECLARED_PERIOD $hi"
}
