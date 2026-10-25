# SRAM macros (FakeRAM2.0)

Black-box SRAM macros for the two memories the generator emits, produced with FakeRAM2.0
(https://github.com/The-OpenROAD-Project/FakeRAM2.0, commit `8e6cd664f8d5f42ae684c8846a536f66c9d22ae8`)
from the configs in this folder (same process parameters as OpenROAD-flow-scripts' own ASAP7 fakeram7 macros).

| macro | size | used for | count in the design |
|---|---|---|---|
| `mem_ext_phys` | 4096 x 128, 265.43 x 84.00 um | one scratchpad bank | 4 |
| `mem_0_bank_ext_phys` | 512 x 256, 132.81 x 42.00 um | one half of an accumulator bank | 4 (2 banks x 2 halves) |

`_wrappers/mem_ext.v` and `_wrappers/mem_0_ext_banked.v` present the generator's memory interfaces
(`mem_ext`, `mem_0_ext`) and instantiate the macros. Two caveats, inherited from FakeRAM2.0: the
macros are single-port and unmasked, so the wrappers tie the byte-write mask off and map the
accumulator's read and write ports onto one port. The result is correct for area, timing, and power
sign-off, which is what is scored; it is not a functional model of the masked memory. Equivalence
checking black-boxes the macros on both sides, so this does not affect the equivalence gate.

Regenerate: `python3 run.py fakeram_scratchpad.cfg --output_dir out` (and the accumulator config),
then `gen_sram_wrappers.py` from the Systole tools to rename the cells to `*_phys` and emit wrappers.
