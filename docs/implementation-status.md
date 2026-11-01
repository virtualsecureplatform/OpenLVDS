# Implementation status

The SKY130 macro implementation and reproducible build flows are present.
**The link is still in electrical bring-up and is not released.**


Latest receiver decision on 2026-11-01:

- Active experiment: uniform fourfold scaling of the DC-passing reduced-tail
  decision stage, retaining the input-pair/mirror/tail width ratios. TT/25
  `receiver_scaled_decision_static/de8b99d5cb7a5d5e` now passes all twelve
  original DC samples. SF/40 and FS/40 also pass all twelve points, including
  the conditions that rejected the PMOS-only variant. All three pilot
  waveforms have been remeasured, and full static matrix
  `receiver_scaled_decision_matrix/a3a34b4ac8e5f600` now passes all fifteen
  process/temperature cases (180 original samples, fixed supplies).
  Source-clock comparison `receiver_clamp/b9f840b0494a787c` has completed
  both its reduced-tail control and uniformly scaled captured-input candidate
  with zero missing edges. The sharp-clock fixture also passes: all three
  original 80 ns fixtures have exactly one output edge in each of 47 scored
  periods. The completed hash-bound `source_clock_admission.json` passes.
  New layout `receiver_layout/8a063d6919387667` passes DRC, LVS, extraction
  and its independent RC audit. Native replay `receiver_replay/90c2618d3cbb6f83`
  is prepared; both original controls are queued on shared slots 1 and 3.
- The PMOS-only W32 alternative is rejected: FS/40 fails two original
  low-common-mode points despite TT/25 and SF/40 passing. Its remaining
  twelve DC cases and all clock cases were correctly held. Monitor relocation
  alone also fails: the completed captured native replay still misses the
  same eighteen edges. Neither alternative is a qualified replacement.
- The completed uniform-scaling TT control comparison is bound in
  `de8b99d5cb7a5d5e/control_comparison.json`. Output decisions agree at every
  original sample, while CO shifts by up to 80.807 mV, CL by 45.084 mV and
  CT by 25.231 mV. Width ratios are preserved; exact operating voltages are
  not assumed invariant. The PP/PN static shifts are at most 34.856/17.900 µV.
  Dynamic behavior and native capacitance remain unproved.
- The full fifteen-case terminal-voltage report is
  `a3a34b4ac8e5f600/decision_headroom/fb9f945f405afaec/summary.json`.
  All five changed schematic decision devices pass the 1.95 V project screen
  over each complete original 144 ns trace. This is not a PDK absolute-rating
  claim or coverage of the remaining receiver/native devices.
- Fixed-supply TT/25 operating-point probe
  `receiver_operating_points/41735e88e064dc98` completed both original
  low/high common-mode input points. Its initial parser held on ngspice's
  unit-wrapped aliases; the simulation and original producer are retained.
  `scripts/analyze_receiver_operating_points.py` validates the unchanged
  manifest, producer, runtime, source fixtures and raw evidence, then compares
  each alias with the actual model parameter. No simulation is rerun.
  The bound result is `analysis/b9f35f4ed065a4af/summary.json` under that probe.
  Tail current is 147.650 uA at P/N=0/0.1 V and 1.390293 mA at 2.3/2.4 V.
  Tail VDS is approximately 14.726/278.641 mV versus modeled VDSAT
  219.187/219.236 mV: the low-common-mode point has limited tail headroom.
  Receiver/bias rail power is 2.797/6.799 mW, with the separate ideal reference
  source delivering 0.820/0.087 mW. These are schematic static points only,
  without native/dynamic/all-PVT power qualification. The low point agrees
  with its transient sample within 1.2 pV; the high point differs by up to
  2.075 mV. Neither exact operating-point invariance nor current scaling is assumed.
- `receiver_operating_point_matrix.py` extends that observation to all twelve
  original input points at every original process/temperature condition.
  Matrix `receiver_operating_point_matrix/584ff581fd63fca4` is prepared and
  `openlvds-receiver-operating-matrix.service` is active, initially waiting
  on shared slot 3. It preserves the six-slot budget and all fixed supplies.
  Preparation first remeasures the complete source matrix; every OP child is
  bound to its exact source case. Completed raw evidence is analyzed without
  rerunning SPICE; partial evidence is retained and refused for in-place retry.
  Only the known unit-vector parser hold can proceed to the separate strict
  model-parameter analysis. Other simulation/provenance errors remain errors.
  This is a static tail-current/headroom and rail/reference-power diagnostic,
  without native/dynamic power, remaining-device stress or PHY admission.
  Four additional tests verify completed-evidence reuse, partial-trace
  preservation, strict error handling and refusal of incomplete source
  coverage. Full regression: 536 tests, 535 passed and one skipped.
- Re-reading both completed 80 ns captured-source waveforms and verifying
  their saved SHA256 bindings confirms exactly one output edge in all 47
  scored periods. Reduced-tail control latency is 343.165/359.340/404.411 ps
  (minimum/median/maximum), versus 347.770/360.086/420.935 ps for uniform
  scaling. Their weakest captured pulse is identical: 83.068 mV peak,
  514.802 ps width at 58.919554 ns. The maximum latency occurs at this pulse.
  Thus the scaled schematic receiver has not demonstrated a speed improvement;
  the hypothesis still needs the actual extracted-RC replay. This source
  diagnostic includes a captured pulse below the 100 mV specified sensitivity
  and does not replace the component or aperture qualification fixtures.
- The operating-point matrix has completed all twelve TT/25 points. Its
  independently revalidated static tail current spans 116.828--1390.293 uA;
  rail power spans 2.727599--7.101542 mW, excluding reference-source power.
  At the six original low-common-mode points (P/N through 0.65 V), tail VDS
  is 11.572--17.422 mV against modeled VDSAT near 219.187 mV. At P/N of
  1.15/1.25 V the tail current is 869.507 uA, versus 485.507 uA with input
  polarity reversed. DC logic passes despite substantial common-mode and
  polarity dependence of current. Dynamic/native bandwidth must be measured;
  width scaling is not treated as a fourfold increase in operating current.
- The scaled receiver layout has 88 devices, nine ports, dimensions
  787.240 x 100.045 um, zero DRC violations and matching LVS. GDS SHA256 is
  `b83cd9b3c5d21f211274442698e38a42df0077015ab2ab814c3c5866aa0e49c1`;
  audited native RC SHA256 is
  `490276d995bbac6a227413ee0be363df2df1914535f40488133cfaf2f2198c66`
  (`build/extracted/c2c5346dfcdcd43d`). The reduced network retains 88 devices,
  16101 resistors and 1250 capacitors. All physical/source admission proofs
  are frozen in the new native replay context; component/link admission still
  requires both complete passing native waveforms.
- Reading both audited extracted networks with the existing
  `inspect_dll_stage_caps.routing_caps(..., with_components=True)` and proving
  one resistor-connected component per observed net gives incident routing C
  for monitor-after tail16 versus uniform scaling, in fF: CO 28.24057 to
  83.62715; CL 25.00120 to 100.19234; CT 30.01471 to 120.56284;
  PP 92.04186 to 126.15072; PN 99.08609 to 131.48089. NL/NR/PL/PR remain
  unchanged. These include coupling at every resistor-connected segment,
  without transistor/MIM capacitance or an effective AC-load interpretation.
  The increased routing loads reinforce the need for actual native replay;
  neither a drive-to-load improvement nor bandwidth gain is presumed.
- `qualify_selected_analog_link.py` prepares the next matched full-RC link
  comparison with both the selected receiver and P64/N24 driver. It first
  requires every original 30 driver and 60 receiver component case to exist
  and pass, then remeasures the cached suites and the completed receiver-only
  reference through their scientific producers. Profile/layout/replay identity
  must agree. The independent component reports, waveforms, fixtures, original
  inputs and producer code are bound in a separate immutable admission record.
  No missing component simulation can start from this cached admission path.
- It reuses the existing matched native driver engine with the selected
  receiver fixed in both alternatives. A failed receiver-only reference may
  supply the fixture, since its old driver may be limiting; both component
  suites must still pass. Candidate success requires actual decoding and
  sampling margins plus at least 100 mV at every measured TX/RX clock center
  in the original 60--120 ns diagnostic window. The control may fail without
  invalidating a passing candidate. Partial uncached traces are retained and
  refused for in-place retry. This remains one ideal-phase loaded-link
  diagnostic, without selected-DLL/digital assembly or full-PHY admission.
- Actual `a3a34b4ac8e5f600/combined_link_preflight.json` records rejection of
  the incomplete driver suite and zero new comparison contexts. Seven tests
  cover that gate, receiver identity mismatch, the admitted failed-reference
  path, independent candidate/control verdicts, decoder/sensitivity failures,
  changed admission inputs and partial-trace preservation.
  `selected_analog_followup/run.py` is active as
  `openlvds-selected-analog-link-followup.service`, waiting for the driver
  component and receiver integration owners. It calls the strict adapter
  after the owners finish and relies on actual scientific evidence, including
  a completed negative reference diagnostic, rather than process exit alone.
  Both matched workers retain the existing shared six-slot scheduler.
  Full regression: 543 tests, 542 passed and one skipped.


Current bring-up evidence on 2026-11-01:

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
  `403eb354e54c2dc8`; all 15 ports are verified. The SS/0 °C source screen passes in its original 1200–1500 ns
  window: CTRL variation 2.576 mV, feedback error 10.045 ps and quarter
  delay 634.257–634.482 ps. TT/25 °C also passes: CTRL variation
  3.014 mV, feedback error 7.853 ps and quarter delay 633.198–633.558 ps.
  FF/0 °C passes: CTRL variation 3.163 mV, feedback error 6.493 ps and
  quarter delay 632.701–633.013 ps. All three source gates are complete.
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
  screens before running native screening. Native qualification
  `dll_qualification/15cac0ba813a9333` now runs its 24-case screen (21 selected
  static offsets and three native loops); remaining 312 fixtures are held for
  the measured model. All 21 selected static offsets now pass, with exact
  SS/0, TT/25 and FF/0 coverage at 0, ±50, ±150 and ±300 ps.
  SS/0 acquisition now completes and passes: CTRL variation 1.849904 mV,
  feedback error 19.010343 ps and quarter delay 668.380426–668.485247 ps.
  The omitted-pulse section check also passes (668.412/642.798/633.563/632.785 ps);
  mean power is 8.451226 mW. TT/25 acquisition also completes and passes:
  CTRL variation 1.671669 mV, feedback error 10.840051 ps and quarter delay
  659.955500–660.204682 ps. Cadence and omitted-pulse section checks pass;
  section delays are 660.037/649.233/639.480/640.926 ps and mean power is
  6.897270 mW. Its actual deck, waveform and raw hashes match the report.
  FF/0 acquisition now also completes and passes: CTRL ripple 1.781503 mV,
  feedback error 7.417610 ps and quarter delay 653.018658–653.408804 ps.
  Cadence/marker checks pass and mean power is 6.365241 mW. All 24 initial
  screen cases pass and the continuation has remeasured their cached traces,
  advancing to the three-corner measured-model/stability stage.
  No measured-model or full-native qualification result is claimed. The
  handoff holds on failed gates, ended producers or changed inputs. Native
  acquisition/recovery at remaining required conditions remains unqualified.
- The early-publication RX (`rx_early_physical_v1`) passes physical DRC/LVS,
  strict topology checks and an independent exact-RC connectivity audit. All
  12 loaded admissions pass. All four native continuous-data duty/jitter/skew
  cases pass (128 words). Its original 480-condition aperture campaign
  (`rx_aperture/20b04dcf527af283`) is running. All 32 SS/40 °C conditions pass,
  across both clock/data slew endpoints, both edge/data polarities and setup/hold.
  Its largest guarded setup/hold bounds are 270/110 ps; the 200 ps clock/data
  subset remains 210/50 ps. All 32 SS/0 °C conditions also pass, with global
  guarded bounds 280/120 ps. All 32 SS/25 °C conditions now also pass, with
  guarded bounds 270/110 ps. Exact 32-condition coverage is verified separately
  at each SS temperature. SF/0 and SF/40 now also have all 32 conditions
  verified, with guarded setup/hold bounds 260/150 and 250/140 ps. Twelve
  SF/25 cases also pass: 172 of 480 conditions are complete and passing.
  Remaining conditions are outstanding and the full table is unqualified. The preceding three
  publication variants remain timing failures and cannot qualify this RX.
- Staged early-RX bundle `phy_candidate/8f364c6a8fdabafb` passes all 54
  generic/native functional cases (2,373,588 bits). Its complete six-fixture RC
  comparison
  passes, with all 12 actual reference/approximation traces verified by
  `rc_certificate.valid` against the current simulator, source and trace policy.
  The driver fixture passes with 0.396 ps maximum edge difference
  and 0.541 mV maximum plateau difference. The completed DLL fixture also passes:
  each of four outputs has 232 matching edges, with at most 0.785 ps crossing
  difference and 0.123 mV plateau difference (`dll_rc_diagnostic.json` beside
  the bundle manifest). These proofs cover this bundle's original networks;
  new DLL/analog/TX networks require their own comparison evidence. The largest
  difference across this complete suite is 2.992 ps for edges and 4.160 mV for
  plateaus, below the unchanged 20 ps/20 mV limits.
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
  `45fbff442fad8e43`). Both original receiver-replay stimuli are retained for
  this actual network at `receiver_replay/f55b204c5e5256b7`, including native
  digital loading and new PP/PN/CO observations. The captured-input fixture is
  complete and still loses nine rising and nine falling output edges. The
  complete sharper-edge control loses none. In the first missing captured
  negative pulse, the input remains negative for 526.689 ps and PP−PN reverses
  for 367.259 ps, but CO reaches only 0.665 V and does not restore the output.
  More input current alone is insufficient with the actual pin waveform.
  Full input-range/PVT behavior and complete-link timing remain unproven.
- Matched `buf_8` TX experiment (`tx_buffer8_physical`) passes the full 54-case
  RTL/native functional regression (2,373,588 bits;
  `tx_buffer8/ed7e08ca1a8e22f7`), physical flow/topology and independent RC audit.
  Its native TX network SHA256 starts `d849e11e2470e9ec`. Diagnostic
  `tx_candidate_link/b1c1b53a01dc8564` replaces only TX in the saved SS/40 °C/
  410 MHz/45% duty/+100 ps skew link, preserving every clock/data stimulus,
  analog/RX/DLL circuit and scoring window. Its native simulation completes and
  fails payload alignment. In 60–120 ns,
  25 receiver-pin rising crossings produce only 13 digital clock rises, versus
  16 with buf_4. The experiment is not selected; the staged assembly retains
  buf_4 and no release is published.
- Snapshot `tx_training_compare/18e4e22fc301ba34` compares the original buf_4
  and buf_8 designs over the same 20–35 ns training interval. Maximum
  digital clock slew improves from 357.342 to 194.375 ps. The shortest negative
  receiver-pin clock pulse narrows from 556.159 to 460.960 ps, and the weakest
  negative peak decreases from 121.521 to 78.663 mV. Both designs miss six
  restored edges under the same per-input-period diagnostic. The completed TX
  payload run independently fails, as recorded above; the
  training observations themselves issue no qualification verdict.
- Receiver decision/restoration candidate `receiver_layout/784114a01817b339`
  retains doubled input tails, doubles decision-stage current/mirror/input widths,
  and reduces the CO inverter gate from P16/N8 to P4/N2. Three inverter stages
  restore the original output polarity and P16/N8 final drive. Source invariants,
  DRC/LVS and independent RC audit pass; native network SHA256 starts
  `30154843ced35188`. Captured and sharper-input native replays are active at
  `receiver_replay/cb6fffffb0809887`, with PP/PN/CO and both restoration nodes
  observed. The complete captured case loses nine rising and nine falling edges,
  unchanged from the input-tail-only candidate. The sharper control also
  completes and loses one rising and one falling edge; the diagnostic is terminal.
  Electrical improvement and PVT qualification remain unproven.
  Isolated full-link fixture `receiver_candidate_link/467b30dda15cf743` is
  prepared with only the analog receiver replaced. It retains buf_4 and the
  entire original stimulus/channel/scoring. Its run gate remeasures both
  completed replays and requires zero missing edges before allocating a slot;
  no full-link run or passing receiver result is claimed.
- Standalone `continue_native_dll.py` waits for the selected native screen owner
  to pass and exit, then rechecks its captured screening evidence. Measured
  SS/TT/FF models gate full native expansion; verified full-native evidence
  gates all 15 model corners. Failed or changed evidence holds progression,
  with no resident-dispatcher edits or release claim.
- Receiver placement experiment `receiver_layout/f2492f47d0df06ca` preserves
  the preceding decision-current source and all finger banks, changing only
  device-bank order. DRC/LVS and independent RC audit pass; exact network SHA256
  starts `b6d987db3ef27b9b`. Incident routing capacitance falls PP 109.141→66.413 fF,
  PN 115.726→62.576 fF and CO 45.447→42.437 fF; CT rises 138.108→165.735 fF.
  These exclude device/MIM capacitance and count full coupling values. Native
  replay `receiver_replay/17c5587a5df91855` completes its captured case and loses
  nine rising and nine falling edges. Its complete sharper control also loses
  seven rising and seven falling edges; the diagnostic is terminal. Both
  original stimuli and loads are retained. No recovery improvement is established. Matching isolated link
  fixture `receiver_candidate_link/98985df18860704a` is prepared and held behind
  both completed, zero-missing-edge replays. Both decision-current placements
  fail the captured-input cadence test, so neither is selected for integration.
- Schematic tracked-clamp comparison `receiver_clamp/e888b13239fc158e` is running
  under the shared simulator budget. It adds a diode-connected replica inverter
  with the first restoration stage's P/N ratio and two parallel precision-poly
  units from CO to the replica trip point. Three fixtures compare unclamped and
  clamped circuits on captured pins, then clamped sharper inputs. Analog cores
  use schematic fingers; the shared bias and native early RX load are retained.
  The complete unclamped/captured schematic control recovers every edge, with
  no missing rising or falling transition and diagnostic latencies 296–413 ps.
  Its CO reaches 1.792 V. The clamped/captured case also completes with zero
  missing edges; its latency is 309–442 ps and CO_TRACK moves 0.503–1.127 V,
  so reference stiffness and native performance remain unproven. Its sharper
  control also completes with zero missing edges; all three source comparisons
  are complete. The schematic/native
  contrast implicates extracted parasitics, but does not isolate wire capacitance
  from explicit extracted device junction geometry. No physical receiver fix
  or clamp improvement is claimed yet.
- `layout_receiver_clamp_candidate.py` and `probe_receiver_clamp_candidate.py`
  prepare the physical/native path behind complete zero-missing-edge clamped
  source replays. They remeasure actual source traces, require exact source
  agreement, preserve original device order except the four added clamp devices,
  and bind source/physical/native proofs. The real incomplete-source preflight
  rejects layout without creating an artifact. Full-link gating selects the
  clamp replay's own verifier. Layout `receiver_layout/f576c6a98d893590`
  now passes DRC/LVS and independent RC audit (85 devices, nine ports; native
  SHA256 starts `ad5ac6a6d26b0b33`). Its actual native replay
  `receiver_replay/7b46eef599fb6e55` is running. Matching full-link fixture
  `receiver_candidate_link/a3b07823d72b7aeb` is prepared behind native replay
  gates. The complete captured replay loses nine rising and nine falling edges;
  its sharper control continues. At its first lost pulse, CO reaches only
  0.789 V while CO_TRACK moves 0.508–0.823 V. No full-link run is admitted.
- Selected receiver component campaign `receiver_components/06ef0f1a751e6c5d`
  has all 60 original schematic/native static/rate PVT fixtures prepared.
  Baseline references verify, and the real run preflight reconstructs all
  fixtures before holding at incomplete loaded-native replay evidence. No new
  component simulation starts. Complete/unique coverage, unchanged stimuli/load/
  scoring and fresh waveform reanalysis are enforced. Loaded replay admission
  requires exactly one output edge per input period, rejecting extra pulses as
  well as missing ones. Baseline component proofs
  and canonical pointers are retained.
- Stronger schematic clamp `receiver_clamp/86e622030245e729` completes with
  P32/N16 reference widths and four parallel poly units (about 500 Ω). Other
  devices and restoration stages remain unchanged. All three original controls
  pass with exactly one output edge in each of 47 checked periods. CO_TRACK
  spans 0.647–0.962 V in the captured case, less movement than the first clamp;
  its diagnostic latency is 313–516 ps. Physical/native comparison is still
  required and no native improvement is claimed.
- Stronger-clamp layout `receiver_layout/feb7596968046dd1` now passes DRC/LVS
  and independent RC audit (91 devices, nine ports; native SHA256 starts
  `32579bcd62e88ff5`). It moves only the added replica/clamp devices beside CO;
  existing receiver devices and connections are retained. Actual native replay
  `receiver_replay/13ab38f8a7b8e217` runs under the unchanged six-slot budget.
  Its completed captured-input case misses 11 rising and 11 falling edges,
  worse than the original receiver's nine of each. The sharp control also
  completes and misses nine rising and nine falling edges. The native owner
  exits successfully after producing both diagnostic reports; the follow-up
  records `held_for_diagnosis` for failed clock recovery and starts no component
  or link simulations. The stronger clamp is not selected for qualification.
  Matching link fixture `receiver_candidate_link/37d95b09d5fb0059` and 60-case
  component campaign `receiver_components/90fff4b7107aa5ae` remain held behind
  its failed loaded native gate. The component preflight verified original fixtures;
  neither downstream campaign started a simulation. Stronger and
  first-clamp verifiers are selected explicitly; no native improvement is claimed.
- Host continuation `continue_receiver_candidate.py` waited on that actual native
  owner and held the prepared component/link jobs for failed one-to-one
  clock recovery. It binds all manifests/producers, repeats scientific checks
  in the children and preserves both running jobs on failure. No release is
  promoted by diagnostics. Its receipt is under the native replay's `followup/`.
  The stronger clamp's completed first-pulse observation has CO peak 0.822 V
  with RESTORE0 above 1.726 V; the output clock does not fall in that interval.
  Routing inspection of the first→stronger clamp finds PP 115.776→122.001 fF,
  PN 122.274→128.498 fF and CO 58.027→73.967 fF; other observed wire sums
  are unchanged. These incident capacitances do not isolate the electrical
  effect of strengthening the reference or establish a causal timing result.
- Wider input-pair source comparison `receiver_clamp/4e55a995d239fb38` is active.
  It changes only the four complementary input devices from 20 to 40 µm,
  retaining tail-device bias, stronger clamp and restoration. Its original
  three controls and native shared bias/digital load remain intact. The captured
  source case completes with exactly one output edge in all 47 checked periods,
  no missing/repeated edges and diagnostic latency 324.978–448.846 ps. Its
  unchanged unclamped control also passes. The sharp-input source control now
  completes; all three cases recover exactly one edge in every checked period.
  Physical/native improvement remains unproven.
  Dedicated layout/replay producers now bind the exact 40 µm input source and
  its three complete, one-to-one source controls. They reject earlier clamp
  evidence and preserve native shared bias, digital load, nine-port order and
  replay timing. Layout `receiver_layout/4cea0a2ca0f9868e` passes DRC/LVS
  (95 devices, nine ports) and the independent RC connectivity audit. Native
  network SHA256 starts `7f2680cc72bcaf63`; replay `5adb1f717c66c41e` is queued
  under the six-slot limit. Incident PP/PN wire sums are 124.217/131.377 fF;
  CO remains 73.967 fF (`receiver_loading/c66f016bc3569690`).
  Host service `openlvds-wide-input-native-continuation-v2` runs those
  physical/RC/native gates in sequence. It freezes
  source and parent manifests plus downstream producers; failed gates hold the
  pipeline. It stops before component/link qualification and release selection.
  Its first invocation stopped after systemd unloaded the successful transient
  source unit. The corrected predicate requires complete reports and repeats
  the exact waveform gate; the original failure receipt is archived under
  `native_continuation_history_516799b`. No scientific simulation was restarted.
  After the previous native owner/follow-up terminated, the downstream dispatcher
  gained explicit `strong_wide_input` source and native-verifier selection.
  Future component/link fixtures retain original stimuli and scoring; their
  native replay gate still requires complete, one-to-one clock recovery.
  Component root `receiver_components/f82998633770e370` prepares all 60 original
  fixtures, and link root `receiver_candidate_link/a1fe429613422650` retains the
  original loaded link diagnostic. Host service `openlvds-wide-input-receiver-followup`
  waits on the native continuation and starts them only after both native cases
  recover every edge exactly once. No component/link simulation has started.
  The live native trace already fails the first short pulse: over 24.5–26.5 ns,
  CO peaks at 0.810757 V, RESTORE0 remains above 1.744 V and the output clock
  has no falling crossing in 24–27 ns. Both original 80 ns controls continue
  to completion; these partial observations are not a qualification verdict.
  The captured native case now completes with nine missing rising and nine
  missing falling edges. This improves on the preceding strong-clamp count of
  11 each, but matches baseline pulse loss and does not pass the native recovery
  gate. The sharp control now also completes with nine missing rising and nine
  missing falling edges. Native continuation and component/link follow-up both
  record `held_for_diagnosis`. Neither downstream campaign starts a simulation.
  The wider-input candidate is not selected for qualification.
- New source comparison `receiver_clamp/af769bd4767fe6c2` restores the five
  decision-stage devices to original widths (tail 64 µm, differential pair
  and mirror devices 8 µm). It retains doubled input tails, original 20 µm
  input pairs, stronger clamp and three restoration stages. Earlier native
  traces show a larger first-pulse PP−PN excursion before the decision-stage
  doubling; reducing its input/device/routing load is a hypothesis, not a
  demonstrated improvement. Three structural tests pass. The original source
  campaign is active under the same six-slot budget; no physical result or
  release selection is claimed.
  Dedicated `layout_receiver_light_decision_candidate.py` and
  `probe_receiver_light_decision_candidate.py` bind `decision_scale=1` and the
  exact original-decision source. Physical preparation requires all three source
  cases complete with exactly one edge per input period; native preparation
  requires DRC/LVS, independent RC audit, matching source and all captured proofs.
  Host service `openlvds-light-decision-native-continuation` waits on its actual
  source owner and runs those stages in sequence. It reuses the corrected
  transient-unit handling and stops on any failed gate. Seven source/physical
  structural tests pass; no physical/native result is claimed.
  Its captured source case now completes with one missing rising edge and one
  missing falling edge around the 58.920 ns negative pulse (514.802 ps,
  83.068 mV peak). CO peaks at 0.948352 V over 58.7–60.7 ns, but the restored
  clock remains above 1.702 V. The source gate therefore cannot admit layout;
  its sharp control now also completes, with no missing edges. All three source
  cases are complete, but the captured failure remains. Native continuation
  records `held_for_diagnosis` after the physical source gate rejects lost
  clock edges. No physical artifact, RC extraction or native replay is produced
  for this candidate.
- Source comparison `receiver_clamp/7002b1f71a4ff337` removes only XCLAMP2/3,
  reducing parallel clamp units from four to two while retaining the original
  decision sizes, doubled input tails, strong replica reference and restoration.
  This tests reduced output loading after the smaller-decision source failure.
  Two structural tests pass. Service `openlvds-light-clamp-source-screen` is live
  and has completed its unchanged source control with no missing edges. Its
  modified captured source case now completes with exactly one output edge in
  all 47 checked periods and diagnostic latency 301.890–510.435 ps. The sharp
  source control now also passes; all three controls have exactly one edge per
  checked period. No native improvement is claimed;
  all original controls and scoring requirements remain.
  Dedicated reduced-clamp physical/native producers use identity
  `light_decision_1k_clamp`, original decision scale and two parallel clamp units.
  They reject source evidence from the four-unit candidate and preserve original
  pin stimuli, bias, digital RX load and scoring windows. Host service
  `openlvds-light-clamp-native-continuation-v2` waited on its actual source owner,
  then runs layout, independent RC audit and both native controls only after
  all source gates pass. The downstream dispatcher selects its exact source
  factory and native verifier. Physical root `receiver_layout/4e540d457ca789a4`
  passes DRC/LVS (77 devices, nine ports) and independent RC audit. Native network
  SHA256 starts `b8e821dc164ef55a`; replay `5c2e6e425ac65e58` now runs captured
  and sharp controls concurrently, each with its own lease from the six-slot
  pool. Incident PP/PN/CO wire sums are 102.831/109.899/44.786 fF
  (`receiver_loading/2b2f0d4e931336c9`); CL/CT sums are 25.001/70.874 fF.
  These routing sums do not establish effective AC load or native timing.
  The prior waiting continuation was retired before the concurrency change;
  its receipt is archived as `native_continuation_history_d6f80e5`. No live SPICE
  process was stopped. Tests verify independent fixture starts, separate leases,
  deterministic report order and completion of the other fixture after one fails.
  All 60 component fixtures (`receiver_components/57488d46b26d09ec`) and the
  original loaded link diagnostic (`receiver_candidate_link/cb4be133271a71ea`)
  are prepared. Service `openlvds-light-clamp-receiver-followup` waits for complete
  one-to-one native recovery before running them; no downstream result is claimed.
  Component preflight reconstructs all 60 fixtures and correctly holds at the
  incomplete native gate, with zero execution receipts or raw traces. Its
  `gate_preflight.json` binds the manifest, verifier and simulator provenance.
  The live captured native trace still fails the first short pulse: over
  24.5–26.5 ns CO peaks at 0.859699 V and RESTORE0 remains above 1.667761 V;
  there is no output falling crossing in 24–27 ns. CO_TRACK spans
  0.738464–0.836576 V in that interval. Both complete original controls continue;
  no partial trace supplies a qualification verdict.
  Both native controls now finish: captured misses 10 rising and 10 falling
  edges; sharp misses nine of each. Cached waveform reanalysis confirms both
  reports. Native continuation and downstream follow-up record
  `held_for_diagnosis`; neither the prepared component nor link campaign starts
  a simulation. The reduced-clamp candidate is not selected for qualification.
- New source comparison `receiver_clamp/0244d3fb608b9d06` connects the two CO
  resistors to the existing 1.2 V VREF port instead of CO_TRACK. The replica is
  retained unloaded as an observation node; every device size and all other
  connections are unchanged. This tests a fixed reference against movement of
  the loaded replica, using the existing fixture reference and fixed supplies.
  Two structural tests pass. Service `openlvds-vref-clamp-source-screen` has
  completed all three source controls with exactly one edge in each of their
  47 checked periods. The modified
  captured case recovers exactly one output edge in all 47 checked periods,
  with latency 260.642–508.359 ps. CO spans 0.387500–1.533384 V, while the
  unloaded replica remains near 0.832621 V. No native improvement is claimed. Reference
  loading and full input-range/PVT behavior still require qualification if selected.
  Dedicated VREF-biased physical/native producers bind the exact resistor
  reference and unloaded-monitor topology. They reject earlier tracked-reference
  source evidence, retain original replay stimuli/bias/digital RX load, and run
  both native controls concurrently within the shared six-slot pool. Downstream
  dispatch selects this variant's exact source factory and waveform verifier.
  Host service `openlvds-vref-clamp-native-continuation` rechecked the completed
  source controls, then built `receiver_layout/c9b54df2758e600a`. It passes
  DRC/LVS (77 devices, nine ports) and independent RC connectivity audit.
  Native network SHA256 starts `36e80ac228591149`; both original controls now
  run concurrently at `receiver_replay/77252e9aa3abb333`. Incident PP/PN/CO wire
  sums are 102.831/109.899/42.695 fF (`receiver_loading/3b41530840a8d2e7`), not
  effective AC loads or timing qualification.
  All 60 component fixtures (`receiver_components/a09b869f2ffff52b`) and the
  loaded link diagnostic (`receiver_candidate_link/3635f229cd4efe04`) are prepared.
  Their preflight reconstructs every component fixture, then holds at the
  incomplete native gate with no simulation started (`gate_preflight.json`).
  Service `openlvds-vref-clamp-receiver-followup` waits for complete one-to-one
  native recovery before running them. No native/component/link pass is claimed.
  The live native captured trace restores the first previously lost short pulse:
  over 24.5–26.5 ns CO reaches 1.152635 V, RESTORE0 falls to 0.329422 V,
  RESTORE1 rises to 1.780347 V and RXCLOCK falls near 25.837800 ns. The trace
  prefix reaches 28.772 ns at inspection. Both complete native controls continue;
  this partial observation does not qualify clock recovery or link timing.
  A later prefix through 62.890 ns shows failure on the weakest negative pulse
  at 58.920 ns: CO reaches 1.060980 V and RESTORE0 falls to 0.718403 V,
  but RESTORE1 reaches only 0.551259 V. No RXCLOCK falling crossing occurs
  before the next same-polarity input edge at 61.213 ns. Complete reports remain
  outstanding; the next comparison targets the internal restoration stages.
  Both native controls now complete. Captured inputs miss one rising and one
  falling edge; the sharp control misses none. Cached waveform reanalysis
  verifies both reports. Native continuation and downstream follow-up hold for
  failed captured recovery; neither component nor link simulation starts.
  This VREF-biased candidate is not selected for qualification.
- Source comparison `receiver_clamp/d2827cbf76f9eb80` retains VREF bias and all
  input/decision devices, but doubles the first two restoration stages using
  existing inverter definitions: P/N widths become 8/4 → 16/8 → 16/8 µm.
  Final output drive and overall polarity are retained. Two structural tests
  verify only those instance bindings change and the control remains identical.
  All three original source controls now complete: each recovers all 47 checked
  periods with no missing or repeated edges. Captured-source latency is
  237.406–494.897 ps, versus 260.642–508.359 ps before stage strengthening;
  the weakest negative pulse improves from 276.441 to 249.913 ps. These source
  results do not prove extracted improvement.
  Dedicated physical/native producers bind identity `vref_fast_restore` and
  widths [[8,4],[16,8],[16,8]], rejecting the previous restoration topology or
  source evidence. They retain VREF bias, unloaded monitor, all nine ports,
  original stimuli/bias/native RX load and scoring windows. Both native controls
  use separate shared simulator leases. Exact downstream source/verifier
  selection and parallel completion/error behavior are tested. Service
  `openlvds-fast-restore-native-continuation` waits on the actual source owner,
  then requires all three source controls, physical DRC/LVS and independent RC
  audit before native replay. Physical root `receiver_layout/64ae7a93d207703b`
  passes DRC (zero errors), LVS and independent RC audit, with 78 devices and
  the original nine ports. Native network SHA256 is
  `b6e0bec697e9ef60f8677d77e1817d9c0e70cd26ab45445ee57ead09a36a4d69`.
  Both original native controls complete in `receiver_replay/93c5ecd2ff603292`:
  each recovers all 47 checked periods with zero missing or repeated edges.
  The weakest captured pulse now produces RXCLOCK falling/rising crossings at
  59.977506/60.493634 ns; RESTORE0 reaches 0.456733 V and RESTORE1 1.770205 V.
  Captured latency spans 804.040–1244.370 ps. This passes the replay diagnostic,
  not component coverage, aperture or full-link qualification.
  Loading receipt `receiver_loading/820ed53b4961c8bb` reports incident CO,
  RESTORE0 and RESTORE1 wire sums 44.360, 47.681 and 58.947 fF. These exclude
  device capacitance and do not establish effective AC load or timing.
- `queue_receiver_followup.py` now waits for that complete native continuation,
  requires both original replay controls to recover every checked edge, then
  prepares the 60 schematic/native component cases and the saved loaded-link
  diagnostic. The existing follow-up independently remeasures native evidence
  before acquiring simulator slots. Service
  `openlvds-fast-restore-component-link-queue` is waiting; its frozen code,
  requirements, upstream manifest and original link receipts are under
  `receiver_clamp/d2827cbf76f9eb80/component_link_continuation/`. Six targeted
  tests cover active/incomplete/failed owners, selection, edge loss/repetition,
  path confinement and the prepare/run handoff. These diagnostics cannot
  qualify the PHY.
  Container `/work/OpenLVDS` output paths are translated to the host workspace
  before validating their artifact kind and confinement. The waiting queue was
  retired before this producer fix, with its original receipt preserved in
  `component_link_continuation_history_6438c51`; it had no scientific child.
  Container inputs use repository-relative paths because `--containall` exposes
  this repository only at `/work/OpenLVDS`. The handoff test checks both path
  directions. The second waiting receipt is retained in
  `component_link_continuation_history_bafce31`, also without a scientific child.
  Replacement service `openlvds-fast-restore-component-link-queue-v3` retains
  the same native gate, stimuli, component coverage and simulator budget.
  Actual container preparation produces component root
  `receiver_components/58bb3aa28d907d28` and loaded-link root
  `receiver_candidate_link/0dee72b71f4525df`. Component preflight reconstructs
  all 60 fixtures and holds before any simulation while native reports are
  incomplete. After both native reports pass, the queue automatically starts
  component/link diagnostics; both independently recheck native waveforms.
  The first three source static cases (TT at 0/25/40°C) fail. At TT/25, expected
  high outputs fail at common modes 0.05/0.2/0.6 V, while 1.2/1.8/2.35 V pass.
  Actual PP/PN differential polarity remains correct, but CO stays at
  1.140763/1.137516/1.127988 V in the failed samples and Q remains low. The
  original source fixture passes these samples with CO at
  0.492830/0.480999/0.451381 V. This identifies a DC decision/clamp interaction
  to isolate; the comparison also changes input-tail sizing and cannot assign
  causality to the clamp alone. The campaign continues without changing gates.
- Matched diagnosis `receiver_static_diagnosis/a6dc85becd2ad09c` now isolates
  that DC cause: it removes only XCLAMP0/XCLAMP1 from the completed TT/25
  source fixture and leaves every transistor, helper, supply, load, input and
  sampling time unchanged. All 12 static samples pass, versus three failed
  expected-high samples in the original. At common modes 0.05/0.2/0.6 V,
  CO falls to 0.560407/0.538582/0.490294 V and Q reaches 1.8 V. The new runner
  remeasures the original control, captures parent/current proofs, reconstructs
  the exact intervention and uses a shared simulator lease. This is TT/25
  source DC evidence only, without native timing or full PVT qualification.
- Source root `receiver_clamp/2c86c40885f97e87` tests that same unclamped core
  with the stronger 8/4 → 16/8 → 16/8 restoration chain. Service
  `openlvds-unclamped-restore-source-screen` queues the original three 80 ns
  source controls with unchanged scoring. Legacy `clamped_*` task names here
  denote the modified cases; the new factory removes both actual CO clamps.
  The unloaded replica monitor remains untouched. One structural test proves
  the modified core equals the passing matched DC intervention and preserves
  the existing control. No physical/native improvement is claimed.
  Dedicated physical/native producers now bind identity
  `unclamped_fast_restore`, `decision_clamped=false`, zero clamp units and no
  clamp reference. They retain the exact source, unloaded monitor, nine-port
  order, restoration widths and original native bias/digital load. Layout
  requires all three complete source traces with one edge per checked period,
  followed by DRC/LVS and an independent RC audit. Six source/physical identity
  tests pass; parallel replay tests cover both completion and one-child
  failure, including truthful unclamped result metadata. Service
  `openlvds-unclamped-restore-native-continuation` waits on the actual source
  owner before attempting these stages. No new layout or native result exists
  while the source screen remains incomplete.
  All three source controls now complete all 47 checked periods with no
  missing or repeated edge. Modified
  captured latency spans 291.168–403.633 ps; the weakest 514.802 ps/83.068 mV
  negative pulse is recovered with 403.633 ps latency. Physical root
  `receiver_layout/cc8468627923265c` passes zero-error DRC, LVS and independent
  RC audit, with 76 devices and the original nine ports. Native network SHA256
  is `5479cc708d5f7c06815b5286b5a632e386d981bfda62057c8bdd4cd08b28352d`.
  Both original controls are running in `receiver_replay/7be8ec522902db81`
  under separate shared leases. Loading root `receiver_loading/11bbf00548f00ecc`
  reports incident CO wire sum 35.917 fF versus 44.360 fF with the clamp;
  these sums exclude device capacitance and do not prove effective AC load
  or timing. Both native controls now complete: captured input loses nine
  rising and nine falling edges; the sharp control loses none. Cached trace
  reanalysis reproduces both reports. Native continuation and follow-up hold
  for failed recovery. No component/link simulation starts for this variant.
  A captured native prefix reaches 27.380 ns and misses the first short pulse:
  over 24.5–26.5 ns CO peaks at 0.676372 V, RESTORE0 stays above 1.783624 V,
  RESTORE1 stays below 0.000316 V and Q stays above 1.799909 V. No output
  falling crossing occurs in that interval. This identifies the first
  restoration threshold as the local failure point. Both complete native
  controls continue; no downstream component/link simulation is admitted.
- The current VREF-clamped component campaign has a numerical slowdown in
  `schematic_receiver_rate_ss_40`. Its simulator is confirmed active and using
  CPU, but a saved prefix advances only about 7 ps over several minutes near
  25.84 ns. Its last 10,000 saved samples span 1.244 ps, with timesteps
  1.29e−17–4.13e−16 s, fixed input pins 1.075/1.325 V and Q within
  1.799942–1.799946 V. This establishes timestep collapse, without identifying
  its internal cause or a qualification verdict. No solver tolerance, stop
  time or scoring gate is changed, and the live simulation is not interrupted.
  This case subsequently recovers and completes successfully after 2678.057 s,
  with original valid-high/low dwell minima 825.637/1504.218 ps. All 15 source
  rate cases now pass; all 15 source static cases fail. The remaining native
  component campaign continues. The numerical slowdown was finite and did not
  require a solver change or restart.
- Matched DC matrix `receiver_static_matrix/1ac68453f143818d` now prepares the
  clamp-removal intervention at all 15 required source PVT points. Every
  original static case is complete; preparation verifies each waveform,
  producer, runtime and fixture before removing only the two resistors.
  `receiver_static_matrix.py` enforces exact process/temperature coverage and
  child-to-parent identity, captures every child manifest and remeasures cached
  traces. Service `openlvds-receiver-unclamped-static-matrix-v2` runs cases
  sequentially, with each new simulation acquiring its own shared lease.
  Two targeted tests reject missing/duplicate/mislabeled cases and native/rate
  substitutions. This is source DC diagnosis only; it cannot establish rate,
  extracted, aperture or PHY qualification. No aggregate electrical result is
  claimed while the matrix is incomplete.
- The earlier matrix `dc93e971d02bb60c` completes TT/0 with all 12 unclamped
  samples passing, then holds on cached TT/25 provenance. Its re-preparation
  rewrote JSON dictionary order, changing manifest bytes; actual waveform
  reanalysis differs only in `manifest_sha256`. It is terminally failed, with
  `retirement.json` and original producers preserved. The corrected producer
  sorts code identities and preserves existing manifest bytes, rejecting
  changed content or JSON types. Matrix failures now save a terminal held
  receipt. Seven targeted tests pass; a second independent preparation process
  preserves all 16 fresh manifest hashes (`preparation_recheck.json`). The new
  matrix reruns the cases under its new producer rather than accepting the
  old cache. The old traces and reports remain unchanged.
- Loaded-link diagnostic `receiver_candidate_link/0dee72b71f4525df` completes
  its original 188.049 ns run and fails: no correctly ordered payload preamble,
  with `sampling_margin_passed=false`. Waveform SHA256 is
  `71970afeaaaed89b0a4e86b0efe9e46c2741b5bfb06fd943da6d7dfe577cbea6`.
  The earlier read-only prefix at
  137.628 ns covers the payload interval, but the unchanged decoder reports
  no correctly ordered preamble. Over 60–120 ns, matched edge transport finds
  no missing/extra edges in 47 clock and 16 data periods. Clock latency spans
  804.843–1247.376 ps; data latency spans 761.984–1432.602 ps. Observed clock
  captures at 73.893010 and 83.627458 ns lie only 13.934 ps before the next
  data edge and 63.827 ps after the preceding data edge respectively. These
  narrow separations can explain corruption after edge recovery, but without
  a decoded preamble the official aligned payload margins remain undefined.
  The original publication window and 200 ps margin gate remain.
- `qualify_unclamped_receiver.py` selects the exact unclamped source/verifier
  in the existing component and loaded-link checks without editing captured
  producers. Its identity requires no clamps, the unloaded monitor and exact
  restoration/input/decision sizing; both scientific identities capture the
  new selector code. Component root `receiver_components/599036f3ae6f5004`
  prepares all 60 original fixtures. Actual preflight reconstructs all 60 and
  holds at incomplete native replay, with no execution receipt or raw trace;
  `gate_preflight.json` captures this check. Link root
  `receiver_candidate_link/83066baeca7824fe` retains the original loaded inputs,
  payload, publication window and margin gate. Service
  `openlvds-unclamped-restore-receiver-followup` waits on both complete passing
  native controls, then lets each child independently remeasure that evidence
  before simulation. No component/link pass is claimed. Two targeted selector
  tests verify exact dispatch, captured code and restoration after a failure.
  This separate entry point now also supports `unclamped_lvt_restore`, selecting
  its exact LVT factory and native verifier and requiring the declared first
  NFET model. Mixed standard/LVT metadata is rejected. Three selector tests
  pass. Before this extension, the failed standard-device follow-up was
  verified terminal and all live manifests were checked not to capture this
  entry point. No active experiment's producer changed, and no LVT component
  or link campaign is prepared before its physical/native gates complete.
- `receiver_lvt_restore_experiment.py` proposes a controlled first-stage
  threshold change: clone the existing P8/N4 helper and change only its NFET
  model to `sky130_fd_pr__nfet_01v8_lvt`. All sizes, nodes, other helper
  definitions, unclamped input/decision circuitry, monitor and later stages
  remain. The pinned PDK contains all corner models and Magic PCell procedures
  for this device. Three structural tests prove the single device-model change,
  unchanged control and exact static/source intervention identity. Static root
  `receiver_lvt_static/6dd7065538873479`, service
  `openlvds-receiver-lvt-static-screen`, queues the original TT/25 static
  fixture with unchanged supplies, common modes, 100 fF load and thresholds.
  The original clamped fixture is its recorded control; the unclamped standard
  NFET result is available separately in the matched DC matrix. This LVT
  TT/25 screen now completes all 12 static samples successfully. Source root
  `receiver_clamp/4ea0f56c1098842a`, service
  `openlvds-lvt-restore-source-screen`, queues the three original clock source
  controls. All three source controls now pass, each with exactly one output
  transition in all 47 checked periods and no missing/extra edges.
  Its unchanged control and modified captured-clock case now complete with
  one output edge in all 47 checked periods and no missing/extra edges.
  Modified latency spans 292.325–377.720 ps; the weakest negative pulse has
  377.720 ps latency. The sharp control also passes. This source result does not establish native recovery.
  Dedicated LVT physical/native producers now require that exact passing
  TT/25 static screen plus all three complete passing clock source controls.
  The static gate remeasures actual cached waveforms and binds the exact
  receiver closure, preserving every original DC sample. Identity records
  `unclamped_lvt_restore` and the explicit first NFET model, rejecting standard
  NFET evidence, any CO clamp, wrong sizes and missing/failed static samples.
  Nine targeted gate tests and parallel completion/error tests pass; the real
  completed TT/25 screen also passes this gate. Service
  `openlvds-lvt-restore-native-continuation` waits on the live source owner
  before layout, DRC/LVS, independent RC audit and native replay. Physical
  root `receiver_layout/6642a01b473f6aa8` now passes DRC (zero violations), LVS
  and independent RC connectivity audit: 76 devices, nine ports. The exact
  reduced network hash starts `82caea7129b27b35`. Loading root
  `receiver_loading/3872354b6c62bd80` measures PP/PN/CO incident wire loads
  100.38129/107.54226/35.91650 fF, essentially unchanged from the standard-NFET
  unclamped candidate. This excludes device/MIM loading and is not a timing proof.
  Native replay `receiver_replay/eea365798223235d` runs both original 80 ns
  controls. Its captured trace has already failed the first short-pulse window
  (24.5–26.5 ns): CO peaks at 0.673319 V, RESTORE0 stays above 1.765710 V,
  and Q has no falling 0.9 V crossing. The captured run has since completed all 80 ns: nine rising and nine falling
  input periods lack their output transition. Sharp control also completes all 80 ns with no missing transition.
  Cached reanalysis repeats both reports. The captured failure holds both
  native continuation and the downstream component/link follower; all 60
  prepared LVT component fixtures still have zero executions/raw traces.
  Exact LVT follow-up roots `receiver_components/101d54670c0ac820` (60 fixtures)
  and `receiver_candidate_link/004b4f282fcea4fc` are prepared. Actual component
  preflight stops at the incomplete-native gate with zero simulation executions
  or raw traces. Service `openlvds-lvt-restore-receiver-followup` waits for the
  original two complete passing native controls; no downstream result is claimed.
- Completed clamped-link waveforms expose an upstream clock-eye limit as well
  as receiver sensitivity. In 60–120 ns, three of 49 RX clock pulse centers
  fall below the original 100 mV threshold; minimum is 85.216 mV at
  104.178171 ns. The TX-side differential is already small before the channel:
  four of 50 centers in 58.8–118.8 ns are below 100 mV, minimum 76.417 mV.
  This is interval-specific eye evidence; TX center counts use the RX threshold
  only as a diagnostic, not a replacement for driver qualification.
  `probe_driver_internal.py` prepares root `driver_internal/c9c5ccd60b8fbe69`
  with identical native library, circuit, stimulus and 188.049 ns run. Only
  unloaded voltage probes are added at AD/AB, L/R and DP/DN named buses for
  both driver instances. Scope validation passes; two targeted tests prove
  exact deck instrumentation and reject missing/ambiguous nodes. Service
  `openlvds-native-driver-internal-observation` is queued. No stage delay cause
  or driver improvement is claimed before its measured trace is available.
  A read-only 20–35 ns prefix now shows AD/AB simultaneously below 0.9 V for
  172.825–173.229 ps and above 0.9 V for 150.429–152.213 ps per interval.
  At the 1.65 V observation level, DN high widths span 123.759–734.732 ps,
  versus DP 1310.171–1488.294 ps; DN peaks at 2.837657 V. These are measured
  crossing widths, not the actual inverter switching thresholds or a claim
  about which transistors conduct. External TXCLOCK/CP/CN/RCP/RCN traces match
  the original on a 5001-point training grid with zero interpolated difference.
- Source driver comparison `driver_restore/cff36fa92d24e01b` tests original
  P48/N40 restoration against P64/N24, retaining 88 µm total gate width per
  inverter. Private helpers change only the two 3.3 V restoration buffers in
  the driver level converter. The matched control and candidate both use
  schematic drivers in the same saved native link; unrelated circuits,
  supplies, stimulus, load, payload, publication window and full 188.049 ns
  transient remain. Three structural/fixture tests pass; actual preparation
  verifies protected closures and probe/node names. Service
  `openlvds-driver-restore-source-comparison` runs both independent cases
  through the shared slot budget. It is source-only evidence, without native
  driver or PHY qualification; no improvement is claimed before both finish.
- Xyce 7.10.0 parses the actual native receiver replay successfully in a
  parser-only check (`xyce_compatibility/ba10c72ce84ed18a`). It reports BSIM4
  4.5→4.6.1 substitution. Inspected upstream commit `e5b7b9bb5b221630` retains
  that fallback. No speed or numerical-equivalence result is claimed, and no
  running qualification campaign changes runtime.
- Last full unit suite: 417 tests, 416 passed and one skipped in the pinned ngspice
  environment. The shared native budget
  remains six real simultaneous simulator leases. Captured active producers,
  fixed supplies, PVT coverage, voltage windows and timing margins are unchanged.
- Full DLL/PVT/model/recovery/readiness/operating-point evidence, all 480 RX
  boundaries, certificates for any replacement networks and the full link matrix remain
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


Bring-up update on 2026-11-01 (input-bias investigation):

- Corrected matched DC matrix `receiver_static_matrix/1ac68453f143818d` is
  complete; an independent cached run remeasures all 15 waveform pairs. Twelve
  modified cases pass. SF/0, SF/25 and SF/40 fail only the original 130 ns
  sample (2.35 V common mode, P=2.3 V, N=2.4 V). Q remains high; CO is
  0.703679/0.726471/0.743371 V respectively. Thus clamp removal fixes the
  low-common-mode loading problem but does not establish full DC coverage.
- The LVT native initial operating point has CT=0.0467892 V and NBC=0.936557 V,
  with PP=1.07999 V and PN=0.903624 V. The low tail drain voltage motivates
  checking input common-mode/headroom; it does not by itself prove a device
  operating region or establish the short-pulse cause.
- New isolated `receiver_input_bias_experiment.py` retains standard-NFET
  unclamped 8/4 → 16/8 → 16/8 restoration and doubles only the four existing
  PP/PN ground-branch resistor lengths, 1.25 → 2.5 µm. Nominal Thevenin bias
  rises from 0.9 to 1.028571 V, with resistance 1 to 1.142857 kΩ. This changes
  gain/RC as well as common mode; no improvement is assumed. Clock controls
  use the exact unchanged standard-NFET unclamped receiver. Three structural
  tests prove the four resistor-only changes, unchanged ports/devices/helpers,
  rejection of changed topology/reapplication, and identical static/clock cores.
  `receiver_input_bias_static.py` first queues the unchanged original 12-sample
  TT/25 fixture (`38a7bc88524f7fab`) and failing SF/40 fixture
  (`7c4866221b0fca57`), preserving supplies, common modes, load, thresholds and
  sample times. Their recorded parent control is the clamped fast receiver;
  the matched unclamped DC matrix above supplies the separate standard-NFET
  reference. No one-factor claim is made against that clamped parent. Both
  static screens must pass before clock/physical/native advancement. TT/25
  now passes all 12 samples, but SF/40 fails the same 130 ns high-common-mode
  sample: PP=1.197507 V, PN=1.313036 V, CO=0.443083 V and Q=1.8 V. Thus
  this candidate is held before source-clock, physical or native work. No
  live campaign or original criterion changed.
- Unchanged native driver observation `driver_internal/c9c5ccd60b8fbe69`
  completes the full 188.049 ns transient and passes cached waveform reanalysis.
  The five original external signals match exactly on its declared comparison
  grid. In 60–120 ns AD/AB and L/R each have 25 rising/falling crossings at
  their declared observation levels. DP has 24/25 crossings at 1.65 V; DN
  has only 16/15, with complete high intervals 369.055–714.148 ps. These levels
  are diagnostic thresholds, not transistor switching points or a PHY gate.
  This localizes substantial pulse compression to the level-converter output
  path, without yet separating its CML and restoration contributions. The
  controlled P64/N24 source comparison remains in progress; its candidate
  has now aborted at 15.366 ns: timestep 1.25e−22 s, trouble at
  `m.xct.xls.xb1.xn.msky130_fd_pr__nfet_g5v0d10v5#dbody`. The simulator PID
  is gone; its actual log/raw/deck hashes are recorded in
  `restore_64_24/failure_observation.json`. The unchanged source control
  continues independently, so the comparison owner remains active while
  this candidate is numerically failed. No comparative improvement is available. No live simulator was stopped.

- `receiver_decision_observation.py` now isolates the unchanged standard-NFET
  unclamped receiver at SF/40, adding only unloaded CL/CT/NBC voltage columns
  to the original static deck (`receiver_decision_observation/2da7f2f39d63c3af`).
  All original 12 samples, stimuli, load and scoring remain. Its purpose is to
  distinguish decision-pair/mirror headroom from a restoration threshold issue
  at the failed high-common-mode point before choosing another circuit change.
  Two tests prove exact source equality to the unclamped factory and that deck
  changes are restricted to the include path and three print columns; absent
  or ambiguous print rows are rejected. The probe completes all 144 ns. Every original P/N/Q/PP/PN/CO sample
  matches the completed unclamped SF/40 reference exactly;
  `sample_comparison.json` binds both reports and the twelve-sample check. Full regression before this observer: 420 tests, 419 passed
  and one skipped; its two additional targeted tests pass.


Decision-tail repair on 2026-11-01:

- The completed SF/40 probe measures CL=0.341373 V, CT=0.170393 V and
  PN=1.182045 V at the failed 130 ns sample. The diode-side input transistor
  therefore has VDS=170.980 mV and VGS=1.011653 V. This supports branch
  headroom loss under high common mode, rather than establishing the compact
  model's operating region from voltage alone. At low common mode, CT is
  only 14–24 mV; the original W64 decision tail has substantial compliance
  variation across the required input range.
- `receiver_tail_headroom_experiment.py` changes only XCT width 64 → 16 µm
  in the standard-NFET unclamped receiver. Input tails, pairs, mirrors, loads,
  all three restoration inverters, monitor, pins and fixed supplies remain.
  The unchanged control uses that same unclamped core with XCT=64. Three
  structural tests verify the one-parameter intervention, reject changed
  topology/reapplication, and bind the exact static and clock source.
- Original TT/25 static screen `receiver_tail_headroom_static/5d065800619f4692`
  and SF/40 screen `c11fd7604ba0838a` both pass all twelve original samples.
  At the previously failing SF/40 sample, PP/PN remain
  1.078740/1.182046 V while CL=0.653296 V and CT=0.348148 V
  (VDS=305.148 mV). CO now reaches 1.417706 V and Q correctly goes low.
  This demonstrates the source DC repair at those two corners; no native
  timing or full-PVT claim follows from it.
- Full fifteen-corner matrix `receiver_tail_headroom_matrix/eaf3b93c66400e6c`
  now runs all original source DC fixtures. Its first four completed cases
  pass, including TT at 0/25/40 and FF/0; remaining cases are outstanding.
  Source clock root `receiver_clamp/d9d7143b8bf2b7a7` runs the original three
  80 ns controls, retaining the original saved pins, bias, early digital RX
  and scoring window. No completed clock result is claimed yet.
- Dedicated physical/native producers require all fifteen complete passing DC
  cases with all twelve samples each, plus all three complete passing source
  clock comparisons. Each gate remeasures the actual cached waves and checks
  the exact receiver closure. Actual preflight holds both incomplete gates
  (`physical_gate_preflight.json`), starting no layout or missing simulation.
  Metadata explicitly binds tail scale 0.25 / width 16 µm and standard NFET
  restoration; mixed old-tail or LVT identities are rejected. Native replay
  retains both independent shared leases, all 80 ns, original pins/stimulus
  and 15–75 ns scoring, and adds unloaded CL/CT/NBC probes. Tests also reject
  a 79 ns prefix as incomplete and let the other control finish after a failure.
- Service `openlvds-receiver-tail-headroom-native-continuation` captures all
  source/matrix/child manifests and transitive producers. It waits on both
  actual upstream owners, then repeats the gates before DRC/LVS, independent
  RC audit and native replay. It is currently waiting for source/full DC.
  No layout or native tail-repair result is claimed. Regression: 434 tests,
  433 passed and one skipped.
- A read-only comparison of complete standard-NFET source/native clock traces
  in the first failed 24.5–26.5 ns window finds maximum PN−PP of
  174.968 mV source versus 58.625 mV native. CO peaks at 1.602605 V versus
  0.676372 V. The LVT pair gives essentially the same internal attenuation.
  This supports a front-end bandwidth limitation in addition to the measured
  DC headroom issue; tail-repair native timing must demonstrate improvement.

- The unclamped follow-up selector now also supports `unclamped_tail_headroom`,
  dispatching its exact source factory and native verifier into the unchanged
  sixty component fixtures and original loaded link. It requires explicit
  tail width 16 µm, scale 0.25 and standard first-stage NFET metadata; carrying
  reduced-tail metadata under an older profile is also rejected. Four selector
  tests pass, including transitive producer capture and restoration after an
  exception. Both previous standard/LVT follower services were confirmed
  terminal before the selector changed; the live tail native continuation
  does not capture this selector. No tail component/link artifact or simulation
  is claimed before its actual physical/native model is available.


Driver numerical retry on 2026-11-01:

- The prior original-circuit repair `component_refresh/sf0_driver_repair.json`
  records the same class of thick-oxide source/body timestep collapse clearing
  with a 20 ps maximum integration step. This motivates a numerical retry,
  without assuming that it will cure the current SS/40 loaded fixture.
- `driver_restore_timestep_retry.py` prepares a separate comparison
  `driver_restore/00fe9eaeef273780`, retaining both source control and P64/N24
  candidate, fixed rails, complete 188.049 ns run, original sources/channel,
  loads, payload, publication window and 200 ps sampling-margin gate. Only
  maximum integration step changes from 100 to 20 ps; output step stays 20 ps.
  `retry_comparison.json` proves byte-identical circuit libraries against
  `cff36fa92d24e01b` and exact deck identity after include-root rebinding and
  that single transient-field substitution. The wrapper captures its own
  producer and restores shared dispatch in `finally`; unexpected original
  timestep commands are rejected. Three targeted tests pass.
- Service `openlvds-driver-restore-20ps-comparison` is active with both fixtures
  waiting for shared leases. The original failed candidate and still-running
  original control remain untouched. No numerical recovery or performance
  improvement is claimed. Regression now covers 438 tests: 437 passed and
  one skipped.
- The smaller-tail source campaign's unchanged captured-clock control now
  completes with no missing output transitions. Its modified captured case
  is running; the sharp case remains outstanding. The full DC matrix has
  five passing completed cases (all TT temperatures and FF/0, FF/25), with
  FF/40 waiting/running next. Native advancement remains gated on the complete
  fifteen-case matrix and all three original source clock reports.


Receiver precision retry and complete predecessor results on 2026-11-01:

- The original smaller-tail modified source clock run remains live but advances
  extremely slowly near 43.840 ns with its original 5 ps maximum integration
  step. No abort is reported. `receiver_tail_timestep_retry.py` prepares a
  separate three-control source campaign `receiver_clamp/dee37af388e0ca28`
  with 1 ps maximum integration step, unchanged 5 ps output step, full 80 ns
  run and original 15–75 ns scoring. Original supplies, saved pin waveforms,
  bias, early digital RX and all receiver devices are preserved.
- The retry's three candidate/library pairs are byte-identical to the original
  campaign. Its decks differ only by include-root rebinding and the final
  `.tran` field, 5 → 1 ps. `preparation_recheck.json` verifies all eleven
  manifest/policy/fixture hashes survive actual re-preparation unchanged.
  Five tests cover exact field substitution, fixed duration/output step,
  immutable cached manifests, changed fixtures and refusal to edit any executed
  control. Service `openlvds-receiver-tail-headroom-1ps-source` queues this
  independent numerical retry under the same shared six-slot budget. The
  original scientific run is not stopped or reinterpreted as failed.
- Source numerical policy is now checked explicitly by physical/native gates.
  Every source producer is captured transitively, including extra numerical
  leaves; policy hashes and the declared maximum step are bound into the
  physical identity. Native fixtures retain all original circuit/stimulus/
  observation/scoring fields and use the same declared 1 or 5 ps maximum
  integration step. Undeclared, mixed, changed, shortened or noninteger
  numerical policies are rejected. Both native controls still require their
  complete original 80 ns traces and independent shared leases.
- Before changing these waiting downstream producers, host PID 1194345 was
  confirmed childless in `waiting_for_source_and_full_dc`. Only that watcher
  was stopped; its original producer, manifest and state are preserved under
  `d9d7143b8bf2b7a7/native_continuation_history_20261101T034425Z`, with a
  retirement receipt. All scientific simulations continue. Replacement
  `openlvds-receiver-tail-headroom-1ps-native-continuation` is now bound to
  the new retry root and the unchanged fifteen-corner DC matrix. It waits on
  both actual owners before repeating complete source/DC gates, layout,
  DRC/LVS, independent RC audit and audited native replay. A real preflight
  validates the numerical policy and stops at the incomplete source gate.
- The complete predecessor clamped fast-restoration component campaign
  `receiver_components/58bb3aa28d907d28` is now reanalyzed from all sixty
  cached child waveforms, without starting SPICE. It passes 27/60: all fifteen
  schematic rate cases and twelve native rate cases. All thirty schematic/
  native DC cases fail. Native SS rate cases fail at all three temperatures
  with zero rising/falling output transitions; at SS/40 Q ranges only
  −1.304 to +1.426 mV in 20–60 ns, versus −23.497 mV to 1.881633 V
  schematically under identical ±250 mV differential drive, 100 ps edges,
  1.2 V common mode and 100 fF output load. Those decks did not save internal
  decision nodes, so no unique analog failure mechanism is claimed from them.
  Full-rate native component checks remain necessary after clock recovery.
- The smaller-tail DC matrix now has seven passing completed cases, adding
  SS/0 to all TT/FF temperatures. Remaining source/static/native/link gates
  are still outstanding. Regression: 447 tests, 446 passed and one skipped.


Completed unchanged-control precision check on 2026-11-01:

- The 1 ps source retry's `unclamped_captured` control completes all 80 ns
  with exactly one output transition in all 47 original checked input periods,
  zero missing and zero repeated edges. Its circuit is the unchanged standard
  unclamped fast-restoration receiver, not the smaller-tail modified case.
- `receiver_clamp/dee37af388e0ca28/unchanged_control_precision_comparison.json`
  binds both complete original/retry waveform, deck and report hashes. Across
  the 47 ordered corresponding transitions, maximum absolute output-crossing
  difference is 0.055405 ps. On a separate diagnostic 5001-point 20–75 ns grid,
  P/N source differences are below 4.45e−16 V; maximum PP/PN/CO differences
  are 39.584/17.265/245.467 µV. Both complete traces are finite and monotonic
  through 80 ns. This is numerical agreement of the unchanged control, not a
  modified-receiver/native/PHY verdict or a new acceptance threshold. The
  modified captured and sharp-control cases remain outstanding.
- The 20 ps driver ratio candidate has now obtained a shared lease (ngspice
  PID 1199093); unchanged driver control remains queued. No full driver
  comparison result is available. The smaller-tail DC matrix now has eight
  passing completed cases, including SS/25; SS/40 and FS/SF remain pending.


Matched native driver experiment on 2026-11-01:

- The 20 ps source P64/N24 run remains live but has entered a second very
  slow interval near 13.447 ns, earlier than the original 15.366 ns abort.
  It has not reported an abort and provides no full-run comparison yet.
  The original native driver observation completed 188.049 ns, motivating
  a matched extracted-geometry experiment while source numerical issues
  remain under diagnosis. No source simulation is stopped.
- `layout_driver_restore_candidate.py` builds isolated control/candidate GDS
  without changing active pointers. Both retain the original nine driver
  ports and exact declared source factories. Immutable captured geometry,
  source, DRC/LVS reports and producer hashes are checked on re-use.
  Control `driver_layout/2457353bd0bd4650` and candidate `57c38a7401ebd975`
  both pass with 266 devices, nine ports, zero DRC errors and strict LVS.
  Their footprints are 4029.07/4030.19 × 154.22 µm respectively. These are
  diagnostic physical results; neither establishes electrical qualification.
- `driver_restore_candidate_rc.py` extracts both GDSs and runs independent
  strict connectivity LVS on their wire-collapsed networks. Both audits pass.
  Control has 3970 capacitors and 63664 → 53633 resistors, exact network hash
  `189a2d70f025fad24ffa5329bcc0e9cfb694085f1fc9b903e186ee23ba3bf372`;
  candidate has 4023 capacitors and 63660 → 53641 resistors, hash
  `e3afbae2c9c91bbf17e6e45bf9649ab625407fb1d4929cc285d6053bfbd2847f`.
  Every capacitor is retained by the degree-four exact resistor reduction;
  approximate transient certification remains separate.
- `probe_native_driver_restore.py` prepares matched native experiment
  `driver_native_restore/0e89103385daf182` from the original completed
  `receiver_candidate_link/0dee72b71f4525df` loaded fixture. Both drivers
  (clock/data) use their selected audited native model. All receiver, bias,
  DLL, delay, serializer and early-RX closures remain exact. Original supplies,
  channel, 32-bit payload, full 188.049 ns run, publication window and 200 ps
  sampling-margin requirement are retained. The declared numerical change
  is a stricter 20 ps maximum integration step in both cases, with unchanged
  20 ps output step. Twelve unloaded driver-stage observations are added.
  `fixture_recheck.json` verifies exact deck restoration and protected/model
  closure hashes for both actual prepared cases. A manual comparison initially
  normalized the experiment root rather than each case directory; correcting
  that comparison confirms the generated fixtures themselves are unchanged
  except for their explicitly declared model/probe/integration differences.
- Each native case owns an independent shared lease. Both complete even if
  one raises an error, and errors leave terminal held receipts. Reports include
  original decoder/margin checks, clock centers, internal stage voltage/edge
  observations and control differences against the saved parent. Every result
  remains `qualified_phy=false`; diagnostic thresholds do not replace PHY
  criteria. Service `openlvds-native-driver-restore-comparison` is queued
  under the existing six-slot limit. No native ratio improvement is claimed.
  Electrical qualification still requires source/native component coverage,
  headroom/power evidence, RC certificates and the full selected link matrix.
- Five physical/cache/extraction tests and three matched native scope/parallel
  tests pass. Full regression: 455 tests, 454 passed and one skipped. The
  smaller-tail DC matrix remains at eight passing completed cases.


Queue-starvation correction on 2026-11-01:

- Real `/proc/locks` inspection identifies the aperture coordinator holding
  slots 1 and 4. Four long scientific runs hold the other four slots. The DC
  matrix and matched native driver cases repeatedly wait while aperture
  searches finish and reacquire leases. The existing
  `rx_candidate_aperture.lease(wait_slot)` already provides a kernel-blocking
  alternative to the shared allocator's 250 ms polling; that exact lease
  implementation is reused, without changing the global six-slot budget.
- `run_spice_wait_slot.py` is an execution-scheduling wrapper, with separate
  receipts bound to the original scientific manifest and all producer hashes.
  It preserves the scientific manifest, fixtures, cached reports, waveform
  data and engine settings. Each parallel simulation still owns a real shared
  lease; selecting one slot serializes independent cases safely. The serial
  DC matrix can retain one real lease across its remaining short cases and
  cached checks. Retained allocation is unavailable for parallel profiles.
  This scheduling receipt carries no qualification verdict.
- The resource handoff is preserved in
  `resident_jobs/queued_spice_handoff_20261101.py` and
  `resident_jobs/kernel_wait_handoff_20261101.json`. Each retired scientific
  coordinator was quiesced alone, with every thread stopped, then verified
  childless and waiting on incomplete cases with no simulation data. Only
  that coordinator was terminated; no process group or simulator was stopped.
  Actual original manifest, deck, source, cached report and raw/ordered
  waveform hashes are verified unchanged before/after the handoff and bound
  in per-artifact `execution_scheduling/handoff_20261101T045020Z` /
  `handoff_20261101T045021Z` receipts. Cached cases are remeasured by the
  unchanged original producers rather than being recopied into a new context.
- `openlvds-receiver-tail-headroom-matrix-blocking` now waits for slot 1,
  retaining it only for the serial matrix. Its scientific artifact remains
  `receiver_tail_headroom_matrix/eaf3b93c66400e6c`. Both cases of
  `openlvds-native-driver-restore-comparison-blocking` independently wait for
  the same slot after that batch, retaining the original
  `driver_native_restore/0e89103385daf182` manifest. Kernel waiter states are
  captured in `b74f93ef596be915` / `e1c3f4b1772fad30` scheduling receipts.
- The source receiver was deliberately left alone: its modified 1 ps case had
  just started and already had an actual raw file. Ngspice PID 1204428 is
  progressing normally (33.174 ns at the latest recorded prefix), so the
  handoff guard refused to retire that coordinator. Its full 80 ns result
  remains pending; no numerical fix is claimed from the prefix.
- The old childless native watcher is archived at
  `dee37af388e0ca28/native_continuation_history_20261101T044631Z`. Updated
  `continue_receiver_tail_headroom.py` captures the scheduling producer and
  supports an explicit native wait slot. Replacement
  `openlvds-receiver-tail-headroom-native-kernel-wait` watches the unchanged
  active source owner and resumed DC owner. Future native controls use slot 4,
  with all original source/DC/DRC/LVS/RC and complete native waveform gates.
- Four scheduling tests prove real blocking exclusion, unchanged six-slot
  reservation bounds, a single retained serial lease, restoration on failure
  and byte-preserved scientific manifests. Two command tests preserve the
  default native invocation and reject invalid explicit slots. Full regression:
  461 tests, 460 passed and one skipped. No acceptance criterion changed.

The upstream search finds [ngspice issue 887](https://sourceforge.net/p/ngspice/bugs/887/),
which reports failures exactly at coincident PWL corners and an experimental
`minbreak` workaround. It does not establish the cause of these local stalls:
current receiver, original driver control and 20 ps candidate trace endpoints
are about 0.346 / 3.563 / 32.369 ps after their nearest PWL corners. These are
local read-only observations, not a proof that the reported mechanism is absent.
No such workaround, model-version edit or engine substitution is applied.
[Upstream ngspice news](https://ngspice.sourceforge.io/news.html) lists newer
releases, but their compatibility or effect on these fixtures is unverified;
all live campaigns retain the pinned ngspice-42 runtime and SKY130 model set.


Reduced decision-tail source gates on 2026-11-01:

- Matrix `receiver_tail_headroom_matrix/eaf3b93c66400e6c` completes all
  fifteen source DC cases: TT/FF/SS/FS/SF at 0, 25 and 40 °C. All 180
  original static samples pass, including the previously failing SF
  high-common-mode polarity. The physical admission gate remeasures every
  cached waveform and verifies the exact smaller-tail factory closure. Its
  `physical_gate_recheck.json` records 77 proof files and the complete matrix
  summary hash. This is source DC evidence; native DC/rate coverage is pending.
- Modified `clamped_captured` in the 1 ps source retry
  `receiver_clamp/dee37af388e0ca28` completes all 80 ns. Every one of the
  47 original checked periods contains exactly one output transition, with
  zero missing/repeated edges. Transport latency is 343.165203–404.410922 ps.
  The historical task label is retained, but this factory has no CO clamps.
  The final sharp control must still pass before layout/native admission.
- After the modified captured case completed, its coordinator was verified
  childless with only the sharp control pending and no sharp waveform. The
  same guarded scheduling-only handoff preserves both completed control
  traces and the original manifest; no simulator is signalled. Receipt
  `execution_scheduling/handoff_20261101T050300Z/receipt.json` records this
  handoff. Replacement source owner
  `openlvds-receiver-tail-headroom-1ps-source-blocking` has acquired slot 4
  and started the sharp control. Native watcher
  `openlvds-receiver-tail-headroom-native-kernel-wait-v2` follows this owner
  and the completed DC owner; all source/DC/physical/native gates remain.
- The completed serial DC batch released slot 1. The matched native driver
  candidate has acquired it and reached 23.195 ns, beyond the two slow source
  intervals. Its full 188.049 ns result and matched native control remain
  pending. This prefix establishes progress only. The six-slot budget and
  all scientific settings remain unchanged.


Automatic smaller-tail follow-up on 2026-11-01:

- `queue_receiver_followup.py --receiver-profile unclamped_tail_headroom`
  waits for the exact native continuation owner to end successfully, verifies
  both original native clock reports and the selected layout, and rejects a
  replay with another receiver profile. It captures the selected verifier's
  complete producer set plus the source/native continuation inputs. The
  default baseline dispatch remains available.
- After admission, the queue uses `qualify_unclamped_receiver.py` for both
  preparation actions and `continue_receiver_unclamped_candidate.py` for
  execution. Thus all 60 source/native component fixtures and the unchanged
  saved loaded-link fixture use the exact smaller-tail source/native model.
  Children independently remeasure native replay evidence before acquiring
  simulator slots. Terminal failures hold downstream work; final child
  reports must pass and match their captured manifests. These diagnostics
  retain `qualified_phy=false` and do not replace release qualification.
- Unit `openlvds-receiver-tail-headroom-component-link-followup` is active,
  waiting on `openlvds-receiver-tail-headroom-native-kernel-wait-v2.service`.
  Its captured state under `dee37af388e0ca28/component_link_continuation`
  confirms waiting for native replay; no component/link simulation has yet
  started. Original score windows, fixed supplies and six shared slots apply.
- Tests cover baseline/tail dispatch, producer capture, an active owner,
  native failure, a mismatched receiver profile and both child reports. Full
  regression: 462 tests, 461 passed and one skipped.


Reduced-tail source clock admission completes on 2026-11-01:

- All three 1 ps controls in `receiver_clamp/dee37af388e0ca28` complete
  their original 80 ns. Each has exactly one output edge in all 47 original
  checked periods and no missing/repeated edge. Modified captured latency
  is 343.165203–404.410922 ps; modified sharp-control latency is
  288.299607–329.646269 ps. The original source owner exits successfully,
  and the native continuation advances to layout with source/DC remeasurement.
- `matched_source_transport_comparison.json` and its local
  `compare_source_transport.py` bind both completed captured-control reports
  and waveforms. All 47 corresponding input crossings match exactly. Rising
  median latency changes from 299.946 to 360.412 ps; falling median latency
  changes from 337.269 to 355.776 ps. Thus the smaller tail adds latency but
  reduces polarity imbalance. Adjacent unique output crossings imply a
  shortest output low pulse of 473.286 ps versus the unchanged control's
  402.375 ps. These are matched source diagnostics, not native or aperture
  qualification; no threshold or scoring window changes.
- Source/DC admission alone does not qualify the receiver. Physical
  DRC/LVS, independent extraction/connectivity audit, both complete native
  controls, all 60 source/native component checks and the loaded-link result
  are still required before the remaining full-PHY release gates.


Reduced-tail physical result and downstream preflight on 2026-11-01:

- `receiver_layout/30a2456cc94d73ea` passes zero-error DRC and strict LVS:
  70 devices, nine ports, 657.160 × 100.045 µm. Reducing XCT from 64 to
  16 µm removes six parallel device fingers; the declared source topology,
  port order and other devices remain unchanged. GDS hash is
  `fc8dd0bd8d34171f0a279e79ad5ed3a45153d9567e916c33ba1bb9b488cf0fd3`.
- Independent extraction and wire-collapsed connectivity audit both pass.
  Exact degree-four resistor reduction retains all 1015 capacitors and
  reduces 15232 resistors to 12472. Reduced native network hash is
  `1e5eff314a14e905135f523518e47b61fc3ac3c3aa761d974a03fb6a2461aeb5`
  (`build/extracted/86f003b3def20c85/openlvds_receiver_core/`).
  These physical checks do not establish electrical qualification.
- Native replay `receiver_replay/54184829d6357e3c` captures the exact new
  layout and unchanged original captured/sharp stimuli. Both cases retain
  full 80 ns duration, original 5 ps output step and 15–75 ns scoring, with
  declared 1 ps maximum integration inherited from their admitted source
  policy. Each independently waits on slot 4 under the existing shared budget.
- Prepared `receiver_components/d01c4ab5952b857c` contains all 60 original
  source/native static/rate conditions. Prepared loaded-link diagnostic
  `receiver_candidate_link/e5dfd3c8e0281ae5` selects the same physical model
  and original full-RC ideal-phase 32-bit reference. Both are prepared early
  to validate fixture construction; their execution is still native-gated.
- Actual invocation of both run commands refuses execution with
  “Both receiver replay cases must complete first.” Both manifests remain
  byte-identical; neither artifact has execution receipts or waveform/raw
  files. Native replay's `downstream_preflight/receipt.json` records the two
  expected holds and zero simulations started. The automatic follow-up will
  reuse these exact immutable fixtures only after successful native admission.


Native driver training-prefix observation on 2026-11-01:

- The live P64/N24 native case has advanced beyond 56 ns. Its completed
  20–35 ns training window is compared with the original completed native
  observation, using copied finite, strictly monotonic prefixes through
  40 ns. `driver_native_restore/0e89103385daf182/training_prefix/` stores
  the analysis producer, prefix arrays, column maps, prefix/model-manifest
  hashes and diagnostic report. No live producer, circuit or simulator setting
  is edited, and this prefix is not substituted for a complete experiment.
- Complete DN high pulses at the diagnostic 1.65 V crossing level span
  621.448–923.655 ps in the new case versus 123.759–734.732 ps in the
  original observation. DP spans 1644.217–1877.569 ps versus
  1310.171–1488.294 ps. Both are threshold observations, not transistor
  conduction-region measurements.
- At the thirteen clock-pulse centers in this same training window, minimum
  TX/RX magnitudes are 149.443/152.267 mV in the new case versus
  113.389/120.907 mV in the original. Both windows have zero centers below
  100 mV. This does not address the original failing centers in 60–120 ns.
- The matched control remains pending. Original and new diagnostics use
  different extracted GDSs and maximum integration steps, so these results
  do not isolate the sizing effect, establish full-run improvement or qualify
  the driver/PHY. Complete matched native traces and original source/native
  component, headroom/power, RC and loaded-link checks remain necessary.
- Receiver native replay remains kernel-queued on slot 4, now held by the
  live 20 ps source-driver control during operating-point solution. That
  simulation is left undisturbed; no scientific job is restarted or stopped.


Driver component flow and receiver queue retargeting on 2026-11-01:

- `qualify_driver_restore_components.py` prepares all thirty original
  source/native driver process/temperature fixtures for either matched
  physical variant. It verifies both declared source factories, physical
  DRC/LVS/GDS/extraction audits and current baseline component proofs. Only
  the selected driver closure, source include and exact unloaded native
  observation aliases change; bias, stimulus, supplies, loads, transient
  settings and original 2510 ns scoring window remain unchanged.
- Execution requires both complete matched native driver reports before
  calling their producer for cached waveform remeasurement; missing cases
  cannot be launched through that gate. All thirty conditions must pass
  original DC polarity/levels, transition order/cadence and loaded-eye
  voltage criteria. A component verdict cannot qualify the PHY. Prepared
  fixtures, manifest and source/runtime/model inputs are checked around
  slot waits and before final reporting. Parallel cases use independent
  shared leases and finish even when another case fails.
- Actual candidate `driver_components/f3d1cd21d727bcc8` contains all thirty
  fixtures. Its `pending_native_preflight.json` binds the manifest and log:
  execution holds with “Both matched native driver cases must complete
  first,” with zero simulations started. Earlier preparation `00f96295947be647`
  is preserved as historical evidence from before additional integrity checks.
- Five tests verify all required conditions, exact source fixture/bias
  preservation, refusal before complete native coverage, strict waveform/eye/DC
  admission and independent parallel completion on simulator failure. Full
  regression passes: 467 tests, 466 passed and one skipped. Implementation
  commit: `55d30fc`. No existing live producer was edited.
- Real coordinator file descriptors identify DLL slot 3 and the source-driver
  operating-point solve in slot 4. The receiver's two native controls had
  queued behind slot 4 without starting. Guarded handoff
  `receiver_replay/54184829d6357e3c/execution_scheduling/`
  `handoff_20261101T053258Z/receipt.json` verifies every queued coordinator
  thread stopped, no descendants, no native data and unchanged scientific
  manifests/decks/libraries before moving only that coordinator to slot 3.
  No simulator is signalled. The exact handoff command/producer is recorded
  in `resident_jobs/receiver_native_slot3_handoff_20261101.{py,json}`.
- Replacement native owner
  `openlvds-receiver-tail-headroom-native-kernel-wait-v2-blocking.service`
  is active with both controls kernel-waiting on slot 3. Replacement
  `openlvds-receiver-tail-headroom-direct-followup.service` directly watches
  that owner and the exact prepared 60-component/link fixtures. The original
  source-to-native watcher ends after its queued subprocess is retired; its
  old dependent queue consequently holds. Supplemental `superseded.json`
  receipts connect their unchanged historical states to the new owners.
  This operational retirement is not an electrical receiver failure.


Automatic driver component continuation on 2026-11-01:

- `continue_driver_restore_components.py` captures the prepared component
  manifest, all scientific input/producer hashes, its own producer and the
  environment launcher. It verifies the exact matched native comparison
  manifest binding and selected physical variant before observing the owner.
  Active/activating/deactivating owners hold work; observation errors retry.
  A terminal owner must finish successfully, and both complete native child
  reports must exactly match their aggregate and current comparison manifest.
- Only then does the continuation invoke the pinned driver component runner,
  which independently remeasures both native traces and all original fixture
  reconstructions before acquiring any simulator lease. A successful process
  exit alone cannot admit the component campaign: its final report must pass
  and match the exact component manifest. Every continuation state remains
  `qualified_phy=false`; full-PHY release gates remain outstanding.
- Unit `openlvds-driver-restore-component-followup.service` is active,
  waiting on `openlvds-native-driver-restore-comparison-blocking.service`
  for `driver_components/f3d1cd21d727bcc8`. Two eventual workers independently
  use the existing shared six-slot allocator. Its identity/state/producer
  receipts are under the component artifact's `followup/` directory.
- Three tests cover incomplete/wrong native manifests and actual child
  reports, active/failed owners, a component command that exits successfully
  but reports failure, a wrong component-report manifest and changed or
  mismatched physical/producer inputs. Full regression: 470 tests, 469 passed
  and one skipped. Implementation commit: `16d992f`.
- The 20 ps source-driver control has solved its operating point and started
  transient analysis, but advances extremely slowly near 14.9978 ns. This
  is a new numerical stall observation, not a completed comparison or proof
  of repair. The matched native candidate remains live near 97 ns, and
  native FF/0 DLL acquisition remains live near 1608 ns of 1700 ns.


Completed initial native DLL screen and driver steady window on 2026-11-01:

- `dll_qualification/15cac0ba813a9333/loop_ff_0` completes all 1700 ns
  and passes. CTRL ripple is 1.781503 mV, feedback error 7.417610 ps and
  quarter delay 653.018658–653.408804 ps. Marker section delays are
  653.295344/649.270988/638.576953/641.094580 ps; cadence/marker checks
  pass and mean power is 6.365241 mW. Actual deck, ordered waveform and raw
  hashes match the report. All 21 static offsets and SS/TT/FF acquisition
  loops now pass: exactly 24 screen cases. `screen_completion_recheck.json`
  verifies 98 file bindings across all 24 reports/decks/waveforms/raw files.
- The existing native continuation remeasures its completed screen and enters
  `running_stability_screen`, with `measure_dll_stability.py` active for
  SS/0, TT/25 and FF/0. This stage still needs simulator leases and verified
  measured-model/step evidence. Remaining 312 cases of the full 336 and all
  fifteen PVT stability models remain gated; the initial screen is not release.
- Receiver native `sharp_control` in `receiver_replay/54184829d6357e3c`
  acquires the released DLL slot 3 and starts; captured control remains queued
  independently behind it. No receiver native result is yet available.
- The native driver candidate completes the entire diagnostic 60–120 ns
  window and advances past 125 ns. Immutable prefix arrays, column maps,
  producer/manifest/prefix hashes and observations are saved under
  `driver_native_restore/0e89103385daf182/steady_prefix/`. Original/new
  TX clock-center minima are 76.416519/117.255151 mV; RX minima are
  85.215528/133.034402 mV. Among 49 centers per lane in this raw-prefix
  comparison, original TX/RX have 4/3 below 100 mV, whereas the candidate
  has zero below 100 mV on either lane. The full 188.049 ns run and matched
  native control still must finish; different baseline GDS and integration
  settings prevent attributing this unmatched comparison solely to sizing.
- At the same diagnostic 1.65 V crossing level, clock DN changes from
  16 rises/15 falls to 25/24 within 60–120 ns; complete high pulses widen
  from 369.055–714.148 ps to 532.731–1097.661 ps. DP remains 24/25;
  AD/AB and L/R remain 25/25. These are stage observations, not transistor
  conduction-state proof, full decoder admission or a PHY verdict.
- Fresh audited loading inspections `receiver_loading/11bbf00548f00ecc`
  and `f8866328c8821f78` compare standard and reduced-tail receiver GDSs.
  PP/PN incident routing capacitance changes from 100.38130/107.54226 fF
  to 96.07947/103.21285 fF; CT changes from 70.87449 to 30.01471 fF.
  CO/CL/RESTORE0/RESTORE1 remain 35.91650/25.00118/47.75790/58.94737 fF.
  These full-coupling wire values exclude device/MIM capacitance and are
  not effective AC loads. Native replay therefore includes both the intended
  smaller-tail electrical change and its new extracted routing.


Isolated 1 ps source-driver integration experiment on 2026-11-01:

- Both existing 20 ps source cases are live but very slow: the ratio
  candidate near 13.447 ns and unchanged control near 14.998 ns. The
  completed receiver precision experiment motivates a separately captured
  driver retry; it does not establish that the same change will repair these
  source-driver numerical intervals. No earlier simulator is stopped.
- `driver_restore_precision_retry.py` uses the exact original source-driver
  comparison with a 1 ps maximum integration step in both matched controls.
  The original 20 ps output command, complete 188.049 ns duration, initial
  time, circuits, supplies, waveform stimulus, observation nodes, scoring
  windows and original sampling margin remain unchanged. Unexpected original
  durations/output/start/maximum steps are refused. The original fixture/CODE
  bindings are scoped to this process and restored even on exceptions.
- Artifact `driver_restore/5a976ac3781d6832` captures the producer and a
  `numerical_policy.json` binding the original manifest, parent and numerical
  fields. Actual `fixture_recheck.py` / `precision_comparison.json` verify
  both source libraries byte-identical to the original 100 ps experiment and
  both decks identical after only include-path and maximum-step normalization.
  Re-preparation preserves every captured manifest, policy, deck and library
  byte. Tampered policies are rejected before the original runner can execute.
- `openlvds-driver-restore-1ps-source-comparison.service` is active with both
  cases waiting for the existing shared allocator. No additional slot or
  reservation is introduced; no result or numerical repair is yet claimed.
  Full native/component/RC/headroom/link gates remain unchanged.
- Four tests cover exact integration-only changes, refusal of changed or
  shortened fixtures, restoration after failure, policy binding, byte-stable
  preparation and tamper refusal. Full regression: 474 tests, 473 passed and
  one skipped. Implementation commit: `92f6abc`.


Receiver cached-verification race corrected on 2026-11-01:

- The component and loaded-link follow-ups run in separate processes and
  both invoke the same native replay producer for cached remeasurement.
  That producer deliberately uses a nonblocking execution lock; simultaneous
  healthy cache checks could therefore make one follow-up fail before any
  component/link simulation. `qualify_unclamped_receiver.recheck` now uses
  a separate blocking cached-verification lock around this shared operation.
  It revalidates the selected profile and requires all three completed replay
  report files inside that lock, preventing a missing case from launching a
  simulation through the cached path. Exceptions propagate and release the
  lock. All source/waveform/model/PVT/timing gates are retained.
- Only cached replay verification is serialized. The independent component
  and loaded-link simulations retain their parallel workers and the original
  shared six-slot allocation. A real-lock concurrency test proves the second
  check waits, never overlaps the first and resumes after the first throws;
  a separate test proves missing cached cases cannot call the producer.
  Full regression: 476 tests, 475 passed and one skipped. Code commit `52f2891`.
- The waiting direct follow-up watcher is verified childless after all its
  threads quiesce, then retired without signalling a simulator. Exact evidence
  is in `resident_jobs/retire_receiver_cached_check_watcher_20261101.{py,json}`
  and the old watcher's `superseded.json`. Current native/physical/driver
  manifests are checked not to capture the modified selector, so those live
  scientific jobs and their producers remain unchanged.
- Fresh components `receiver_components/e5095fc389735754` and loaded-link
  `receiver_candidate_link/15d06853a0ad3ce1` capture the new selector. Actual
  recheck `receiver_cached_check_fixture_recheck_20261101.py` verifies all
  sixty component libraries byte-identical and all decks identical after only
  include-path normalization, including the loaded-link library/deck. Identity
  contexts differ only in the selector producer hash. The replay's
  `followup_context_replacement.json` captures 248 bindings and verifies zero
  simulations started in either the old or new component/link artifacts.
- Replacement `openlvds-receiver-tail-headroom-serialized-cache-followup.service`
  is active and waiting on the unchanged native owner, selecting these fresh
  artifacts. Its receipts are in replay `followup/e9500fb9e650e5ea`; the
  previous watcher's `replacement.json` links the new owner/context proofs.
  Native sharp replay is progressing beyond 22 ns and the native driver
  candidate beyond 170 ns; complete native results are still required.


Native driver candidate completes; retained receiver clock failure localized
on 2026-11-01:

- `driver_native_restore/0e89103385daf182/restore_64_24` completes the
  original 188.049 ns, with 29904 raw rows and ngspice return code zero.
  The per-case `completion_recheck.json` verifies current manifest, library,
  deck, ordered waveform and completed report hashes. The full report
  preserves the improved clock-center minima: TX 117.255151 mV and RX
  133.034402 mV, with zero checked centers below 100 mV in 60–120 ns.
- The original decoder nevertheless fails: no correctly ordered payload
  preamble and all published words zero. Sampling-margin admission fails.
  This is a complete negative loaded-link result, not electrical/PHY success.
  Matched native control remains queued, so the sizing effect is not isolated.
- `completed_link_localization/analyze.py` and `summary.json` independently
  verify finite, strictly monotonic complete original/new traces through
  188.049 ns, binding the waveform, manifest and report hashes. In 60–120 ns
  the new driver's retained analog receiver clock output stays between
  −7.239 and +5.945 mV, with zero 0.9 V crossings; Q0/Q1 stay near zero.
  RXVALID is high. Thus the recovered-clock signal disappears before the
  digital capture/publication stage, despite improved differential clock pins.
- Data is still driven: TX data has 7 rises/8 falls at 0.9 V; differential
  RX data has 9 rises/9 falls at zero and spans −327.882 to +328.143 mV.
  The retained receiver's RXDATA has only 4 rises/4 falls. Its prior complete
  native SS rate tests likewise held the output near zero. These observations
  support replacing the clamped receiver rather than claiming that better
  driver pin swing alone closes the link. No receiver internal nodes were
  saved here, so a unique internal analog mechanism is not asserted.
- The original completed diagnostic's RXCLOCK still has 24 rises/25 falls
  in this same window and RXDATA has 9/10. Different driver GDS/numerical
  settings mean this remains an unmatched localization comparison. Both
  receiver and driver must still pass their selected native/component gates
  before the combined analog link and full selected PHY are qualified.
- After the candidate releases its lease, the queued 1 ps source-driver
  control acquires slot 1 and starts (ngspice PID 1214447). Matched native
  control remains kernel-waiting on that slot; no process is stopped. The
  receiver native sharp control and DLL measured-model coordinator remain
  active, with the native captured receiver and remaining source cases queued.


Reduced-tail sharp prefix and input placement experiment on 2026-11-01:

- Native sharp replay `receiver_replay/54184829d6357e3c` advances beyond
  50 ns. Its `first_sharp_pulse/` stores immutable prefixes through 30 ns,
  column maps, producer/model/deck hashes and the same 24.5–26.5 ns diagnostic
  window used previously. Standard/new reduced-tail CO peaks are
  1.356111/1.233518 V; RESTORE0 minima 82.448/236.534 mV. Both recover
  this sharp pulse: standard output fall/rise 25.723799/26.128155 ns, new
  25.809655/26.187368 ns. This local observation does not qualify the full
  80 ns sharp control or the still-queued weak captured-input control.
- `layout_receiver_input_island.py` explores placement only: it preserves
  every exact source device/finger/model/dimension/node and moves the four
  input mirror output banks and ten load resistors immediately before the
  decision stage. All other device order, including the admitted unloaded
  monitor placement, is retained. The source is byte-identical to reduced-tail
  reference `30a2456cc94d73ea`; source/DC gates are remeasured unchanged.
- Alternative `receiver_layout/f0f9ee68d2a80ba2` passes zero-error DRC,
  strict LVS and independent extracted connectivity audit: 70 devices,
  nine ports, 657.160 × 100.045 µm. Its GDS hash is
  `ec1687c02706de3876e6cbf0e785359c77625a75be3f2e8eac6cbae3e24bea13`.
  Exact reduction retains all 1031 capacitors and reduces 15234 resistors to
  12507, network hash
  `469e760c9619668808006f992d1c61ebf1e6386ab9d1cacb9af2c9df0e3da250`
  (`build/extracted/8736fe0c98351e95/openlvds_receiver_core/`).
- Loading `receiver_loading/c540d6e865f9d33a` reduces PP/PN incident wire
  capacitance from 96.07947/103.21285 fF to 80.78245/74.77354 fF. However,
  the full `input_loading_comparison.json` also checks upstream mirror nodes:
  NL/NR increase from 60.71743/61.92002 to 81.91689/85.17926 fF; PL/PR
  increase from 62.79109/70.95722 to 67.63202/73.33675 fF. CO/CL/CT
  remain 35.91650/25.00118/30.01471 fF. These incident full-coupling wire
  loads exclude device capacitance and are not effective AC loads or timing
  proof. The mirror-node penalty may offset the smaller decision-input load.
- Consequently this alternative is retained for diagnosis, without replacing
  the running native layout or launching a new native replay. A useful next
  layout experiment should reduce decision-node routing without lengthening
  upstream mirror-control nets, for example by changing sensitive-net bus
  priority while preserving the original device order. It must still pass
  exact source/physical/audit and complete native controls.
- Immutable caching records every actual GDS/schematic/DRC/LVS/source/report
  hash and refuses changed or partial geometry. Actual cached evidence is
  verified without redrawing. Three structural/cache tests pass; full
  regression: 479 tests, 478 passed and one skipped. Code commit `dc06552`.
- The 1 ps unchanged source-driver control terminates numerically at
  13.782610 ns (14326 raw rows), reported timestep 1.25e−24 s and node
  `xtx.vgnd.t436`. `driver_restore/5a976ac3781d6832/source_control/`
  `failure_observation.json` binds its log/raw/deck/library/manifest/policy.
  Its inherited execution receipt remains stale `running`; actual PID 1214447
  is gone and ngspice explicitly reports aborted. No performance verdict is
  issued. The ratio case remains queued, so the comparison is incomplete.
  The released slot now runs matched native driver control, PID 1215510.
  Further precision-only changes are not established as a repair.


Receiver bus-order experiment and captured-prefix diagnosis on 2026-11-01:

- Reduced-tail native `receiver_replay/54184829d6357e3c/sharp_control`
  completes all 80 ns. All 47 original checked periods contain exactly one
  output transition; zero missing/repeated edges. Latency is
  853.026050–1072.241020 ps. Its `completion_recheck.json` verifies the
  exact library, manifest, deck and ordered waveform bindings. Captured-input
  replay has acquired slot 3 and is running; the full native gate is pending.
- `layout_receiver_bus_priority.py` changes only the internal bus-order
  assignment in the captured drawing function. A guarded syntax-tree
  specialization preserves every other drawing statement, including device
  transforms, bus widths and public pins. The order is PP/PN/CO/CL/CT/
  NL/NR/PL/PR, followed by remaining internal nets. Source/DC admission and
  immutable physical caching remain. Unknown routing code or missing nets
  is refused. This alternative does not alter active layout pointers.
- `receiver_layout/5fae56c00f7706ad` passes zero-error DRC, strict LVS
  and independent extraction/connectivity audit. All 70 devices, nine ports,
  657.160 × 100.045 µm dimensions and public pin positions match reference
  `30a2456cc94d73ea`. Actual `routing_scope_recheck.json` verifies identical
  source bytes, flattened schematic and every device transform. GDS hash is
  `c7fd75bb4aaf5a2b0f2b7bd08987f20e33e4891b8b43cf41bed28413df1d843b`;
  native network hash
  `edc3c2af481a47140dad7d000a995b14ce2fde858f34b5c6019994b29298c969`
  (`build/extracted/ae0110e5e51039e6/openlvds_receiver_core/`). Exact
  reduction retains all 1058 capacitors and reduces 15232 resistors to 12502.
- The result is a negative routing experiment. Its full
  `input_loading_comparison.json` reports PP/PN increasing from
  96.07947/103.21285 fF to 98.78515/111.21920 fF; CO/CL increase from
  35.91650/25.00118 fF to 39.83411/28.85147 fF. NL/NR/PL/PR improve
  modestly, but sensitive-node incident capacitance does not. Wire length
  alone did not predict full coupling capacitance. No native replay is
  launched for this alternative. Three routing/geometry tests pass; full
  regression: 482 tests, 481 passed and one skipped. Code commit `54ab292`.
- Captured replay's `first_captured_pulse/` stores immutable prefixes through
  30 ns. In the original 24.5–26.5 ns local observation, reduced-tail CO peaks
  at 0.709227 V versus standard-tail 0.676372 V, and RESTORE0 remains
  above 1.783265 V. `known_complete_periods.json` applies the unchanged
  15–75 ns matching rule only to periods whose next same-polarity edge
  already exists in the prefix. Both layouts have three missing edges in
  ten complete available periods. Specifically the 24.777050 ns falling
  pulse is 526.689 ps wide, peaks at 108.848 mV and has no corresponding
  output crossing before the next input period. This confirms a local missed
  edge, while the original full 80 ns run continues for its complete report.
- Source-only `decision_threshold_envelope.json` sidecars bind all 180
  original DC samples for standard-tail matrix `1ac68453f143818d` and
  reduced-tail matrix `eaf3b93c66400e6c`. Standard-tail expected-output-high
  CO can reach 0.915188 V (FS/40) while expected-output-low CO can be as
  low as 0.703679 V (SF/0); a single ideal fixed threshold cannot separate
  that complete set. Reduced-tail extrema are 0.934215 V and 1.380087 V,
  a 0.445871 V gap. These envelopes are not measured inverter transfer
  curves or native admission, but support preserving the DC headroom fix.
- A concrete next placement test is to move the six unloaded reference
  monitor devices after all functional devices, preserving their circuit and
  all other device order. That removes them from the physical decision-output
  to first-restorer span without lengthening upstream mirror nets. Measure
  CO and all input-stage loads before deciding to simulate this alternative.
- The 1 ps source-driver pair is explicitly held after its unchanged control
  aborts. Its remaining ratio case was unstarted; its coordinator is quiesced,
  verified childless, then retired alone. No simulator is signalled and all
  failed-control/fixture/manifest bytes are preserved. Exact receipt/procedure:
  `resident_jobs/hold_failed_driver_precision_20261101.py` and
  `driver_restore/5a976ac3781d6832/held_after_control_abort.json`. Required
  coverage remains two, with zero complete, one numerically failed and one
  unstarted. No incomplete source comparison is admitted as passing.


Decision-output placement improvement on 2026-11-01:

- `layout_receiver_monitor_after.py` moves only the six unloaded XTRACK
  fingers after all functional devices. `receiver_layout_reference.py`
  shares the source-bound validation/cache/build policy for this experiment.
  Before drawing it captures the original device multiset and refuses any
  change of model, parameter, node, instance or count, including accidental
  in-place mutation by a placement callback. Policy overrides cannot replace
  source/admission metadata. Original source/DC gates are remeasured.
- New `receiver_layout/8be736a2b11e5b89` passes zero-error DRC, strict
  LVS and independent extracted connectivity audit: 70 devices, nine ports,
  657.160 × 100.045 µm. Actual `placement_scope_recheck.json` verifies
  identical source bytes and the complete flattened device multiset, with
  every functional device retaining its relative order. CO-connected device
  origin span falls from 71.10 to 28.44 µm. That geometric observation is
  not itself a capacitance/timing verdict.
- Extraction confirms the intended load change. Its
  `input_loading_comparison.json` reports CO incident routing capacitance
  35.91650 → 28.24057 fF; PP/PN 96.07947/103.21285 →
  92.04186/99.08609 fF. NL/NR/PL/PR remain effectively unchanged at
  60.71743/61.92006/62.79109/70.95722 fF; CL/CT also remain essentially
  unchanged. These are full incident coupling wire values, excluding device
  capacitance, and still require native timing verification.
- GDS hash is
  `7d668f0234c7419ec42e0cae7684ad95ef84ea7105484d7d6a80db55cea3ee32`.
  Exact reduction preserves all 1012 capacitors and reduces 15236 resistors
  to 12499, native hash
  `178acfa1051455861d35031f91a4deeeea21edf12a9d844a680287e6bebd8293`
  (`build/extracted/d351f4892818f104/openlvds_receiver_core/`). Five tests
  cover exact monitor-only movement, malformed device mutations, missing
  monitor fingers, immutable/partial caches and protected admission metadata.
  Full regression: 487 tests, 486 passed and one skipped. Code `030df0e`.
- Native `receiver_replay/822c30476339d818` prepares both original full
  80 ns controls with the inherited declared 1 ps maximum step, 5 ps output
  command and 15–75 ns analysis window. Actual `fixture_recheck/summary.json`
  verifies both decks identical to previous native replay after include-path
  normalization; the selected receiver matches its audited RC and both
  unrelated replay closures (bias and digital RX) are identical. A manual
  checker initially assumed the full-link library's roots; correcting it to
  this replay's actual two protected roots passes without changing fixtures.
- `openlvds-receiver-monitor-after-native.service` has both cases queued
  independently on shared slot 3. Prepared full 60-case component campaign
  `receiver_components/d6fda107c33d401a` and loaded link
  `receiver_candidate_link/e8fada5af2c6c3a0` select this exact layout/replay.
  `openlvds-receiver-monitor-after-followup.service` is active, waiting for
  both native controls to pass. Actual downstream run preflights refuse
  execution before native completion, preserve both manifests and start zero
  simulations; replay `downstream_preflight/receipt.json` records this.
  No voltage/timing/PVT/coverage gate or active pointer is changed.

Capacity review on 2026-11-01:

- Four live source diagnostics currently occupy four of six simulator slots.
  Two observations 137.215 seconds apart measure advances of
  0.000190260 / 0.000010773 / 0.000000361 / 0.000168779 ns for
  PIDs 1191416 / 1194729 / 1199093 / 1207333. These are live processes,
  not jobs declared terminal from an observation timeout. Required native
  receiver and driver controls are still progressing in the other slots.
- `resident_jobs/stalled_source_retirement_proposal/proposal.json` binds
  exact three source-diagnostic units, process start ticks, commands/cgroups,
  immutable available raw-prefix snapshots, scientific inputs and protected
  completed-case proofs. It proposes retiring only these four simulations,
  preserving incomplete evidence rather than admitting any result as passing.
- This proposal changes the current practice of leaving live simulations
  untouched, so user approval was requested asynchronously. Its status is
  `pending_user_approval`; no simulator has been signalled. Native/PVT work
  and the unchanged six-slot budget continue while a decision is pending.


Decision-load circuit experiment on 2026-11-01:

- Monitor-after native replay `822c30476339d818` still runs its original
  full 80 ns captured case. Its `first_captured_pulse/summary.json` measures
  CO peak 0.753394 V versus 0.709227 V before relocation, but neither
  layout produces an output crossing for the original 526.689 ps pulse.
  `first_captured_pulse/check_periods.py` applies the original scoring rule
  only to complete available periods: both prefixes have three missing
  edges in ten periods. This is a negative prefix observation, not a
  completed native report; the full controls remain required.
- `receiver_decision_load_experiment.py` changes only the decision PMOS
  diode/mirror XCD/XCM from W8 to W32, retaining L0.15, original W64/L0.5
  decision tail, W8 input pair, removed clamps and original stronger
  restoration buffers. This compares against the standard unclamped W64
  control, not against the reduced-tail W16 circuit. The hypothesis is to
  raise the decision common-mode/headroom while retaining higher charging
  current. Actual static and dynamic results must decide whether that works.
- `receiver_decision_load_static.py` remeasures a completed original control
  and verifies its exact factory closure, immutable fixtures, inherited input
  hashes, producer hashes and pinned runtime. The candidate changes only
  those two widths and adds unloaded CL/CT/NBC observations. It preserves
  the original 144 ns, all twelve sampling points and 100 fF output load.
  Full finite, monotonic waveforms are required; cached reports are
  remeasured, and partial executions are retained rather than overwritten.
- Three pilots are queued on actual shared slot 1, within the six-slot
  budget: TT/25 `receiver_decision_load_static/e33c866803601b0d`, SF/40
  `51e8be8847013846`, FS/40 `21e1c870086d1f65`. Services are
  `openlvds-decision-load-{tt25,sf40,fs40}`. All remain waiting at this
  observation; no passing electrical result is claimed. A preparation-only
  TT artifact `abd07dedf91fbbfc` predates the stronger inherited-input and
  partial-run guards and has never been queued.
- Admission order remains: three pilots, all fifteen source static corners,
  original three source clock controls, physical DRC/LVS/RC audit, both
  full native replay controls, full component and loaded-link gates. Do not
  queue clock or physical work for this circuit before its static gate passes.
  The reduced-tail circuit retains its demonstrated DC evidence separately.
- Matched native driver comparison `driver_native_restore/0e89103385daf182`
  is now complete for both cases. Both fail the full decoder/margin gates.
  In the matched 60–120 ns observation, receiver-input minimum magnitude
  improves from 86.644 to 133.034 mV, but the stronger-driver clock output
  has no crossings. Component campaign `driver_components/f3d1cd21d727bcc8`
  has started independently; its first schematic TT/0 case passes. Full
  thirty-case component admission is still pending and cannot establish
  complete link qualification by itself.
- Four targeted tests cover the exact two-device intervention, unchanged
  static fixture, all original sampling points, and rejection of incomplete,
  nonfinite, nonmonotonic or missing-observation data. No live simulator was
  stopped, scientific gate weakened, or active analog pointer promoted.

- Validation after the decision-load addition: 491 regression tests, 490
  passed and one skipped. All four new targeted tests pass.


Full decision-load DC gate prepared on 2026-11-01:

- `receiver_decision_load_matrix.py` prepares exactly the fifteen required
  source process/temperature points from the completed standard unclamped
  control matrix, ordered with TT/25, SF/40 and FS/40 first. It captures the
  complete child manifests, source selection, current requirements and code.
- Matrix `receiver_decision_load_matrix/6fd0fd7ce4169f32` reuses the three
  live pilot artifacts without changing their manifests. Before running any
  remaining case it requires every pilot's complete report, remeasures each
  actual waveform through the scientific runner, and requires all three to
  pass. Incomplete or failed pilots cannot launch remaining simulations.
- Actual run preflight refuses incomplete pilots and records
  `incomplete_pilot_preflight.json`: fifteen required cases, zero complete,
  zero new simulations. This is an expected admission hold, not a numerical
  failure. Four targeted matrix tests exercise exact coverage, pilot order,
  missing results, failed results and mandatory remeasurement/hash binding.
- The full matrix is prepared but not running. Once all independent pilot
  owners finish successfully, resume with
  `./scripts/env.sh --ngspice python3 scripts/receiver_decision_load_matrix.py run build/diagnostics/receiver_decision_load_matrix/6fd0fd7ce4169f32 --wait-slot 1`.
  It holds a shared lease only during each actual uncached child simulation;
  it does not retain a lease while invoking nested runners.

- Matrix regression: 495 tests, 494 passed and one skipped; all eight
  decision-load factory/static/matrix tests pass.

Completed monitor-after captured replay on 2026-11-01:

- `receiver_replay/822c30476339d818/captured` has finished its complete
  original 80 ns. The scientific report checks 47 periods and finds eighteen
  missing edges (nine rising and nine falling), matching the previous
  monitor-before reduced-tail layout. The sharp-control simulator has now
  started; no aggregate completion or downstream admission is claimed.
- `completed_captured_comparison/analyze.py` independently remeasures both
  complete captured waveforms with the original 15–75 ns period rule and
  verifies reports against waveform/deck/library/manifest hashes, current
  code, inherited inputs and runtime. Both layouts miss exactly the same
  eighteen input edges and have no extra edges. The lower wire capacitance
  and larger first-pulse CO swing therefore do not resolve the captured
  clock failure. Continue the stronger-PMOS circuit's static pilots before
  another physical receiver build.


First stronger-PMOS pilot result and DC continuation on 2026-11-01:

- SF/40 pilot `receiver_decision_load_static/51e8be8847013846` completed
  and passes all twelve original static samples. At the previously failing
  130 ns high-common-mode sample, the unchanged standard-tail control gives
  CO 0.743371 V and Q 1.799990 V (incorrect high). The stronger PMOS
  candidate gives CO 1.186662 V, CL 0.674832 V, CT 0.206839 V and
  Q approximately 0 V (correct low). This is source DC evidence at one
  corner; no dynamic or native performance is inferred.
- TT/25 and FS/40 pilots still wait on the original shared slot. The DLL
  delay_0 trace completed and delay_1 is live and advancing; the native
  monitor-after sharp control is also live. No stalled source run is stopped.
- Resource-only `receiver_decision_load_matrix/6fd0fd7ce4169f32/followup/run.py`
  was first attempted as `openlvds-decision-load-dc-followup.service`. It captures
  current code/environment/matrix hashes and waits for all three exact pilot
  units to become inactive with successful status. Transient observation
  failures retry; unsuccessful terminal owners hold. The existing scientific
  matrix runner then remeasures the pilot waveforms before any remaining
  simulation, so successful process exit alone cannot admit a failed pilot.
  The follow-up uses slot 1 and the unchanged six-slot budget. It will
  report full DC success only from the actual fifteen-case passing report;
  source clock, physical and native admission remain separate requirements.

- The first follow-up correctly held before launching any case because
  systemd had garbage-collected the successful SF/40 transient unit. Its
  original failed receipt is preserved. New resource context `followup_v2/`
  (`openlvds-decision-load-dc-followup-v2.service`) accepts an inactive,
  not-found owner only when its complete child report binds the expected
  manifest; loaded unsuccessful owners still hold. This does not substitute
  for waveform validation: the scientific matrix remeasures all pilots before
  running any remaining case. The v2 service is verified active and waiting
  for the still-live TT/25 and FS/40 owners.


Gated stronger-PMOS source clock implementation on 2026-11-01:

- `receiver_decision_load_clock.py` first requires a completed, passing
  fifteen-case DC matrix and remeasures every existing child through its
  scientific runner. Missing reports are refused before preparing any clock
  artifact, so cached admission cannot start missing DC simulations.
- Clock preparation derives a fresh immutable context from the declared
  stronger-PMOS factory. All original source/library bytes, pin stimuli,
  print observations, full 80 ns duration, 5 ps output step and original
  15–75 ns scoring window remain; only the maximum integration step becomes
  1 ps for all three controls. The new identity directly captures every DC
  proof, source-template file and numerical policy. Existing or executed
  source contexts are never edited. Legacy task names `clamped_*` identify
  the modified factory here; neither source variant contains CO clamps.
- Source admission requires exactly the three original controls, 47 scored
  periods per control, zero missing and zero repeated edges, with complete
  finite monotonic waveforms. `source_clock_admission.json` is separate from
  the diagnostic report and never establishes physical/native/PHY admission.
  Partial failed traces are preserved and refused for in-place retry.
- Actual `6fd0fd7ce4169f32/source_clock_preflight/receipt.json` proves
  preparation refuses the incomplete DC matrix and creates zero new source
  contexts. Five new tests cover byte-preserving fixture derivation,
  immutable re-preparation, changed/incomplete fixtures, incomplete or failed
  DC admission, missing controls and missing/repeated clock edges.
- Resource-only `clock_followup/run.py` is verified active as
  `openlvds-decision-load-clock-followup.service`. It waits for the exact
  full-DC owner to finish and requires its full passing report; it then calls
  the gated scientific prepare/run commands. Context/code/environment hashes
  are captured. A collected systemd owner is accepted only with complete
  manifest-bound passing evidence; missing evidence or failed owners hold.
  Clock runs use actual shared slot 1 within the unchanged six-slot budget.
- Full regression: 500 tests, 499 passed and one skipped; all thirteen
  decision-load tests pass. No new clock case is running or claimed passing
  at this observation. SF/40 remains the sole completed static pilot.


PMOS-only rejection and uniform decision scaling on 2026-11-01:

- All three PMOS-only W32 pilots are now complete. TT/25 and SF/40 pass;
  FS/40 fails original 22 ns and 46 ns low-common-mode, positive-polarity
  samples. CO is 1.033041 / 0.984529 V and Q remains approximately
  0 V instead of the required high. The standard-load control at these
  same samples gives CO 0.915188 / 0.858569 V and correct high Q.
  Increasing only the PMOS mirror raises CO in both polarity conditions;
  its SF headroom benefit does not establish all-corner restoration.
- `receiver_decision_load_matrix/6fd0fd7ce4169f32/rejected_static_pilot.json`
  binds the failed report and actual waveform. The automatic full-DC gate
  remeasures the completed pilots and holds on the actual FS failure.
  Its clock continuation also holds. Exactly three pilot simulations ran;
  zero of the remaining twelve DC cases and zero clock cases were launched.
  The gate prevented unnecessary downstream work without moving criteria.
- `receiver_scaled_decision_experiment.py` implements a different hypothesis:
  uniformly scale all five decision devices by four from the independently
  DC-passing reduced-tail receiver. XCT goes W16 to W64; XC0/XC1 and
  XCD/XCM each go W8 to W32, with original models, nodes, lengths and all
  other circuit devices unchanged. This preserves decision-device sizing
  ratios and seeks more charging current. It also increases PP/PN gate
  loading, so a DC pass cannot establish dynamic improvement.
- Preparation remeasures the completed reduced-tail static control, verifies
  its exact declared source closure and full waveform, and binds inherited
  inputs, code and runtime. The original 144 ns deck already contains the
  unloaded CL/CT/NBC observations; only its source inclusion is rebound.
  All twelve sampling times, supplies, stimuli and 100 fF load remain.
  New waveform validation rejects incomplete/nonfinite/nonmonotonic data;
  partial failures are retained and cached measurements rechecked.
- New pilots under `receiver_scaled_decision_static/` are queued on actual
  shared slot 1: TT/25 `de8b99d5cb7a5d5e`, SF/40 `aeb25b9ac3f5874e`,
  FS/40 `d3d3385283fb72cb`. Units are `openlvds-scaled-decision-{tt25,sf40,fs40}`.
  None is yet complete. The original six-slot budget and live jobs remain.
- Three new tests verify the exact five-device intervention and every other
  circuit/device, all five width ratios, refusal of wrong/repeated topology,
  and prevention of an uncached control simulation during preparation.
  Full regression: 503 tests, 502 passed and one skipped. No analog pointer
  or physical/native/PHY admission is promoted.


Uniform-decision full DC admission prepared on 2026-11-01:

- `receiver_scaled_decision_matrix.py` prepares exactly all fifteen original
  process/temperature source DC conditions from completed reduced-tail matrix
  `eaf3b93c66400e6c`. Each control is independently remeasured before cloning
  the uniform five-device width scaling. Selection uses the existing exact
  coverage/name checker; the new matrix captures that helper's code as well.
- Matrix `receiver_scaled_decision_matrix/a3a34b4ac8e5f600` reuses the same
  TT/25, SF/40 and FS/40 pilot contexts. Before any remaining case it requires
  complete manifest-bound pilot reports and remeasures all three actual
  waveforms. Any failed pilot holds the remaining simulations. Every child
  retains the original twelve points and full 144 ns static fixture.
- Actual `incomplete_pilot_preflight.json` binds an expected hold with zero
  additional nonpilot simulations. Resource-only `followup/run.py` is verified
  active as `openlvds-scaled-decision-dc-followup.service`, waiting for those
  exact pilot owners. Its immutable code/context receipts and handling of
  successful collected units follow the prior corrected resource policy.
  The scientific matrix, rather than service exit alone, decides admission.
- Three targeted tests verify that missing reports cannot invoke the runner,
  failed remeasured pilots block advancement, and passing flags require
  complete reports bound to the expected manifests. Full regression: 506
  tests, 505 passed and one skipped. All six uniform-decision tests pass.
- At this observation all three uniform-scaling pilots still wait on actual
  shared slot 1. The live native sharp-control simulator continues separately.
  No old scientific code, live simulator, supply, sampling rule or six-slot
  resource limit was changed. Source clock and downstream physical/native
  gates have not been admitted for the uniformly scaled circuit.


Uniform-decision clock handoff and completed native rejection on 2026-11-01:

- FS/40 uniform-scaling pilot `receiver_scaled_decision_static/d3d3385283fb72cb`
  passes all twelve original DC samples. In particular Q is high at both
  22 and 46 ns, which failed with PMOS-only scaling. TT/25 already passes;
  SF/40 is still queued. The remaining twelve DC cases stay held until all
  three pilots pass and their actual waveforms are remeasured.
- `receiver_scaled_decision_clock.py` reuses the immutable source-clock
  reconstruction and admission helpers with an explicit uniform-scaling
  factory profile. Its control is the reduced-tail receiver, and the modified
  source scales all five decision devices together. The profile restores
  every temporary factory/gate binding on success or error. Preparation
  captures inherited code from all actual DC manifests, including source
  factory dependencies, before deriving a fresh full three-control context.
- Clock admission retains all original stimuli and probes, full 80 ns,
  5 ps output step, 1 ps maximum integration and original 15–75 ns scoring.
  All three controls must have exactly one output per original 47 periods,
  complete finite monotonic traces, and unchanged static evidence. This is
  source-clock admission only; all physical/native/component/link gates remain.
- Actual `a3a34b4ac8e5f600/source_clock_preflight/receipt.json` proves that
  incomplete full DC evidence refuses preparation and creates zero clock
  contexts. `clock_followup/run.py` is verified active as
  `openlvds-scaled-decision-clock-followup.service`, waiting for the exact
  full-DC owner and a manifest-bound fifteen-case passing report. It freezes
  the leaf and shared helper code/environment and uses the unchanged global
  six-slot budget and actual shared slot 1.
- Three new tests verify exact profile selection, restoration of temporary
  factories/code on errors, and refusal of uncached DC or clock preparation
  from incomplete evidence. Full regression: 509 tests, 508 passed and one
  skipped; all nine uniform-decision tests pass.
- Native monitor-after replay `receiver_replay/822c30476339d818` is now
  fully complete and independently remeasured through the serialized cached
  verifier. Both original 80 ns cases contain 47 scored periods. Sharp
  control has zero missing/extra edges; captured control has eighteen
  missing (nine rising, nine falling), zero extra. `completion_recheck.json`
  binds the full scientific reports, waveforms, decks and manifest. The
  native owner exits successfully as a completed diagnostic; its actual
  electrical failure correctly holds the downstream owner. Both prepared
  component `d6fda107c33d401a` and link `e8fada5af2c6c3a0` still have
  zero simulations. No failed native branch is promoted.


Uniform-decision physical gate prepared on 2026-11-01:

- `layout_receiver_scaled_decision_candidate.py` requires all three completed
  source-clock controls, their passing admission, and the exact correlated
  full DC matrix before any geometry is drawn. It serializes cached source
  remeasurement separately from the scientific execution lock; missing
  results cannot launch missing simulations through a cache-verification path.
- The source is reconstructed from the exact uniform-scaling factory. New
  metadata explicitly identifies `unclamped_uniform_decision_scale4`,
  decision input/load W32 and tail W64, retaining input-tail scale 2 and
  original three restoration buffers. This is distinct from the old reduced-
  tail profile and cannot acquire its native/component admission implicitly.
- Placement reuses the monitor-after ordering and verifies the full device
  multiset before drawing, including all nodes, models and parameters.
  Geometry caches verify all seven physical evidence files, preserve partial
  builds for diagnosis and refuse changed source or identity. The source
  flattening has 88 devices and nine ports; those are not yet GDS/LVS counts.
- `a3a34b4ac8e5f600/physical_preflight.json` binds the actual expected refusal
  from missing source-clock results and zero generated layouts. Resource-only
  `physical_followup/run.py` is verified active as
  `openlvds-scaled-decision-physical-followup.service`. It waits for the exact
  clock owner and hash-bound passing source report, then invokes the gated
  Magic DRC/LVS build and independent extracted-connectivity audit. It freezes
  code/context/environment, handles completed collected owners, and leaves
  native/component/link/PHY admission explicitly pending after extraction.
- Three tests check exact scaled devices and functional placement order,
  incomplete-clock refusal before rechecking or launching simulations, and
  prevention of drawing after a failed source gate. Full regression: 512
  tests, 511 passed and one skipped; all twelve uniform-decision tests pass.
  No geometry or source-clock case has yet run for this branch. SF/40 remains
  queued; TT/25 and FS/40 are the only completed uniform-scaling pilots.


Uniform-decision pilot gate passed on 2026-11-01:

- SF/40 `receiver_scaled_decision_static/aeb25b9ac3f5874e` completes and
  passes all twelve original samples. All three pilots now pass. The actual
  scientific matrix remeasures their waveforms and advances to the remaining
  source DC corners; TT/0 also completes by this observation. All required
  fifteen conditions remain; no partial matrix is admitted as complete.
- `a3a34b4ac8e5f600/pilot_threshold_envelope.json` binds all thirty-six
  completed pilot samples and their actual manifests/reports/waveforms.
  Expected-output-high CO is at most 0.913786 V (FS/40 at 22 ns);
  expected-output-low CO is at least 1.426299 V (FS/40 at 10 ns), leaving
  a 0.512513 V ideal fixed-threshold separation for these pilots only.
  This is not a measured inverter transfer curve or a full-PVT/native bound.
- The full-DC owner remains live. Clock and physical continuations wait for
  their exact upstream owners and actual passing full reports. No clock case
  or new geometry is started from the pilot result alone. All shared slot
  ownership, fixed supplies, original fixtures and failure criteria remain.


Uniform-decision native replay prepared on 2026-11-01:

- `probe_receiver_scaled_decision_candidate.py` implements a distinct native
  profile for decision scale four, tail W64 and input/mirror W32. It rejects
  the old reduced-tail and PMOS-only metadata, then requires the exact source
  factory, current full source/DC proofs, DRC/LVS, GDS/source binding and an
  independent native connectivity audit before preparing either replay case.
- Assembly preserves the exact shared bias and digital RX closures. Both
  original captured/sharp fixtures retain full 80 ns, 5 ps output, original
  pin stimuli/load and 15–75 ns scoring; maximum integration is explicitly
  1 ps in both. Prepared library/deck/manifest caches cannot be rewritten.
  Both case IDs must be present exactly once. No new native context exists
  at this observation because the required audited geometry is not built.
- Each actual simulator takes its own shared lease, with zero, one or two
  selected wait slots allowed only inside the existing six-slot budget.
  Resource receipts are separate from the immutable scientific manifest.
  Complete finite monotonic waveforms and current hashes are required;
  cached reports are remeasured and partial failed traces retained rather
  than rerun in place. Failed case execution is recorded explicitly, while
  the independent other control is allowed to finish.
- The native aggregate distinguishes a completed diagnostic from passing
  clock transport: both original 47-period cases must have exactly one output
  edge per period. `native_clock_passed` does not imply full PVT, component,
  stress, power, aperture, loaded-link or PHY qualification. Existing legacy
  selectors do not silently admit this new profile.
- Actual `a3a34b4ac8e5f600/native_preflight.json` proves missing audited
  geometry refuses preparation and creates zero native contexts.
  `native_followup/run.py` is verified active as
  `openlvds-scaled-decision-native-followup.service`, waiting for the exact
  physical owner and its completed extraction/audit. It freezes code and
  parent context, then calls the scientific prepare/run gates using selected
  slots 1 and 3 independently. Failed native transport holds further admission.
- Five new tests verify strict profile selection, original numerical fixture,
  missing-geometry refusal, preservation of both partial traces without any
  simulation launch, and actual cached waveform remeasurement/incomplete-
  waveform refusal. Full regression: 517 tests, 516 passed and one skipped.
  All seventeen uniform-decision tests pass. The actual full DC campaign has
  eight passing cases; SS/0 is queued for its shared lease. Source clock,
  physical and native continuations remain gated on completed evidence.


Uniform-decision component/link selector prepared on 2026-11-01:

- `qualify_scaled_receiver.py` explicitly selects the new native profile for
  the unchanged receiver component and saved reference-link engines. It
  requires the exact uniform-decision metadata; old reduced-tail and PMOS-only
  profiles cannot be substituted. Factories, verifiers and producer-code
  bindings are restored after preparation/run success or any error.
- Before integration can start, both actual native waveforms are remeasured
  through their scientific producer. Complete case reports must already
  exist, so this cache path cannot launch a missing native simulation. A
  shared blocking cache-verification lock serializes the independent component
  and link consumers. The new `native_clock_passed` result must be true and
  bound to the current manifest, in addition to the existing transport gate.
- The original component engine retains all sixty source/native DC/rate
  conditions and exact fixture reconstruction. The link engine retains the
  saved full-RC ideal-phase SS/40, 410 MHz, 32-bit diagnostic reference
  `build/link/ss_40_410m_d0.45_s100_e0_ideal_32/6735242e52a2`.
  This receiver-only diagnostic does not establish final selected-driver,
  measured-DLL, early-digital-RX or full-PHY qualification. Uncached partial
  integration traces are refused for in-place retry and retained for diagnosis.
- Actual `a3a34b4ac8e5f600/integration_selector_preflight.json` binds the
  current selector and completed old native replay. Both component and link
  preparation reject that profile before creating any diagnostic context.
- Resource-only `integration_followup/run.py` is verified active as
  `openlvds-scaled-decision-integration-followup.service`. It waits for the
  exact native owner and passing hash-bound report, then prepares the full
  sixty-case suite and reference-link check. Two component workers and one
  link process use independent actual shared leases within the unchanged
  six-slot limit; no outer lease is retained around child workers. Both
  diagnostics must report passing results bound to their actual manifests.
  Fresh selected-analog/digital assembly and complete release gates remain.
- Six tests verify exact profile selection, restoration of temporary bindings,
  missing-case refusal, rejection of false native admission despite successful
  exit, real flock serialization for both cache consumers, and partial-trace
  preservation. Full regression: 523 tests, 522 passed and one skipped.
- The actual full DC campaign now has nine completed passing cases, including
  SS/0. SS/25 is next in the live campaign. No new receiver clock, geometry,
  native replay, component or reference-link simulation is admitted yet.


Changed-decision terminal observations on 2026-11-01:

- `receiver_decision_headroom.py` measures all six terminal-pair differences
  for each of the five changed thin decision devices from every recorded
  time point in each completed original 144 ns schematic trace. Settled
  drain/source magnitudes use the original twelve sampling times separately.
  It remeasures the actual waveforms, verifies their saved results, code,
  input/fixture/runtime hashes, exact five-width source intervention, fixed
  3.3/1.8 V rails and required process/temperature coverage. It launches no
  simulator and changes no existing producer, fixture or waveform.
- Immutable report
  `a3a34b4ac8e5f600/decision_headroom/5c8b09f2bb46fee8/summary.json`
  covers eleven completed source cases, not all fifteen. All five observed
  devices remain below the existing project thin-device screening guard of
  1.95 V. This is the guard already used by `ota_operating_points.py`, not
  a newly asserted PDK safe-operating-area rating.
- The largest recorded difference is 1.793156 V at XC1 drain/body in FF/0,
  83.953226 ns. Minimum settled tail drain/source magnitude is 5.530552 mV
  in SS/0. The CL-side and CO-side input-device minima are 298.724 mV and
  25.429 mV respectively. These are measured terminal voltages, not BSIM
  VDSAT values or saturation-region classifications. Source currents and
  power are explicitly unmeasured; remaining receiver devices and all native
  parasitics are outside this observation's scope.
- Initial observation `decision_headroom/6fa068f689870e81` is retained with
  its matching `producer.py`; the current report additionally validates the
  exact matrix coverage and producer context. More completed cases generate
  a new content-bound report rather than rewriting earlier observations.
- Three tests cover all five declared devices, a transient guard violation
  between the static sampling times, separate settled headroom measurement,
  and refusal of incomplete waves or unobserved terminal nodes. Full
  regression: 526 tests, 525 passed and one skipped.
- The actual DC campaign has now completed twelve passing cases, including
  FS/0; FS/25, SF/0 and SF/25 remain. Clock and downstream continuations
  still require the complete actual upstream reports; no partial voltage
  observation is promoted to full receiver or PHY qualification.
