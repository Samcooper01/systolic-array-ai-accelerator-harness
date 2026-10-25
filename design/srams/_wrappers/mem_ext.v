// AUTO-GENERATED graybox wrapper (tools/gen_sram_wrappers.py). DO NOT hand-edit.
// Presents the masked RTL memory interface but drives an UNMASKED single-port
// FakeRAM macro (mem_ext_phys) for PPA only. The write mask is TIED OFF (full-word
// write), so this is NOT functionally correct: harden for area/timing/power, do
// not run functional sim on the netlist. Replace with a masked OpenRAM macro.
module mem_ext(
  input  [11:0] RW0_addr,
  input  RW0_clk,
  input  [127:0] RW0_wdata,
  output [127:0] RW0_rdata,
  input  RW0_en,
  input  RW0_wmode,
  input  [15:0] RW0_wmask
);
  mem_ext_phys phys (
    .clk      (RW0_clk),
    .ce_in    (RW0_en),
    .we_in    ((RW0_en & RW0_wmode)),
    .addr_in  (RW0_addr),
    .wd_in    (RW0_wdata),
    .rd_out   (RW0_rdata)
  );
endmodule
