// AUTO-GENERATED graybox wrapper (tools/gen_sram_wrappers.py --bank). DO NOT hand-edit.
// Presents the masked RTL memory interface but drives 2 UNMASKED single-port
// FakeRAM bank macros (mem_0_bank_ext_phys, 256 bits each) for PPA only: FakeRAM puts every
// pin on the macro's left edge at track pitch, and a 512-bit word on one edge
// cannot escape global routing. The write mask is TIED OFF (full-word write), so
// this is NOT functionally correct: harden for area/timing/power only.
// NOTE: 1R1W memory mapped onto SINGLE-PORT banks (write priority);
//       read+write collide and area understates a true dual-port cell.
module mem_0_ext(
  input  [8:0] R0_addr,
  input  R0_clk,
  output [511:0] R0_data,
  input  R0_en,
  input  [8:0] W0_addr,
  input  W0_clk,
  input  [511:0] W0_data,
  input  W0_en,
  input  [63:0] W0_mask
);
  mem_0_bank_ext_phys bank_0 (
    .clk (W0_clk), .ce_in ((R0_en | W0_en)), .we_in (W0_en), .addr_in ((W0_en ? W0_addr : R0_addr)),
    .wd_in (W0_data[255:0]), .rd_out (R0_data[255:0])
  );
  mem_0_bank_ext_phys bank_1 (
    .clk (W0_clk), .ce_in ((R0_en | W0_en)), .we_in (W0_en), .addr_in ((W0_en ? W0_addr : R0_addr)),
    .wd_in (W0_data[511:256]), .rd_out (R0_data[511:256])
  );
endmodule
