# Evaluator environment: the pinned platform (tech and cell LEFs, per-corner libraries, RCX rules) and
# the fixed SRAM macros. The evaluator's scripts read the submitted layouts themselves; nothing here
# comes from the entry.
export PLATFORM = asap7
CB := $(abspath $(dir $(lastword $(MAKEFILE_LIST)))../..)
export DESIGN_NAME = Gemmini
export DESIGN_NICKNAME = eval
export ADDITIONAL_LEFS = $(CB)/design/srams/mem_ext/mem_ext.lef $(CB)/design/srams/mem_0_bank_ext/mem_0_bank_ext.lef
export ADDITIONAL_LIBS = $(CB)/design/srams/mem_ext/mem_ext.lib $(CB)/design/srams/mem_0_bank_ext/mem_0_bank_ext.lib
export GDS_ALLOW_EMPTY = .*_ext_phys
export LAYER_PARASITICS_FILE = $(CB)/flow/gemmini/setRC.tcl
export SDC_FILE = $(CB)/flow/gemmini/constraint.sdc
