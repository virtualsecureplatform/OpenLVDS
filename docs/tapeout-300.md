# 300 MHz macro implementation and release

The deliverables are separate `openlvds_tx_300` and `openlvds_rx_300` hard macros.
OpenPLL, buffered 1.2 V VREF, IREF sinks, pads/ESD, and package are external.
Startup calibration, receiver training/deskew, freeze, and fault recovery are
required. Manual codes are test overrides, disabled during payload operation.
There is no CDR or background tracking. Robustness takes priority; select passing
implementations by area, then power. No hard area/power limits are imposed.

`clocking_300mhz.json` remains the canonical electrical policy: 290/300/310 MHz,
600 Mb/s nominal DDR, 40/50/60 percent duty, five process corners, temperatures
0/25/40 C, fixed 3.3/1.8 V supplies, and minimum 200 ps sampling margin.
OpenPLL stays on main at the existing pin. Legacy 400 MHz contracts are retained.

## Implementation sequence

1. Pin stock Xyce 7.10/KLU, shared libraries, models and numerical settings.
   Qualify actual MOS/passive/diode models; resolve substitution and clamping
   against measurements rather than hiding warnings. Refine critical edges to
   within 1 ps and settled voltages to within 1 mV. Subtract characterized model
   and numerical uncertainty from timing margins. Certify resistor-only reduction
   against complete full RC while preserving nonlinear/capacitive endpoints.
2. Reproduce the unequal-slew DCC failure and evaluate the INV8 output repair.
   Complete the loaded dual-contact TG/control repair and four-section DLL legal
   code closure over 15 PVT. Require monotonic legal codes, gap <=20 ps, overlap,
   period error <=20 ps and quadrature/half-cycle error <=50 ps after uncertainty.
   Restructure fixed delay paths if their loaded range cannot close.
3. Requalify analog driver/bias/receiver, common-mode stability, references,
   restart, aperture, device stress and statistically supported offset/mismatch.
   Assemble actual analog blocks, code ROM, v3 controllers, DDR and clock routes.
   Export parallel clocks, management reset/enable/train/readiness/fault status,
   and serial test/status. Keep backend trial and settling signals internal.
4. Harden both complete macros, preserving matched clock/detector structures.
   Close DRC/LVS, antenna/density/ERC, well/tap, rails and references; extract a
   fresh shared final RC view. Check CDC/reset, atomic updates and equivalence.
5. Qualify component boundaries, calibration epochs, rotations, timeouts, stop
   high/low and recovery. Run the full behavioral PVT/frequency/duty/skew matrix
   with jitter and >=1 million bits; extracted factored 45-case matrix plus worst
   joint points, 4096 nominal/512 corner bits and two measured OpenPLL traces.
   Use measured bounded models only for large control campaigns. Native boundary
   and link tests require complete raw output and actual automatic readiness.
6. Generate GDS/LEF/CDL/SPICE, functional and black-box Verilog, 15 PVT Liberty,
   constraints, electrical/power tables and integration/test guides. Validate a
   clean host using only published views. Bind all evidence to frozen sources,
   PDK, tools, solver and final macro bytes. Public PDK handoff does not establish
   host/foundry acceptance or silicon BER.

## Current executable infrastructure

`qualification_300.json` lists release gates and evidence receipts separately
from the legacy analog DLL/OTA release. Each passing receipt must bind the
contract, complete checked evidence, and hashes of all relevant files. Native
campaign reports are not automatically promoted to passing release receipts.
`make qualify-300` inventories missing evidence; it does not qualify circuits.
`make signoff-300` and `make release-300` fail when any gate or published view is
missing. The checker is an evidence inventory; campaign-specific acceptance and
final-view validation must be implemented before receipts are admitted.

New campaigns use `scripts/xyce_profile_300.py`; historical hashed helpers remain
unchanged. Runtime selection is explicit and rejects a changed executable.
Baseline/refined/strict settings are candidates, not qualified timing profiles.

## Completed backend evidence

All nine cases in `openpll_xyce_benchmark_300_v1/dc5c16e8fbe6f061` completed.
The quiet strict-reference case took 361.6 s with ngspice and 8.9 s with stock
Xyce; the active 300 MHz case took 617.1 s and 783.9 s respectively. Modified
UMFPACK took 1038.3 s on the active case. Stock Xyce is selected within Xyce;
there is no general speedup claim. Active edge displacement reached 8.215 ps;
its ngspice reference used relaxed ABSTOL=1e-9. BSIM4 4.5-to-4.6.1 substitution
and parameter clamps remain open model-compatibility issues. No PHY is qualified.
