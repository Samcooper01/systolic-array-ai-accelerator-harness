package chipyard

import org.chipsalliance.cde.config.{Config}
import gemmini._

// Chipbase Competition 01 reference design: stock int8 Gemmini (16x16 array) built as an
// 8x8 mesh of 2x2 tiles, so the Tile is a real hardening unit that repeats 64 times.
// Only the convolution training paths are dropped (Gemmini's own inference config knob);
// everything else is the upstream default (256 KiB scratchpad in 4 banks, 64 KiB accumulator
// in 2 banks, both dataflows, max-pool and nonlinear activations kept).
object ChipbaseGemmini {
  val int8_16x16_tile2 = GemminiConfigs.defaultConfig.copy(
    meshRows = 8, meshColumns = 8,
    tileRows = 2, tileColumns = 2,
    has_training_convs = false)
}

class ChipbaseGemminiConfig extends Config(
  new gemmini.DefaultGemminiConfig(ChipbaseGemmini.int8_16x16_tile2) ++
  new freechips.rocketchip.subsystem.WithNBigCores(1) ++
  new chipyard.config.WithSystemBusWidth(128) ++
  new chipyard.config.AbstractConfig)
