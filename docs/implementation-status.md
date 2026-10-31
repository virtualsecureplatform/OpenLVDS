# Implementation status

The SKY130 macro implementation and reproducible build flows are present.
**The link is still in electrical bring-up and is not released.**

The pulse-area comparison milestone on 2026-10-29 is described at the end of
this document and in [the experiment workflow](dll-experiments.md). Its circuits
remain separate from the active PHY. Current bring-up evidence is recorded below.

The preceding canonical checks on 2026-10-28 include:

- RTL: 2,373,576 bits across 54 cases: 1,186,788 each for generic RTL and native
  SKY130 serializer cells, plus DLL control and generic/native PHY assembly.
- Schematic characterization previously passed all 60 cases. The revised receiver
  passes 15 static and 15 rate canonical cases at tt/ff/ss/fs/sf and 0, 25, and
  40 °C.
- Extracted driver: all 15 corners pass, including edge identity, polarity,
  amplitude, common mode, and propagation measurements.
- The compact receiver passes all 15 full-RC static and 15 full-RC rate corners. The rate test uses 840 Mb/s,
  250 mV differential input, and 100 fF output load.
- Physical checks: all five analog macros and three digital macros pass
  DRC/LVS. The integrated phase-qualifier DLL and PFD pass fresh physical
  checks and exact RC extraction. All five analog networks pass independent
  RC connectivity audits. Electrical qualification of the new DLL is pending.
- The completed steering-only DLL baseline passes its 1500 ns exact-RC nominal
  test at tt, 25 °C, 400 MHz, and 50% duty. The integrated phase-qualifier
  revision is now undergoing its own nominal test.
- Unit tests: 72 pass, including stale-evidence rejection, parallel input timing,
  link measurement boundaries, driver latency/polarity, physical port policy, and RC trace provenance.

Extracted DLL qualification and the complete full/approximate RC
comparison remain outstanding. Completed driver cases are recorded individually
under `build/analog_extracted/`. No approximate network is qualified until the
complete comparison certificate passes. Each reusable reference now carries hashes
of its simulator provenance, requirements, circuit, fixture, waveform, and producer
snapshot. Unattested legacy traces cannot qualify or resume a reference. Fresh
receiver, delay-line, TX, and RX comparison pairs pass; driver and DLL pairs are
still required for a complete certificate.

An archived partial extracted DLL trace showed approximately 508 ps quarter-cycle
delay and 310 ps detector-input error. Automatically inserted clock-delay buffers
were found on the phase detector's inputs and outputs. All three digital macros
have been rebuilt without those cells and pass physical checks; the phase
detector additionally preserves direct clock and UP/DN connections. With equal
45 fF loads, its isolated extracted output pulses now reach approximately 1.82 V,
versus 1.29–1.35 V before the correction. The completed extracted DLL run with the rebuilt PFD fails: quarter-cycle delay
  spans 814–845 ps and detector-input error reaches 405 ps. The isolated pulse
  test is diagnostic evidence. The new schematic response bench also shows the
  existing indicator staying low at ±150 and ±300 ps error; a low indicator
  alone cannot establish lock.

A short extracted link diagnostic with late parallel input changes shows payload
ordering errors. The earlier receiver clock-load problem was corrected and
checked independently.
The bench now launches parallel data according to the existing physical input
constraints. An isolated transistor-level TX diagnostic using the unqualified
approximate RC view and 80 fF output loads decodes all 64 payload bits correctly;
a subsequent 32-bit end-to-end diagnostic decodes every payload bit with valid
voltage levels, but measures approximately 35 ps setup margin against the
unchanged 200 ps requirement. That diagnostic uses a
0.9 V logic threshold: three sampled highs remain below 1.44 V at its selected
sample time, so it does not establish valid CMOS levels or output timing margin.
Short diagnostic runs use less training than
the 256-cycle PHY startup and cannot establish release performance.

The 4096-bit nominal electrical link and complete 45-case extracted regression
have not passed. The current release checker therefore reports failure. Read
`build/release/status.json` and the source-checked tables in
`build/characterization/` for machine-readable evidence. Missing results are
failures, and behavioral or diagnostic results cannot replace them.

The deliverable is a reusable macro library with RTL integration. It does not
include pads, ESD, a complete assembled PHY GDS, mismatch/yield qualification,
or a monolithic PLL/DLL/link noise simulation. Supply voltages remain fixed;
no voltage sweep is included.

The standalone phase-error response bench is available as:

```sh
./scripts/env.sh --ngspice python3 scripts/verify_phase_detector.py --extracted
```

Add `--corners` for all five process corners at 0, 25, and 40 °C. The bench
applies 0, ±50, ±150, and ±300 ps detector-input offsets at fixed supplies,
with the real DLL analog loading and a 20 fF indicator load. It checks that
the indicator stays low at small offsets and reaches a valid high for large
errors; a stuck-low flag cannot pass. It is a standalone diagnostic and does
not replace DLL acquisition or complete link qualification.

The revised receiver uses 10 µm input-mirror devices and a 64 µm decision tail.
Each decision input now has 2 kΩ in parallel with 4 kΩ to VREF, and 4 kΩ to
ground. Its Thevenin equivalent remains 1 kΩ, with a 0.9 V bias derived from the
external 1.2 V reference. This restores decision-stage headroom across the static
corner matrix. A 32-bit replay using this schematic receiver and extracted
capture logic gives zero errors, approximately 174 ps setup margin and 268 ps
hold margin. The setup result still fails the 200 ps target; it is an intermediate
improvement over the preceding approximately 35 ps result. End-to-end timing checks remain required.

Receiver routing now uses 5 µm total inter-cell clearance, local internal buses,
and local signal-pin escapes. Its width drops from 985 to 607 µm. Extracted
coupling-capacitance sums incident on Q decrease from 130 to 23 fF, PP from
121 to 68 fF, PN from 128 to 72 fF, and CO from 43 to 24 fF. These are network
capacitance sums, not independent grounded loads. Compact-layout PVT passes all 30 cases. Its full/approximate RC comparison passes
with at most 1.23 ps edge error and 0.15 mV plateau error. Whole-link diagnostics
remain in progress.

Analog LVS now compares fixed-width poly resistors individually. The PDK's
mixed series/parallel reduction gave an extraction-order-dependent property
error for an unchanged ladder. Disabling those reductions preserves each
connection and resistor length check: the compact layout passes, and a
controlled doubled-length resistor is rejected. Property errors remain fatal.

The preceding native XOR transmitter passed DRC/LVS and timing (7 ps setup
slack, 88 ps hold slack), but its 32-bit extracted-channel payload has only
140 ps setup and 126 ps hold margin, despite zero bit errors. Data common mode
also dips to 1.12265 V, below 1.125 V. These measurements are from the completed
payload window of a still-running diagnostic transient, not release evidence.
Internal traces show alternating clock launch delays of 786–999 ps and data
launch delays of 750–987 ps. Pattern-dependent encoded-state delay is too large.

The revised transmitter uses three plain sampling registers and a PH90-selected
mux for data, with an identical PH0-selected constant-input clock replica.
Both input bits still belong to the same rising-edge capture. Generic and
native RTL pass the full 54-case regression and functional PHY assembly.
The mux revision passes physical DRC/LVS and timing, with 58 ps worst setup
slack and 87 ps hold slack. Native cell connections pass the independent
physical policy. Fresh extracted electrical checks remain required.

The compact receiver with the preceding transmitter revision completes a
32-bit extracted-channel diagnostic with zero errors, 202 ps setup margin,
and 257 ps hold margin. That run uses shortened training and no injected
jitter; it does not qualify the revised native transmitter or the link matrix.
The preceding XOR transmitter's full/approximate RC comparison passes, with
maximum edge error 3.31 ps and plateau error 2.29 mV. That comparison does not qualify the new mux transmitter; the complete certificate remains outstanding.

DLL experiments with stronger charge-pump branches reduce settled nominal
feedback error to 67 ps (8 times the original current) and 48 ps (16 times).
However, the respective control-copy errors reach 80 and 154 mV, exceeding the
50 mV limit. Neither candidate is promoted. A stronger control buffer is under
test. The original phase-error flag also remains inadequate: raw-clock window
prototypes improve sensitivity, but broader process, temperature, and slew
checks expose missed faults or invalid pulse cadence. These prototypes remain
separate from the canonical analog and PFD implementations.

The mux transmitter's fresh full/approximate RC pair passes with a maximum
edge difference of 1.72 ps and plateau difference of 9.18 mV. Receiver,
delay-line, and capture-core comparisons also pass; driver and DLL fixtures
are still needed for the complete six-fixture certificate.

The phase-selected mux completes its 32-bit diagnostic payload with zero errors,
349 ps setup margin, 476 ps hold margin, and passing electrical levels. The
transient is still running through its final idle interval. The separate
100 mV averaged phase-detector prototype passes all 70 extreme-PVT/slew cases.
The reusable `lvds_phase_qualifier` analog subcircuit now implements its matched
clock-input filters, error averaging, matched-unit reference, and comparator.
It is not yet connected into the canonical DLL; integrated PVT and extracted
qualification remain required.

The stronger pump/buffer prototype passes all 15 schematic PVT cases, but its
600 ns patched-extraction diagnostic fails feedback error: 110 ps for the
8-times pump and 117 ps for the 16-times pump. Correctly measured control-copy
errors are 17 and 33 mV, respectively. The original diagnostic producer used
the BAD column for its copy-error field; the retained waveform headers and
independent `copy_audit.json` files identify and correct that analysis error.
Neither candidate is qualified. The 420 MHz, 55% duty delayed-enable retry
finishes successfully, with 37 ps feedback error and 14 mV copy error.

The first DLL repair now uses 32 reference units per pump branch, complementary
steering gates, the 8-times follower with 2 pF output storage, and matched native
buf_8 PFD output drivers. The physical policy retains direct reference clocks
and explicitly verifies both drivers and buffered reset coincidence. The phase
qualifier component is preserved for the next integration step. This source
revision still requires its own physical and extracted qualification.

The averaged qualifier is now connected in the canonical DLL and native PFD.
The analog macro has 22 terminals and the PFD has 12; the public DLL core and
PHY ports are unchanged. Sense inputs remain independently drivable in the
phase-fault bench. The reference inverter now has 16/8 µm drive, and PH270/FB
carry matched passive sensing loads. The physical policy verifies each native
qualifier cell and connection, including the two-buffer window, independently
of the UP/DN steering paths. Full RTL regression passes 2,373,576 bits in 54
cases, and all 72 unit tests pass. The regenerated analog DLL passes DRC
(zero errors), LVS, exact RC extraction with the expected 22 ports, and an
independent RC connectivity audit. The native PFD also passes DRC/LVS and
its explicit cell-path policy, and its 12-terminal exact RC extraction assembles
with the DLL by terminal name. Complete extracted nominal, PVT, phase-fault,
clock-duty, RC-comparison, and link release evidence remains outstanding.
Earlier prototype results do not qualify this integrated source.

The integrated DLL has 329 devices, zero DRC errors, and exact RC network hash
`00bdf5fce102`; the PFD exact network hash is `2dce4c008a2d`. The fresh
0.1 ps TICER models remain unqualified until comparison with these exact
networks completes. The release checker accepts the current physical and RTL
evidence and rejects missing phase-fault, DLL, and complete link qualification.
A queued nominal test preserves the preceding steering-only baseline and starts
the integrated full-RC test only after that baseline completes successfully.

The completed stressed 32-bit TICER approximate-RC diagnostic at 420 MHz, 45% duty, +100 ps data
skew, and 100 ps peak-to-peak jitter has zero bit errors but fails the current
margin and dynamic transmitter-level checks: setup margin −47 ps and minimum
loaded data/clock eye-center amplitudes 179/225 mV. Receiver sample amplitude
remains above 100 mV. These are diagnostics with ideal DLL phases and shortened
training, not a release result. The captured-waveform driver replay remains
in progress; output-level and aperture requirements have not been relaxed.

The full/fast DLL fixture now includes the same 40 fF PH0 and PH90 launch
loads as the nominal electrical bench and delays enable by 200 ps after
precharge. The previous 20 fF PH90 fixture is not sufficient for the current
six-fixture certificate. All 72 unit tests pass in the pinned ngspice image.

Both hierarchical-schematic driver replays terminate before payload: the dense
replay fails at an ideal-source branch near 10.25 ns, and its bounded-waveform
retry fails at a MOS body node near 10.73 ns. They cannot establish a driver
bandwidth result. The replacement routing-isolation circuit keeps all 266
extracted device instances, removes only parasitic R/C, and passes an independent
LVS audit. Its full 110 ns replay completes with 32 checked bits and zero
word errors, but only 37 ps setup margin and 438 ps hold margin. Data eye-center
swing improves to 228 mV; clock ringing creates extra zero crossings and still
fails the loaded transmitter-eye check. Receiver decision voltage remains at
least 167 mV. This routing-only change fails the existing 200 ps margin and
250 mV transmitter requirements. A separate exact-RC driver replay is running
with the original approximate receiver/capture models. These mixed-model and
routing-isolation runs remain diagnostic and unqualified. The complete replay
analysis is retained in
`build/diagnostics/driver_stress_replay/routing_removed_driver/complete_analysis.json`.

An isolated source-terminated driver experiment is prepared in
`analog/experiments/source_terminated_driver.spice`. It doubles the output
mirrors and switches using parallel copies of the original devices, preserves
the input stage and 35 µA external reference, and adds a nominal 100 Ω source
shunt made from 22 PDK resistor units. The test circuit retains extracted
finger geometry and diffusion parameters; its LVS comparison against the
experimental schematic passes. A controlled transient is queued only if the
exact-driver replay confirms a swing failure with a complete, correctly decoded
payload and valid common mode. The PHY continues to instantiate the existing
driver. This experiment has no electrical or GDS qualification yet.

The steering-only repair completes its full 1500 ns exact-RC nominal transient.
Scoring 117 cycles in the settled window gives 43.53 ps maximum feedback error,
29.35 mV maximum control-copy error, and 687.43–687.70 ps quarter-cycle delay.
These meet the unchanged 100 ps feedback, 50 mV copy, and 625 ± 100 ps phase
limits. The run uses fixed 3.3/1.8 V supplies, a 1.2 V reference, a 35 µA sink,
and the pinned native ngspice engine at tt/25 °C. An independent audit verifies
file hashes, the completed waveform, engine and conditions, and recomputes all
settled metrics.

This is the preceding 16-terminal analog DLL / 9-terminal PFD circuit, with
exact network hashes `7cb9f30e214c` and `d2b3f284fdde`. Its archived evidence is
under `build/diagnostics/phase_integration/steering_baseline/`. Scope validation
accepts that evidence for its own circuit and rejects it for the integrated
22/12-terminal revision. The latter's fresh full-RC nominal transient has
started. Its complete nominal result, PVT/clock matrices, and phase-fault
reports remain required for release.

The current integrated 22/12-terminal DLL completes its full 1500 ns exact-RC
nominal test at tt/25 °C: feedback error 28.34 ps, control-copy error 29.92 mV,
quarter-cycle delay 666.73–666.96 ps, and maximum settled PHASE_BAD 0.624 mV.
All nominal gates pass. The same current extraction also passes tt/0 °C;
tt/40 °C is running in the sequential, fail-fast PVT queue. These are two of
the required 15 PVT cases. Extracted standalone phase-fault testing has started
in the second simulation slot; the full 105/70 fault matrices remain required.

The completed exact-driver replay reproduces the stressed swing failure with
zero errors over 32 bits: minimum data/clock eye-center amplitudes 179/224 mV
and setup margin −47.58 ps. The source-terminated, routing-free extracted-device
experiment also completes 32 bits with zero errors and passes electrical levels:
minimum data/clock amplitudes 281/259 mV and receiver decision voltage 247 mV.
Its setup margin is only 11.61 ps against the unchanged 200 ps target; hold
margin is 499.09 ps. It is not promoted to the PHY. Timing diagnosis and fresh
physical/PVT qualification are still needed; electrical success in this
mixed-model diagnostic cannot establish release.


## Pulse-area DLL comparison

The active PHY still uses the preceding DLL; the new circuits are isolated
experiments. The corrected, immutable architecture campaign is
`build/diagnostics/dll_architecture/6d99d42cf3eb5d31/`. The preceding campaign
`2c89de68294cda33` was stopped because its loop fixture duplicated the bias
generator already present in the DLL wrapper. No loop result from that fixture
is accepted. All prepared cases now check for exactly one reference generator.
The unchanged monitor waveforms were hash-checked and reanalyzed in the corrected
campaign; the affected loop and follower cases run afresh.

The monitor averages UP and DN independently, applies a signed window, and
checks for inactive/stuck PFD outputs. All 21 offset and six stuck-output
diagnostics pass at SS/0 °C, TT/25 °C and FF/0 °C with the captured PFD and
schematic monitor. This includes quiet 0/±50 ps and asserted ±150/±300 ps cases.
These results do not qualify a fresh extracted monitor.

Three NMOS-follower pump repairs and four averaged-PFD/current-mirror-OTA loops
are prepared. Completed loaded replay peaks are 48.72 mV for `cp_b1_c4` and
43.47 mV for `cp_b2_c2`, against the unchanged 50 mV limit. The comparison
supervisor prioritizes `cp_b2_c2` at SS/0 °C alongside the three `ota_w4_c8`
corners. Startup-only traces interrupted to make this comparison earlier are
archived within their task directories. On 2026-10-30 the user authorized two
additional concurrent simulations. The comparison now runs six transients,
adding `ota_w8_c8` at SS/0 °C and TT/25 °C while preserving the original four.

All 15 fixed-supply OTA characterization cases complete. Transconductance is
39.35–48.69 µS with the correct control direction; the largest equivalent input
offset is 14.51 mV over the characterized signal range. These cases fail the
prototype's 10 mV offset screen. They do not establish loop failure or passing
phase accuracy: complete acquisition, phase, ripple and stability checks remain
necessary. The largest measured thin-oxide signal-node magnitude is 1.4 V;
this limited signal check is not a general device-stress qualification.

The eight-terminal PFD, `ota_w4_c8` and `cp_b2_c4` analog layouts pass DRC,
strict LVS, exact RC extraction, and independent RC topology audits. Their
analog interface has 15 ports. Clock paths, pump controls and averaging inputs
remain within the control island; the window/reference bank occupies the quiet
island. Exact analog network hashes are `3502faf1b5c1` and `62713ea94c5a`;
the new PFD network is `11fa96b45bbb`. The assembled full-RC OTA circuit also
passes an operating-point-only parser/solver check. No transient qualification
is implied by that check.

The matched native `buf_4` serializer experiment passes 54 functional cases
(2,373,588 checked bits), DRC/LVS, positive timing slack, direct-output cell
policy, exact RC extraction and its independent audit. The initial routed retry
that inserted extra output buffers is preserved and rejected. The passing
direct-output network is `cdf6cbd8a901`; it is not promoted to the active PHY.

Native DLL qualification is prepared for both physical candidates, with 313
transients per candidate and prerequisites on its three-corner architecture
screen. It covers 15 PVT points, nine clock/duty conditions, the 105/70 phase
fault matrices, frequency endpoints, stuck outputs, frequency steps and clock
loss/rearm. Full/fast DLL comparisons include nominal and phase-fault fixtures.
An omitted pulse after the settled scoring window checks unwrapped delay
through every section. CTRL and VCOPY measurements bind actual storage-capacitor
terminals, whose names survive extraction and RC reduction. Every voltage
probe is checked before a case is queued. These DLL comparisons do not replace
the complete six-fixture RC certificate.

Full-RC receiver aperture characterization is queued behind the same simulator
lease. It has 480 setup/hold boundaries across 15 PVT points, both capture edges,
both data polarities and all 20/200 ps clock/data slew combinations. It observes
the published pair and valid output, bisects to 5 ps, adds 20 ps guard and rounds
up to 10 ps. Link release evidence now requires a complete current table and
rechecks its boundary witnesses. The extra 200 ps link margin is unchanged.
Legacy 200/80 ps aperture estimates are permitted only for diagnostic runs.

The completed architecture comparison selects W8/C4 for continued OTA work:
SS/0 °C, TT/25 °C and FF/0 °C pass the schematic loop screen. Its new layout
passes DRC, strict LVS, exact RC extraction and the independent RC topology audit.
The exact network is `0f0c41cbc75c`; its 15 analog ports are verified. Native
qualification `d4d687cf4e0b5e1e` passes the initial SS/0 °C 0/+50 ps monitor
cases but fails SS/0 °C ±150/±300 ps and TT/25 °C +150 ps. The old coordinator
is draining already submitted cases; new dispatch has been retired.
Its 336-case manifest holds the full matrix until the 24-case native screen and
measured stability gates pass. The active release remains unchanged.

The controller now requires 615 acquisition cycles after a phase fault, alongside
the existing 32-cycle precharge and 64-good-cycle counters. The complete RTL
regression passes 54 cases and 2,373,588 checked bits. The candidate qualifier
now covers 27 clock/duty points across TT/25 °C, SS/0 °C and FF/0 °C and
frequency-step/rearm cases at each of those three corners.

The stability runner measures native G/Y with the clock held low and high,
PFD pulse-area gain at ±50 ps, and delay sensitivity at CTRL ±10 mV. It tests
the two clock states and their averaged model with one-cycle latency, then
compares predicted amplitude and settling against native 400→390/410 MHz
steps. Expansion requires at least 60° phase margin and 6 dB gain margin and
at most 25% model disagreement. The AC backend and schematic OTA
instrumentation smoke tests pass; extracted W8/C4 stability results are pending.

An isolated bundle assembler captures the audited DLL/PFD and buf_4 serializer
with the current driver, receiver and bias. It checks public TX terminals and
proves that DLL/TX replacement leaves the other instantiated circuit closures
unchanged. A smoke assembly with the previously extracted W4/C8 circuit passes;
this is tool validation, not W8/C4 qualification. The automatic workflow stages
W8/C4 only after its native electrical and all-PVT stability gates pass.

The staged bundle now connects to the six-fixture RC validator, the stressed
32-bit diagnostic and the full 45-case regression. Its certificate and matrix
summary stay within the bundle directory. The OpenPLL mean duty is captured
as a native TT DLL qualification input; the link phase reader checks the matching
native trace instead of consulting active-circuit characterization. The automatic
workflow waits for a complete RX table before the non-diagnostic link matrix.
These tools have not yet produced passing W8/C4 bundle results.

W8 OTA signal characterization `c1c03f8e7a5e8dd9` is queued for two shared
simulator slots. It covers all 15 PVT points, input common modes 0.32–0.75 V
(including FF's observed 0.34 V), and CTRL 0.82–1.09 V, with unchanged fixed
supplies and bias. It is a schematic diagnostic; it does not replace extracted
loop qualification or general device-stress verification.

Native limiting-corner recovery and readiness replay runners are implemented
and connected before staged PHY validation. Recovery includes the lowest phase
margin, lowest gain margin and slowest modeled settling corners. Readiness uses
the actual controller RTL and native all-PVT step waveforms; added 4700 ns loss
fixtures allow lock both before and after a 2200–2300 ns clock interruption.
The backend passes actual RTL tests for settled lock, BAD-fault requalification,
late clock-loss/rearm and rejection of unsafe native phase with a quiet BAD flag.
Production W8/C4 recovery/readiness evidence remains pending.

A further exact RC profile is captured in `dll_layout/schur_00f7e3a63d66eb41`.
Degree-8 algebraic elimination reduces 95,814 resistor-graph nodes and 280,285
resistors to 10,484 nodes and 36,372 resistors. Protected nodes include every
capacitor/device terminal and public port. The new network `fae3e67dab9c` passes
an independent topology audit and four complete-graph sparse numerical witnesses
at all 7,431 protected resistor terminals. Maximum current difference is
1.137e-12 A; relative solve residuals are below 2.84e-16. Capacitor, device and
port statements are unchanged.

Native equivalence benchmark `rc_equivalence/ebcffa26f586eebf` passes both
SS/0 °C 0/+50 ps comparisons. Maximum crossing/plateau differences are
0.858 ps/0.232 mV; native execution is 3.75–3.76× faster, excluding slot wait.
The profile is eligible for fresh native qualification. These two quiet-offset
comparisons do not qualify the electrical matrix or correct monitor failures.

The native SS/0 °C +150 ps BAD output remains low through 160 ns. At +300 ps,
BAD returns high only at 147.6 ns (+300 ps) and 137.5 ns (−300 ps),
too late for the unchanged 120–160 ns fault
window. The filtered UP−DN difference remains approximately 89/161 mV,
respectively. SS/0 °C −150 ps and TT/25 °C +150 ps also miss the fault.
Exact-name extracted capacitance sums incident on PA/PB are 530/561 fF;
comparator XPOS O/OB have 223/221 fF. These are network capacitance sums,
including coupling. Slow readout under these loads is a hypothesis, not yet a
confirmed cause; distributed resistance, device junctions and bias remain
possible contributors.

Monitor diagnostic `monitor_repair/9a9a9300e6682a18` uses two shared
slots. The loaded-baseline SS/0 °C +150 ps control reproduces the missed
fault (filtered error 89.51 mV, BAD below 4.5 µV). The repaired loaded +150 ps
case passes: BAD returns high at 88.271 ns and stays near 1.8 V throughout
120–160 ns; comparator O averages 1.127 V versus 0.643 V in the control.
Remaining controls and repaired offsets are pending. Its repaired source divides monitor resistor lengths by four, replicates
the two averaging capacitors four times and increases comparator branch widths
fourfold. Nominal divider ratios and averaging R×C are preserved. Explicit
unloaded/loaded baseline controls test the capacitive-loading hypothesis, then
all seven offsets run at SS/0 °C, TT/25 °C and FF/0 °C. The proxy retains native
extracted PFD/bias, but omits analog distributed resistance and device junction
geometry; it cannot replace fresh layout and native qualification. The held
unchanged-profile campaign `4f6072867e73460a` and advancement service remain
inactive while this failure is diagnosed. RX characterization continues.

A source-specific three-corner screen producer now accepts the exact repaired
source, captures native-finger schematic analog/delay devices with extracted
PFD/bias, and binds its fixtures, source and producer hashes. Its prepared screen
`dll_architecture/d8b9a06ef038cd76` is queued on one shared simulator slot. The repaired layout
`dll_layout/88342cdbe6c80ac2` passes DRC (zero errors), strict LVS, exact RC
extraction and the independent topology audit. It has 518 devices and 15
verified public ports. Further exact degree-8 reduction
`schur_e4b240c20b314964` retains 53,508 resistors and 14,631 resistor-graph
nodes, with four passing sparse witnesses at 10,035 protected terminals
(maximum current difference 3.91e-13 A). The new native qualification
`0cc06862af2fae63` is prepared but not dispatched. The first loaded +150 ps proxy passes; full native electrical qualification
remains pending. Advancement accepts an explicit
matching screen; it cannot reuse the old architecture evidence for new source
bytes. A hold survives restarting the same candidate; selecting a new candidate
clears only the previous OTA hold/stage, preserving the RX and CP settings.

`ota_operating_points.py` implements correlated operating-point characterization
from native loop and all-PVT step traces. Each observed UF/DF common mode and
CTRL point receives ±20 mV/±10 mV guards, with finite-difference gain at zero
and actual differential input, offset and thin-device terminal checks. It keeps
corner/condition correlations instead of combining unrelated extremes. This
production gate has not run and requires passing native/model evidence first.

The current host test run completes 184 tests: 179 pass and five skip for the
container/analysis backends checked separately in earlier runs. Native W8/C4
qualification, the complete RX aperture table, operating-point characterization,
readiness replay, limiting-corner recovery, six-fixture RC certification and the
full 45-case link regression remain outstanding. No candidate is released.


The staged release checker now accepts a bundle plus all-PVT model, recovery,
readiness and correlated OTA reports. It reconstructs the audited DLL and PHY
libraries, rechecks all native DLL cases and full/fast waveform comparisons,
then checks the unchanged analog/RTL/OpenPLL evidence and the full link matrix.
Source reuse is limited by circuit closure; obsolete CP/copy and raw-clock
qualifier gates are replaced by native OTA/PFD-area/readiness evidence for this
path. All 336 current native fixtures reconstruct exactly under the pinned
container. A missing-bundle negative control fails with a saved isolated report;
there is no positive production release result. Advancement runs this gate after
the matrix. Exact-byte promotion tooling is implemented below; electrical
qualification and a passing production release remain required.


Candidate RTL assembly now uses the matching 15-port analog macro and 8-port
PFD while preserving the external DLL/TX/RX interfaces and 615-cycle controller.
Bundle `65f795152adf2bfb` passes its isolated full 54-case regression with
2,373,588 checked bits, controller, generic/native PHY tests and physical-interface
elaboration. Its source/probe wiring agrees with the characterized SPICE core.
The canonical development wrapper remains unchanged. Staging now keeps the
exact shared bias in both views before applying the protected-circuit checks.
The six-fixture certificate and electrical qualification remain pending.


Local release promotion is now implemented. It repeats the staged checker,
seals exact full/fast library bytes, the eight GDS/LEF macro pairs, the matching
candidate schematic/RTL sources and evidence summaries, then atomically publishes
`build/release/current.json`. The prior pointer is retained on gate or copy
failure. Unit tests cover stale/failed input, mandatory reanalysis, byte copying,
immutable-package rejection and LEF pin mismatches; all eight real macro LEF
interfaces match the corresponding extraction port sets. No production package
or current release pointer has been published. The workflow invokes promotion
only after candidate RTL, native electrical/model/recovery/readiness/OTA gates,
six-fixture RC certification and all 45 link cases pass.
