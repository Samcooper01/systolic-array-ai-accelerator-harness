# Power grid for the level-2 hardened blocks (ExecuteController, Scratchpad, the controllers).
# Rails on M1/M2, then the stock ASAP7 M5 (vertical) and M6 (horizontal) stripes, plus M7
# vertical stripes that become the block's power pins: the top's M8 horizontal mesh crosses them
# and drops vias. A ring on M6/M7 ties the stripes together at the block edge. These blocks route
# signals on M2 to M7; the top routes over them on M8/M9. Sub-macros inside (Tiles with M5 pins,
# SRAMs with M4 pins, AccumulatorScale with M5 pins) are picked up by the crossing stripes.
add_global_connection -net {VDD} -inst_pattern {.*} -pin_pattern {^VDD$} -power
add_global_connection -net {VDD} -inst_pattern {.*} -pin_pattern {^VDDPE$}
add_global_connection -net {VDD} -inst_pattern {.*} -pin_pattern {^VDDCE$}
add_global_connection -net {VSS} -inst_pattern {.*} -pin_pattern {^VSS$} -ground
add_global_connection -net {VSS} -inst_pattern {.*} -pin_pattern {^VSSE$}
global_connect
set_voltage_domain -name {CORE} -power {VDD} -ground {VSS}

define_pdn_grid -name {top} -voltage_domains {CORE} -pins {M7}
add_pdn_ring   -grid {top} -layers {M6 M7} -widths {0.288 0.288} -spacings {0.096 0.096} -core_offset {0.3}
add_pdn_stripe -grid {top} -layer {M1} -width {0.018} -pitch {0.54} -offset {0} -followpins
add_pdn_stripe -grid {top} -layer {M2} -width {0.018} -pitch {0.54} -offset {0} -followpins
add_pdn_stripe -grid {top} -layer {M5} -width {0.12}  -spacing {0.072} -pitch {5.4} -offset {0.300} -extend_to_core_ring
add_pdn_stripe -grid {top} -layer {M6} -width {0.288} -spacing {0.096} -pitch {5.4} -offset {0.513} -extend_to_core_ring
add_pdn_stripe -grid {top} -layer {M7} -width {0.288} -spacing {0.096} -pitch {5.4} -offset {0.700} -extend_to_core_ring
add_pdn_connect -grid {top} -layers {M1 M2}
add_pdn_connect -grid {top} -layers {M2 M5}
add_pdn_connect -grid {top} -layers {M5 M6}
add_pdn_connect -grid {top} -layers {M6 M7}

# sub-macros: SRAM power pins are horizontal M4 (met by the M5 stripes), Tile and AccumulatorScale
# power pins are vertical M5 (met by the M6 stripes)
define_pdn_grid -name {macro_grid} -voltage_domains {CORE} -macro -orient {R0 R180 MX MY} -halo {2.0 2.0 2.0 2.0} -default
add_pdn_connect -grid {macro_grid} -layers {M4 M5}
add_pdn_connect -grid {macro_grid} -layers {M5 M6}
