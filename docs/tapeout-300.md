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

## Fresh implementation campaigns

- `dcc_xyce_300_v1/b12dc12b493548ab`: 48 native source cases; baseline/INV8,
  both unequal-slew directions and matched controls, 40/60% duty, three numerical
  profiles. Each variant binds its own full native inventory (136/144 MOS).
  First baseline half-cycle error is 53.685 ps, reproducing the timing failure.
  Initial native terminal screens also exceed 1.95 V; investigate before admission.
- `model_switching_xyce_300_v1/23adadf823af90c0`: interrupted after detecting an
  incorrect three-terminal generic-poly fixture. Xyce rejected it; preserve logs.
- `model_switching_xyce_300_v2/763096f288bc9069`: corrected two-terminal generic
  poly, paired Xyce/ngspice fixed-supply representative MOS/poly/MIM controls at
  all 15 PVT. Input waveforms exercise switching; supplies remain fixed.
- `dcc_ng_reference_300_v1/e2f8b3c2c305dc26`: four strict native reference cases
  for cross-engine investigation of unequal-slew timing and internal stress.

Each campaign uses at most two workers and shares the six-slot dispatcher.
A running campaign is never release evidence. Timeout/error/partial results are
retained and cannot pass. Numerical refinement and model comparison are distinct
from physical/source admission.

## Numerical diagnosis and early repair evidence

The strict PWL model matrix v2 is interrupted and superseded. In the 14-case
`model_numerics_300_v1/4dfa5bf48f9c37db` isolation, all four tight nonlinear Xyce
PWL controls failed near the first ramp, even with time-integration ABSTOL relaxed
from 1e-12 to 1e-8. The baseline numerical PWL control passed. All seven smooth
controls, including strict Xyce and ngspice, completed. Smooth controls retain
50% edge epochs and 20/250 ps 10–90 slews, with fixed supply rails. This diagnoses
stimulus/numerical sensitivity; it does not establish a simulator source bug.

`model_switching_xyce_300_v3/6b72fd5c248c35f6` completed all 30 runs, giving 15
paired PVT comparisons. Representative MOS midpoint-crossing differences are
below 0.159 ps, and MIM differences below 0.003 ps. This limited geometry/load
screen does not resolve the full model qualification. In particular, generic
poly DC output differs by up to 19.44 mV and high-poly by 1.485 mV, so passive
model semantics need investigation before admission. Peak pointwise voltage
error is distinct from settled error and edge displacement.

The complete strict ngspice 310 MHz/SF40/60% unequal-slew control shows INV8
reduces half-cycle error from 53.874 ps to 2.189 ps. Reverse-slew strict ngspice
controls failed at input-source breakpoints and remain failures. Complete native
Xyce controls independently reproduce the timing improvement. Both source-only
versions fail the current terminal screen. The separate native diagnosis
`build/reports/dcc_stress_300_v1/27a117cdad8754ca` identifies up to 2.334 V drain-to-
source and roughly 2.032 V gate-related differences in standard-cell internal
nodes. No stress limit was relaxed. Source-only diffusion-node bootstrapping must
be compared with actual extracted cell/routing capacitance before adding shunts
or replacing flop architecture.

`dcc_inv8_physical_300_v1/c88cfb35d76fa88f` is a fresh diagnostic routed INV8
candidate. It preserves the pulse/hold/toggle topology, checks INV8 explicitly,
uses 310 MHz constraints without the old broad input/output false path, and
requires fresh DRC/LVS/antenna/topology and full RC extraction. It deliberately
does not claim source-matrix, device-stress, STA or PHY admission. A physical
candidate is needed to distinguish missing source interconnect capacitance from
a stress problem that requires a circuit change.

## Routed candidate and passive-model compatibility

The INV8 physical diagnostic completed with zero final route/Magic/KLayout DRC,
LVS and antenna violations. Its topology retained the exact INV8 pulse/hold/toggle
island; extracted RC passed strict topology/property comparison. GDS SHA256 is
`6944e60df74f8334c7e170eaf815483e22492e09b704b70bab95f61e0122d858`.
The full extraction has 6956 resistors and 773 capacitors; positive-conductance
reduction retains 2328 resistors. Reduction timing equivalence and native stress
remain separate electrical requirements.

PEX preflight captures v1/v2 were never simulated: each rejected an observation
alias absent from this routed netlist. V3 uses the actual second hold gate contact
`second_hold.A2.t2` for the second reset observation. The fresh native campaign
is `dcc_inv8_pex_300_v3/723d0d1965d3f452`, with full/reduced RC for both unequal-
slew directions and a matched control. The native input, reset, output and all
MOS terminal samples remain actual circuit observations.

Xyce's generic-poly warnings identify ignored TC1R, TC2R and DW parameters.
Its NARROW semantics also shorten length, so renaming DW cannot reproduce the
PDK resistor. [Xyce resistor implementation](https://github.com/Xyce/Xyce/blob/master/src/DeviceModelPKG/OpenModels/N_DEV_Resistor.C)
provides the supported parameters and geometry equation. Importantly, the pinned
ngspice **42** local `src/spicelib/devices/res/restemp.c` applies **2*DW** to width;
current upstream source must not be substituted for that pinned behavior.

The first explicit adapter (v4 matrix `714be1c666dfb942`) left a 9.287 mV TT0
DC mismatch at w=0.5/l=1. The parameter diagnosis
`poly_parameters_300_v1/90fe835bfb4933d2` independently reads the same rp1, DW
components, temperature coefficients and temperature in both engines, while the
native ngspice nominal resistor is 108.559 ohm. The corrected isolated adapter
`generic_poly_xyce_300_v2.py` implements pinned ngspice 42 geometry and explicit
temperature correction. V5 matrix `291b4176c56acf59` compares three geometries,
including actual w=0.48/l=0.5 tie resistors, over 15 PVT. Neither adapter edits the
PDK or establishes noise/statistical qualification. High-poly's separate
1.1–1.5 mV mismatch remains open.

Release receipts now also require the same `candidate.json` digest, frozen
source/tool receipt hashes, matching PDK/contract, and published-view manifest.
The Liberty inventory requires distinct files tagged with all 15 process/temperature
points. No candidate exists yet; signoff deliberately remains closed.
