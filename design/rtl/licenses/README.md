# Licenses of the generated design

The Verilog in `design/rtl/` was generated from third-party open-source hardware (see
`design/generator/README.md` for how). It carries the licenses of the sources it was generated from:

| Source | License | Text |
|---|---|---|
| Gemmini, commit `8c8b38b` (https://github.com/ucb-bar/gemmini) | BSD 3-Clause, The Regents of the University of California | `LICENSE.gemmini` |
| Chipyard 1.11.0, commit `ac58f38d` (https://github.com/ucb-bar/chipyard) | BSD 3-Clause, The Regents of the University of California | `LICENSE.chipyard` |
| Rocket Chip, as included by Chipyard (https://github.com/chipsalliance/rocket-chip) | BSD 3-Clause (The Regents of the University of California) and Apache 2.0 (SiFive) | `LICENSE.rocket-chip.Berkeley`, `LICENSE.rocket-chip.SiFive` |

The memory macro views in `design/srams/` were generated with FakeRAM2.0
(https://github.com/The-OpenROAD-Project/FakeRAM2.0, commit `8e6cd66`), which publishes no license
file; the configurations that produced them are in that folder.
