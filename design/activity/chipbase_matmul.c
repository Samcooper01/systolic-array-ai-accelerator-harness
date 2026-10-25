// Chipbase Competition 01: the pinned power workload. One tiled weight-stationary matrix multiply on
// Gemmini with everything the accelerator's datapath does in a real layer: C = relu(scale * (A * B + D)),
// clipped to int8, with the bias D preloaded into the accumulator. Full-range random int8 operands and
// random bias (fixed seed), so switching activity is representative, not the 0/1 data of the stock test.
// The program prints the cycle counter around the accelerator call and exits right after it, so a
// waveform started at the first mark covers only the multiply. Built with CHECK_RESULT=1 it also runs
// the CPU reference on four sampled rows (all columns) and compares (chipbase_matmul_check), without
// tracing; the full reference is too slow to run in simulation.
#include <stdint.h>
#include <stddef.h>
#include <assert.h>
#include <stdlib.h>
#include <stdio.h>
#include "include/gemmini_testutils.h"

#ifndef CHECK_RESULT
#define CHECK_RESULT 0
#endif
#define MAT_DIM_I 128
#define MAT_DIM_K 128
#define MAT_DIM_J 128
#define SCALE ((acc_scale_t)(1.0 / 64.0))
typedef acc_t ACC_T;

static elem_t A[MAT_DIM_I][MAT_DIM_K] row_align(1);
static elem_t B[MAT_DIM_K][MAT_DIM_J] row_align(1);
static elem_t C[MAT_DIM_I][MAT_DIM_J] row_align(1);
static ACC_T D[MAT_DIM_I][MAT_DIM_J] row_align_acc(1);

static uint32_t seed = 0xC41Bu;
static uint32_t rnd(void) { seed = seed * 1664525u + 1013904223u; return seed >> 8; }

int main() {
  gemmini_flush(0);
  for (size_t i = 0; i < MAT_DIM_I; ++i) for (size_t k = 0; k < MAT_DIM_K; ++k) A[i][k] = (elem_t)(int)(rnd() % 256 - 128);
  for (size_t k = 0; k < MAT_DIM_K; ++k) for (size_t j = 0; j < MAT_DIM_J; ++j) B[k][j] = (elem_t)(int)(rnd() % 256 - 128);
  for (size_t i = 0; i < MAT_DIM_I; ++i) for (size_t j = 0; j < MAT_DIM_J; ++j) D[i][j] = (ACC_T)((int)(rnd() % 4096) - 2048);

  unsigned long start = read_cycles();
  printf("CHIPBASE_WINDOW_START %lu\n", start);
  tiled_matmul_auto(MAT_DIM_I, MAT_DIM_J, MAT_DIM_K,
          (elem_t*)A, (elem_t*)B, &D[0][0], (elem_t*)C,
          MAT_DIM_K, MAT_DIM_J, MAT_DIM_J, MAT_DIM_J,
          MVIN_SCALE_IDENTITY, MVIN_SCALE_IDENTITY, MVIN_SCALE_IDENTITY,
          RELU, SCALE, 0, false,
          false, false,
          false, false,
          0,
          WS);
  gemmini_fence();
  unsigned long end = read_cycles();
  printf("CHIPBASE_WINDOW_END %lu\n", end);
  printf("CHIPBASE_CYCLES %lu\n", end - start);

#if CHECK_RESULT
  int bad = 0; static const size_t rows[] = {0, 37, 64, MAT_DIM_I - 1};
  for (size_t ri = 0; ri < sizeof(rows) / sizeof(rows[0]); ++ri) for (size_t j = 0; j < MAT_DIM_J; ++j) {
    size_t i = rows[ri];
    full_t acc = D[i][j];
    for (size_t k = 0; k < MAT_DIM_K; ++k) acc += (full_t)A[i][k] * B[k][j];
    full_t s = ACC_SCALE(acc, SCALE);
    if (s > elem_t_max) s = elem_t_max; if (s < elem_t_min) s = elem_t_min;
    if (s < 0) s = 0;
    if (C[i][j] != (elem_t)s) { if (bad < 8) printf("mismatch C[%d][%d]=%d gold=%d\n", (int)i, (int)j, C[i][j], (int)s); bad++; }
  }
  printf("CHIPBASE_CHECK %s (%d mismatches)\n", bad ? "FAIL" : "PASS", bad);
  exit(bad ? 1 : 0);
#endif
  exit(0);
}
