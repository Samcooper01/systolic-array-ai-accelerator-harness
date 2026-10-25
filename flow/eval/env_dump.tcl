# Print the platform variables the DRC step needs (run through the flow's make environment).
foreach v {TECH_LEF SC_LEF ADDITIONAL_LEFS GDS_FILES KLAYOUT_TECH_FILE KLAYOUT_DRC_FILE UTILS_DIR FLOW_HOME PLATFORM_DIR GDS_LAYER_MAP} {
  puts "ENV $v [expr {[info exists ::env($v)] ? $::env($v) : ""}]"
}
exit
