# Implementation status

The SKY130 macro implementation and reproducible build flows are present.
**The link is still in electrical bring-up and is not released.**


Current bring-up evidence on 2026-10-31:

- All three source-matched SS/TT/FF fast-reset architecture loops pass
  (`dll_architecture/0ca8225b328ecaa1`). All 21 selected native static offsets
  pass. Combined native candidate `dll_qualification/1d201e9ed2f89f56` has 336
  prepared fixtures. Native SS acquisition completed and failed: CTRL varies
  34.693 mV against 20 mV; the omitted-pulse final section measures 731.772 ps
  against the 625 ± 100 ps section limit. TT/FF acquisition and downstream
  progression are held. Measured model and full native qualification remain gated.
- Captured native diagnosis `dll_loop_diagnosis/43f094030fe944fc` separates
  32.977 mV cycle-mean movement from at most 1.659 mV cycle ripple. This supports
  slow startup settling. All four native AC fixtures are complete. Both clock
  states and their averaged G/Y response estimate 271 kHz unity-gain frequency,
  93.54° phase margin and 42.44 dB gain margin (`summary.json` in the diagnostic
  directory). These use
  trajectory-inferred delay gain and do not provide an independent model or
  transient-step validation; no qualification verdict is issued.
  New passive-preset experiment `dll_architecture/9e0ebce74ac41dcd`
  changes only the startup divider to nominal 1.2 V. It retains W8/C4, the actual
  fast-reset PFD, fixed supplies and original three source-screen fixtures.
  Physical candidate `dll_layout/dfb62f717c9bdb42` passes DRC/LVS and independent
  RC extraction/connectivity audit. Its exact reduced network SHA256 starts
  `403eb354e54c2dc8`; all 15 ports are verified. Source screens remain pending.
- Routing-capacitance inspection (`dll_stage_loading/c26dc74a57838968`) finds
  monotonically increasing internal loads across the four native delay sections:
  N = 48.174/56.614/65.053/73.493 fF and S =
  53.309/63.334/73.359/83.383 fF. These are incident wire capacitances, including
  coupling, excluding device/MIM capacitance; they are not effective AC loads.
  The preset-only layout retains this gradient (`dll_stage_loading/33a2a3dbcde34f95`).
  New `dll_layout/9368e5712c444b03` uses five local delay islands (four sections
  plus the existing replica), preserving all 519 devices and the preset source.
  DRC/LVS and independent extraction/connectivity audit pass. Measured incident
  routing capacitances now match across all four sections: N = 34.472 fF,
  S = 36.991 fF, B = 36.310 fF and PCTRL = 106.921 fF
  (`dll_stage_loading/96132db0d653d2ff`). The preset-only waiting
  native handoff was archived and superseded without stopping any simulation.
  Exact resistor-only profile `dll_layout/schur_513f603fc5e6c3aa` further reduces
  146,526 resistors to 43,836 while preserving every device, capacitor and port.
  Four independent terminal-admittance witnesses and a fresh connectivity audit
  pass; native transient qualification remains mandatory. Its handoff
  (`queue_preset_native_screen.py`, receipt
  `dll_layout/schur_513f603fc5e6c3aa/native_handoff.json`) waits for the same source
  screens before preparing/running native screening. It
  holds on failed gates, ended producers or changed inputs. Native acquisition
  and omitted-pulse timing remain unproven.
- The early-publication RX (`rx_early_physical_v1`) passes physical DRC/LVS,
  strict topology checks and an independent exact-RC connectivity audit. All
  12 loaded admissions pass. All four native continuous-data duty/jitter/skew
  cases pass (128 words). Its original 480-condition aperture campaign
  (`rx_aperture/20b04dcf527af283`) is running. All 32 SS/40 °C conditions pass,
  across both clock/data slew endpoints, both edge/data polarities and setup/hold.
  Its largest guarded setup/hold bounds are 270/110 ps; the 200 ps clock/data
  subset remains 210/50 ps. Other PVT coverage remains active. The preceding three
  publication variants remain timing failures and cannot qualify this RX.
- Staged early-RX bundle `phy_candidate/8f364c6a8fdabafb` passes all 54
  generic/native functional cases (2,373,588 bits). Its six-fixture RC comparison
  is running. The driver fixture passes with 0.396 ps maximum edge difference
  and 0.541 mV maximum plateau difference. The completed DLL fixture also passes:
  each of four outputs has 232 matching edges, with at most 0.785 ps crossing
  difference and 0.123 mV plateau difference (`dll_rc_diagnostic.json` beside
  the bundle manifest). These proofs cover this bundle's original networks;
  new DLL/analog/TX networks require their own comparison evidence. A complete
  certificate is still pending.
- Current component evidence verifies all 90/90 distinct proofs: all 45 schematic
  driver/receiver cases, all 30 native analog receiver cases and all 15 native
  drivers. The final SF/40 °C native driver passes. Both refresh processes are
  terminal, and `component_refresh/current_evidence.json` verifies every current
  source/fixture/waveform/runtime/producer proof. The original refresh batch's
  historical failure remains recorded; it is not rewritten as a passing batch.
  This completes baseline component evidence. The new receiver candidate,
  DLL, full aperture and link qualifications remain required.
- The 32-bit exact-RC data-path diagnostic at SS/40 °C/410 MHz, 45% duty,
  +100 ps skew and 100 ps peak-to-peak jitter completed and failed payload
  alignment (`build/link/ss_40_410m_d0.45_s100_e0_ideal_32/6735242e52a2`).
  Read-only clock diagnosis `link_clock/b7266f117369574e` finds 25 receiver-pin
  rising crossings but only 16 digital receiver-clock rising edges in 60–120 ns.
  Digital TX low pulses reach 858.520 ps; receiver-pin low pulses reach 514.807 ps.
  Cumulative duty distortion and receiver clock pulse loss require a separate
  loaded pulse-width investigation; moving the payload decoder window cannot
  repair missing clock edges. This remains an ideal-phase diagnostic, without
  measured-DLL qualification.
- Loaded receiver replay `clock_restore/50565a94b3b04171` retains the captured
  analog receiver pins, exact native analog/data receivers, shared bias and
  early-RX digital load. The complete captured-input replay reproduces the link
  clock loss: 25 input rising crossings produce only 16 output rising edges
  during 15–75 ns. The complete sharper-edge control improves that count only
  to 18. Both fixtures retain the measured pulse widths. This reproduces pulse
  loss without the live TX/driver and supports a receiver bandwidth limitation
  in addition to TX duty distortion; it does not qualify the link.
- Receiver input-current candidate `receiver_layout/2ec2942caa46a841` changes
  only XNT/XPT widths from 12 to 24 µm in the source, retaining complementary
  inputs, signal mirrors, decision stage and all nine ports. Source invariants,
  DRC/LVS and the independent RC audit pass (native network SHA256 starts
  `45fbff442fad8e43`). Both original receiver-replay stimuli are queued against
  this actual network at `receiver_replay/f55b204c5e5256b7`, including native
  digital loading and new PP/PN/CO observations. Bandwidth, node headroom,
  full input-range/PVT behavior and complete-link timing remain unproven.
- Matched `buf_8` TX experiment (`tx_buffer8_physical`) passes the full 54-case
  RTL/native functional regression (2,373,588 bits;
  `tx_buffer8/ed7e08ca1a8e22f7`), physical flow/topology and independent RC audit.
  Its native TX network SHA256 starts `d849e11e2470e9ec`. Diagnostic
  `tx_candidate_link/b1c1b53a01dc8564` replaces only TX in the saved SS/40 °C/
  410 MHz/45% duty/+100 ps skew link, preserving every clock/data stimulus,
  analog/RX/DLL circuit and scoring window. Its native simulation is running;
  the current staged
  candidate assembly continues to require buf_4 and no release is published.
- Unit suite: 288 tests, 283 passed and five skipped. The shared native budget
  remains six real simultaneous simulator leases. Captured active producers,
  fixed supplies, PVT coverage, voltage windows and timing margins are unchanged.
- Full DLL/PVT/model/recovery/readiness/operating-point evidence, all 480 RX
  boundaries, the complete six-fixture certificate and full link matrix remain
  required. No PHY release has been published.

Earlier entries below preserve the bring-up history; their running-state and
coverage statements describe the snapshot at the time, not the current status.

The pulse-area comparison milestone on 2026-10-29 is described at the end of
this document and in [the experiment workflow](dll-experiments.md). Its circuits
remain separate from the active PHY. Subsequent bring-up evidence is recorded below.

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


The combined fast-reset physical PFD plus repaired analog macro now passes all
three original SS/0 °C static seed fixtures under 120–160 ns scoring. At +150 ps,
BAD stays at 1.8 V and filtered UF−DF is +107.721 mV; at −150 ps BAD stays at
1.8 V and filtered UF−DF is −103.105 mV. At 0 ps, BAD remains below 1 nV and
filtered UF−DF is +1.826 mV. Waveform hashes (+150/−150/0 ps):
`c65660edb4987a757042a06c1a535b246759f1048056d6caa3def3285ef01792`,
`62985221b3935b6c3e23b5a646a4840ba6984a658d07439cf7238a63b799b74c`,
`896088cdbe0a82ad4d40c2d297d776ed22500cf3275e4ae8b5be33df52daf6d4`.
The conditional follow-up rechecked all seed artifacts and dispatched the
remaining 18 static SS/TT/FF cases. Architecture acquisition is still pending.

RX SS/0 °C internal publication control with 20 fF external loads reproduces
the baseline public measurements exactly (maximum reported limit difference
0 V). The publication flop output is already near 1.8 V and the final buffer
input near 0 V while the public outputs still charge. Final-driver local VDD
remains above 1.77 V. Removing only the two 20 fF external data loads makes the
same fixture pass: Q0/Q1 minima become 1.79890/1.79842 V. This demonstrates an
external-load contribution in the native circuit, with the original window and
VALID load preserved. Other controls and a separately hardened stronger-driver
candidate must establish the repair before any RX qualification.


Isolated RX `buf_4` candidate `rx_buffer4_physical_v1` completes its physical
flow with zero final routing, Magic and KLayout DRC errors; zero LVS device,
net, property and pin errors; no antenna violations; and a passing retained
native topology policy. Source identity is
`5f8b2734b05398da11153ad596a40c0c037ed21e6c775e37586acdd7de7bb1af`.
It preserves publication/sampling logic and explicit unit-strength VALID drive.
Its isolated functional scoreboard passes all 54 generic/native-RX cases,
1,186,794 bits per implementation, across the requested clock/duty/skew points
with jitter and reset behavior (`rx_buffered_rtl/5b4107f583cb8aee`). Host unit
checks: 224 total, 219 passed, 5 skipped. Actual GDS extraction and independent
RC connectivity LVS are now running. Loaded native endpoint and full aperture
qualification remain pending; this RX has not been selected or promoted.


Buffered RX actual GDS extraction and independent strict RC connectivity LVS
both pass. GDS SHA-256:
`39552fad4164d50bf619b9c535a09eb422ea5688fbfe85abfe8db871adf84bf4`;
exact reduced network SHA-256:
`f6e4ef38f920772c845917e4e121929642fc9a897c65e1d6d40195c669a4d61e`.
All 1,208 extracted capacitors and protected terminals are retained; exact
positive-conductance algebraic elimination reduces 21,690 resistors to 4,267.
The independent audit has zero topology errors. Native loaded endpoint tests
and a fresh complete aperture matrix are still required for this network.


Source-bound buffered RX aperture artifact `7636dbd7a4c55979` is prepared with
all 480 original conditions and exact native network `f6e4ef38f920772c...`.
Service `openlvds-rx-buffer4-aperture` queues six loaded both-polarity SS/TT/FF
endpoints, then expands only after their intact passing waveforms are rechecked.
The full matrix uses up to three workers under the global six-slot budget.
Original frozen producer files are unchanged. Unit checks: 230 total, 225
passed, 5 skipped; admission rejects incomplete/duplicate matrices and missing,
failed or changed endpoint evidence, and the selected-slot lease is exclusive.
No buffered native endpoint or aperture qualification result is claimed yet.

Combined native DLL static follow-up now passes six SS/0 °C offsets: 0, ±50,
±150 and +300 ps. −300 ps and TT/FF static coverage remain in the queue, and
all three source architecture loops are still running. The complete PHY remains
unqualified.


Buffered RX loaded native endpoints now pass both SS/0 °C data polarities and
TT/0 °C rising data at slow clock slew, using the original windows and limits.
Remaining seeds continue under service `openlvds-rx-buffer4-aperture`.
A separate six-case SS/0, SS/40 and SF/40 slow-clock diagnostic is queued under
`openlvds-rx-buffer4-limiting` to expose limiting publication behavior early.
Both services use the existing six real SPICE leases without signalling any
active simulator. Full aperture, full DLL and PHY qualification remain pending.


Staged integration supports an explicitly selected audited RX in both circuit
views, archived-source RTL verification, matching physical package selection
and exact-model aperture/link checks. Diagnostic bundle `712bb74a908d85f4`
passes all 54 functional cases (2,373,588 bits), including native TX+RX and PHY
assembly/control. All three digital GDS identities and exact/approximate model
hashes match their staged inputs (`digital_model_binding.json`). Canonical RTL
also passes after the verifier update. Unit checks: 234 total, 229 passed and
5 skipped. A staged release negative control remains failing with 565 checks;
missing native DLL, all-PVT model/proofs, analog/current-analysis, aperture,
RC certificate and full link evidence are not bypassed. No release is produced.

The early limiting RX test fails SS/0 °C rising-data setup at 200 ps clock slew
under the original 20 fF load: Q0/Q1 minima are 1.40981/1.29742 V. Thus passing
the 20 ps clock-slew SS endpoints and TT endpoints does not qualify `buf_4`.
The original limits remain fixed. Remaining broad RX work is being held at an
idle coordinator boundary, preserving native traces, before a stronger native
publication/output path is evaluated. The DLL source/static jobs continue.


The current selected-RX staged bundle `712bb74a908d85f4` passes actual physical
reconstruction, archived RTL and canonical source-fingerprint gates in a fresh
565-check release negative control. Release remains false because required
native DLL/PVT/proofs, current analog evidence, complete RX aperture, six-fixture
certificate and full link matrix are incomplete. Exact/fast digital model and
GDS metadata agree. No package or current release pointer is published.

The `buf_4` RX fails both polarities at SS/0 and SS/40 with 200 ps clock slew.
A hold request is active for its full matrix coordinator at the next idle search
boundary. Current native work is not interrupted. Stronger source
`openlvds_ddr_rx_buffer8_publish4.v` retains data `dfrtp_4` publication and
`buf_8` outputs, with unchanged pipeline and VALID behavior. Its 54-case generic
and native RX functional regression passes 1,186,794 bits per mode. Physical
and loaded native timing validation remain pending. Shared RX producer helpers
stay unchanged while the preceding active users drain.


The failed `buf_4` aperture dispatcher has been retired after its active native
children finished. Receipt `rx_aperture/7636dbd7a4c55979/drain.json` preserves
12 collected point reports and separately reanalyzes one completed uncollected
trace. No native SPICE process was signalled; its partial matrix is unqualified.
The limiting coordinator was retired while idle after both SS/0 and SS/40
polarities failed. Old source/producer archives and native traces remain intact.

Stronger RX `rx_buffer8_publish4_physical_v1` passes Magic/KLayout DRC and strict
LVS with zero errors, retains its declared native publication/driver topology,
and passes actual GDS extraction plus independent RC connectivity LVS. Source:
`b3125079c567f616dfd9985185f8d9f16942961bb3b1bc46fc7386a893d6a21f`;
GDS `e1fa7f2fcbade1245e4ee29dd6e77011cfeecbbf0c08a7dd013189d449d366ac`;
exact native network `4a62593449b1e94de0c224de1e00caff25f197eae0397b8ed82899631407865b`.
All 1,413 extracted capacitors are retained. Exact algebraic reduction reduces
22,046 resistors to 4,633 without removing protected terminals or devices.

Aperture artifact `f99deb414f62ab19` is prepared. Service
`openlvds-rx-buffer8-publish4-aperture` runs 12 stronger loaded admission points,
then only on success the complete 480-condition matrix with worst SS/SF cases
first. Failure now holds queued work while active searches finish, and incomplete
coverage cannot produce a complete table. The shared six-slot budget is intact.
Unit checks: 239 total, 234 passed, 5 skipped. The stronger RX has no loaded
native endpoint or full-aperture qualification result yet.


The fast-reset source-matched architecture screen completes FF/0 °C successfully
under the unchanged 1200–1500 ns window: maximum feedback error 6.5465 ps,
quarter-cycle delay 632.6245–632.9995 ps, CTRL mean 0.731602 V and total variation
3.1627 mV; BAD maximum 0.423 µV. Raw waveform SHA-256:
`793a3351d06c56c8523e6489b2f31e1580bdc06adc01cfc87101b723d8b54dbf`;
exported waveform:
`015ef69ccdf88f033ac37066a78998e9c514da1c551860a0ada8057700bcfe72`.
TT/SS source screens and full native-RC loop qualification remain outstanding.

Release checking also exposes stale driver/analog-receiver characterization.
A refresh coordinator now runs all 15 PVT points for schematic and exact native
views of driver, static receiver and rate receiver (90 component cases), using
fixed solved supplies and no voltage sweep. Every new simulator subprocess now
acquires a real shared SPICE slot; cached valid waveforms are reanalyzed without
acquiring a slot. Mismatched prior evidence is moved to content-hashed case
history before regeneration, preserving original traces, decks, sources and
producer files. Tests verify cache/slot behavior and archived file hashes.

The initial refreshed TT/0 °C driver passes both settled polarities into 100 Ω:
differential 0.31558–0.31612 V and common-mode 1.24470–1.25612 V. TT/25,
TT/40, FF/0 and FF/25 schematic drivers also pass with current analysis. Service
`openlvds-component-evidence-refresh` continues the remaining component cases.
The shared SPICE budget remains six; active DLL/RX fixtures and producers were
not modified. Unit regression remains 239 tests (234 passed, 5 skipped).


The stronger RX's first loaded native admission point fails SS/40 °C with
200 ps clock slew: Q0/Q1 minima are 1.21208/1.10179 V, below 1.44 V in the
unchanged publication window. Its fail-stop logic correctly holds the remaining
11 endpoints and never expands the full aperture matrix. Root
`rx_aperture/f99deb414f62ab19` records the failed witness and held cases.
Physical/functional passes do not qualify this timing result.

New staged bundle `754e8b6301c3cc78` with the stronger RX passes the complete
54-case generic/native TX+RX functional regression (2,373,588 bits). Its native
publication timing remains a failure. Internal diagnostics at
`rx_publication/3efd83d2a44327ab` now target this exact failed SS/40 condition,
retain the original stimulus/window, observe actual output-stage, clock-input
and clock-controlled transistor terminals, and compare 20 fF versus zero
external data loading. The diagnostic accepts a source-bound failed seed report
without requiring a complete aperture table. Service
`openlvds-rx-strong-publication-probe` is queued under the six-slot budget.
Another width change is held until those native internal traces identify delay.


All three source-matched fast-reset DLL architecture loops now pass their
original window. SS/0 °C maximum feedback error is 10.0304 ps (CTRL mean
0.815841 V, variation 2.5738 mV); TT/25 °C error is 7.8211 ps (0.759505 V,
2.9996 mV); FF/0 °C error is 6.5465 ps (0.731602 V, 3.1627 mV).
All 21 selected full-RC static offsets at SS/0, TT/25 and FF/0 also pass.
Service `openlvds-fast-reset-native-screen` now runs the three native-RC
acquisition cases using those unchanged captured libraries/fixtures, reusing
intact completed static evidence without simulation restart.
`openlvds-native-dll-gated-progression` waits for actual native screen success,
then runs measured three-corner stability/step validation; only passing model
reports admit full 336-case native qualification, followed by all-PVT model
measurement. Failed gates hold expansion. The resident automatic OTA/CP entries
remain disabled, avoiding duplicate native dispatch. Full PHY remains unqualified.

The controlled `buf_8`/publication-1 RX passes its 54-case generic/native
functional regression (1,186,794 bits each), zero-error physical DRC/LVS and
strict native topology, actual GDS extraction and independent RC connectivity
LVS. Source identity:
`e842ec085bc658245c8dde9fefb33ef799ac173fb9d9a77f964519b7887d6918`;
GDS `8732722a02671ed4377dc4948c50139c0a2e91c201c3544a09325d35742bac4f`;
exact network `83e0a24d2f74c0885c4b512688b54833a33473e88b4a2b631b20b190cc479315`.
All 1,352 extracted capacitors are retained; exact algebraic reduction reduces
21,951 resistors to 4,515. The distinct `public-data-buf8-publish1` policy checks
its actual publication cells and driver wiring; it cannot inherit publication-4
success. Native artifact `rx_aperture/4032d9b01f924bfd` runs the same 12 admission
points and conditionally the full matrix under
`openlvds-rx-buffer8-publish1-aperture`. No native timing result is claimed yet.
Unit checks: 240 total, 235 passed, 5 skipped.

All 45 distinct schematic driver/static-receiver/rate-receiver PVT cases now
have current passing reports. The SF/0 driver initially hit a timestep collapse
at 2470.05 ns in a thick-oxide level-shifter source-body node. Repeating that
same case with a tighter 20 ps maximum integration step completes normally and
passes the original DC and transition criteria. Its original failed data is
preserved in case history; the batch's original failure returncode is retained.
Repair receipt: `component_refresh/sf0_driver_repair.json`. Three native driver
PVT cases have passed so far; the remaining exact-RC component refresh continues.

The publication-cell comparison also fails native SS/40 °C at 200 ps clock
slew: publication-1 with buf_8 gives Q0/Q1 minima 1.56645/1.26103 V.
Artifact `rx_aperture/4032d9b01f924bfd` holds its remaining 11 admissions.
Internal publication-4 traces (`rx_publication/3efd83d2a44327ab`) distinguish
the causes: local clock input crossings are within 0.343–0.711 ps, but the
publication Qs cross 1.44 V only after 664–672 ps. Loaded public outputs reach
1.44 V after 817.283/824.523 ps, outside the unchanged 800 ps window start;
unloaded outputs cross at 764.879/772.168 ps. Further drive-strength tuning
is therefore superseded by an isolated half-cycle publication experiment.

`rtl/experiments/openlvds_ddr_rx_early.v` prepares a completed pair on the falling
edge: a held rising sample and the falling sampler drive buf_4 public outputs.
VALID is held on that falling edge too, preserving the first valid word for a
positive-edge consumer. Explicit native cells and the distinct
`half-cycle-publish-buf4` policy retain all sampler clocks, enables, word holding
and VALID wiring through routing. This changes public update phase; integration
must respect the positive-edge consumption contract. It remains an experiment,
not a promoted receiver.

Fresh functional evidence `rx_buffered_rtl/3fc750281ff3b4bb` passes 54 cases,
1,186,794 bits per generic/native model. Directed evidence
`rx_early_contract/711c7d2a275a2c4a` passes 18 frequency/duty/model cases, including
four asynchronous reset phases, first-valid word ordering, pre-edge consumer
streams and post-edge pair agreement with the original RX. Physical artifact
`rx_early_physical_v1` is being built for independent native RC audit and the
unchanged 12-admission / 480-condition timing gates. No native timing pass is
claimed from these functional checks.

Both parallel native analog receiver batches complete successfully: 15 static
receiver and 15 rate-receiver cases, fixed supplies and 0/25/40 °C. Exact-RC
driver refresh and native DLL acquisition remain running; their captured
producers are unchanged.

The early RX physical artifact completes with zero routing, Magic, KLayout and
LVS errors. Its independent native RC audit passes. GDS SHA-256:
`723b7149cab3a7ea6c936da1d15eff9ec255db889c6ce1f345f374807ce6bd9c`;
exact network `6def14fbd570903751f922c3a86132bbd801957c3dfd3d09c7c81729361515c3`.
All 1,171 capacitors are retained; exact algebraic elimination reduces 21,701
resistors to 4,229. The nominal routed STA has no setup/hold violations; worst
setup slack is 68.315 ps and hold slack 134.170 ps. These nominal checks are not
PVT timing qualification.

Native admission/full campaign `rx_aperture/20b04dcf527af283` now runs under
`openlvds-rx-early-aperture`, with unchanged acceptance and fail-stop gates.
Combined diagnostic bundle `phy_candidate/8f364c6a8fdabafb` selects this exact RX
and its matching functional cell model. Its full RTL regression is running.
No promotion or release claim is made. Current unit regression: 241 tests,
236 passed and 5 skipped. A second native-driver refresh service uses two workers
with shared slots and existing per-case locks, accelerating the remaining cases
without overwriting running evidence.

The selected early RX bundle passes all 54 full generic/native TX+RX functional
cases (2,373,588 bits), including DLL-control and functional-PHY checks. Evidence:
`8f364c6a8fdabafb/rtl_validation/c7d7efce94da841f`. Its first two native admissions
both pass SS/40 °C with 200 ps clock slew and 20 fF loads. Rising data Q0/Q1
minima are 1.79999958/1.79999895 V; falling-data maxima are 0.300/0.0133 µV.
The original window and 0.36/1.44 V thresholds are unchanged. Remaining ten
admissions and the full 480-condition matrix remain outstanding.

`openlvds-early-phy-rc-validation` now compares all six exact/approximate nonlinear
fixtures for this bundle with two workers. Shared leases keep actual native
DLL, driver refresh, RX and certificate simulations within six total. There
is no passing RC certificate, complete native RX table or released PHY yet.

Supplementary native burst artifact `rx_burst/0a6a8b72e9d5e53d` now probes the
new half-cycle path under continuous data. Its first SS/40 °C case passes all
32 consecutive words at 410 MHz, 45% duty, -100 ps skew, independent ±50 ps
clock-edge jitter, 200 ps clock/data slew and 20 fF public loads. Across the
unchanged publication windows, the minimum high is 1.79999127 V and maximum low
95.912 µV. Three further duty/skew cases remain; this is supplementary evidence,
not a replacement for aperture or link qualification. Six original RX admissions
have now passed. New diagnostic and corruption/fixture tests are committed as
`03fcd7a`; unit suite: 243 tests, 238 passed, 5 skipped. All active producers and
original coverage/limits remain unchanged.

All four native continuous-data burst cases now pass and their service exits 0:
128 checked words at SS/40 °C and 410 MHz, both 45/55% duties and both ±100 ps
skews, independent ±50 ps edge jitter, 200 ps clock/data slew and 20 fF loads.
Across every word's original public window, minimum high is 1.79999126 V and
maximum low 96.1872 µV. Artifact `rx_burst/0a6a8b72e9d5e53d` has four actual
source-bound reports; no missing case is counted as coverage. This completes the
supplementary half-cycle diagnostic, while the full aperture and link gates
remain mandatory. Eleven original admissions have passed and the final FF/0
falling-data case is live. DLL, driver refresh and six-fixture RC comparison
continue without source changes or simulation restart.

The early RX clears all 12 original loaded native admission points with zero
held cases. `rx_aperture/20b04dcf527af283/seed_summary.json` binds each actual
waveform witness to manifest
`bd12c38ce8362bd289826175a9ee3b650f3a49fafd0116ab9d3092aa231e16bc`.
The same coordinator has rechecked those admissions and entered `running_full`
with three boundary workers for the original 480-condition matrix. Actual
simulator dispatch remains limited by the six shared leases. This clears the
publication admission failure that held the preceding three RX variants; it
does not yet prove complete aperture bounds or full PHY qualification.

The independent current-component receipt now verifies 80/90 actual proofs:
all 45 schematic cases, all 30 native analog receiver cases and five native
drivers. FF/40 and SS/0 native drivers are live; the other eight native drivers
still have stale reports awaiting refresh. The native FF/25 driver completes
and passes its original DC and transition criteria. The receipt distinguishes
running/stale evidence from electrical failure, retains historical batch errors,
and checks exact case names rather than overlapping receiver globs. Source:
`scripts/verify_component_evidence.py`; output:
`component_refresh/current_evidence.json`. Read-only shared locking has also
been exercised on this workspace's NFS filesystem. No active producer changed.


The early RX completes its first full boundary condition at SS/40 °C with
200 ps clock and data slew, rising clock edge and rising data: 87.5 ps fails,
90.625 ps passes, resolution 3.125 ps, retained guard 20 ps, rounded setup bound
120 ps. This is one actual condition in the required 480, not a complete table.
All three boundary workers now have real simulator leases. Current component
receipt advances to 81/90 after the FF/40 native driver passes.

The staged driver's completed exact/approximate comparison passes with 32
matching transitions, maximum edge difference 0.395436 ps, differential plateau
difference 0.540915 mV and common-mode plateau difference 0.367787 mV. Both traces
are reverified through their captured circuit/simulator/fixture attestations;
no resimulation or looser comparison was used. Supplementary result:
`phy_candidate/8f364c6a8fdabafb/driver_rc_diagnostic.json`. The original six-fixture
coordinator continues and no complete certificate is claimed from this subset.


Three original full-aperture conditions now pass at SS/40 °C with 200 ps clock
and data slew. Rising-clock/rising-data setup retains its 120 ps guarded bound.
Rising-clock/falling-data setup brackets 178.125 ps failing and 181.25 ps passing,
then verifies the 210 ps guarded witness. Rising-clock/falling-data hold brackets
-181.25 ps failing and -178.125 ps passing; the original guard/rounding policy
conservatively clamps the reported hold requirement to zero and verifies that
actual zero-offset witness. Remaining conditions continue under unchanged code.

The native SS/0 °C driver completes and passes, with settled differential levels
0.294919–0.295079 V into 100 Ω and common mode 1.24841–1.25159 V for its positive
polarity. Its delayed transition stream also passes original polarity/cadence
checks (propagation 1.34898–1.38597 ns). The independent current receipt verifies
82/90 component proofs. Eight native driver PVT cases remain outstanding.


Both SS/40 °C falling-clock setup conditions now pass with 200 ps clock/data
slew. Rising data brackets -28.125 ps failing and -25 ps passing; the unchanged
guard/rounding policy produces a conservative zero requirement and the actual
zero-offset witness passes. Falling data brackets 59.375 ps failing and 62.5 ps
passing, with a verified guarded 90 ps bound. Together with both rising-clock
setup and hold results, six of 480 full-aperture conditions pass. The remaining
falling-clock hold searches are active; no complete PVT aperture table is claimed.

A release handoff review found that digital GDS/LEF and synthesis sources were
included, but the routed digital netlists were omitted. Promotion now includes
both logical and power-aware netlists for the exact selected TX, PFD and RX.
Their expanded interfaces, logic connectivity and cell supply/body connections
are checked before packaging; validated byte hashes also prevent a changed file
from being copied after validation. The native tap cell's two supply terminals
are handled explicitly, while logic cells require all four supply/body ties.

The new non-publishing `--check-netlists` preflight passes against actual selected
bundle `8f364c6a8fdabafb`, including the early RX. Its receipt is
`netlist_preflight.json`, with no electrical qualification or release pointer
change. Tests reject swapped/missing power ties, changed logic, wrong bus widths,
wrong directions and duplicate cells, and verify that preflight preserves an
existing current release. Unit suite: 253 tests, 248 passed, five skipped. Active
DLL, RX, component and RC producers remain unchanged.

A link-analysis review identified an observation mismatch: payload decoding used
one sample at half a period, outside the RX's characterized +0.80–1.05 ns window.
For the early RX, that sample can approach the next falling-edge publication
under duty/jitter stress. The link analyzer now requires stable legal data and
high VALID over all 51 points in the original window, with no timing/voltage
relaxation. Input capture margins, analog checks, payload lengths and complete
qualification coverage are unchanged.

New tests cover early next-word updates after the window, brief illegal data or
VALID inside it, and both window boundaries. The analyzer also decodes three
actual completed native guarded witnesses correctly (rising setup 120/210 ps and
falling-clock hold 50 ps). Unit suite: 256 tests, 251 passed, five skipped.
The analyzer's runner fingerprint gives future link runs a fresh identity; no
active native DLL, aperture, component or RC producer was modified.

Supplementary exact-RC integration probe `openlvds-early-exact-link-probe` is
queued under the six-slot budget. Its artifact is
`build/link/ss_40_410m_d0.45_s100_e0_ideal_32/6735242e52a2`. It uses 32 bits at
SS/40 °C, 410 MHz, 45% duty, +100 ps data skew and 100 ps peak-to-peak jitter,
actual full-RC data-path macros, ideal quarter-phase clocks and solved fixed
supplies. A 60 ns diagnostic training override shortens this supplementary test;
it does not replace the required measured-DLL-phase diagnostic or full trained
link matrix. The new window analyzer is committed as `d9d73eb`; this producer is
now held unchanged while the test runs. No integration result is claimed yet.


The complete SS/40 °C group at 200 ps clock and data slew passes all eight
original boundary conditions. Each guarded witness was actually simulated:

| Capture clock edge | Data transition | Setup bound (ps) | Hold bound (ps) |
| --- | --- | ---: | ---: |
| Rising | Rising | 120 | 0 |
| Rising | Falling | 210 | 0 |
| Falling | Rising | 0 | 50 |
| Falling | Falling | 90 | 0 |

These are guarded/rounded requirements, including conservative zero clamping
of negative boundaries. This group does not replace the other original slew
combinations or remaining PVT points. Eleven of 480 conditions currently pass,
with no failed completed condition.

Native SS/40 °C driver characterization also completes successfully. Its settled
differential output is 0.288671–0.288713 V into 100 Ω; positive-polarity common
mode is 1.249158–1.249705 V. Original polarity, cadence and transition checks
pass (propagation 1.37523–1.39375 ns). The independent current-proof receipt now
verifies 83/90 cases. Native SS/25 and FS/0 drivers are active; five subsequent
native driver cases remain stale until refreshed. The exact-RC integration
probe remains queued under the six-slot limit, with no result claimed.

The downstream workflow now has an explicit completed-native resume path:
`advance_ota_candidate.py --qualified-native ... --all-pvt-stability ...`.
It reanalyzes complete native qualification and verifies the all-PVT model before
any downstream command. It carries the selected RX/table through all original
operating-point, recovery, readiness, RTL, RC, diagnostic, full-link and release
gates, without preparing a new native campaign or modifying resident dispatcher
configuration. A qualification-wide nonblocking lock prevents duplicate owners.

Tests cover incomplete/failed/native-damaged/model-damaged evidence, rejection
of CP artifacts, selected RX preservation, unchanged resident configuration and
exclusive advancement ownership. An actual attempt against the currently
incomplete native campaign stops at the native gate, creates no advancement
directory and starts no downstream job. Unit suite: 261 tests, 256 passed, five
skipped. Active qualification producers and fixtures remain unchanged.

Runtime inspection found that the base image contains no Apptainer executable,
while the downstream orchestrator previously called `env.sh` for every child.
Its child-command builder now executes base jobs directly inside the established
container and enters the existing Nix shell for tool jobs. Host-side command
construction retains the environment wrapper. Literal arguments are preserved
with proper shell quoting for the Nix command string.

Actual smoke checks pass for both paths: a base child validates the selected
TX/PFD/RX netlist handoff, and a Nix-shell child exposes the advancement CLI.
The waiting downstream watcher was stopped for this correction; no native
simulation was stopped or restarted. Unit suite: 264 tests, 259 passed, five
skipped. The resume path retains complete native/all-PVT and downstream gates.


The native SS/25 °C and FS/0 drivers complete successfully. Their original
transition propagation ranges are 1.36533–1.39077 ns and 1.16675–1.22170 ns,
respectively. The independent current receipt verifies 85/90 component cases;
five native driver PVT cases remain outstanding. Thirteen RX aperture conditions
have passed, with no failed completed condition. The exact-RC link simulator has
started its operating-point solve; absence of a raw file during that solve is
not evidence that the job is queued or stopped.

Service `openlvds-early-phy-post-native` now waits on the existing standalone
native/model progression, then invokes the completed-native resume path with
the explicit early RX/table. Its source and qualification/RX manifest hashes are
bound in `resident_jobs/early_phy_post_native.json`; source drift, RX failure or
terminal upstream failure holds downstream execution. It tolerates transient
status-read failures and checks actual service state. Resume itself repeats
complete native and all-PVT verification before signoff. Current state is
`waiting_for_native_and_all_pvt_model`; no native or model completion is claimed.
The prior waiting watcher's source and receipt are preserved in resident job
history. No scientific simulator was stopped for the workflow corrections.
