# 300 MHz implementation

## Fresh DCC source campaign

`scripts/dcc_source_300.py` adds a separate profile-bound source-cell matrix:
810 fresh cases covering five process corners, 0/25/40 C, 290/300/310 MHz,
40/50/60% complementary input duty, 20/250 ps slew, and 0/+/-140 ps input
event-spacing error. The independently admitted historical clock-aware reset
source selects the exact circuit/library bytes only; none of its 400 MHz
timing results count toward this matrix. Fixed 1.8 V, original reset,
18-cycle native integration, 20 fF load, tolerances, observations and event/
reset-hold/50 ps balanced-half-cycle checks remain unchanged.

The new runner uses one priority-2 worker through the unchanged six-slot
dispatcher. It binds every transitive model include across all library
sections, source-selection receipts, circuit libraries, generated decks,
profile, producer dependencies and native runtime. It refuses prior execution
and retains all errors and failed cases. Four focused tests pass (0.674 s),
covering the complete matrix, exact duty-only stimulus change, transitive
model-file rejection, and event/reset/symmetry gates. Preparation is validating
the historical source-selection receipt; no new source result is admitted yet.
Even a passing source matrix will not qualify physical DCC RC, startup,
device-terminal stress, a loaded DLL, or the complete PHY.

The first preparation refused to proceed because the inherited counter model
list omitted `parameters/montecarlo.spice`, referenced by the top-level model
library. No campaign or transient was created. The failed log is retained as
`build/dcc-source-300-prepare.log`. Preparation now discovers and hashes its
own complete model graph, including quoted/unquoted include and library-file
directives, then checks those captured hashes during execution. Four updated
tests pass (0.609 s); log: `build/dcc-source-300-model-closure-tests.log`.
The fresh preparation attempt uses `build/dcc-source-300-prepare-v2.log`.

Preparation now succeeds as `dcc_source_300_v1/1a4f4e8eabb896e4`, capturing
319 transitive model files (including the previously omitted Monte Carlo
parameters) and all 810 freshly generated decks. Independent model-discovery
preflight is retained in `build/dcc-source-300-model-closure-preflight.log`.
Unit `openlvds-dcc-source-300-v1`, invocation
`791b8814509f48519ae8093409efed40`, runs its single priority-2 worker;
the first native ngspice process is confirmed live. Log:
`build/dcc-source-300-v1.log`. There are six active SPICE processes including
this new worker; existing campaign caps and dispatcher inodes are unchanged.
No completed source result or source/PHY admission is claimed at launch.

`scripts/replay_dcc_source_300.py` now verifies complete selected native cases
without a SPICE lease. It binds the source manifest, libraries, model/runtime
inputs, per-case summaries and every retained native witness; it reproduces
the original measurements exactly, then independently checks observed input
frequency/duty/phase spacing, one event and output transition per source
event, reset hold, output swing and balanced mean half-cycle error. Deliberate
+/-140 ps input spacing cases test event handling; the 50 ps symmetry bound
applies only to zero-error inputs, as in the original source contract.

Native replay of cases 0 and 1 completed in
`dcc_source_native_replay_300/aa26c26d52eee286`: both original measurements
reproduce and both independent screens pass. The zero-error case has
29.811819301 ps balanced mean half-cycle error. Log:
`build/dcc-source-300-first-native-replay.log`. Four consumer tests pass
(0.066 s), including missing-event, wrong-duty, reset-hold and incomplete/
nonfinite-waveform rejection. The first test attempt's incomplete fixture
still extended beyond the required stop time; its corrected fixture and
passing run are retained in `build/dcc-source-300-replay-tests-v2.log`.
Full source-matrix admission explicitly requires all 810 completed cases and
fresh successful remeasurement; a selected replay cannot grant it. All PHY
and physical-DCC qualifications remain false/open.

The first complete SF40/310 MHz DCC source cohort (cases 0--17) now passes
both original and independent checks. Its exact 18-point coverage is
40/50/60% duty x 20/250 ps slew x 0/+/-140 ps input-spacing error. Independent
receipts are `dcc_source_native_replay_300/aa26c26d52eee286` (0--1),
`409742ff0b289cf0` (2--8), and `3c66d98c6644361b` (9--17).
All source-event/reset checks pass, and the worst zero-input-error balanced
mean half-cycle error is 29.824359864 ps against the unchanged 50 ps limit.
The final cohort replay log is `build/dcc-source-300-sf40-310-final-replay.log`.
This establishes one source-only PVT/frequency cohort; the other 792 matrix
cases and all physical-DCC/PHY gates remain required. The unchanged single
worker continues at the next frequency.

The complete nominal SF40/300 MHz source cohort (cases 18--35) also passes
original and independent checks in
`dcc_source_native_replay_300/f470710605c64804`. Its exact 18-point duty/slew/
spacing coverage matches the 310 MHz cohort, with worst balanced mean
half-cycle error 29.831467650 ps. Log:
`build/dcc-source-300-sf40-nominal-replay.log`. Thus cases 0--35 have independent
passing source evidence at SF40 and both 300/310 MHz; 290 MHz and the other
PVT conditions remain pending, as do all physical-DCC and PHY gates.

SF40 source-frequency coverage is now complete: cases 36--53 at 290 MHz
also pass original and independent checks in
`dcc_source_native_replay_300/3456c116dbc6d4eb`. The exact 18-point duty/slew/
spacing cohort has worst balanced mean half-cycle error 29.837616202 ps.
Log: `build/dcc-source-300-sf40-290-replay.log`. All 54 SF40 source cases at
290/300/310 MHz now have independent passing evidence; the remaining 14 PVT
conditions and all physical-DCC/PHY gates remain open. No captured circuit,
runner, numerical tolerance, load, dispatcher or qualification bound changed.

The first cold source cohort, SF0/310 MHz cases 54--71, also passes both
original and independent checks in
`dcc_source_native_replay_300/4ad93fd7a1068f7b`. Exact coverage remains all
three approved duties, both slew limits and all three spacing errors;
worst balanced mean half-cycle error is 26.613362856 ps. Log:
`build/dcc-source-300-sf0-310-replay.log`. Cases 0--71 now have independent
passing source evidence, with the SF0 lower frequencies and remaining PVT
conditions still pending. This is still ideal-input, source-cell evidence;
no physical DCC, DLL or PHY admission is granted.

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

## Automatically replay completed counter cases

Fresh counter case 2 (SS40, 310 MHz, 40% duty, stopped high) also replays
successfully with all non-clear metrics unchanged. Its receipt is
`counter_clear_replay_300/1bdd07415317b05a`; three fresh counter cases now have
passing original-3-ns replay evidence. The 270-case matrix remains incomplete.

`watch_counter_clear_300.py` runs on the host and invokes the pinned contained
replay tool serially as original case summaries complete. It verifies the
captured parent manifest and its own consumer sources, indexes only completed
receipts with matching tasks, preserves real failed points and refuses to
retry a case with partial replay evidence. Native errors are retained for
inspection. It neither changes dispatcher tickets nor starts, stops or
restarts SPICE. A terminal native coordinator with unfinished cases stops the
watcher for inspection; an observation failure alone is not treated as
terminal.

Five watcher tests pass (0.006 s): completed/partial receipt handling,
preservation of failed points, rejection of conflicting duplicate evidence
and native error handling. Log: `build/watch-counter-clear-300-tests.log`.
Unit `openlvds-counter-clear-watch-300`, invocation
`a09581fcd91b48298b258200252a34d3`, is live with context
`counter_clear_watch_300/6a76f5028c86c5c2`. It uses one replay worker, batches
of at most six and 30 s polling; the initial index contains three completed,
passing cases. Progress and child logs live within that context. Even a
complete index remains explicitly unqualified: final whole-matrix evidence
validation, all remaining clock/link gates and physical release stay open.

## Actual next-bank load fixture prepared, not launched

`next_bank_fixture_300_v2.py` replaces the first bank's artificial 20 fF load
with the complete native input of a second identical bank. Every native
transistor, extracted component definition, model/limit and connection is
retained; only instance/public-net names change. The second bank's output
retains the 20 fF far load. Separate controls permit next-bank fine0/fine31,
and the fixture saves every second-bank transistor terminal, logical control
and actual programming gate. Shared interbank wires remain ideal; detector
fanout, four-section DLL and whole-clock routing remain unqualified.

The immutable material context is
`next_bank_zero_materials_300_v2/3ccbbdcfc1410706`, based on the current MIM4
zero/50% SS40/310MHz source fixture. It contains an unshifted/centered
next-fine0 pair and a centered next-fine31 case, each with 4376 actual native
MOS across both complete banks. The waveform, fixed supply, tolerances and
first-bank controls are unchanged. All three decks and observation maps
regenerate and pass the actual native runner's translation preflight.
State is `prepared_unqualified`, simulations zero, and loaded active numerical
parity is explicitly pending. No loaded simulation is launched before a
candidate's component gates justify it.

Four native-map/fixture tests pass (4.973 s) across baseline, single-driver
and MIM4 circuits, including illegal codes, damaged maps and double loading.
Three runner tests pass (8.455 s), checking translation and preservation of
all saved names. Logs: `build/next-bank-fixture-300-tests.log`,
`build/next-bank-fixture-300-v2-tests.log` and
`build/next-bank-zero-materials-300-v2-prepare.log`.

The retained first implementation/context
`next_bank_zero_materials_300/0ee9ac03b06981fe` failed runner preflight because
OUT/VDD were duplicated in the saved-vector list. It was never simulated.
The captured v1 helper and files remain intact; v2 removes duplicate aliases
without losing any observation and invokes runner preflight on every deck.
Use the v2 helper/context, not the retained v1 artifact.

## New endpoint results still reject both candidates

The single-driver campaign now completes. Active numerical control fails its
full-vector 2 mV requirement: maximum difference is 33.511180 mV on
`v(xd.xdecode1_3.a_110_47#)`. Crossing difference is only 0.000779 ps and all
gate classifications agree, but that does not override the vector failure.
Its conservative overlaps also remain negative (-68.540655 / -62.116372 ps),
and fine60 already fails history. The complete campaign is not admitted.

The first centered MIM4 fine60 point completes with native terminal stress,
control settling and 194.471299 ps maximum output slew passing. Its rising
history span is 143.812567 ps and maximum period error 141.267880 ps, so it
fails the unchanged 20 ps gates. The fresh paired unshifted run and other
endpoints remain live. The current MIM4 bank cannot advance to loaded/PVT/DLL
qualification from this point. Next work must inspect its stage/charge
history and complete numerical control before another architecture/range
trial is selected; no threshold, supply or numerical tolerance is changed.

The counter watcher has now indexed four completed cases, all passing the
separate original-3-ns replay, with no failed replayed points. This remains
partial evidence from the 270-case matrix.

## MIM recovery failure independently reproduced

`replay_bank_300_v2.py` and `bank_stage_history_300_v2.py` extend the immutable
original helpers to the new MIM producer. The complete replay
`bank_native_replay_300_v2/0c6d13870c127e06` reproduces every original metric,
independent timing, terminal envelope and control/gate settling for centered
MIM4 fine60. Stage/recovery context
`bank_stage_history_300_v2/27d64d057235a80a` completes on the same unchanged
native waveform. Three tests pass (0.037 s), including source-terminal
provenance and rejection of incomplete recovery events.

Of the rising-history failure, 139.193884 ps lies in pre_out -> fine_node:
its delay changes from 435.129780 to 295.935896 ps. Before later pre-driver
rising transitions, fine_node reaches only about 1.603927 V, versus 1.804770 V
initially. Representative PFET/NFET capacitor-side switch terminals reach
1.444119 / 1.436984 V, versus 1.800890 / 1.800646 V initially. Thus these
observed nodes have not recovered to their initial voltages during the short
clock phase. The final output regenerator masks the incomplete internal swing
in the output-slew check, while the history gate correctly rejects it.
The report measures actual saved MOS-terminal voltages, not charge on an
unobserved MIM plate. Logs: `build/replay-mim4-failure-300.log` and
`build/mim4-stage-recovery-300.log`.

The centered MIM4 zero-code point subsequently passes, but with only
11.610458 ps quarter-period margin under 20 fF. This makes zero latency and
real loading mandatory gates for any new architecture; the failed fine60
point remains disqualifying.

## Distributed fine-stage architecture trial launched

`distributed_fine_bank_300.py` implements controlled changes using only the
retained qualified P80/N32 (two P40/N16) driver and switched-MIM components.
The stronger pre-driver replaces P10/N8 at the same three-inversion path.
Capacitance can then be reduced or split over pre_out and fine_node. Coarse
taps, muxes, group restoration, output driver, controls, numerical models and
20 fF load remain unchanged. Strengthening the pre-driver also changes the
load on selected; native zero-code quarter-period checks are mandatory.

| Variant | Pre-node copies/enable | Fine-node copies/enable | Native MOS | Native MIM | Programming gates |
| --- | ---: | ---: | ---: | ---: | ---: |
| strong_pre_c4 | 0 | 4 | 2282 | 326 | 452 |
| strong_pre_c2 | 0 | 2 | 2096 | 202 | 266 |
| split_c1_c1 | 1 | 1 | 2096 | 202 | 266 |
| split_c2_c2 | 2 | 2 | 2282 | 326 | 452 |

These isolate strength (original MIM4 versus strong_pre_c4), count
(strong_pre_c4 versus strong_pre_c2) and placement (each split versus the
matching unsplit count). All retain 86 logical controls. The exact native
expansion verifies that changes stay within the declared pre-driver/capacitor
instances and that every actual programming-gate record still names the
correct native gate terminal. Qualified subcircuit definitions are unchanged.
Four native-transform tests pass, including one-factor call comparisons.

`probe_distributed_fine_300.py` requires the completed independent MIM replay
and recovery diagnosis, including the observed fine-node/switch-side recovery
loss, before preparation. It binds the full retained physical/native/Schur
material proof and all original source/profile/model/runtime guards. Two
fixture/protocol tests pass. All six architecture/pilot tests pass together
in 5.618 s; log `build/distributed-fine-300-all-tests.log`. Every prepared deck
also passes the actual native runner translator.

The live context is `distributed_fine_pilot_300_v1/f07675577cda70f9`, unit
`openlvds-distributed-fine-300-v1`, invocation
`ef369cc17fdf49ac93600e74b9970253`. Fourteen 40 ns SS40/310MHz cases include
fresh unshifted/centered fine60 pairs for all four variants, then
zero/50%, fine31/40% and coarse1/50% for each split candidate. Both numerical
pairs use the full-vector 2 mV / crossing 0.25 ps limits. The original
period/history <=20 ps, zero quarter <=806.452 ps, slew <=250 ps, voltage and
control gates remain unchanged, and both conservative overlaps must be
positive. Missing events reject a candidate. No capacitor-charge guess,
phase wrapping, voltage sweep or tolerance change is used.

At most two priority-1 workers use the unchanged six-slot dispatcher; the
existing healthy jobs continue. Log: `build/distributed-fine-300-v1.log`.
Even a passing component candidate still requires actual next-bank loading,
common monotonic all-PVT codes, new routed shared RC, full clock/DLL/DCC/link
qualification and qualified area/power comparison before release.

## Extracted 300 MHz clock source completed and verified

The original `openpll_trace_300/20261108T013035Z` transient completes naturally.
Its measured frequency is **301.151834 MHz**, duty 50.852331--50.852474%, with
12 late rising edges. All eleven required physical construction metrics
remain zero. The extracted source includes capacitance, not interconnect
resistance; its 0.002458 ps measured period spread is a deterministic native
simulation result, not physical noise/jitter statistics or closed-loop PLL
qualification. This fixed-code TT25/1.8 V source remains distinct from the
RTL/controller/calibrated-DCO source at 300.430287 MHz.

`verify_clock_sources_300.py` independently checks frequency, duty, edge
counts and period spread for both source traces, verifies every captured
input and the unchanged OpenPLL pin, revalidates physical metrics/extraction
scope, and regenerates the physical CSV byte-for-byte from the original
70 ns native waveform. No edges are scaled, synthesized or tiled. Four tests
pass (0.006 s). The verified source bundle is
`verified_clock_sources_300/b919a47f1f6cefea`; log
`build/verify-clock-sources-300.log`. It is source evidence only. The physical
trace has only 11 complete late periods (22 complete DDR bit intervals),
so it cannot satisfy the 4096-bit native payload budget.

## Parity-gated long physical clock capture

`capture_openpll_long_300.py` prepares a 70 ns KLU pilot followed, only if its
observed native waveform parity passes, by a genuine 20 us capture. The
original 70 ns default-solver run is complete and untouched. The pinned
ngspice-42 runtime confirms compiled KLU support; banner log:
`build/openpll-klu-runtime-version.log`.

The pilot changes exactly one declaration: `.option klu`. All MOS models,
geometry, code2/fine12, TT25/1.8 V bias, reset release/edge times, 2 ps steps,
Gear method and numerical tolerances are unchanged. It compares PLLOUT over
the entire absolute 0--70 ns interval in both interpolation directions,
requires <=2 mV observed voltage difference and <=0.25 ps absolute crossing
error, and forbids phase alignment or rescaling. Only PLLOUT was saved in the
original source; the proof explicitly does not claim internal-node voltage
parity. A failed pilot is retained and prevents the long run.

The long deck extends both stop time and the reset pulse's high hold/period,
so the DCO does not accidentally reset again at 75 ns. It retains the original
late-window edge extraction and requires at least 4096 complete observed DDR
bit intervals. The source comes from actual native integration, never repeated
or scaled short-trace data. Passing this source check would not establish
actual data-bit transmission, interconnect-R/noise behavior, closed-loop PLL
jitter or a PHY. Five tests pass (0.016 s), including unchanged-tolerance and
reset-hold checks, strict absolute waveform parity, and rejection of partial
or altered references. Log: `build/capture-openpll-long-300-tests.log`.

The live context is `openpll_long_trace_300_v1/7398cf894f0d9e4f`, unit
`openlvds-long-clock-300-v1`, invocation
`1e652fbc3dcd4c959f9c43bf0c1d279f`. One worker uses priority 1 for the parity
pilot and priority 2 for the long capture, under the unchanged global six-slot
budget. No healthy solver is interrupted. Log: `build/long-clock-300-v1.log`.
The current stage is the parity pilot; long-capture results remain pending.

## Full counter-matrix recomputation gate ready

`qualify_counter_matrix_300.py` requires a naturally complete, zero-error
270-case native campaign and exact completed replay coverage of every new
290/300/310 MHz condition. It rejects missing/duplicate/mismatched tasks,
legacy frequencies, changed clear deadlines and non-native provenance. It
then validates all captured source/model/geometry/runtime/raw hashes,
recomputes every original strict metric and corrected 3 ns metric from each
actual 40 ns waveform, and requires exact agreement with the stored native
results and corrected receipts. It does not accept the watcher's index as an
electrical certificate.

Only after all 270 traces are recomputed does it report complete 15-PVT
coverage and a routed-counter matrix pass/fail, including genuine failed
cases, minimum low-window margin and maximum terminal stress. Whole-clock
and PHY qualification remain false. All old failure records are retained;
no SPICE is restarted. Future output context:
`build/diagnostics/counter_matrix_recomputed_300`.

Four coverage-schema tests pass (0.041 s); their synthetic metadata creates
no electrical artifact. The actual current campaign is correctly refused
before creating a certificate because it is incomplete. Logs:
`build/qualify-counter-matrix-300-tests.log` and
`build/counter-matrix-300-incomplete-preflight.log`. When prerequisites are
complete, run through the combined numerical/physical environment:

```
./scripts/env.sh --tools --ngspice build/tools/counter-physical-venv/bin/python scripts/qualify_counter_matrix_300.py
```

The counter watcher now indexes 14 completed passing replays. The first
centered `strong_pre_c4` architecture control completes with native stress,
control settling and slew passing, but rising history spans 183.813491 ps
and period error reaches 182.581523 ps. Pre-driver strength alone therefore
does not fix the observed recovery failure. The reduced-count and split-node
trials remain pending; no new candidate is admitted from this control. The
completed 40 ns result is retained unchanged.

## Smaller current-origin numerical control queued

`probe_small_center_300.py` tests 10 uA, then 1 uA only if the first offset is
not admissible, against the complete unshifted single-driver fine60 SS40 /
310 MHz / 40 ns reference. This responds to the observed 33.511 mV full-vector
failure of the previous 1 mA offset; it does not reinterpret that failure as
passing. All circuit/model parameters, fixed 1.8 V supply, stimuli, timestep
and tolerances remain unchanged. The current is an external ideal-supply
bench load, not an analog device-bias or voltage sweep. Its 18 uW / 1.8 uW
contributions are excluded from chip power.

The macro/bench must have no feedback from I(VDD), and the generated deck
must pass the actual native runner's translation. The original unshifted
measurement must reproduce exactly before the new test. Both directions of
full native voltage interpolation must remain within 2 mV, all input/output
crossings within 0.25 ps, and every aggregate and individual stress/control/
programming-gate classification must match. The original physical history
failure must remain a failure. This tests numerical equivalence only, not a
circuit fix; every new circuit still requires its own active control.

Three tests pass (0.059 s), including exact deck restoration, fixed supply
and feedback/offset rejection. Log: `build/probe-small-center-300-tests.log`.
The immutable context is `small_current_center_300_v1/91f5a0b6b1bc4219`, unit
`openlvds-small-current-center-300`, invocation
`4be78c19c8c04f13ae0b1dbca85b492e`. One priority-2 worker uses the unchanged
six-slot dispatcher. Existing simulations and tickets are untouched. Native
engine elapsed time is recorded separately from wall time including queue
wait; no speed improvement is asserted before measurements. Log:
`build/small-current-center-300.log`.

Fifteen completed counter cases have passing corrected replay evidence. The
main distributed-capacitance and long-clock parity trials remain live; no new
physical candidate or matrix is admitted by this numerical experiment.

### MIM4 coarse/fine coverage evidence

The completed MIM4 coarse-one, zero-code and fine-40 cases were independently replayed in `build/diagnostics/bank_native_replay_300_v2/bbdcae2806f20b0c`. All original metrics, independent timing, terminal envelopes and control/gate settling reproduce without parameter changes. The coarse-one rising delay spans 1006.906320–1008.882041 ps; falling delay spans 915.313020–915.315699 ps. Comparing the minimum fine-60 delay against the maximum coarse-one delay gives conservative overlap of **−108.514845 ps rising / +4.243203 ps falling**.

This centered pilot cannot provide continuous rising-edge coverage and already fails the 20 ps history/period gate at fine 60. It is not promoted to a loaded bank or full-PVT campaign. Its unshifted native reference continues unchanged to finish numerical parity evidence. The running distributed fine-capacitance experiment remains the next architecture test; neither its control results nor these component results qualify the PHY.

### Extracted clock KLU failure and baseline-solver fallback

The KLU pilot `openpll_long_trace_300_v1/7398cf894f0d9e4f` terminated with exit 1 at the initial transient point: `Timestep too small` at `vcoarsetherm00#branch`. The log confirms KLU selection and reports 2501.603 s elapsed. It provides no admitted waveform/parity result, and no long KLU capture launched. This is numerical initialization failure, not evidence of physical clock failure or a KLU speed improvement. The completed original SMP 70 ns trace remains valid and unchanged. All failed pilot files are retained.

New immutable producer `scripts/capture_openpll_long_smp_300.py` and artifact `openpll_long_smp_trace_300_v1/04c08364a5eb6cf6` retain the successful baseline SMP solver. They extend only the native integration duration to 20 us and the reset high hold/period to 20/40 us, with no reset reassertion during capture. Models, fixed supplies, tolerances, integration method, two threads and 2 ps timestep remain identical. At 70 ns the generated deck is byte-identical to the completed reference; three focused tests pass. No new solver-parity pilot runs because the solver is unchanged. The inherited parity helper/limits remain unused metadata in this separate producer.

Unit `openlvds-long-smp-clock-300-v1` (invocation `5c71e63d56434ea584b90853b235d637`) queues one priority-2 worker under the unchanged six-slot dispatcher. Runtime is unproven and may be substantial. Admission still requires a complete genuine native trace with at least 4096 late-window DDR intervals, frequency/duty checks, and unchanged input hashes; no tiling, time scaling or full-link/PHY admission is implied.

### Fresh 300 MHz DDR-core functional traffic

`scripts/verify_ddr_core_300.py` completed artifact `ddr_core_functional_300/c84b05ff924fbc4b`: **54/54 cases pass**, checking **1,186,812 bits in RTL and 1,186,812 bits in SKY130 functional TX/RX model mode**. Each mode covers the full 290/300/310 MHz × 40/50/60% duty × −100/0/+100 ps channel-skew matrix, with deterministic ±50 ps clock-edge jitter, 22,000 cycles per case, readiness revocation/restart, held second-bit serialization, ordered pair checking and all 16 pair transitions. Source, policy and tool-executable hashes and complete per-case logs are retained; no legacy 400 MHz result is reused.

This closes the million-bit **DDR-core functional** traffic requirement only. The bench supplies an ideal quarter-phase clock and forces readiness/lock. It does not exercise the physical DLL/DCC, training controller, analog I/O, electrical margins or extracted clock. Those integrations and full PHY release remain pending; `qualified_phy` remains false.

### Smaller current-origin trial: 10 µA rejected

Case 0 of `small_current_center_300_v1/91f5a0b6b1bc4219` completed its native 40 ns integration in **1032.027 s**. The 10 µA external bench load fails the original all-vector 2 mV parity gate: **33.511179731 mV** maximum difference at `v(xd.xdecode1_3.a_110_47#)`. Clock-crossing difference is only **0.000779516 ps**, all gate classifications agree, and the genuine physical history failure remains **24.349056846 ps**. These smaller timing differences do not override voltage parity failure. The preplanned 1 µA case remains pending under the same dispatcher.

Read-only worst-node analysis (`build/small-center-worst-node-300.log`) locates the maximum at t=0: the unshifted node is −29.362422627 mV while both the previous 1 mA and new 10 µA runs give +4.148757104 mV. The discrepancy persists after 2 ns (33.510817 mV). The captured netlist identifies this as an internal stacked-NFET decoder junction. This supports an operating-point/internal-node numerical sensitivity rather than a proportional effect of offset magnitude; it does not establish a safe method or justify excluding the node, trimming startup, or relaxing parity. No offset is admitted from this result.

### Small-offset numerical experiment complete: neither offset admitted

`small_current_center_300_v1/91f5a0b6b1bc4219` is complete with two executed cases and zero execution errors. The **1 µA** case also fails all-vector parity at **33.511179731 mV**, at the same internal decoder junction. Maximum absolute clock-crossing difference is **0.001706936 ps**, all gate classifications are preserved, and the original history failure remains failed. The campaign reports `admissible_offset_for_reference_case_a: null`; neither 10 µA nor 1 µA is admitted.

Native elapsed times are **982.658 s unshifted reference / 1032.027 s at 10 µA / 2272.996 s at 1 µA**. Queue-inclusive wall time is recorded separately and is not a solver benchmark. The lower offsets did not improve elapsed time for this completed case, and reducing the offset did not resolve the persistent internal-node discrepancy. This closes the two planned numerical trials without changing the circuit, tolerances, parity limits or physical history gates. Future numerical work must address the operating-point discrepancy explicitly and still prove complete-vector parity; no further blind offset-size sweep is justified by these results. Existing architecture campaigns continue unchanged.

### Restored P80 baseline complete: parity passes, physical coverage fails

`native_bank_300_v1/b3f726547e6143f8` completed all five cases with zero execution errors. The unshifted fine-60 reference integrated all 40 ns / eight input epochs, taking **18145.873 s** native elapsed time. Independent replay `bank_native_replay_300_v2/ab74e697dd84469d` reproduces all original measurements plus independent timing, terminal envelopes and control/gate settling. Its rising history span is **1.165351908 ps**, falling **0.002036536 ps**, with maximum period error **1.165323906 ps**; point-level electrical/timing checks pass.

Fresh active numerical parity **passes** for this exact P80 circuit: maximum all-vector error **0.771589366 mV**, maximum absolute clock-crossing error **0.001203276 ps**, and all gate classifications preserved. This is case-specific and does not supersede the separate P40 parity failures. Despite passing all five point checks and parity, conservative fine-to-next-coarse overlap remains **−125.475676 ps rising / −114.675677 ps falling**, so `component_pilot_passed` and `qualified_phy` are false. The baseline is rejected for continuous clock-phase coverage and is not promoted to full-PVT or loaded-chain qualification.

The completed reference closes numerical uncertainty for the baseline coverage failure. The running distributed-capacitance controls/candidates remain the next architecture experiment; changing placement/range must repair the physical coverage/history gates, rather than changing numerical-origin size or relaxing bounds.

### MIM4 campaign complete: numerical parity passes, physical timing fails

`native_bank_mim4_300_v1/a8105c49e52731af` completed all five cases with zero execution errors. The unshifted fine-60 reference completed 40 ns with 37,889 native points in **23063.633 s** native elapsed time. Independent replay `bank_native_replay_300_v2/9eefd76d95131c38` reproduces all original metrics plus independent timing, terminal envelopes and control/gate settling. Rising history variation is **143.812218992 ps**, falling **8.375872158 ps**, and maximum period error **141.267934419 ps**. The rising history and period checks fail the unchanged 20 ps limits.

Fresh active numerical parity passes for this exact MIM4 circuit: maximum all-vector difference **1.388446216 mV**, maximum absolute clock-crossing difference **0.001495403 ps**, and all gate classifications preserved. The prior centered-waveform failure therefore remains supported by a complete unshifted native reference; this does not qualify another circuit's numerical offset.

The campaign's aggregate conservative overlap is **−108.514844977 ps rising / −107.440086271 ps falling**, taking the minimum delay across both fine-40 and fine-60 points against the maximum coarse-one delay. The earlier fine-60-only falling comparison of +4.243203 ps was narrower evidence and does not establish aggregate coverage. `component_pilot_passed` and `qualified_phy` remain false. MIM4 is not promoted to loaded-chain or full-PVT qualification. The running distributed-capacitance controls/candidates remain the next architecture experiment, with all physical and numerical gates unchanged.

### Strong-driver control independently reproduced

The unshifted `strong_pre_c4` case 0 in `distributed_fine_pilot_300_v1/f07675577cda70f9` completed 40 ns / 37,960 native points in **23714.077 s** native elapsed time. It fails rising history at **183.813603765 ps** and maximum period error at **182.581589815 ps**; falling history is **4.203789076 ps**. This corroborates the centered control's failure. Stronger pre-drive alone does not repair this four-cell fine-node configuration. The split-capacitance candidates remain separate pending experiments.

New immutable `scripts/replay_distributed_bank_300.py` binds the captured producer, all variant libraries and selected complete native files, uses each task's exact variant observations, recomputes every original measurement, then independently checks timing, terminal envelopes and control/programming-gate settling through the existing native metrology. It refuses incomplete, changed or duplicate cases, retains failed attempts, and never grants whole-bank or PHY admission. Actual native replay of cases 0 and 1 completed successfully in `distributed_bank_native_replay_300/ffc4b9e213c736cb`, reproducing both failures and every independent check. Log: `build/distributed-strong-pre-c4-replay-300.log`. Aggregate pair parity remains the running campaign's separate final analysis; no captured producer or circuit was modified.

### Two-cell strong-driver control independently reproduced

Cases 2 and 3 (`strong_pre_c2`, unshifted and centered fine 60) in `distributed_fine_pilot_300_v1/f07675577cda70f9` completed without execution errors. The unshifted reference integrated 40 ns / 40,853 native points in **22720.941 s** native elapsed time. Rising history variation is **30.890311267 / 30.890350244 ps**, falling **0.027189349 / 0.027292009 ps**, and maximum period error **30.886894420 / 30.886851409 ps**, respectively. Both rising-history and period checks fail the unchanged 20 ps limit. Reducing the fine-node count improves this control's history relative to four cells, but does not qualify it.

Independent replay `distributed_bank_native_replay_300/15a302da171a9d37` reproduces both complete original measurements plus independent timing, terminal stress and control/programming-gate settling. Log: `build/distributed-strong-pre-c2-replay-300.log`. This closes measurement reproduction for both strength/count controls; active numerical pair parity remains separate pending campaign analysis. The dispatcher has advanced both workers to cases 4 and 5, the unshifted/centered `split_c1_c1` candidate. No current, timing, startup, loading or qualification limit was changed, and no loaded-chain or full-PVT promotion is made.

### First split-capacitance fine-60 point passes; qualification remains open

Centered case 5 (`split_c1_c1`, one qualified MIM cell per enabled code at each of the pre-output and fine nodes) completed 40 ns / 20,008 native points in **927.832 s** native elapsed time. Rising history variation is **19.883901035 ps**, falling **0.017394862 ps**, maximum period error **19.881014624 ps**, and maximum output slew **120.071981003 ps**. Its point-level clock-interface screen passes, including terminal and control/gate checks, at the unchanged 20 ps history/period limit. The rising-history headroom is only about **0.116 ps**; this is one SS40/310 MHz component point, not evidence of robustness across PVT or loading.

Independent replay `distributed_bank_native_replay_300/02db153ac4cb62f2` reproduces every original measurement and independent timing, terminal envelope and control/programming-gate check. Log: `build/distributed-split-c1-fine60-replay-300.log`. Unshifted case 4 remains live and must establish active numerical parity. Zero-code quarter headroom, fine-40 behavior, next-coarse coverage, actual next-bank/shared-RC loading and all-PVT qualification remain open; `qualified_phy` remains false. The unchanged campaign has advanced its available worker to case 6, the next split-capacitance variant's unshifted reference.
