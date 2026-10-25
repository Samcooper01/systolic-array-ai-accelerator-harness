# Pin-level connectivity of one design, for the layout-vs-netlist comparison: one line per connected
# instance pin or port, "net<TAB>instance/pin". EVAL_CONN_SRC=def reads the layout (EVAL_DEF);
# EVAL_CONN_SRC=verilog reads the netlist (EVAL_VERILOG, top module EVAL_TOP). Output: EVAL_CONN_OUT.
source [file join [file dirname [info script]] common.tcl]
ev_lefs
if {$::env(EVAL_CONN_SRC) eq "def"} {
  read_def $::env(EVAL_DEF)
} else {
  read_verilog $::env(EVAL_VERILOG)
  link_design $::env(EVAL_TOP)
}
set f [open $::env(EVAL_CONN_OUT) w]
foreach net [[ord::get_db_block] getNets] {
  if {[$net getSigType] in {POWER GROUND}} continue
  set n [$net getName]
  foreach it [$net getITerms] { puts $f "$n\t[[$it getInst] getName]/[[$it getMTerm] getName]" }
  foreach bt [$net getBTerms] { puts $f "$n\tPORT/[$bt getName]" }
}
close $f
exit
