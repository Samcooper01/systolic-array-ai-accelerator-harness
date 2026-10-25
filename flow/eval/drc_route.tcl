# Routing design rules of one layout with the detailed router's own checker (the technology LEF's
# rules on every routing and via layer). Environment: EVAL_DEF, EVAL_DRC_OUT, EVAL_EXTRA_LEFS.
source [file join [file dirname [info script]] common.tcl]
ev_lefs
read_def $::env(EVAL_DEF)
drt::check_drc -output_file $::env(EVAL_DRC_OUT)
set n 0
if {[file exists $::env(EVAL_DRC_OUT)]} { set fh [open $::env(EVAL_DRC_OUT)]; foreach l [split [read $fh] "\n"] { if {[string match "violation type:*" $l]} { incr n } }; close $fh }
ev_result drc_route_violations $n
exit
