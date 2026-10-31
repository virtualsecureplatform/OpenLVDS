# Implementation status

The SKY130 macro implementation and reproducible build flows are present.
**The link is still in electrical bring-up and is not released.**


Current bring-up evidence on 2026-10-31:

- Local comparator routing passes native SS/0 °C 0 and ±150 ps monitor tests
  with the preceding PFD (`c47b7dc98d92327b`). These results do not qualify the
  combined fast-reset PFD candidate.
- The preceding PFD and an internal-Q-reset physical variant give the wrong
  correction sign at −850 ps. The single-AOI reset physical PFD passes all
  three native −850/+850/0 ps capture controls, as well as DRC/LVS, extraction
  and the independent RC audit (`6562211b6d43fb89`).
- Three source-matched SS/TT/FF architecture loops are running
  (`0ca8225b328ecaa1`). Combined native candidate `1d201e9ed2f89f56` has 336
  prepared fixtures and is running the first SS/0 °C 0/±150 ps static probes.
- The frozen RX aperture campaign completes 480 conditions: 356 pass, 124 fail.
  All failed +800 ps endpoints have high VALID but illegal public data levels.
  Native internal publication probes and matched external-load controls are
  queued (`rx_publication/dd89f11b1af99f29`). The failed table cannot qualify RX.
- Full DLL/PVT/model/recovery/readiness/operating-point evidence, a passing RX
  aperture table, the six-fixture certificate and full link matrix remain required.


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
cases but fails SS/0 °C ±150/±300 ps and TT/25 °C ±150 ps. The old coordinator
has finished draining submitted cases and is retired; no old-campaign worker remains.
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
`0cc06862af2fae63` has completed its early SS/0 °C +150 ps probe and fails:
BAD never reasserts through 160 ns. The first loaded +150 ps proxy passes;
the difference requires further native diagnosis before full dispatch. Advancement accepts an explicit
matching screen; it cannot reuse the old architecture evidence for new source
bytes. A hold survives restarting the same candidate; selecting a new candidate
clears only the previous OTA hold/stage, preserving the RX and CP settings.

`ota_operating_points.py` implements correlated operating-point characterization
from native loop and all-PVT step traces. Each observed UF/DF common mode and
CTRL point receives ±20 mV/±10 mV guards, with finite-difference gain at zero
and actual differential input, offset and thin-device terminal checks. It keeps
corner/condition correlations instead of combining unrelated extremes. This
production gate has not run and requires passing native/model evidence first.

The current host test run completes 214 tests: 209 pass and five skip for the
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


A further exact degree-12 performance candidate, `schur_5dc0fd57ddac9cbc`,
passes topology audit and four numerical witnesses. It reduces the repaired
resistor graph to 11,826 nodes and 51,305 resistors, versus 14,631/53,508 for
degree eight. Every capacitor/device/port statement is preserved. Maximum
witness current difference is 4.41e-13 A. Source matching and unchanged unrelated
DLL definitions are checked against physical reference qualification
`e4b01eb8a59d0c93`. Native equivalence and runtime comparisons remain required
before selecting this profile; the active and prepared qualification selections
have not changed.


The repaired physical monitor has larger incident external capacitance sums than
its proxy baseline: PA/PB are 664.7/699.2 fF (previously 530.2/560.7 fF), and
positive-comparator O is 396.3 fF (previously 222.7 fF). These sums include
coupling and are not independent grounded loads. An early native SS/0 °C
+150 ps static monitor probe under qualification `0cc06862af2fae63` has failed.
It uses the unchanged full-RC fixture and the same six-slot lease, with no claim
of campaign or PHY qualification. The source-specific SS loop remains running;
all architecture/model/full-matrix requirements still apply.


Architecture provenance is independently rechecked before registering a native
campaign and during release verification. The screened candidate source must
match the audited physical source byte for byte, and source-specific screen
producer files must match both current files and their captured archive hashes.
The original and repaired campaign bindings pass these checks. Fault-injection
unit tests reject changed screened sources, producer files and archived copies.
Running simulation producers were not modified.


The unloaded SS/0 °C +150 ps control passes with BAD reasserting at 28.794 ns;
the matched loaded control fails, and the repaired loaded control passes at
88.271 ns. Filtered differences are 90.03, 89.51 and 85.86 mV respectively.
This controlled triplet strengthens the loading diagnosis. At +300 ps the
unloaded/loaded controls assert at 22.119/121.023 ns and both pass reference-cycle
scoring, while the native old layout asserts at 147.595 ns and fails. The proxy
therefore does not reproduce the full native delay; its original negative-control
expectation remains recorded as a mismatch. No limits or expectations were edited
in response to these results.

The original qualification coordinator is confirmed retired after its final
TT/25 °C −150 ps case failed (no BAD reassertion, filtered difference −93.17 mV).
The repaired native SS/0 °C +150 ps probe completed on the actual exact-RC
network and failed. A between-transient priority handoff held only the slot-free proxy
coordinator for about 0.15 seconds, then resumed it after the probe acquired its
slot; no SPICE process was signalled. The native failure remains recorded with the original limits; remaining proxy
conditions are pending.


The repaired native SS/0 °C +150 ps trace has BAD below 7.66 µV throughout
120–160 ns and no rising edge after startup. UF−DF averages 85.287 mV, close
to the passing loaded proxy's 85.863 mV. CTRL averages 0.752208 V. These
measurements do not establish whether the remaining failure is settling time or
DC gain/headroom. `diagnose_native_monitor.py` prepares source-bound internal-node
transients and a separate DC diagnostic using the same native devices and R/C,
with UF, DF and CTRL clamped to this trace's measured means. The DC task completes with BAD at 1.80 V and comparator O at 1.457 V,
supporting a settling problem at this measured fault operating point. An
internal-node transient is queued on the existing slot pool. Neither diagnostic can qualify the PHY, and
extended traces retain the original 120–160 ns phase result. Full dispatch and
promotion of this failed candidate remain held.


A circuit-preserving local comparator layout, `dll_layout/0a4253d72e392de9`,
now passes zero-error DRC and strict LVS with 518 devices and 15 public ports.
`layout_dll_candidate.py --local-comparators` puts the passive network, each
of the four comparators and the output logic in separate child islands.
Comparator O/OB/L/T nodes remain local. The candidate schematic and control
island bytes match layout `88342cdbe6c80ac2`; extracted capacitance, the RC
audit and native electrical response remain to be checked.


The first local layout's RC extraction/audit passes. Exact degree-8 profile
`schur_7d612d8097709e6d` passes four independent witnesses at 9,935 protected
terminals (maximum current difference 1.14e-12 A); qualification
`a101ed246a85e135` is prepared but has not been dispatched. Incident positive
O capacitance falls from 396.255 to 93.272 fF and OB from 199.656 to 41.225 fF.
However PA/PB increase to 706.290/832.032 fF and LAD1 to 1281.820 fF, because
its child signal ports extend across the passive bank. These are external
network capacitance sums including coupling. This layout is retained as a
diagnostic, not selected for full native dispatch.

The revised local-port variant `dll_layout/b0aa9ac2faf0887f` reuses the DLL's
local signal-port escapes within each child. It passes zero-error DRC and
strict LVS with the same source and control-island bytes. Its extraction,
audit and immutable native preparation are running. The failed original
physical monitor's internal transient is also running with added probes.


The revised local-port layout now passes extraction and the independent RC audit.
Its incident O/OB/L/T capacitances are 50.792/25.048/49.620/75.144 fF;
PA/PB are 491.374/527.494 fF, NA/NB 405.852/455.232 fF and S 418.688 fF.
LAD1/LAD12 are 313.825/333.271 fF, slightly higher than the preceding layout's
279.620/313.360 fF. The source-bound comparison is retained under
`b0aa9ac2faf0887f/monitor_capacitance_comparison.json`. Exact degree-8 profile
`schur_6ce2c5e21bf17f36` and native qualification `c47b7dc98d92327b` are prepared.
Its unchanged SS/0 °C +150 ps fixture is queued as an early diagnostic; full
dispatch remains held.

The repaired source-specific SS/0 °C loop screen `d8b9a06ef038cd76` has now
completed and fails. In 1200–1500 ns CTRL averages 1.783719 V, feedback error
reaches 845.001 ps, quarter delays span 223.578–223.622 ps and BAD is high.
Cadence and CTRL ripple (1.509 mV) pass, which does not establish phase lock.
UF/DF means are 0.760554/0.601174 V. Local monitor routing alone cannot establish
passing acquisition for this source. The earlier passing screen used a different
captured PFD and an extracted standalone delay line; the newer screen uses the
8-port PFD and native-finger schematic delay. Those changes must be separated
from the monitor R/C repair before attributing the acquisition failure. The next
loop investigation should check detector area polarity over the startup phase
range and compare reset-path timing/precharge, while preserving these failed
traces and all original limits. TT/FF screen work and RX characterization remain
under their original coordinators.


The original failed monitor's internal transient has completed with phase metrics
identical to the original test. It confirms a positive 11.292 mV comparator
input difference but O averaging only 0.640525 V, with normal PC/local VDDD
and quiet LOW/HIGH flags. The local-port variant's early native +150 ps probe
is now running. Detector capture controls `pfd_capture/b65a8cceadd819c0` are
prepared and waiting for a slot: exact-RC native output-reset PFD, matched PDK
schematic output-reset PFD and schematic internal-Q-reset PFD at −850/+850/0 ps.
No physical PFD change or passing acquisition result is claimed.


The local-port layout's native SS/0 °C +150 ps probe passes under the original
120–160 ns scoring window. BAD falls after startup at 26.275 ns and reasserts
at 54.619 ns, remaining at about 1.8 V throughout scoring. UF−DF averages
85.641 mV, close to the failed preceding layout's 85.287 mV. Native waveform
`da0b12b5e298762284281cc41440625e6a77638fbff604a0e4f5eb421ff7e285`
and its unchanged fixture are retained under `c47b7dc98d92327b/phase_ss_0_150ps`.
Conditional native quiet 0 ps and −150 ps follow-ups are queued and stop on
failure. Full qualification remains held by acquisition and remaining gates.

The separate exact-RC PFD −850 ps input control reproduces the wrong pulse-area
sign: UP/DN average 0.894585/0.633516 V in 60–80 ns, giving +261.069 mV.
Both input clocks have eight rising edges in that interval, while UP has five
and DN six; the longest complete UP high spans 2.858485 ns, exceeding the
2.5 ns reference period. The native schematic analog load and PFD/bias library
is identical to the failing source-specific loop library. This isolates a
wide-range PFD capture problem from feedback acquisition dynamics. The matched
schematic output-reset and internal-Q-reset controls remain in progress.


An isolated internal-Q-reset PFD implementation now passes physical checks under
its separate strict topology policy. Magic and KLayout report zero DRC errors;
LVS reports zero device, net, property and pin errors. Source/archive fingerprint
is `4806b668e84e4f0d173affb62cea988375034d0f6330206882d6734cfb9dcf9f`.
The previous policy's rejection is retained, and the summary explicitly records
`pulse-area-q-reset`. Actual RC extraction/audit are running. The preceding PFD
source, policy, active manifests and frozen producers remain unchanged.

At −850 ps the matched schematic output-reset and Q-reset controls both give
correct negative area (−617.441/−612.378 mV); they do not reproduce the native
+261.069 mV error. The new physical variant therefore needs native proof before
selection. No passing acquisition result is inferred from these controls.


The physical Q-reset PFD's RC extraction and independent connectivity audit
now pass. GDS SHA-256 is
`bb3a28c1372cd12ba24160dc91341b51b056aad6da37595e028f4d0f8416e3dd`
and extracted netlist SHA-256 is
`810a134361f82d9051ca1524bbc44ef14e25c22f64a3e44be88317fe77a9f8e6`.
`probe_pfd_physical_candidate.py` verifies source/producer archives, actual
post-route connectivity, GDS/netlist/audit hashes and matched reference fixtures
before preparing native −850/+850/0 ps capture probes. The probe coordinator is
active, waiting for the shared simulation slots. No physical capture or
closed-loop pass is claimed yet.


The local-port native SS/0 °C quiet 0 ps follow-up passes: BAD remains below
0.713 nV in 120–160 ns, with UF−DF = −1.595 mV. Its native waveform is
`d9081dfbd79416c63fd16120a83d020a8e4cd976e2a6e5ef2763af8eade0a26f`.
The −150 ps follow-up is running.

The physical internal-Q-reset variant fails the −850 ps capture control:
UP−DN = +260.742 mV, close to the preceding native PFD's +261.069 mV.
The passing schematic controls therefore did not predict a working physical
repair. This candidate remains unselected, with +850/0 ps controls continuing.
A distinct single-AOI reset experiment replaces the two-gate coincidence/clear
chain with `a22oi_4`, using a high-tied fourth input to implement
`clear_b = !(raw_up & raw_dn | disallow)`. A separate `nand2_1` derives disallow
from RESET_N/PD_ENABLE outside the Q-to-reset critical path. The new structural
policy checks this exact wiring, high ties, direct clocks and buffered outputs.
Its first build stopped at lint on a reserved instance name and is preserved;
corrected `pfd_fast_reset_physical_v2` is undergoing physical implementation.
No native success or acquisition result is claimed for it.


The local-port −150 ps native follow-up passes, with BAD reasserting at
59.249457 ns and remaining high throughout 120–160 ns. Its waveform SHA-256 is
`dd8757242626a9339c04be5d757b7b69106ec870d27d30bc2ec801710ff3d0ab`.
All three initial SS/0 °C static probes (0, +150, −150 ps) pass; this is not
full static/PVT or closed-loop qualification.

The single-AOI reset physical build passes zero-error Magic/KLayout DRC, zero
LVS device/net/property errors and its explicit structural policy. RC extraction
and the independent connectivity audit also pass. GDS SHA-256 is
`5051c9d97f0f8330f60a36dd07a69aaa3a0e3b0eec115e6b2edb09cfd78e22b5`
and extracted netlist SHA-256 is
`0806d75fcec1e4648580d6bec6370362efe1815a592585287b1cab785b8b2fc5`.
Matched native capture root `pfd_physical_capture/6562211b6d43fb89` is prepared
and its coordinator is waiting for a slot. Selection still requires actual
capture, quiet/activity, near-zero phase response and acquisition evidence.


The single-AOI physical PFD passes its −850 ps native capture-direction check:
UP/DN average 0.380123/1.016338 V, giving −636.215 mV instead of the preceding
PFD's incorrect +261.069 mV. UF/DF average 0.341069/0.861005 V. Its waveform
SHA-256 is `1303e4bda86a02e4731b0017b622f1a16149771601a370b73629f67ac3db8a97`.
The +850 and 0 ps controls remain pending; this is not a closed-loop result.

`screen_fast_reset_dll.py` prepares source-matched SS/0 °C, TT/25 °C and
FF/0 °C loops using the actual single-AOI PFD extraction, the same native-finger
schematic analog/delay devices and exact bias. Proposed source changes only
the PFD definition; all other circuit definitions remain unchanged. It reuses
the captured architecture stimuli, startup and loads, with the original
1200–1500 ns scoring window and 1500 ns stop. Input, source, extraction and
producer archives are validated. Native capture reports are checked against
their waveforms before admission, and missing or wrong-sign large-offset
controls hold dispatch. The 0 ps area-balance diagnostic is retained; integrated
quiet behavior remains subject to the unchanged loop/phase gates.

Prepared screen `dll_architecture/0ca8225b328ecaa1` validates its actual inputs
and is held for the remaining capture controls. Its conditional coordinator is
active and will run all three loops only after admission succeeds. No new
architecture-screen result or native/full-PHY qualification is claimed.


All three single-AOI physical PFD capture controls now pass: raw UP−DN is
−636.215 mV at −850 ps, +640.506 mV at +850 ps and +1.800 mV at 0 ps.
The +850/0 ps waveform hashes are
`7c0d35c2bde4ec93cc70ebd6d234b3b9e66d5fb7422d00da693177f526bbc386`
and `64d1b57258e825b73a05a7986958525e8200206f5c26817b547b334e210b9294`.
The three-corner source screen passes admission and is running; FF/0 °C is
active while SS/TT wait for slots. No settled-loop result is available yet.

Audited analog source binding `dll_layout/pfd_bind_1583499260541bb4` associates
proposed source `fc18ef4ca882d3bc38e8216a9b9b2ef16055ee74b9f73691a0af6fc49599334c`
with the existing analog GDS. The tool proves that only the unrelated PFD
definition changed; the flattened analog scope remains
`371e858737298457a8a17215ca8b2e8e279918ad7c240193b21dd4b7cae8eb91`.
GDS `d5fb7db80c22210b8521fd5442fe40d77e401eb56d429baab4b9f6acd189e23d`
and exact network `1113fdcdc6f8a5af7037155c9e2fbb42a7ca267b640145d5fcd3b8521f2a2573`
are unchanged, and a fresh strict RC audit passes. No electrical qualification
is inherited by this source binding.

The obsolete monitor-proxy and original capture-control coordinators were retired
while holding no SPICE lease and having no active SPICE descendants. Their
18/5 completed per-case summaries and all traces are preserved with retirement
receipts. The old source's current TT loop continues unchanged; a watcher will
retire only its remaining queued FF case after TT completes. Current-source
loop tests and the frozen RX campaign continue.


Staged release topology checking now selects the explicitly declared PFD policy.
The preceding buffered-reset and single-AOI designs retain distinct strict
checks; missing, unknown or internal-Q-only policy labels cannot qualify. Both
actual post-route netlists pass their corresponding structural checks. Saved
release reports bind the policy selector, fast-reset checker and base physical
checker hashes, and promotion/current-release inspection reject changed helpers.
A missing-candidate negative control still fails and writes its isolated report
(561 checks); no release package or passing production report is produced.
Native qualification assembly support will be integrated after the remaining
old-source simulation drains, preserving its producer snapshot.


Native DLL assembly now accepts the explicitly declared single-AOI reset policy
and archives both policy helpers. Prepared candidate
`dll_qualification/1d201e9ed2f89f56` contains 336 original fixtures, the exact
repaired analog network and the fast-reset physical PFD. Input validation passes.
Advancement accepts an explicit `--pfd` selection instead of silently substituting
the preceding PFD. The full campaign remains held pending the source screen.

Architecture evidence now compares the actual PFD and bias dependency closures
in each of the three screen libraries against the native library. Matching source
text alone cannot authorize a different physical detector. The prepared candidate
passes this check; a preceding-PFD substitution is rejected. Unit regressions
also reject changed PFD, bias and private physical implementation bodies.
Host validation: 216 tests, 211 passed and 5 backend-dependent skips.

The frozen RX aperture campaign has completed all 480 conditions; its table has
`passed: false` and cannot qualify a release. Its original artifacts are retained
for diagnosis. All three new source-screen loops are now running concurrently;
there is no settled-loop qualification result yet.


Combined native static service `openlvds-fast-reset-native-static.service` now
runs SS/0 °C +150/0/−150 ps full-RC cases from candidate `1d201e9ed2f89f56`
with three workers. Alongside the three source-screen loops this occupies all
six native SPICE slots. No active simulation was interrupted or restarted.
Host regression after the concurrency change: 219 tests, 214 passed, 5 skipped.
The source-screen FF/TT/SS traces have reached approximately 501/118/72 ns;
these are partial progress observations, before the 1200–1500 ns scoring window.

RX diagnosis rechecks all 248 endpoints of the 124 failed conditions. Both
endpoints fail in every condition; every +800 ps endpoint has high VALID but
illegal data levels. The detailed receipt and proposed isolated RX controls
are recorded in `dll-failure-analysis.md`. The complete PHY remains unqualified.


RX publication diagnostic `rx_publication/dd89f11b1af99f29` prepares six
source-bound SS/TT/FF endpoint controls with internal extracted output-stage
and supply probes. Three preserve 20 fF data loading; three remove only that
external load to isolate its contribution. All use the original observation
window. Native terminal discovery passes on the actual extraction. Host tests:
221 total, 216 passed, 5 skipped. Service `openlvds-rx-publication-controls`
will use one worker, waiting for a global SPICE slot while the six current DLL
simulations continue. Results do not qualify RX or the PHY.
