# Shared evaluator setup. Environment (set by evaluate.py): EVAL_WORK (scratch), EVAL_EXTRA_LEFS and
# EVAL_EXTRA_LIBS (space-separated: the evaluator's own block abstracts and timing models), CORNER (BC, TC
# or WC, from the platform config), plus the platform variables the flow's make environment exports.
set ::ev_dir [file dirname [file normalize [info script]]]
proc ev_lefs {} {
  read_lef $::env(TECH_LEF)
  foreach l $::env(SC_LEF) { read_lef $l }
  foreach l $::env(ADDITIONAL_LEFS) { read_lef $l }
  if {[info exists ::env(EVAL_EXTRA_LEFS)]} { foreach l $::env(EVAL_EXTRA_LEFS) { read_lef $l } }
}
proc ev_libs {} {
  foreach l $::env(LIB_FILES) { read_liberty $l }
  if {[info exists ::env(EVAL_EXTRA_LIBS)]} { foreach l $::env(EVAL_EXTRA_LIBS) { read_liberty $l } }
}
# the pinned constraints with the clock period replaced (the one knob an entry chooses)
proc ev_sdc {period} {
  set fh [open $::env(SDC_FILE)]; set t [read $fh]; close $fh
  regsub {set clk_period [0-9.]+} $t "set clk_period $period" t
  set f [file join $::env(EVAL_WORK) "constraint_$period.sdc"]
  set fh [open $f w]; puts $fh $t; close $fh
  read_sdc $f
}
# The pinned resistance and capacitance per layer, read from the harness's own file by path: the platform
# sets SET_RC_TCL to its own setRC.tcl after the evaluator's settings are read, and that file has no
# M8/M9 values (the IR drop analysis then stops on a zero-resistance layer).
proc ev_layer_rc {} {
  source [file join $::ev_dir .. gemmini setRC.tcl]
}
# parasitics extracted by the evaluator with the pinned rules; the entry's own SPEF is ignored
proc ev_extract {spef} {
  ev_layer_rc
  if {[file exists $spef]} { read_spef $spef; return }
  define_process_corner -ext_model_index 0 X
  extract_parasitics -ext_model_file $::env(RCX_RULES)
  write_spef $spef
  read_spef $spef
}
# signal nets with two or more connections and no routing
proc ev_unrouted {} {
  set n 0; set names {}
  foreach net [[ord::get_db_block] getNets] {
    if {[$net getSigType] in {POWER GROUND} || [$net isSpecial]} continue
    if {[llength [$net getITerms]] + [llength [$net getBTerms]] < 2} continue
    if {[$net getWire] eq "NULL"} { incr n; if {[llength $names] < 10} { lappend names [$net getName] } }
  }
  return [list $n $names]
}
proc ev_result {key value} { puts "EVAL $key $value" }
