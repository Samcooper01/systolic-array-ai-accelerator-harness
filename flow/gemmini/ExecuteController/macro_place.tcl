# Tile grid inside the ExecuteController block. All tiles are R0 with column 0 on the left, so A
# enters on the block's left edge next to the scratchpad interface pins, and B, D, and the control
# signals come down from the band above row 0. The transposer is left to the automatic macro
# placer. Tiles are never mirrored: the tile is 39.046 um wide, not a multiple of the 0.048 um
# track pitch, so a mirrored tile puts every top and bottom pin 22 nm off the routing grid.
set tile 39.046
set px [expr {$tile + 12.0}]     ;# vertical channel: A bus and control
set py [expr {$tile + 16.0}]     ;# horizontal channel: B, D and the pipeline registers
set x0 30.0
set y0 45.0
set y_top [expr {$y0 + 7 * $py}]
for {set r 0} {$r < 8} {incr r} {
  for {set c 0} {$c < 8} {incr c} {
    place_macro -macro_name "mesh/mesh/mesh_${r}_${c}" \
      -location [list [expr {$x0 + $c * $px}] [expr {$y_top - $r * $py}]] -orientation R0
  }
}
