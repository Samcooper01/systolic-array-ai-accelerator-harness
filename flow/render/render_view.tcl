# Headless stage render. Env: VIEW (floorplan | placement | cts | routing | macros), OUT, RES_PX
# (pixels across the die height). The image always covers exactly the die, so renders of different
# blocks can be composited by coordinates.
set block [ord::get_db_block]
set die [$block getDieArea]
set x1 [ord::dbu_to_microns [$die xMin]]; set y1 [ord::dbu_to_microns [$die yMin]]
set x2 [ord::dbu_to_microns [$die xMax]]; set y2 [ord::dbu_to_microns [$die yMax]]
set px 1200
if {[info exists ::env(RES_PX)]} { set px $::env(RES_PX) }
set resolution [expr {($y2 - $y1) / double($px)}]
gui::clear_highlights -1
gui::clear_selections
gui::set_display_controls "*" visible false
gui::set_display_controls "Layers/*" visible true
gui::set_display_controls "Nets/*" visible true
gui::set_display_controls "Instances/*" visible true
gui::set_display_controls "Shape Types/*" visible true
gui::set_display_controls "Misc/Instances/*" visible false
gui::set_display_controls "Misc/Instances/Names" visible false
set view $::env(VIEW)
if {$view eq "macros"} {
  gui::set_display_controls "Nets/*" visible false
  gui::set_display_controls "Shape Types/*" visible false
  gui::set_display_controls "Instances/StdCells/*" visible false
  gui::set_display_controls "Instances/Physical/*" visible false
} elseif {$view eq "placement"} {
  gui::set_display_controls "Nets/Power" visible false
  gui::set_display_controls "Nets/Ground" visible false
  gui::set_display_controls "Shape Types/Routing/*" visible false
  gui::set_display_controls "Instances/Physical/Fill cell" visible false
} elseif {$view eq "cts"} {
  # the routed clock network only, over the cell outlines
  gui::set_display_controls "Nets/*" visible false
  gui::set_display_controls "Nets/Clock" visible true
  gui::set_display_controls "Instances/Physical/*" visible false
} elseif {$view eq "routing"} {
  gui::set_display_controls "Nets/Power" visible false
  gui::set_display_controls "Nets/Ground" visible false
}
save_image -area [list $x1 $y1 $x2 $y2] -resolution $resolution $::env(OUT)
