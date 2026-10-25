# Rendering the reference layout images

The five stage images on the challenge page (`app/static/img/ref_chip_*.webp` in the [chipbase](https://github.com/Samcooper01/chipbase) repository) came from these
scripts, run on the development machine against the reference run's stage databases.

- `render.sh`: for the top and for the Tile block, opens each stage's database (`2_floorplan.odb`,
  `3_place.odb`, `5_route.odb`) in OpenROAD's GUI offscreen with `render_driver.tcl` and writes a
  3,600 px (top) or 1,600 px (block) WebP; copies the flow's own clock-tree image for the CTS stage.
- `render_view.tcl` and its variants: the view settings. `render_view_fp_clean.tcl` is the floorplan
  (no power grid, no pin markers, block internals drawn, a clear die edge); `render_view_nopins.tcl`
  the placement; `render_view.tcl` the routing; `render_view_finish.tcl` the finished die with every
  layer. `render_driver.tcl` picks the view named in `VIEWTCL`.
- `highlight_groups.tcl`: colours the flat logic by the RTL hierarchy it came from (for inspection).
- `conn_plot.py`: block-to-block net connectivity drawn over the floorplan, from a `conn.tsv`.
- `asap7.lyp`: ASAP7's KLayout layer colours, copied unchanged from OpenROAD-flow-scripts at the pinned
  commit (`flow/platforms/asap7/KLayout/asap7.lyp`) so a reader can open the finished layout on their
  own machine, where the container's copy is out of reach: `klayout -l flow/render/asap7.lyp
  baseline/final.gds`.
- `swap_images.py`: installed the rendered images into the page's static directory under their
  `ref_chip_*` names; the 1,600 px `_sm` display copies of the routing and finish images were made
  from the full renders with Pillow.

The scripts carry the development machine's paths (`/home/sam/Geetus2.0/chipbase-ref`,
`.../Flow/OpenROAD-flow-scripts`, `.../PD-Leet/app`): set `W`, `O` and the output paths to your own
before running. The run directories they read are `work/results/asap7/gemmini_flat*/base/` after
`run_baseline.sh` (the reference run on the development machine used the nickname `gemmini9`).
