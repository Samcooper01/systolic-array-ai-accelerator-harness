#!/usr/bin/env python3
"""Replace the 8 mock-up cards on the challenge page with the real reference layout renders."""
import os,shutil,re,sys
W="/home/sam/Geetus2.0/chipbase-ref/img"; APP="/home/sam/Geetus2.0/PD-Leet/app"
imgs={("gemmini_ExecuteController_Tile","floorplan"):"ref_tile_1_floorplan.webp",("gemmini_ExecuteController_Tile","placement"):"ref_tile_2_placement.webp",
      ("gemmini_ExecuteController_Tile","cts"):"ref_tile_3_cts.webp",("gemmini_ExecuteController_Tile","routing"):"ref_tile_4_routing.webp",
      ("gemmini","floorplan"):"ref_chip_1_floorplan.webp",("gemmini","placement"):"ref_chip_2_placement.webp",
      ("gemmini","cts"):"ref_chip_3_cts.webp",("gemmini","routing"):"ref_chip_4_routing.webp"}
missing=[f"{d}_{v}.webp" for (d,v),_ in imgs.items() if not os.path.exists(f"{W}/{d}_{v}.webp")]
if missing: sys.exit("missing renders: "+", ".join(missing))
for (d,v),dst in imgs.items(): shutil.copy(f"{W}/{d}_{v}.webp", f"{APP}/static/img/{dst}")
tile=[("Floorplan","The 2 by 2 tile's outline, power rails, and pins: A in on the left edge and out on the right, B, D, and control in on the top edge, B, C, and control out on the bottom, each output mirrored to the input it feeds so tiles abut in a grid."),
      ("Placement","The four processing elements' standard cells placed inside the tile."),
      ("Clock tree synthesis","The tile's clock network, buffered to reach every flip-flop with balanced arrival."),
      ("Routing","The tile fully routed on M2 to M5. This abstract is what the ExecuteController block places 64 times.")]
chip=[("Floorplan","The nine hardened blocks on the die: the Scratchpad (eight SRAM (Static Random-Access Memory) macros and the accumulator datapath inside) on the left, the ExecuteController (the 64-tile array and its transposer inside) on the right with their 3,504-pin interface edges facing across a 40 um channel, and the seven controller blocks in the band above, each over the pins it talks to. The power mesh is on M8 and M9."),
      ("Placement","The remaining top-level logic, about 8,000 cells of command routing, arbiters, and interface buffers, placed between the blocks."),
      ("Clock tree synthesis","One clock tree reaching every block's clock pin and the top-level registers."),
      ("Routing","The top level routed on all nine metal layers: the interface bundle across the channel, the controller traffic down to the block pins, the die pins at the edges. The finished reference chip.")]
def cards(prefix,caps):
    out='    <div class="stage-gallery">\n'
    for i,(n,note) in enumerate(caps,1):
        out+=f'''      <figure class="stage-shot">
        <span class="stage-num">{i}</span>
        <img src="/static/img/{prefix}_{i}_{['floorplan','placement','cts','routing'][i-1]}.webp?v={{{{ asset_v }}}}" alt="Gemmini reference {prefix.split('_')[1]} after {n}" loading="lazy">
        <figcaption><b>{n}</b><span>{note}</span></figcaption>
      </figure>
'''
    return out+'    </div>\n'
p=f"{APP}/templates/challenge.html"; t=open(p).read()
s=t.index('    <h2>The reference layout, stage by stage</h2>'); e=t.index('  </section>',s)
new=('    <h2>The reference layout, stage by stage</h2>\n'
     '    <p>The reference flow, rendered from its own databases: the smallest block through the flow, then the full chip. Two more levels sit between them (the array block and the memory block, each hardened once), which is where the reference does its floorplanning.</p>\n'
     '    <h3 class="rules-sub">One block: the 2 &#215; 2 tile</h3>\n'+cards("ref_tile",tile)+
     '    <h3 class="rules-sub">The full chip: the top level</h3>\n'+cards("ref_chip",chip))
t=t[:s]+new+t[e:]; open(p,"w").write(t); print("page section replaced; mock cards removed:", t.count("mock-badge"))
