# The floorplan editor used for the reference

`fpedit.py` is the interactive editor the reference top-level floorplan was drawn with: drag the
hardened blocks and the SRAM macros around the die, see the block-to-block bus connectivity as lines
between pin centroids weighted by bit count, with a wire-length score, overlap and channel-width
warnings, mirroring and rotation, undo, and save to JSON. `fpctl.py` drives it from another process
(the development session moved blocks on request through it; `cmd_log.txt` on the development machine
is that conversation). `fpedit_flat.py` is the variant for the opened-hierarchy reference (flat logic
at the top, nine block types plus the eight memories).

Inputs: `bus_graph.json` (which block ports connect to which, extracted from the synthesized top by
`extract_bus_graph.py`, `extract_top_graph.py`, `extract_flat_graph.py`, `extract_graph2.py`) and the
blocks' abstracts for their sizes and pin positions. `split_mwd.py` splits a wide-data bus for the
graph; `legalize_logic_file.py` snaps a saved floorplan to the placement grid; `make_dataflow_anim.py`
draws the dataflow animation that was tried for the page.

`tight2_src.json` is the compact floorplan as drawn and `tight2_legal.json` the same snapped to the
grid. Save writes both the JSON and the `place_macro` Tcl the flow reads; `flow/gemmini/macro_place_tight2.tcl`
(the floorplan the reference flow uses) is that output for `tight2_legal.json`. The scripts carry development-machine paths; set them before use. The large
intermediate files (the per-net table, the rendered frames) were not brought over.
