#!/bin/bash
# Render floorplan / placement / routing from the stage databases, and take the flow's own clock-tree image.
O=/home/sam/Geetus2.0/Flow/OpenROAD-flow-scripts; W=/home/sam/Geetus2.0/chipbase-ref
cd $O/flow && source $O/env.sh >/dev/null 2>&1
export VIEWTCL=$W/render/render_view.tcl
for D in gemmini_ExecuteController_Tile gemmini; do
  R=$W/flow/results/asap7/$D/base; P=$W/flow/reports/asap7/$D/base
  for pair in floorplan:2_floorplan placement:3_place routing:5_route; do
    v=${pair%%:*}; odb=${pair##*:}
    [ -f $R/$odb.odb ] || { echo "missing $R/$odb.odb"; continue; }
    RES_PX=$([ $D = gemmini ] && echo 3600 || echo 1600) ODB=$R/$odb.odb VIEW=$v OUT=$W/img/${D}_$v.webp QT_QPA_PLATFORM=offscreen timeout 900 openroad -exit $W/render/render_driver.tcl > $W/img/${D}_$v.log 2>&1
    echo "$D $v exit $? $(stat -c%s $W/img/${D}_$v.webp 2>/dev/null)B"
  done
  cp $P/final_clocks.webp $W/img/${D}_cts.webp 2>/dev/null && echo "$D cts copied"
  cp $P/final_all.webp $W/img/${D}_final.webp 2>/dev/null
done
