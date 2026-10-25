# Top-level power grid for the Gemmini reference. Rails on M1/M2 as in the stock ASAP7 grid, then
# vertical M5 stripes only where standard cells are (the hardened blocks obstruct M5, so these
# run in the channels between blocks), and the mesh proper on the two thick top layers: M8
# horizontal, M9 vertical, 0.32 um wide at a 5.4 um pitch. M6 and M7 carry no power at all and
# M3 to M7 are free for signals over the blocks. Block power pins are the blocks' own M7 stripes,
# reached with via stacks from the M8 stripes crossing over them. Die power pins are on M9.
# (A direct M2-to-M9 via stack through the M8 stripes is not something pdngen will build; the
# short M5 hop is what makes the connection.) Entrants may replace this grid as long as the IR
# drop gate passes.
add_global_connection -net {VDD} -inst_pattern {.*} -pin_pattern {^VDD$} -power
add_global_connection -net {VDD} -inst_pattern {.*} -pin_pattern {^VDDPE$}
add_global_connection -net {VDD} -inst_pattern {.*} -pin_pattern {^VDDCE$}
add_global_connection -net {VSS} -inst_pattern {.*} -pin_pattern {^VSS$} -ground
add_global_connection -net {VSS} -inst_pattern {.*} -pin_pattern {^VSSE$}
global_connect
set_voltage_domain -name {CORE} -power {VDD} -ground {VSS}

define_pdn_grid -name {top} -voltage_domains {CORE} -pins {M9}
add_pdn_stripe -grid {top} -layer {M1} -width {0.018} -pitch {0.54} -offset {0} -followpins
add_pdn_stripe -grid {top} -layer {M2} -width {0.018} -pitch {0.54} -offset {0} -followpins
add_pdn_stripe -grid {top} -layer {M5} -width {0.12} -spacing {0.072} -pitch {5.4} -offset {0.3}
add_pdn_stripe -grid {top} -layer {M8} -width {0.32} -spacing {0.32} -pitch {5.4} -offset {1.0}
add_pdn_stripe -grid {top} -layer {M9} -width {0.32} -spacing {0.32} -pitch {5.4} -offset {1.0}
add_pdn_connect -grid {top} -layers {M1 M2}
add_pdn_connect -grid {top} -layers {M2 M5}
add_pdn_connect -grid {top} -layers {M5 M8}
add_pdn_connect -grid {top} -layers {M8 M9}

# hardened blocks: power pins are their M7 stripes, met directly by the M8 stripes over them
define_pdn_grid -name {block_grid} -voltage_domains {CORE} -macro -orient {R0 R180 MX MY} -halo {2.0 2.0 2.0 2.0} -default
add_pdn_connect -grid {block_grid} -layers {M7 M8}
