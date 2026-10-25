set_layer_rc -layer M1 -resistance 7.04175E-02 -capacitance 1e-10
set_layer_rc -layer M2 -resistance 2.97126E-02 -capacitance 1.84542E-01
set_layer_rc -layer M3 -resistance 3.12872E-02 -capacitance 1.53955E-01
set_layer_rc -layer M4 -resistance 1.80365E-02 -capacitance 1.89434E-01
set_layer_rc -layer M5 -resistance 1.89936E-02 -capacitance 1.71593E-01
set_layer_rc -layer M6 -resistance 1.18797E-02 -capacitance 1.76146E-01
set_layer_rc -layer M7 -resistance 1.25097E-02 -capacitance 1.47030E-01

set_wire_rc -signal -resistance 3.23151E-02 -capacitance 1.73323E-01
set_wire_rc -clock -resistance 5.13971E-02 -capacitance 1.44549E-01

set_layer_rc -via V1 -resistance 1.72E-02
set_layer_rc -via V2 -resistance 1.72E-02
set_layer_rc -via V3 -resistance 1.72E-02
set_layer_rc -via V4 -resistance 1.18E-02
set_layer_rc -via V5 -resistance 1.18E-02
set_layer_rc -via V6 -resistance 8.20E-03
set_layer_rc -via V7 -resistance 8.20E-03
set_layer_rc -via V8 -resistance 6.30E-03

# --- Chipbase pinned values for M8 and M9 --------------------------------------------------
# Stock ORFS stops at M7. ASAP7 defines M8/M9 as real 80 nm pitch, 40 nm wide layers. Resistance
# is scaled from the calibrated M7 by cross-section (M7 32 x 64 nm vs M8/M9 40 x 80 nm) with a
# margin for the copper resistivity floor; capacitance is set near M7. These are the judge's
# values for any entry that routes on M8 or M9.
set_layer_rc -layer M8 -resistance 9.00E-03 -capacitance 1.45000E-01
set_layer_rc -layer M9 -resistance 9.00E-03 -capacitance 1.45000E-01
