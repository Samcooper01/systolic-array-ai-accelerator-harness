# How the RTL was generated

The Verilog in `design/rtl/` is the fixed input of the competition. It was generated once and is
pinned by content; nobody needs to run the generator. This file records how it was made.

- Generator: Gemmini (https://github.com/ucb-bar/gemmini) at commit `8c8b38b9dea3e4d6ba9695346a883b2094bd7388`,
  inside Chipyard 1.11.0 (https://github.com/ucb-bar/chipyard) at commit `ac58f38d77c99e9d1cafa64dfd6d4b00bdcd43e1`,
  emitted with CIRCT firtool 1.61.0 (`make CONFIG=ChipbaseGemminiConfig verilog` in `sims/verilator`).
- Configuration: `ChipbaseConfigs.scala` (this folder). Stock int8 Gemmini defaults, except
  `meshRows = meshColumns = 8`, `tileRows = tileColumns = 2` (a 16 by 16 array as an 8 by 8 mesh of
  2 by 2 tiles) and `has_training_convs = false` (Gemmini's own inference setting), plus Rocket-chip's `WithoutTLMonitors` so the
  simulation-only TileLink assertion monitors are not generated.
- What was kept: the 120 modules reachable from the `Gemmini` module (see `../rtl/MODULES.txt`), plus
  `plusarg_reader.sv`, Rocket-chip's blackbox for simulation plusargs, which synthesizes to its default
  constant (`SYNTHESIS` is defined by the flow).
  The rest of the generated SoC (Rocket core, buses, peripherals) is not part of the design.
- Memories: the generator emits two behavioral memory modules, `mem_ext` (scratchpad bank,
  4096 x 128, one read-write port with a byte mask) and `mem_0_ext` (accumulator bank, 512 x 512,
  one read and one write port with a byte mask). They are replaced by the SRAM macros in
  `../srams/` through the wrappers in `../srams/_wrappers/` (see that folder).
