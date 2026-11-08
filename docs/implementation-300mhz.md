# 300 MHz implementation

The active target is 600 Mb/s DDR with a 300 MHz forwarded clock. The
versioned `clocking_300mhz.json` profile supplies 290/300/310 MHz and
40/50/60% duty, fixed supplies and five process corners at 0/25/40 C.
Historical `requirements.json` and captured 400 MHz producers remain intact.
All new results must bind the new profile; legacy results cannot qualify it.

## Completed foundations

- The profile loader derives an 806.452 ps fastest quarter-period budget,
  862.069 ps slowest quarter, 1612.903 ps minimum bit interval and
  3948.276 ps minimum RX deskew range. Absolute precision and eye limits stay
  unchanged.
- The pinned OpenPLL main revision already supports divider 12. The new wrapper
  exposes `clk_serial`. Its separate RTL/controller capture measures
  300.430287 MHz, 49.9699--50.0150% duty and 12 ps behavioral period jitter.
  Evidence is in `build/openpll_300`; this is not a physical jitter certificate.
- The namespace-safe 400 MHz drainer preserves solver children and archives
  only tickets whose owner-lock inodes belong to the verified coordinator.
  The old counter coordinator PID 2178341 has retired after its solver children
  finished naturally. `frequency_migration_300/2178341_469977845` records
  178 completed summaries and 180 retained cases as `archived_incomplete`,
  with the original artifact unchanged. This does not qualify the old campaign.
- The numerical current-centering control completes all three cases without
  errors or guarded runs. Active native voltage parity is 0.875368 mV maximum,
  crossing parity 0.001964 ps, with the original real history failure retained.
  This permits controlled use of the external bench load, whose 1.8 mW must be
  excluded from chip power. It is not a voltage sweep or a changed MOS model.

## Native bank pilots now running

`native_bank_300_v1/b3f726547e6143f8` uses the restored P80/N32 bank,
original qualified native components and a fresh 310 MHz SS40 stimulus.
The five 40 ns/eight-startup-event cases are:

1. Fine31/60% with the original ideal supply bench.
2. The exact same case with a 1 mA external supply-current offset.
3. Zero/50% with the offset.
4. Fine31/40% with the offset.
5. Coarse1/fine0/50% with the offset.

The full-vector active comparison must retain all individual terminal,
control and programming-gate classifications within 2 mV and 0.25 ps.
All pulse, epoch, period/history, slew, stress and control gates remain.
The zero-code quarter limit now comes from 310 MHz, never from the legacy
410 MHz constant or the more permissive nominal 300 MHz quarter. Both
conservative coarse overlaps must be positive. Missing events reject admission.
These are component-RC pilots with 20 fF output load; actual next-bank
loading and routed bank RC remain required.

Overnight completed 400 MHz results reinforce the range issue: the restored
bank fails overlap at -144.855/-117.525 ps, and paired-stage removal fails
at -211.910/-246.465 ps. Its loading also makes zero-code latency worse.
The restored P80 zero delay is approximately 753.372 ps, leaving only a
projected 53.080 ps margin against the new fastest-quarter budget before
actual 300 MHz and next-load checks. Pair removal must not be assumed faster.

## Remaining implementation sequence

1. Independently replay the fresh pilot measurements. Test actual next-bank
   loading before admitting any bank or making a delay table.
2. Repair the fine range if required: test the qualified single P40/N16 fine
   driver, then switched 2x3 MIM fine cells, initially four copies per enable.
   Bound the search to two/four/eight copies and single/two-parallel P40/N16;
   change one factor at a time. Reassess paired-stage removal only with measured
   input loading. Select qualified extracted area, then power.
3. Establish common monotonic codes across all 15 PVT, <=20 ps gaps, RX range
   >=3948.276 ps, and complete 290/300/310 MHz boundary/update tests.
4. Requalify DCC, stopped-clock counter and detector at the new rates, including
   the new 270-case counter matrix. Preserve 25 MHz management, 64 confirmations,
   256 warm-up cycles, 100 ms timeout and eight-cycle clock-loss invalidation.
5. Obtain a genuine extracted 300 MHz OpenPLL DCO trace; qualify calibration,
   training, 45 full-link PVT/frequency cases, duty extremes, 4096/512 native
   bits, both OpenPLL traces and one million behavioral bits. Complete fresh
   physical DRC/LVS and joint RC before release.

New checks so far: two profile tests, seven drain safety tests, two clock
contract tests and five native-pilot tests pass. None of these software checks
admits a PHY. Global SPICE budget stays six, with at most two workers per campaign.

## Physical OpenPLL source reconstruction

The pinned source is being rebuilt in a private git-archive copy under
`openpll_physical_300/20261108T011353Z`. Unit
`openlvds-physical-openpll-300`, invocation
`999e557c291241658eb1cbffe332560f`, runs the unchanged upstream DCO physical
configuration and then its Magic extraction script. The source submodule and
old captures are untouched. The manifest binds the archive, producer, profile,
PDK and intended coarse2/fine12 operating point. Physical construction has
reached routing; extracted waveform qualification has not started.

Two tests verify that a wrong source pin cannot launch physical tools and
that a failing physical flow retains its evidence without running extraction
or producing a successful summary. Log: `build/physical-openpll-300-tests.log`.
The physical rebuild alone will not admit a clock trace or a PHY.

## Physical construction complete; extracted transient running

The isolated DCO rebuild and extraction now complete. Final metrics report
zero routing, Magic and KLayout DRC errors, zero unmapped instances, and zero
LVS device/net/property differences or unmatched devices/nets/pins. These
checks establish this source layout, not its electrical clock behavior.

`capture_openpll_physical_300.py` checks all eleven physical metrics, verifies
private source files against the pinned git objects and checks the mode table
before preparing a fixed coarse2/fine12 transient. It fingerprints the GDS,
extracted netlist, extraction settings, PDK model files, numerical runtime and
producer dependencies. The 70 ns TT25/1.8 V transient uses a real reset pulse,
2 ps maximum steps and one priority-1 lease under the existing six-slot budget.
No current-centering offset or source waveform rescaling is applied here.

The fresh trace context is `openpll_trace_300/20261108T013035Z`; unit
`openlvds-extracted-clock-300`, invocation
`33b06a6e8bb142839903a39b40370faf`. Its solver is live; waveform qualification
is pending. The upstream extraction includes capacitance and omits route
resistance, which is recorded explicitly. This source trace cannot certify
full interconnect-R clock jitter or closed-loop PLL behavior.

The capture requires alternating finite late edges, full swing on each
complete high/low interval, and a -0.15--1.95 V digital-input screen before
converting analog crossings into clock edges. Exact threshold samples count
once. Six tests cover these checks, source physical-check completeness and
failure retention; all pass in 0.011 s. Log:
`build/capture-openpll-physical-300-tests.log`.

The centered 310 MHz fine31/60% bank point also completes without execution
errors. Its rising-history span is 1.165129 ps, falling span 0.001525 ps,
and maximum period error 1.165169 ps. All individual native point gates pass.
The unshifted comparison and the zero/fine40/coarse endpoints remain pending;
this single centered point does not admit the bank or prove range overlap.

## Single-driver range experiment launched

The fresh baseline zero/50% point now completes with every individual native
point gate passing. Its maximum delay is 750.541009 ps, leaving 55.910604 ps
against the 310 MHz quarter-period limit under the original 20 fF load.
Baseline fine40, coarse1 and unshifted active parity are still pending.

The next one-factor revision is `native_bank_300_v2/2d31edbabe113146`.
`single_fine_driver_300.py` removes only branch Xb from the qualified parallel
fine-driver wrapper, preserving Xa's numerical definition verbatim. Actual
native expansion verifies 2070 MOS / 138 MIM, all remaining transistor
connections unchanged, 86 controls and all 266 programming-gate observations.
No coarse topology, fine capacitance, pre-driver or output load changes.

`openlvds-single-driver-300-v2`, invocation
`1c9bad181f3c4b39ae71ec80dd79557e`, runs the same five 310 MHz SS40,
40 ns/eight-event cases, including its own unshifted/centered active control.
It uses the unchanged dispatcher, at most two workers and priority 1; lease
availability determines concurrency. Its consumer additionally verifies the
entire reconstructed source identity and exact bench-offset metadata. This
producer and its dependencies are now captured and must remain immutable.

Three new transformation tests pass (0.581 s), checking exact native terminal
preservation and rejection of damaged observations or an already modified
wrapper. Five pilot contract/stimulus tests pass (0.262 s). These tests do not
qualify the new bank: range overlap, analog point gates and active numerical
parity must pass first, followed by next-bank loading and full qualification.


## Fresh counter protocol and 270-case campaign

`counter_protocol_300.py` retains the seven actual raw-clock pulses and the
qualified 808-MOS/57-MIM loaded counter with 17087 shared-wire resistors and
4407 capacitors. The new transient lasts 40 ns. REQUEST falls at 28 ns and
reasserts at 32 ns, after the last possible 290 MHz/60% raw transition
(<24.86 ns). The clock must remain stopped from 27 ns, and public outputs,
armed and high1/low1 state are checked from 30 ns by the captured v1
producer. This introduced a 2 ns clear allowance; the correction below
restores the original 3 ns deadline at 31 ns through the second REQUEST
assertion. The initial REQUEST assertion stays at 3.4 ns.

The new measurement checks all seven raw and buffered clock epochs, exact
raw frequency/duty, causal buffered events, two/three qualifying edges,
positive bounded release latency, phase order, guaranteed-low assertion
windows, stopped-clock asynchronous clear/reassertion and every original
transistor terminal-pair stress limit. Waveforms and device models are not
rescaled; supplies stay fixed at 1.8 V. The unchanged generic seven-cycle
low-window algorithm is applied only after validating the full 40 ns trace.

`counter_pvt_300_v1.py` prepares 270 fresh native traces: five process corners
at 0/25/40 C, three clock frequencies, three duties and two stopped levels.
It binds the new profile and the existing qualified actual shared-RC libraries,
reconstructs all 808 native terminal maps, verifies the original topology
certificate and reuses zero old timing cases. Historical 400 MHz traces cannot
satisfy any new point. Two workers use priority 2 and the unchanged global
six-slot dispatcher. All qualification flags remain false until the relevant
new electrical gates pass; this campaign alone cannot admit the whole clock
or PHY.

Eight synthetic metrology/matrix/fixture tests pass (0.130 s), including all
18 frequency/duty/stopped-level combinations and rejection of truncated,
missing-clock, wrong-frequency/duty and unintended release cases. Synthetic
signals verify the measurement, not the hardware. The initial test invocation
used an environment without KLayout and failed at import; the successful runs
use `build/tools/counter-physical-venv/bin/python` through `scripts/env.sh`.

All 270 counter benches and library copies have now been prepared and their
manifest bound successfully. The live context is
`counter_pvt_300_v1/eec2546717d211ee`, unit
`openlvds-counter-pvt-300-v1`, invocation
`d5a929bffc7f478bbea7ecad802aa2e9`. The coordinator has entered its running
state; electrical results remain pending. The producer, protocol and captured
dependencies are immutable for this campaign. Log:
`build/counter-pvt-300-v1.log`.

## Switched-MIM circuit materials prepared

`mim_fine_bank_300.py` implements the approved bounded range-repair family:
qualified 2x3 switched-MIM RC cells, two/four/eight copies per enable, and
single/two-parallel P40/N16 fine drivers. It preserves the complete original
coarse tree, pre-driver, output driver, controls and output load. The full
retained physical/native/Schur proof bindings revalidate (94 material inputs);
the numerical cell definition is reused verbatim, including its existing
extracted programming-gate resistance.

The immutable circuit bundle is
`mim_fine_bank_materials_300_v1/3de6071016724809`. All six complete native
libraries and observation maps regenerate from the captured source. It is
explicitly `prepared_unqualified`, with zero simulations. Four copies are the
planned first MIM point after the single-driver results establish need and
which driver retains quarter-period margin. This bundle does not launch a
parameter search or bypass the pending numerical parity/endpoint gates.

| Fine driver | Copies/enable | Actual MOS | Actual MIM | Programming gates |
| --- | ---: | ---: | ---: | ---: |
| Single P40/N16 | 2 | 1946 | 200 | 266 |
| Single P40/N16 | 4 | 2132 | 324 | 452 |
| Single P40/N16 | 8 | 2504 | 572 | 824 |
| Two parallel P40/N16 | 2 | 2002 | 201 | 266 |
| Two parallel P40/N16 | 4 | 2188 | 325 | 452 |
| Two parallel P40/N16 | 8 | 2560 | 573 | 824 |

All variants retain 86 logical controls. Gate maps are rebuilt from actual
native transistor terminals and resistor connectivity to EN/ENB. Every
non-fine transistor connection and all 80 non-fine programming-gate records
are preserved. The builder rejects changed numerical cells, shorts between
programming controls, missing fine copies, damaged observation maps and
choices outside the approved search bounds. Five tests pass (2.873 s),
including all six complete native expansions. Preparation then validates the
captured files and reconstructs all variants again. Logs:
`build/mim-fine-bank-300-tests.log`,
`build/mim-fine-bank-300-materials.log` and
`build/mim-fine-bank-300-prepare.log`.

The six occupied SPICE slots remain assigned to the live baseline,
single-driver, extracted OpenPLL and fresh counter runs. Read-only inspection
of flushed samples confirms progress (not qualification): baseline unshifted
24.862 ns, baseline coarse endpoint 26.243 ns, single-driver centered
34.699 ns and the first new counter point 14.914 ns. No healthy solver was
stopped or restarted.

## Independent fresh-bank replay and observed range failure

`replay_bank_300.py` validates the captured producer context and completed
case hashes, repeats every original metric, then independently measures native
threshold crossings, complete pulse epochs, period/history/slew/duty,
quarter-period margin, every transistor's terminal-voltage envelope and
control/programming-gate settling from waveform extrema. It requires full
40 ns data and never rewrites the original result or wraps event epochs.
It also closes the baseline consumer's missing explicit source-identity
comparison. Four synthetic metrology tests pass (0.044 s); tests do not admit
hardware. Log: `build/replay-bank-300-tests.log`.

Three replay receipts now complete with all selected original metrics and
independent checks reproduced:

- `bank_native_replay_300/19f78105cf672e13`: baseline zero/50%, case 2.
- `bank_native_replay_300/17e33e8e2dafa5e4`: baseline fine60/fine40/coarse1,
  cases 1/3/4.
- `bank_native_replay_300/45db2f98e4e9256d`: single-driver fine60, case 1.

All four centered baseline endpoints pass individual native gates. Its
conservative overlap nevertheless fails at **-125.475676 ps rising /
-114.675677 ps falling**. The single-driver fine60 case fails the unchanged
20 ps history and period limits in both benches: rising history is
24.349091 ps unshifted / 24.349046 ps centered, with period error
24.338721 / 24.338685 ps. The replay preserves those failed classifications.
Thus neither bank is admitted: the baseline needs more fine range and the
weaker driver introduces a repeatability failure. Aggregate active numerical
parity and full qualification are still required.

## Evidence-gated strong-driver MIM4 pilot launched

The observed failures select the next one-factor trial: retain the baseline's
two parallel P40/N16 drivers and replace only the fine-cell implementation
with four qualified 2x3 switched-MIM cells per enable. Coarse routing, group
restoration, pre-driver, final driver, controls and 20 fF load stay unchanged.
This is the prepared `p80_c4` circuit: 2188 MOS, 325 MIM, 86 controls and 452
actual programming-gate observations. Its startup/range/slew/stress behavior
is unproven until the new native points complete.

`mim4_evidence_300.py` requires all three completed replay receipts, verifies
their unchanged input hashes, requires passing baseline individual points and
both negative conservative overlaps, and requires the single-driver history
and period failures in both original/centered benches. It cannot select the
trial from a truncated trace or a merely proposed range problem. Four new
evidence/fixture tests pass (0.307 s), including refusal when proof is missing,
quarter margin fails or range repair is unnecessary. Log:
`build/native-bank-mim4-300-tests.log`.

`native_bank_mim4_300_v1/a8105c49e52731af` binds those receipts and the full
captured MIM-material proof, regenerates the exact circuit and all observation
maps, and prepares five 310 MHz SS40 40 ns cases. The active original/centered
pair is mandatory for this new circuit, before individual zero/fine40/coarse
points can collectively admit even a component pilot. External bench-current
power remains excluded; neither voltage nor device models are changed.
Historical proof raw files are fully hashed at preparation, campaign start
and finalization; per-lease guards retain every non-raw proof, source, model,
fixture and circuit input. Current scientific result files are never reused
or overwritten.

Unit `openlvds-mim4-bank-300-v1`, invocation
`3782b4bbc70a45e3880447978126dc9d`, uses at most two priority-1 workers under
the unchanged six-slot dispatcher. Log: `build/mim4-bank-300-v1.log`.
The existing healthy campaigns continue and lease availability determines
when the new solvers start. Producer/helpers are now captured and immutable.

The first new counter case (SS40, 310 MHz, 60% duty, stopped high) completes
with every native point gate passing and minimum remaining low window
474.841681 ps. This is one of 270 fresh conditions, not full counter or PHY
qualification.

## Diagnose the fresh stopped-low counter clear failure

The first SS40/310MHz/60%-duty stopped-low point completes with public clear,
phase ordering, low-window timing and all terminal stress checks passing, but
fails the captured producer's internal clear checks. Diagnosis
`counter_reassertion_diagnosis_300/ba5c7205c882bcd2` repeats every original
metric and preserves the original failure. Three diagnostic tests pass
(0.003 s); log `build/counter-reassertion-diagnosis-300-tests.log`.

The cause is an introduced metrology error: the original 26 ns protocol checks
clear state from 24 ns after REQUEST falls at 21 ns, allowing 3 ns. The new
40 ns producer checks from 30 ns after REQUEST falls at 28 ns, allowing only
2 ns. At 30 ns the actual low1/armed nodes are still decaying at 0.378372 V /
0.475650 V. Their maxima over the entire remaining trace from the original
3 ns deadline (31 ns) are only 0.027994 V / 0.028505 V. There are no extra
50% logic assertions after REQUEST reassertion. Public PREPARE/RESET_N stay
below 0.030550 V / 0.023843 V throughout the stricter original new window.
The diagnosis changes no gate and grants no electrical admission.

`counter_protocol_300_v2.py` restores the original 3 ns clear allowance from
the measured REQUEST falling edge, identically for public and internal state.
It retains the actual captured 40 ns stimulus, 4 ns REQUEST-low interval,
all event counts, 180 mV clear limit, phase/latency/window checks and every
transistor stress limit. The source/model/runtime and the live 270-case
producer are untouched. Four tests pass (0.152 s), including rejection of a
real late clear failure and equivalence of all other timing metrics across
all 18 clock/duty/stopped combinations.

`replay_counter_clear_300.py` binds the actual legacy 21/24 ns source and
stimulus, requires the completed diagnosis, repeats every original strict
measurement, and permits changes only to clear-settling predicates and their
aggregate flags. Three tests pass (0.002 s), including rejection of changed
stress classification or an arbitrary 5 ns allowance. The separate replay
retains both old gates and corrected results. It completes on fresh cases
0/1 under unit `openlvds-counter-clear-replay-300`, invocation
`8dfb88a82bdb4183afa00d0ad1fe7fab`; log
`build/counter-clear-replay-300.log`. No full-matrix or PHY admission is implied.


Replay `counter_clear_replay_300/87e00dff7df3cb45` completes both cases. The
stopped-high point remains passing; the stopped-low point changes from the
introduced 2 ns failure to passing the original 3 ns deadline. Every original
strict metric reproduces, and every metric outside the declared clear
predicates is identical. The original failed record is preserved. This closes
the identified measurement-window bug for these two cases, not the entire
270-case matrix. All future completed cases require the same separate replay
before the counter matrix can be admitted.

## Complete native stage diagnosis

`bank_stage_history_300.py` captures complete fixed-epoch histories for both
baseline and single-driver fine31 endpoints at 60% and 40% duty. It checks all
eight stage events, the known inversion polarity, causal ordering, input
stimulus epochs and exact agreement with the recorded outer delay arrays.
The original failed gates remain in the report. Three tests pass (0.031 s),
including rejection of missing/noncausal stages, changed outer delays and
missing startup. Log: `build/bank-stage-history-300-tests.log`.

`bank_stage_history_300/dd8ea5d1d99002a7` completes all four cases. At 60% duty,
the single-driver pre_out -> fine_node delay changes by -27.051040 ps from
first to last event; the strong-driver baseline changes by only -2.024483 ps.
The other stage changes are similar: coarse/selected about +4.09 ps and
pre-driver about -1.10 ps in the weak case. The weak fine driver therefore
dominates its measured 24.349046 ps total history failure. At 40% duty the
weak fine-stage change is only -1.995531 ps and total history spans 1.435642 ps.
All stage sums reproduce the outer delays with zero reported residual.

The duty dependence is consistent with incomplete fine-node recovery during
the shorter clock phase; this is an inference from the stage history, not a
terminal-current or charge-state proof. It supports keeping the stronger
driver in the ongoing MIM trial. No new architecture is admitted from this
diagnostic alone. Log: `build/bank-stage-history-300.log`.
