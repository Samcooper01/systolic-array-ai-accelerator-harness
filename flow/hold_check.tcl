# Worst hold slack of a finished run at the flow's corner (the ASAP7 default, BC: FF libraries), on its
# extracted parasitics. Run through "make ... FLOW_VARIANT=<variant> open_6_final.odb".
read_spef $::env(RESULTS_DIR)/6_final.spef
set_propagated_clock [all_clocks]
puts [format "WORST_HOLD %.2f" [sta::worst_slack -min]]
exit
