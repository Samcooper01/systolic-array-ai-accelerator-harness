# Power of every instance of one hardened block at the typical corner and the fixed reference clock:
# the block is read once (its DEF and the evaluator's extracted parasitics), then each instance's own
# switching activity is applied in turn (activity.py wrote one Tcl file per instance).
# Environment: EVAL_BLOCK, EVAL_DEF, EVAL_SPEF, EVAL_INSTANCES ("instance=activity.tcl" pairs), CORNER=TC.
source [file join [file dirname [info script]] common.tcl]
set b $::env(EVAL_BLOCK)
ev_lefs
read_def $::env(EVAL_DEF)
ev_libs
ev_sdc 1000
source [file join [file dirname [info script]] .. gemmini setRC.tcl]
read_spef $::env(EVAL_SPEF)
set_propagated_clock [all_clocks]
foreach pair $::env(EVAL_INSTANCES) {
  lassign [split $pair =] inst tcl
  source $tcl
  set p [sta::design_power [sta::cmd_scene]]
  ev_result "block_power.$b.$inst" [format %.6g [lindex $p 3]]
}
exit
