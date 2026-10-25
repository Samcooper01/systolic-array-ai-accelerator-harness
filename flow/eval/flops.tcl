# List a loaded design's flip-flops (instance, master, output pins) and input ports for activity.py.
# Environment: EVAL_FLOPS, EVAL_PORTS (output paths). Sourced after the design is read.
proc ev_dump_flops {} {
  set f [open $::env(EVAL_FLOPS) w]
  foreach i [[ord::get_db_block] getInsts] {
    set m [$i getMaster]
    if {[$m isBlock]} continue
    # ASAP7 sequential cells by name: flip-flops and latches (clock gates, ICG*, are not state)
    if {![regexp {^(DFF|ASYNC_DFF|DHL|DLL|SDF)} [$m getName]]} continue
    set outs {}; foreach it [$i getITerms] { if {[$it isOutputSignal]} { lappend outs [[$it getMTerm] getName] } }
    puts $f "[$i getName]\t[$m getName]\t[join $outs ,]"
  }
  close $f
  set f [open $::env(EVAL_PORTS) w]
  foreach bt [[ord::get_db_block] getBTerms] { if {[$bt getIoType] eq "INPUT"} { puts $f [$bt getName] } }
  close $f
}
