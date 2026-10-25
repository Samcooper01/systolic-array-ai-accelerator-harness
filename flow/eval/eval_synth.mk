# The pinned synthesis, run by the evaluator on a submitted module (equiv.py): the module's golden RTL
# through the pinned Yosys with the pinned settings, the entry's own hardened blocks and the SRAM macros
# as black boxes (their timing models, which the evaluator derived itself). The entry's final netlist of the
# module must be equivalent to this output. Settings an entrant may not change: the RTL, the constraint
# file (its clock period steers synthesis), the frontend, and the hierarchy mode, which is 1 for a module
# that instantiates hardened blocks and 0 for a leaf block (as in the reference flow).
include $(dir $(lastword $(MAKEFILE_LIST)))eval.mk
export DESIGN_NAME = $(EVAL_SYNTH_NAME)
export DESIGN_NICKNAME = evalsynth_$(EVAL_SYNTH_NAME)
export VERILOG_FILES = $(sort $(wildcard $(CB)/design/rtl/*.sv)) $(CB)/design/srams/_wrappers/mem_ext.v $(CB)/design/srams/_wrappers/mem_0_ext_banked.v
export SYNTH_HDL_FRONTEND = slang
export ADDITIONAL_LIBS += $(EVAL_SYNTH_LIBS)
export SYNTH_HIERARCHICAL = $(EVAL_SYNTH_HIER)
export ADDITIONAL_LEFS += $(EVAL_SYNTH_LEFS)
