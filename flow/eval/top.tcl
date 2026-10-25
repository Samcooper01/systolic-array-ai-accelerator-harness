# The top level: read the submitted layout (DEF) with the evaluator's own block abstracts and timing
# models, extract parasitics, and measure one corner's checks.
#   EVAL_MODE=setup   (CORNER=WC) worst setup slack at the declared period
#   EVAL_MODE=hold    (CORNER=BC) worst hold slack, placement legality, unrouted nets, die area
#   EVAL_MODE=power   (CORNER=TC) total power at the fixed reference clock with the pinned switching
#                     activity (EVAL_ACTIVITY_TCL, written by activity.py), then static IR drop
# Environment: EVAL_DEF, EVAL_PERIOD, EVAL_WORK, EVAL_EXTRA_LEFS, EVAL_EXTRA_LIBS, CORNER.
source [file join [file dirname [info script]] common.tcl]
source [file join [file dirname [info script]] flops.tcl]
set mode $::env(EVAL_MODE)
ev_lefs
read_def $::env(EVAL_DEF)
ev_libs
set period [expr {$mode eq "power" ? 1000 : $::env(EVAL_PERIOD)}]   ;# power: the fixed reference clock
ev_sdc $period
ev_extract [file join $::env(EVAL_WORK) top.spef]
set_propagated_clock [all_clocks]

if {$mode eq "setup"} {
  ev_result setup_wns_ps [format %.2f [sta::worst_slack -max]]
} elseif {$mode eq "hold"} {
  ev_result hold_wns_ps [format %.2f [sta::worst_slack -min]]
  ev_result placement_legal [expr {[catch {check_placement -verbose} msg] == 0}]
  lassign [ev_unrouted] n names
  ev_result unrouted_nets $n
  if {$n} { ev_result unrouted_examples [join $names ,] }
  set die [[ord::get_db_block] getDieArea]
  set ::env(EVAL_FLOPS) [file join $::env(EVAL_WORK) top.flops.tsv]; set ::env(EVAL_PORTS) [file join $::env(EVAL_WORK) top.ports.tsv]
  ev_dump_flops
  ev_result die_area_um2 [format %.1f [expr {[$die dx] / 1000.0 * [$die dy] / 1000.0}]]
} elseif {$mode eq "power"} {
  if {[info exists ::env(EVAL_ACTIVITY_TCL)]} { source $::env(EVAL_ACTIVITY_TCL) }
  set p [sta::design_power [sta::cmd_scene]]
  ev_result top_power_w [format %.6g [lindex $p 3]]
  ev_result top_power_internal_w [format %.6g [lindex $p 0]]
  ev_result top_power_switching_w [format %.6g [lindex $p 1]]
  ev_result top_power_leakage_w [format %.6g [lindex $p 2]]
  set_pdnsim_net_voltage -net VDD -voltage 0.70
  set_pdnsim_net_voltage -net VSS -voltage 0.0
  foreach net {VDD VSS} {
    analyze_power_grid -net $net -voltage_file [file join $::env(EVAL_WORK) "ir_$net.csv"]
  }
}
exit
