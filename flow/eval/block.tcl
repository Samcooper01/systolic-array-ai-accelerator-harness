# One hardened block: read its submitted layout (DEF), extract parasitics, write the evaluator's own
# abstract and timing model for this corner, and check its placement and routing.
# Environment: EVAL_BLOCK (name), EVAL_DEF, EVAL_OUT (output directory), CORNER.
source [file join [file dirname [info script]] common.tcl]
source [file join [file dirname [info script]] flops.tcl]
set b $::env(EVAL_BLOCK); set out $::env(EVAL_OUT)
ev_lefs
read_def $::env(EVAL_DEF)
ev_libs
ev_sdc 1000
ev_extract [file join $out "$b.spef"]
set_propagated_clock [all_clocks]
set_clock_latency -source 0 [all_clocks]
write_timing_model [file join $out "${b}_$::env(CORNER).lib"]
if {$::env(CORNER) eq "BC"} {
  write_abstract_lef -bloat_occupied_layers [file join $out "$b.lef"]
  set legal [expr {[catch {check_placement -verbose} msg] == 0}]
  ev_result "block_$b.placement_legal" $legal
  lassign [ev_unrouted] n names
  ev_result "block_$b.unrouted_nets" $n
  set ::env(EVAL_FLOPS) [file join $out "$b.flops.tsv"]; set ::env(EVAL_PORTS) [file join $out "$b.ports.tsv"]
  ev_dump_flops
}
ev_result "block_$b.model_$::env(CORNER)" ok
exit
