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

Cold nominal SF0/300 MHz cases 72--89 also pass original and independent
checks in `dcc_source_native_replay_300/9e42b9ea25063836`. The exact 18-point
duty/slew/spacing cohort has worst balanced mean half-cycle error
26.619931678 ps. Log: `build/dcc-source-300-sf0-nominal-replay.log`.
Cases 0--89 now have independently passing source evidence. SF0/290 MHz,
the remaining PVT conditions, and every physical-DCC/DLL/PHY gate remain open.

SF0 source-frequency coverage is now complete: cases 90--107 at 290 MHz
pass original and independent checks in
`dcc_source_native_replay_300/8539391a90f49e61`, with worst balanced mean
half-cycle error 26.625320636 ps. Log:
`build/dcc-source-300-sf0-290-replay.log`. Cases 0--107 now have independently
passing source evidence: both SF0 and SF40 cover all three frequencies and
the full approved duty/slew/spacing matrix. SF25 and the other process
corners remain pending, together with all physical-DCC/DLL/PHY gates.

SF25/310 MHz cases 108--125 pass original and independent source checks in
`dcc_source_native_replay_300/8ab55b0ebe48bde0`. Exact 18-point duty/slew/
spacing coverage has worst balanced mean half-cycle error 28.699071613 ps.
Log: `build/dcc-source-300-sf25-310-replay.log`. Cases 0--125 now have
independently passing source evidence, including SF/310 MHz at all three
requested temperatures. SF25 lower frequencies, the other four process
corners and all physical-DCC/DLL/PHY gates remain pending.

SF25/300 MHz cases 126--143 pass original and independent source checks in
`dcc_source_native_replay_300/ba3b8ed3726dc0b9`. Exact 18-point duty/slew/
spacing coverage has worst balanced mean half-cycle error 28.706494702 ps.
Log: `build/dcc-source-300-sf25-nominal-replay.log`. Cases 0--143 now have
independently passing source evidence, including SF/300 MHz at all three
requested temperatures. SF25/290 MHz, the other process corners and all
physical-DCC/DLL/PHY gates remain pending.

The final SF25/290 MHz cohort, cases 144--161, passes original and independent
checks in `dcc_source_native_replay_300/2a45695f6ffecee8`, with worst balanced
mean half-cycle error 28.712639631 ps. Log:
`build/dcc-source-300-sf25-290-replay.log`. The eleven completed replay
receipts contain exactly 162 unique cases (0--161), without omissions or
duplicates, covering the full SF x 0/25/40 C x 290/300/310 MHz x 40/50/60%
duty x 20/250 ps slew x 0/+/-140 ps event-spacing matrix. Every selected
original and independent source screen passes. All receipts remain source-only
and `qualified_phy: false`; the complete 810-case matrix is not admitted.
The unchanged one-worker campaign has advanced to SS; the other 648 source
cases and all physical-DCC/DLL/PHY gates remain required.

### Separate complete-pair numerical receipts

`scripts/replay_distributed_parity_300.py` can analyze a complete captured
unshifted/centered distributed-bank pair while the unchanged 14-case campaign
continues. It binds the full original campaign identity, every variant
library, selected native files, per-case summaries and imported analysis
scripts. It requires the exact same variant and stimulus with one unshifted
and one centered run, reproduces all original measurements, then invokes the
captured full-vector/crossing/classification parity calculation. Limits remain
2 mV across all native voltages and 0.25 ps across all eight rising/falling
input/output events, with every individual terminal/control/programming-gate
classification preserved. Failed physical points remain failed regardless of
numerical parity; no bank, coverage, loading, PVT or PHY admission is granted.

Three pair-selection/rejection tests pass (0.002 s); log:
`build/distributed-active-parity-300-tests.log`. The first actual complete-pair
analysis targets the two-cell strong-pre-driver control and is reading its
retained native evidence; log:
`build/distributed-strong-pre-c2-active-parity-300.log`. No parity verdict is
claimed before its receipt completes. This tool creates a separate receipt,
takes no SPICE lease and does not edit captured producers, libraries, running
decks, state files, queue tickets or dispatcher lock inodes.

The two-cell strong-pre-driver pair (cases 2/3) completed separate native
parity analysis in `distributed_bank_active_parity_300/16b3d621df3f4b44`.
Every original measurement reproduces. Full-vector parity passes at
0.316828100 mV maximum error across 6,894 vectors and 40,853 reference samples;
the worst vector is `v(xd.xtail_load.xb.out.t31)`. Maximum absolute crossing
error is 0.000860260 ps, and all individual gate classifications are preserved.
Both original point results remain failed: their approximately 30.89 ps
rising-history/period errors still exceed 20 ps. Thus this numerical control
closes origin-equivalence uncertainty for this exact circuit without repairing
or admitting it. The independent tool was validated against actual complete
native evidence; the running 14-case producer and every physical limit are
unchanged. Log: `build/distributed-strong-pre-c2-active-parity-300.log`.

### Split candidate unshifted point completes

Case 4 (`split_c1_c1`, unshifted SS40/310 MHz fine-60 stimulus) completed
the full 40 ns native integration in 14744.703 s native elapsed time. The
captured producer reports rising history variation 19.883750129 ps, falling
0.020463603 ps, maximum period error 19.881242913 ps, and maximum output slew
120.090599383 ps. All point-level event, terminal, control/programming-gate
and current clock-interface checks pass. This agrees with the previously
independently replayed centered point, but rising-history headroom remains
only about 0.116 ps and does not establish PVT/load robustness.

Fresh complete-pair numerical analysis of cases 4/5 is running separately
through `replay_distributed_parity_300.py`; log:
`build/distributed-split-c1-active-parity-300.log`. Numerical parity has no
verdict yet. Independent unshifted-point metrology, zero-code headroom,
fine-40 behavior, conservative coarse overlap, actual loading, common routed
RC and full PVT remain required. No bank or PHY admission is granted.

The exact split-c1 pair (cases 4/5) now passes full active numerical parity in
`distributed_bank_active_parity_300/e2cd3e35bae30ea2`. All original metrics
reproduce and both point classifications remain passing. Maximum all-vector
difference is 1.411157975 mV across 6,894 vectors / 34,050 unshifted samples;
the worst vector is `v(xd.xtail_load.xb.u_inv1.gate.vnb.t26)`. Maximum absolute
input/output crossing difference is 0.002788677 ps, and every individual
terminal/control/programming-gate classification is preserved. No startup
trimming, alignment, tolerance change or voltage-node exclusion was applied.
Log: `build/distributed-split-c1-active-parity-300.log`.

Independent unshifted-point metrology is running through the existing
`replay_distributed_bank_300.py`; log:
`build/distributed-split-c1-unshifted-native-replay-300.log`. This numerical
receipt closes the active origin-equivalence check for this exact pair only.
Zero/fine-40/coarse coverage, actual next-bank loading, common RC, PVT and PHY
qualification remain open; the approximately 0.116 ps history margin remains
unchanged and narrow.

Independent unshifted-point replay completed in
`distributed_bank_native_replay_300/8beb77a1a6770ff2`. Every original metric
and independent timing, native terminal envelope, control and programming-gate
settling measurement reproduces. All eight rising/falling input and output
epochs are retained, including the first-event history shift; no startup
event is discarded. Observations bind 2,096 native MOS devices, 86 controls
and 266 programming gates. The completed centered-point replay plus this
unshifted replay and passing active parity establish this fine-60 component
point only. Zero-code quarter headroom, fine-40 behavior, next-coarse overlap,
actual loading, routed RC, full PVT and PHY qualification remain open.
Log: `build/distributed-split-c1-unshifted-native-replay-300.log`.

### Larger split candidate fails the centered history screen

Case 7 (`split_c2_c2`, two qualified MIM cells per enable at each of the
pre-output and fine nodes) completed its full 40 ns centered SS40/310 MHz
fine-60 run: 20,008 native points, 1135.439 s native elapsed time. Rising
history variation is 179.211258659 ps and maximum period error
178.831729531 ps, failing the unchanged 20 ps limits. Falling history is
0.692412367 ps, output slew is 167.815204769 ps, and observed terminal/
control/programming-gate checks pass. Doubling capacitance at both nodes
does not preserve the smaller split candidate's passing centered history.
No loaded-chain or PVT promotion is made from this failed point.

Independent native replay is running through the existing consumer; log:
`build/distributed-split-c2-centered-native-replay-300.log`. Its unshifted
case 6 remains live and complete-pair numerical parity is still pending;
this centered result alone does not close that separate comparison. The
unchanged campaign's available worker has advanced to case 8, the smaller
split candidate's zero-code/50%-duty quarter-headroom test. Neither a failure
nor a passing fine-60 point changes coverage, loading, PVT or PHY gates.

Independent case-7 replay completed in
`distributed_bank_native_replay_300/d0a2b232ee31f56d`. Every original metric
and independent timing, terminal envelope, control and programming-gate
settling measurement reproduces, including the 179.211 ps rising-history
and 178.832 ps period-error failures. The larger centered split is therefore
rejected by both measurement paths. Its live unshifted reference and exact
pair parity remain separate pending evidence; no failure is discarded or
reclassified, and no physical limit or numerical parameter changes.
Log: `build/distributed-split-c2-centered-native-replay-300.log`.

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


### Distributed zero code rejected; native stage diagnosis retained

Centered case 8 (`split_c1_c1`, SS40/310 MHz, coarse/fine zero) completed
40 ns and all eight native epochs. Rising delay is 643.335405–644.379752 ps;
falling delay is 872.900611–872.902640 ps. Against the unchanged fastest
quarter target of 806.451613 ps, conservative headroom is **−66.451027 ps**.
History, period, slew, terminal and control/gate checks pass, but the zero-code
quarter and current clock-interface checks fail. This architecture cannot be
promoted unchanged, even though its fine-60 point passed narrowly.

Independent replay `distributed_bank_native_replay_300/213842ed2311145d`
reproduces every original metric plus independent timing, terminal envelope
and control/programming-gate settling. Log:
`build/distributed-split-c1-zero-native-replay-300.log`.

New read-only `scripts/diagnose_distributed_stages_300.py` binds the complete
captured campaign, every selected native witness and imported analysis code.
It uses existing fixed-epoch stage metrology, rejects missing/noncausal events,
reproduces original outer delays, and preserves all original gate results.
Actual cases 5 and 8 pass this diagnostic in
`distributed_bank_stage_diagnosis_300/98eca3f48ee1313e`; every stage sum has
zero residual against the eight original outer delays. Log:
`build/distributed-split-c1-stage-diagnosis-300.log`.

At zero code, falling-edge stage delays are approximately 409.96 ps through
selection, 290.90 ps through the pre-driver, 111.07 ps through the fine driver,
and 60.97 ps through the output stage. Thus about 701 ps precedes the fine
inverter; the zero-code failure is not a repeated-history failure. At fine 60,
rising stage-history spans are 3.565/5.476/9.942/0.903 ps, respectively.
These measurements identify selection/pre-driver delay and the fine-stage
history tradeoff as redesign targets; they do not prove a particular resizing
will repair both. Finish fine-40/coarse-one coverage before selecting the next
circuit variant. The existing workers and physical/numerical limits remain
unchanged; no loaded-chain, PVT, component or PHY admission is granted.


### First SS source cohort independently verified

Fresh DCC source cases 162–179 (SS40, 310 MHz, 40/50/60% duty,
20/250 ps input slew, and 0/±140 ps event-spacing error) completed with no
execution errors. Independent replay
`dcc_source_native_replay_300/14d8c908460ecc33` reproduces all 18 original
measurements and passes every independent source screen. Log:
`build/dcc-source-300-ss40-310-replay.log`. Together with the complete SF
corner receipts, independently replayed source coverage is now 180 cases.
The remaining source matrix, physical DCC and full PHY remain unqualified.


### Prepared single-P40 pre-driver architecture control

`scripts/medium_pre_distributed_bank_300.py` prepares a bounded follow-up to
the independently reproduced zero-code failure. Starting from the exact
split-one-cell architecture, it replaces only the two-parallel P40/N16
pre-driver wrapper with one verbatim qualified extracted P40/N16 cell.
The fine driver remains two parallel cells, both fine-capacitor attachments
and all qualified leaf definitions remain unchanged. Full native terminal
maps must match except for the removed 56-MOS pre-driver branch; inventory
is 2040 MOS / 201 MIM, with all 86 controls and 266 programming-gate
observations retained. It rejects unexpected source wiring or native maps.

Three tests pass in 2.396 s, covering complete topology/observation invariants,
changed-source rejection, and native runner translation for both active
numerical controls and all three candidate endpoint decks. Log:
`build/medium-pre-distributed-bank-300-tests-v2.log`. The earlier two-test
structural run is retained separately. No SPICE experiment has been launched
for this candidate and no timing claim is made. Lower pre-driver input load
may improve selection delay, while weaker pre-drive may increase its own
delay and fine-60 history; the net result requires fresh native measurement.
Finish the existing fine-40/coarse-one coverage before selecting the next
circuit experiment. This preparation does not modify any captured helper,
running deck, dispatcher, worker cap, numerical tolerance or admission gate.


### Evidence-gated runner for the medium pre-driver control

`scripts/probe_medium_pre_distributed_300.py` adds the fresh five-case native
experiment for the prepared single-P40 pre-driver. Order is zero-code/50%,
centered fine-60, unshifted fine-60, fine-40, and coarse-one/50%. Each case
retains SS40/310 MHz, all eight startup-inclusive events, 40 ns integration,
20 fF loading, complete terminal/control/programming observations and the
original measurement limits. Its single priority-1 worker uses the unchanged
global dispatcher. The active fine-60 pair must meet the original complete-
vector 2 mV / 0.25 ps numerical parity limits with every gate class preserved.
Conservative overlap takes the minimum delay over both fine duty points
against the maximum coarse-one delay, for each edge; all point checks and
positive overlap are required for a component pilot pass. PHY admission is
always false.

Preparation requires complete unchanged predecessor cases 5/8/9/10, exact
independent zero-code replay, and the two-case fixed-epoch stage diagnosis.
It captures their witnesses along with the entire model/runtime/profile and
qualified-material closure. The native topology, observations and all decks
are reconstructed and checked before execution. It preserves prior or partial
experiments rather than reusing them. Three focused tests pass in 0.991 s,
including exact case coverage, pending-evidence rejection and all five native
fixtures. Log: `build/medium-pre-distributed-pilot-300-tests-v2.log`.

An actual preparation preflight correctly refuses at predecessor case 9,
which is still running; case 10 is also pending. Log:
`build/medium-pre-distributed-pilot-300-pending-preflight.log`. No experiment
artifact or extra SPICE process was created. The runner is ready for use once
those coverage witnesses complete, and does not bypass or restart either
existing architecture worker.


### Split-one-cell fine-40 point independently verified

Predecessor case 9 (`split_c1_c1`, centered fine 31, 40% input duty,
SS40/310 MHz) completed 40 ns / 20,008 native points in **965.805 s** native
elapsed time. Rising history is **2.691822088 ps**, falling **0.073121098 ps**,
maximum period error **2.691400161 ps**, and maximum slew **120.071981003 ps**.
All original point-level clock-interface, terminal and control/gate screens
pass. Rising delays span 764.362531–767.054353 ps; falling delays span
1018.557497–1018.630619 ps. This is distinct from the fine-60 history result;
both duty points remain required in the conservative overlap calculation.

Independent receipt `distributed_bank_native_replay_300/dbb9119325deef83`
reproduces every original metric and independent timing, terminal-envelope
and control/programming-gate checks. Log:
`build/distributed-split-c1-fine40-native-replay-300.log`. Coarse-one case 10
has started normally in the existing worker. Its coverage result remains
pending; the independently reproduced zero-code quarter failure still prevents
admission of this unchanged bank. No PHY qualification is claimed.


### SS40 nominal source cohort independently verified

DCC source cases 180–197 (SS40, 300 MHz, 40/50/60% complementary duty,
20/250 ps input slew, and 0/±140 ps event-spacing error) completed with no
execution errors. Receipt `dcc_source_native_replay_300/08ece4f6dc6ee149`
reproduces all 18 original measurements and passes every independent source
screen. Log: `build/dcc-source-300-ss40-nominal-replay.log`. Independently
replayed source coverage is now 198 cases. The full 810-case source matrix,
physical DCC, loaded clock chain and complete PHY remain unqualified.


### Four-cell strong-pre control numerical parity independently verified

Complete active-pair replay of predecessor cases 0/1 (`strong_pre_c4`)
finishes in `distributed_bank_active_parity_300/7281d6bd825ec77d`.
Every original measurement reproduces; all 7,638 native voltage vectors
(including startup and internal nodes) meet numerical parity at a maximum
**0.021277495 mV** difference, with maximum absolute clock-crossing error
**0.000124846 ps** and every aggregate/individual gate class preserved.
Both original point results remain false: the approximately 183.814 ps rising
history and 182.582 ps period failures are retained. Log:
`build/distributed-strong-pre-c4-active-parity-300.log`. This closes the
completed four-cell control's numerical-origin question without admitting
its architecture or changing any limit. The remaining larger split pair is
separate and still requires its live unshifted reference.


### Smaller split bank endpoint coverage closes with two physical failures

Coarse-one case 10 completes without execution error and passes its point
screens: rising history **0.987502025 ps**, falling **0.001891767 ps**,
maximum period error **0.986889388 ps**, and maximum slew **83.651549764 ps**.
Independent replay `distributed_bank_native_replay_300/9968f97a350ae52d`
reproduces all original measurements and independent timing, terminal and
control/programming-gate checks. Log:
`build/distributed-split-c1-coarse1-native-replay-300.log`.

Using completed centered fine-60/fine-40/coarse-one cases 5/9/10 and the
unchanged conservative formula (minimum across both fine duties minus maximum
coarse-one delay) gives **−116.116961 ps rising / −33.819311 ps falling**.
Thus this bank has discontinuous code coverage as well as the independently
reproduced **−66.451027 ps** zero-code quarter headroom. Passing individual
fine/coarse points and active pair parity does not override either failure.
The larger variant's unshifted reference remains separate and live; this
calculation does not claim the entire 14-case campaign is complete.

Before any follow-up capture, the single-P40 pilot order was changed to zero,
centered fine-60, fine-40, coarse-one, then unshifted fine-60. This obtains
all centered range witnesses before the potentially slow active reference,
while preserving every case and unchanged final parity/coverage requirements.
The three updated tests pass in 1.010 s; log:
`build/medium-pre-distributed-pilot-300-tests-v3.log`.


### SS40 source coverage complete across all three frequencies

Independent source replay `dcc_source_native_replay_300/d81e7d30cc0c2a24`
verifies DCC cases 198–215 at SS40/290 MHz, reproducing all original metrics
and passing every independent source screen. Log:
`build/dcc-source-300-ss40-290-replay.log`. Combined with cases 162–197,
this closes the 54-case SS40 source cohort at 290/300/310 MHz,
40/50/60% complementary duty, 20/250 ps input slew and 0/±140 ps event
spacing error. Independently replayed source coverage is 216 cases, including
the complete SF corner. Other SS temperatures and remaining corners are
pending; physical DCC, the loaded clock chain and complete PHY remain
unqualified.


### Single-P40 follow-up prepared and launched

Preparation now succeeds as
`medium_pre_distributed_pilot_300_v1/42cbec6c352fbe01`, validating the
completed predecessor endpoint witnesses, independent zero-code replay,
stage diagnosis, qualified component materials, all model/runtime inputs,
complete observations and all five native decks. Log:
`build/medium-pre-distributed-pilot-300-prepare.log`.

Unit `openlvds-medium-pre-distributed-300-v1`, invocation
`a2948e69d1634cd083b0e819028f9a9c`, runs one priority-1 worker through the
unchanged six-slot dispatcher. It acquired slot 2 after DCC case 223 released
it normally; the first native zero-code process is confirmed live. The DCC
worker waits normally rather than exceeding the global budget. No existing
solver was preempted and neither campaign/dispatcher caps nor captured
helpers were changed. Runtime log: `build/medium-pre-distributed-300-v1.log`.
This is an unqualified architecture experiment; no result or electrical,
component, PVT, loaded-chain or PHY admission is claimed at launch.


### Independent consumer ready for single-P40 native results

`scripts/replay_medium_pre_distributed_300.py` binds the new producer,
complete captured topology/profile/model/runtime inputs, all variant libraries,
and explicitly selected complete native witnesses. It reproduces every
original metric exactly, then runs the existing independent fixed-epoch timing,
terminal-envelope and control/programming-gate metrology with the new exact
observations. It uses separate content-addressed receipts, preserves failures,
rejects changed/duplicate/unknown/incomplete cases and never grants whole-bank
or PHY admission. No SPICE lease or running-file mutation is performed.

Three refusal tests pass in 1.180 s, covering invalid selections, pending
native output, execution failure and mismatched task identity. Log:
`build/medium-pre-distributed-native-replay-300-tests.log`. An actual bound
preflight against the captured campaign correctly rejects still-running case
0 before creating a receipt; log:
`build/medium-pre-distributed-native-replay-300-pending-preflight.log`.
The native solver remains live in operating-point initialization with no raw
waveform yet. There is no completed native replay or timing claim for this
new architecture; validation on actual data remains required after case 0.


### Retained zero-code stage comparison narrows the delay tradeoff

Existing immutable stage metrology completes a new two-case receipt
`bank_stage_history_300_v2/14eec5976ea72bf3` for zero-code case 2 of the
restored P80 baseline and MIM4 bank. Both complete eight-event outer delays
reproduce exactly, with zero stage-sum residual. Log:
`build/restored-zero-stage-comparison-300.log`. These are retained native
waveforms; no new SPICE process or changed qualification gate is involved.

Baseline zero-code rising stage ranges are approximately
217.527–217.743 / 242.180–243.752 / 197.496–197.664 / 91.375–91.383 ps
(selection / pre-driver / fine driver / output). Falling ranges are
251.961–251.963 / 242.351–242.354 / 138.961–138.962 / 70.169–70.172 ps.
MIM4 preserves essentially the same selection/pre-driver delays, while its
fine stage rises to 232.171–232.346 ps rising and 163.862–163.863 ps falling;
output delay rises to approximately 100.87 / 77.64 ps. Their worst outer
zero-code delays are 750.541 / 794.841 ps, respectively, within the unchanged
806.451613 ps fastest-quarter target.

The separately measured split-one-cell strong-pre zero point instead has
approximately 409.96 / 290.90 / 111.07 / 60.97 ps falling stage delays and
872.902640 ps worst outer delay. This comparison shows why the zero-code
failure must be tracked independently of fine range/history. It does not
isolate pre-driver sizing alone across these different capacitor architectures
or prove the single-P40 follow-up will repair all gates. That fresh experiment
remains live; a smaller input load and weaker output drive have competing
consequences that require its complete native results.


### Larger split bank zero-code failure independently reproduced

Case 11 (`split_c2_c2`, centered zero code, SS40/310 MHz) completes without
execution error. Worst rising delay is **696.455320273 ps**, worst falling
delay **933.745892356 ps**, giving **−127.294279453 ps** fastest-quarter
headroom against the unchanged 806.451613 ps limit. Rising/falling history
are **1.051692956 / 0.002024939 ps**, maximum period error **1.051732632 ps**,
and maximum slew **90.864925894 ps**. History, period, terminal, control/gate
and slew screens pass, while zero-code quarter/current clock-interface gates
fail. This zero-code range failure is separate from the larger bank's fine-60
history/period failure; neither is discarded or relaxed.

Independent receipt `distributed_bank_native_replay_300/ab2a9fda449922e2`
reproduces every original metric plus independent timing, terminal envelopes
and control/programming-gate settling. Log:
`build/distributed-split-c2-zero-native-replay-300.log`. Fine-40/coarse-one
coverage and unshifted active-pair evidence remain pending for this larger
variant; it is not promoted to loaded-chain or PVT qualification. The
single-P40 follow-up remains a separate running experiment.


### Single-P40 zero-code point passes and independently reproduces

The new single-P40 pre-driver case 0 completes without execution error.
Worst rising delay is **613.337921420 ps** and worst falling delay
**784.774103926 ps**, giving **+21.677508977 ps** headroom against the
unchanged 806.451613 ps fastest-quarter limit. Rising/falling history are
**1.859507978 / 0.003333103 ps**, maximum period error **1.859532552 ps**,
and maximum slew **84.894587745 ps**. All original point-level clock-interface,
terminal and control/programming-gate screens pass at SS40/310 MHz.

Independent receipt
`medium_pre_distributed_native_replay_300/3d82eff834a0cc6a` reproduces every
original metric and passes independent fixed-epoch timing, terminal-envelope
and control/programming-gate checks. This validates the new consumer on its
first actual native dataset, beyond its refusal tests. Log:
`build/medium-pre-distributed-zero-native-replay-300.log`.

Removing the second qualified P40 pre-driver branch repairs the measured
zero-code quarter failure for this exact component point. It does not yet
repair or prove fine-range overlap, fine-60 history, active numerical parity,
actual next-bank/shared-RC loading, all-PVT behavior, DLL/DCC operation or PHY
qualification. The existing one-worker campaign has advanced to centered
fine-60 case 1; its native solver is confirmed live. No further topology or
limit was changed after capture.


### DC-zero transient bench-current experiment prepared

`scripts/probe_ramped_center_300.py` tests a different numerical boundary
condition rather than another constant-offset size. It uses the completed
P40 unshifted fine-60 reference in `native_bank_300_v2/2d31edbabe113146`,
whose constant-origin active parity failed at an internal decoder junction.
The sole new bench source is
`I_BENCH_CURRENT_CENTER VDD 0 DC 0 PWL(0 0 2p 0 4p 1m 40n 1m)`:
zero during DC initialization, followed by one fixed 2–4 ps ramp to 1 mA.
The ideal 1.8 V supply, native circuit, original 40 ns/eight-event stimulus,
observations, solver and tolerances remain unchanged. The bench source has
no circuit-current feedback and its maximum 1.8 mW power is excluded from
chip power. No voltage or offset-size sweep is introduced.

The hypothesis is that DC-zero initialization may preserve the original
floating-node solution while centering the supply-source current during
transient integration. It is not assumed valid. Admission for this exact
reference requires original measurements to reproduce, all native voltages
(including startup/internal nodes) within 2 mV in both interpolation
directions, every input/output crossing within 0.25 ps, all aggregate and
individual gate classifications preserved, and an additional all-voltage
DC-sample difference at t=0 of at most 1 nV. The genuine physical history
failure must remain failed. Even success cannot qualify another circuit or
repair timing; each new circuit still needs its own active parity.

Four tests pass in 0.106 s: exact single-card/library-only change, feedback/
existing-offset rejection, unapproved supply/offset rejection, and rejection
of 1 µV DC drift even when full-waveform error remains below 2 mV. Log:
`build/ramped-current-center-300-tests.log`. Full preparation succeeds as
`ramped_current_center_300_v1/4dd1b69e62d555ef`, capturing the complete
reference/model/runtime/native inputs and one fresh deck; log:
`build/ramped-current-center-300-prepare.log`. No native result or numerical
admission is claimed at preparation.


The ramped-current controller is launched as unit
`openlvds-ramped-current-center-300-v1`, invocation
`aab2ff0591954adca9897f86e0f5c2dc`. Its original-reference remeasurement
completed successfully before execution state; the live controller has
registered a single priority-2 dispatcher ticket for case 0 and is waiting
for a normal slot handoff. Six native ngspice processes remain active;
no existing solver was preempted or modified. Log:
`build/ramped-current-center-300-v1.log`. The queued numerical trial remains
unqualified and introduces no result or solver-speed claim.


### Single-P40 fine-60 failure reproduced and localized

Centered single-P40 case 1 completes without execution error, but rising
history is **41.784717991 ps** and maximum period error **41.736209958 ps**,
failing the unchanged 20 ps limits. Falling history is **0.221085226 ps**,
maximum slew **127.725792240 ps**, and terminal/control/programming-gate
checks pass. The zero-code repair is real but insufficient for qualification.
Independent receipt
`medium_pre_distributed_native_replay_300/b27c1c08c4db9ff7` reproduces every
original metric and independent timing, terminal and control/gate check.
Log: `build/medium-pre-distributed-fine60-native-replay-300.log`.

New read-only `scripts/diagnose_medium_pre_stages_300.py` applies the same
startup-inclusive fixed-epoch stage metrology to the exact new producer and
observations. Actual zero/fine-60 cases 0/1 complete in
`medium_pre_distributed_stage_diagnosis_300/623b3b7d2f4125eb`; all original
outer delays reproduce and every eight-event stage sum has zero residual.
Log: `build/medium-pre-distributed-stage-diagnosis-300.log`. No SPICE lease,
changed source waveform, startup trimming or qualification relaxation is used.

At fine 60, rising stage-history spans are **2.615800 / 26.808991 /
16.794789 / 0.796050 ps** (selection / pre-driver / fine / output).
First-to-last changes are approximately **+2.614951 / −26.808931 /
−16.794604 / −0.796050 ps**, giving the observed total −41.784634 ps.
Thus the observed pre-driver and fine-stage timing evolution dominates;
the selection contribution partly cancels it. Stage timing alone does not
measure MIM plate charge or prove a specific recovery mechanism. At zero,
falling selection delay is about 315.24 ps versus 409.96 ps for the previous
strong-pre split-one-cell bank, while falling pre-driver delay remains about
291.07 ps. This localizes the measured zero-code benefit without assuming
that weaker pre-drive can also satisfy fine-60 history and coverage.

The existing campaign continues to fine-40/coarse-one and its unshifted
active reference, preserving all failures. Further architecture selection
must address this measured history tradeoff together with conservative
code overlap and actual loading; no component or PHY admission is granted.


### Larger split bank fine-40 point independently verified

Predecessor case 12 (`split_c2_c2`, centered fine 31, 40% duty,
SS40/310 MHz) completes without execution error. Rising history is
**9.232725731 ps**, falling **0.378193232 ps**, and maximum period error
**9.219609525 ps**. Its original point-level clock-interface screen passes.
Independent receipt `distributed_bank_native_replay_300/df50c6ee09530ea7`
reproduces every original metric and independent timing, terminal envelopes
and control/programming-gate checks. Log:
`build/distributed-split-c2-fine40-native-replay-300.log`. The larger bank's
fine-60 history and zero-code quarter failures remain failed; this passing
duty point does not admit the architecture or qualify the PHY. Coarse-one
coverage and its still-live unshifted active reference remain separate.


### Native voltage recovery motivates a pull-down-specific control

`diagnose_distributed_recovery_300_v2.py` binds complete native cases and
resolves each representative capacitor's actual pre/fine attachment from
the captured top-level netlist. It samples the actual extracted switch-side
MOS nodes for fine enables 0/15/30 and both driver outputs 20 ps before
all eight causal input transitions (rising 10%, falling 90%), retaining
startup and reproducing the complete original stage/outer delays. It reports
voltages only, without inferring MIM plate charge or granting qualification.
Three tests pass in 0.112 s, including all four existing topologies, missing
events, truncated traces and nonfinite observations. Log:
`build/distributed-voltage-recovery-300-v2-tests.log`.

The first immutable diagnostic uses the original split-one-cell copy
assignment and is retained as `diagnose_distributed_recovery_300.py` with
receipt `distributed_voltage_recovery_300/c74bb64fca8ef547` for single-P40
cases 0/1. V2 replaces that assumption with actual native attachments and
also handles unsplit/four-cell controls. Its single-P40 receipt is
`distributed_voltage_recovery_300_v2/58bb46bef11400bf`; all recovery values
for those two cases agree exactly with the first probe. Strong-pre split-one
case 5 completes separately in
`distributed_voltage_recovery_300_v2/dad5f1a139f2ea3b`. Both V2 receipts
reproduce original delays with zero stage-sum residual. Logs:
`build/medium-pre-distributed-voltage-recovery-300-v2.log` and
`build/strong-pre-split-voltage-recovery-300-v2.log`.

For the failed single-P40 fine-60 point, pre-driver output before its rising
output stimulus changes from **−2.302 mV** initially to **111.425 mV** on
the last event; representative enabled capacitor-side nodes change from
about zero to **183–188 mV**. The fine-driver output before discharge changes
from **1.808180 V** to **1.752652 V**, with representative capacitor-side
nodes falling from about 1.802 V to **1.613–1.620 V**. At zero code, these
driver recovery values repeat closely across all eight events. The stronger
pre-driver's fine-60 low recovery is **40.262 mV**, and its downstream high
recovery **1.767182 V**, at the same respective sample definitions.

The qualified fine cell already contains a transmission gate and an off-state
discharge clamp. These measured enabled-state recovery differences support
a pre-driver pull-down intervention; they do not establish a unique mechanism
or prove a new circuit will meet history, coverage and loading requirements.
The next bounded control keeps total pre-driver P40 strength while using N32,
assembled from retained cells, before considering another increase of both
pull-up strength and input loading.


### P40/N32 pre-driver recovery control prepared from retained components

`scripts/p40n32_pre_distributed_bank_300.py` replaces only the single-P40/N16
pre-driver call with the existing parallel wrapper of two verbatim qualified
P20/N16 cells. This retains total P40 pull-up, increases pull-down to N32,
and preserves pre/fine capacitor placement, P80/N32 fine driver, every other
native leaf definition, and all 86 controls / 266 programming-gate observations.
The complete native terminal map must match outside the replaced pre-driver;
reachable inventory is **2056 MOS / 202 MIM**, including exactly **40 PFET /
32 NFET** in the pre-driver. New shared wiring remains ideal/unqualified.

Three tests pass in 3.005 s, covering retained topology/native maps, explicit
pre-driver P/N census, source-map rejection and native translation of both
numerical origins and all endpoint stimuli. Log:
`build/p40n32-pre-distributed-bank-300-tests-v2.log`; the earlier structural
run is retained separately. No simulation has been launched for this control.
It tests the recovery hypothesis rather than assuming that nominal drive
ratios predict native behavior. Fresh zero/fine-60/fine-40/coarse-one checks,
active numerical parity, actual loading, routed RC and PVT remain required;
component and PHY admission are false.


### DC-zero ramped-current trial passes the formerly failing P40 parity case

`ramped_current_center_300_v1/4dd1b69e62d555ef` completes its one native
40 ns case with zero execution errors. The DC-zero 2–4 ps / 1 mA ramp
preserves **every saved native voltage exactly at t=0** (maximum DC error
**0.0 V**). Bidirectional complete-waveform parity passes: forward maximum
**0.246145289 mV**, reverse **0.176565361 mV**, over **6,790 native voltage
vectors**, including startup and internal decoder nodes. Maximum absolute
input/output clock-crossing error is **0.000365333 ps**; every aggregate and
individual terminal/control/programming-gate classification is preserved.

The original genuine physical failure remains failed: rising history is
**24.349097590 ps**. This differs from the rejected constant-current origins,
which retained a 33.511 mV internal-node mismatch. The result supports the
specific DC-initialization hypothesis and admits this exact ramped origin
for this exact completed reference case only. It does not transfer numerical
admission to another topology, change any circuit/solver/tolerance gate,
repair timing, or qualify the PHY.

The native run has **20,015 samples**, compared with 20,010 reference samples;
full interpolation in both directions is retained. Native elapsed time is
**1066.313 s**, versus **982.658 s** for the original unshifted reference.
This case establishes parity, without establishing a solver-speed improvement.
Queue-inclusive wall time remains separate. Manifest, every native witness,
original remeasurement, parity result, terminal log and final state are retained
in the content-addressed campaign. Runtime log:
`build/ramped-current-center-300-v1.log`. Future circuit experiments may test
this method but still require fresh active parity for their own full waveforms.


### Single-P40 fine-40 point independently verified

Centered fine-40 case 2 completes without execution error. Rising history
is **1.483440728 ps**, falling **0.161789033 ps**, and the original point-level
clock-interface screen passes. Independent receipt
`medium_pre_distributed_native_replay_300/f145131864472508` reproduces every
original measurement plus independent timing, terminal-envelope and control/
programming-gate checks. Log:
`build/medium-pre-distributed-fine40-native-replay-300.log`. Its pass does
not override the separately reproduced fine-60 history/period failure.
Coarse-one coverage and the unshifted numerical reference remain pending;
no component or PHY admission is granted.


### Evidence-gated P40/N32 recovery pilot implemented

`scripts/probe_p40n32_pre_distributed_300.py` tests the prepared two-P20/N16
pre-driver while retaining the split-one-cell fine architecture. Its five
SS40/310 MHz native cases are zero/50%, fine-60, fine-40, coarse-one/50%,
then the unshifted fine-60 reference. All use the original 40 ns/eight startup
cycles, 20 fF load, complete device/control observations and unchanged
physical timing/stress/settling/overlap limits. A single priority-1 worker
uses the existing global six-slot dispatcher.

Preparation requires complete predecessor zero/fine-60/fine-40 cases and
their independent timing, terminal and control/gate receipts; measured
pre-driver low recovery change above 100 mV and fine-driver high recovery
change above 50 mV in the topology-resolved voltage proof; and the exact
completed DC-zero numerical trial with preserved physical failure and zero
DC-voltage difference. It captures and checks all native witnesses and
transitive source/material/model/runtime inputs. No pending predecessor
unshifted result is reclassified or replaced by this separate experiment.

Centered cases use the previously tested fixed DC-zero 2–4 ps / 1 mA bench
ramp, while case 4 remains fully unshifted. The new circuit must establish
its own active numerical parity: complete voltage comparison in both
interpolation directions at 2 mV, all eight input/output crossings at
0.25 ps, all aggregate and individual classifications identical, and DC
voltages preserved within 1 nV. Existing ramp admission for another circuit
cannot admit this one. Positive conservative rise/fall overlap across both
fine duty points and every original point check remain required; PHY
admission is always false.

Three focused tests pass in 1.196 s, covering exact five-case coverage,
all native fixtures and bench cards, plus rejection of DC drift or a reverse-
direction voltage failure. Log:
`build/p40n32-pre-distributed-pilot-300-tests-v2.log`. Preparation is running
in `build/p40n32-pre-distributed-pilot-300-prepare.log`; no new native result
or circuit admission is claimed at this stage.


P40/N32 preparation now succeeds as
`p40n32_pre_distributed_pilot_300_v1/3efd00e62550ef86`. The captured native
library, complete observations, model/runtime/evidence closure and all five
decks pass reconstruction and binding; log:
`build/p40n32-pre-distributed-pilot-300-prepare.log`.

Unit `openlvds-p40n32-pre-distributed-300-v1`, invocation
`7f01f91d9b164ba9bba9f6d8134c73ff`, is confirmed live after initial complete-
input verification, with its first single-worker priority-1 ticket queued
through the unchanged dispatcher. No existing solver is preempted, and all
running/captured helpers and worker caps are preserved. Runtime log:
`build/p40n32-pre-distributed-300-v1.log`. This launch does not claim a native
result, speed benefit or component/PHY admission.


### Larger split bank coverage closes with rising-edge discontinuity

Coarse-one case 13 of the original distributed campaign completes without
execution error. Rising history is **0.934440533 ps**, falling
**0.002192702 ps**, and the original point-level clock-interface screen passes.
Independent receipt `distributed_bank_native_replay_300/cda55dc74b1e8436`
reproduces every original metric and independent timing, terminal envelopes
and control/programming-gate checks. Log:
`build/distributed-split-c2-coarse1-native-replay-300.log`.

Using completed centered fine-60/fine-40/coarse-one cases 7/12/13, the original
conservative overlap is **−102.078546 ps rising / +132.829063 ps falling**.
The positive falling result cannot admit the rising discontinuity or override
the independently reproduced fine-60 history and zero-code quarter failures.
All centered endpoints for this larger candidate are complete and rejected;
its unshifted reference remains live, so the full 14-case campaign and active
pair parity are still pending. The P40/N32 zero-code solver is now confirmed
live following a normal dispatcher slot handoff; its separate circuit remains
unqualified.


### Shared independent replay supports the captured P40/N32 producer

`scripts/replay_distributed_native_300_v2.py` selects only the registered
original distributed, single-P40 and P40/N32 producer versions, then invokes
the selected producer's complete bound verification. It checks exact selected
tasks and all native witnesses, reproduces every original metric, and invokes
the unchanged independent timing/terminal/control-and-gate metrology with
the exact variant observations. Separate content-addressed receipts preserve
failures and never admit a whole bank or PHY. Existing consumers and captures
remain unchanged.

Four tests pass in 2.238 s, covering producer dispatch, unsupported versions,
empty/duplicate/unknown selections, execution failure, mismatched task and
pending output. Log:
`build/distributed-family-native-replay-300-v2-tests.log`. An actual preflight
against the complete P40/N32 capture correctly refuses still-running case 0,
without creating a receipt; log:
`build/p40n32-native-replay-300-v2-pending-preflight.log`. First validation
on a complete native dataset is running for single-P40 coarse-one case 3,
whose replay was not previously executed through another consumer. This is
read-only metrology with no SPICE lease or running-file mutation.


### SS0/310 MHz DCC source cohort independently verified

Fresh DCC source cases 216–233 complete without execution errors. Independent
receipt `dcc_source_native_replay_300/dc4dd1d8931480a2` reproduces all 18
original measurements and passes every independent source screen at SS0/
310 MHz, 40/50/60% complementary duty, 20/250 ps slew and 0/±140 ps event
spacing error. Log: `build/dcc-source-300-ss0-310-replay.log`. Independently
replayed source coverage is now **234 cases**. Remaining SS0 frequencies,
SS25 and other corners are pending; this source-only evidence does not
qualify physical DCC RC/startup/stress, the loaded DLL or the complete PHY.


### Single-P40 centered coverage closes; shared replay validated on native data

Coarse-one case 3 completes without execution error and passes the original
point-level clock-interface screen. Rising history is **2.143391111 ps**,
falling **0.003566806 ps**. New shared-consumer receipt
`distributed_family_native_replay_300_v2/c4ef85516ac1cae3` reproduces every
original metric plus independent timing, terminal envelopes and control/
programming-gate settling, validating producer dispatch and metrology on a
complete actual dataset. Log:
`build/medium-pre-coarse1-family-native-replay-300-v2.log`.

The unchanged conservative overlap across centered fine-60/fine-40/coarse-one
cases 1/2/3 is **−72.490802 ps rising / +15.918970 ps falling**. Together
with the independently reproduced fine-60 history/period failure, this rejects
the unchanged single-P40 architecture despite its repaired zero-code quarter
headroom. Its unshifted reference and numerical pair remain separate pending
evidence. The P40/N32 experiment must still demonstrate positive overlap as
well as recovery/history improvements; its first native run remains live.
No component, loaded-chain, PVT or PHY qualification is claimed.


### P40/N32 zero-code point passes with independently verified headroom

Case 0 of `p40n32_pre_distributed_pilot_300_v1/3efd00e62550ef86`
completes 40 ns / **20,015 native samples** without execution error in
**979.031 s** native elapsed time. Worst rising delay is **650.984795547 ps**,
worst falling delay **724.898367130 ps**, giving **+81.553245774 ps** headroom
against the unchanged 806.451613 ps fastest-quarter target. Rising/falling
history are **2.091798429 / 0.003113578 ps**, maximum period error
**2.091812800 ps**, and maximum slew **85.261273094 ps**. Every original
point-level clock-interface, terminal and control/programming-gate check
passes.

Independent receipt
`distributed_family_native_replay_300_v2/a149f233bd8c9029` reproduces all
original metrics and independent timing, terminal envelopes and control/
programming-gate settling using the exact P40/N32 observations. Log:
`build/p40n32-pre-zero-native-replay-300.log`. This validates shared producer
dispatch/metrology on the new actual native dataset as well as the preceding
single-P40 case. It does not establish fine-60 history, positive overlap,
active numerical parity, actual loading, routed RC, PVT, DLL/DCC or PHY
qualification. The one-worker campaign has acquired a normal dispatcher slot
for fine-60 case 1; all remaining cases and original gates are retained.


### Registered recovery metrology supports P40/N32 native waveforms

`scripts/diagnose_distributed_recovery_300_v3.py` uses the shared registered
producer selector and imports the unchanged V2 topology resolver and
startup-inclusive voltage sampler. It adds P40/N32 support without modifying
any captured producer or metrology helper. Exact native witnesses, imported
code and source/model/runtime inputs remain bound in separate receipts;
unsupported producers and pending cases are refused before output creation.
Two integration tests pass in 0.380 s, checking actual P40/N32 capacitor-side
attachments and representative enable coverage, unrecognized attachment
rejection, and pending-data refusal. Log:
`build/distributed-voltage-recovery-300-v3-tests.log`.

Actual P40/N32 zero-code replay completes as
`distributed_voltage_recovery_300_v3/c8e3fe8e7a032294`. All original eight-
event outer delays reproduce and every stage sum has zero residual. Log:
`build/p40n32-zero-voltage-recovery-300-v3.log`. Falling stage ranges are
**333.364450–333.366667 ps** selection,
**230.335698–230.337914 ps** pre-driver,
**101.667530–101.668825 ps** fine driver, and
**59.525469–59.527533 ps** output. The preceding single-P40 zero point had
approximately 315.24 / 291.07 / 115.69 / 62.78 ps at these stages.
Thus improved downstream stage delays outweigh the measured selection-delay
increase for this exact zero-code comparison. This does not isolate the
physical contribution of transistor sizing from the retained cells' differing
local RC, or prove enabled-state fine-60 recovery.

All eight zero-code pre-driver pre-transition low samples remain between
**−3.565397 and −3.528717 mV**, while its high samples remain around
**1.806941 V**. The report retains actual switch-side voltages, without
inferring MIM plate charge. Fine-60, coverage, numerical parity, actual
loading, PVT and PHY qualification remain open.


### P40/N32 fine-60 history repair independently verified

Case 1 completes without execution error and passes every original point-
level clock-interface, terminal, slew and control/programming-gate check.
Rising history is **6.719727885 ps**, falling **0.014604682 ps**, maximum
period error **6.718512439 ps**, and maximum slew **127.760343499 ps**.
Rising delays span 830.919836–837.639564 ps; falling delays span
860.256736–860.271341 ps. This repairs the preceding single-P40 fine-60
history/period failure at this exact SS40/310 MHz component point while
retaining the independently verified zero-code headroom.

Independent receipt
`distributed_family_native_replay_300_v2/7a40cc9be4a06f92` reproduces every
original metric and independent timing, terminal envelopes and control/gate
checks. Log: `build/p40n32-pre-fine60-native-replay-300.log`.
Topology-resolved recovery receipt
`distributed_voltage_recovery_300_v3/6b5792e313a8636a` reproduces all outer
delays with zero stage-sum residual; log:
`build/p40n32-fine60-voltage-recovery-300-v3.log`.

At the same pre-transition definitions used for the failed single-P40 point,
pre-driver low voltage changes from **−2.733 mV** initially to **12.095 mV**
on the last event (previously about 111.425 mV). Representative enabled
pre-capacitor-side voltages reach about **30–32 mV** (previously 183–188 mV).
Downstream fine-driver high recovery changes from **1.807988 V** to
**1.787528 V** (previously 1.752652 V), with representative fine-capacitor-side
voltages about **1.731–1.734 V** (previously 1.613–1.620 V).
Rising stage-history spans are **2.368187 / 3.468418 / 5.503746 / 0.115832 ps**
(selection / pre-driver / fine / output); the former pre/fine spans were
26.808991 / 16.794789 ps. These observed voltage/timing changes support the
recovery intervention, without inferring MIM charge or isolating every local-
RC contribution of the different retained cell assembly.

Fine-40/coarse-one coverage, the unshifted active reference and its fresh
bidirectional/DC parity remain required. Actual next-bank/shared-RC loading,
PVT, DLL/DCC and full PHY qualification remain open. No component-pilot or
PHY admission is granted from the passing zero/fine-60 points alone.


### Serial DCC source replay watcher implemented and preflighted

`scripts/watch_dcc_source_300.py` adopts the counter watcher's serial replay
pattern for the existing 810-case DCC source campaign. It verifies receipt
identity/content addressing, exact case coverage, original-source predicates,
every bound native/model/code input, native summary and witness inclusion,
and independent result/aggregate consistency before indexing existing proof.
Source failures remain failed, native execution errors remain non-replayable,
and partial replay evidence prevents an automatic retry of the same cases.
Immutable inputs are hashed once per watcher process; final matrix admission
still requires a fresh full consumer remeasurement of all 810 native cases.

The watcher accumulates completed cases into batches of at most 18, runs one
consumer at a time, and polls every 30 seconds. It uses no SPICE lease and
never changes, preempts or restarts a native solver. After the native parent
is complete and all 810 selected-case receipts are indexed, it invokes the
existing consumer's `--full` path, which independently rechecks all original
and source-event measurements. Its terminal result remains source-only;
physical DCC, loaded DLL and PHY admission cannot be granted by the watcher.

Seven focused tests pass in 0.012 s: complete bound receipt adoption,
changed-native rejection, partial receipt protection, original failure
preservation, conflicting independent-result rejection, cohort/terminal
batching and native-error exclusion. Log:
`build/dcc-source-watch-300-tests-v2.log`. Actual read-only preflight verifies
**234 cases / 15 receipts**, with **no partial or failed receipts**; log:
`build/dcc-source-watch-300-receipt-preflight.log`. Further DCC selected-case
replays will be owned by this watcher to avoid concurrent duplicate attempts.


### P40/N32 fine-40 point independently verified

Case 2 completes without execution error and passes the original point-level
clock-interface screen. Rising history is **3.393195911 ps** and falling
**0.228084129 ps**. Independent receipt
`distributed_family_native_replay_300_v2/a6a643d705854caf` reproduces every
original metric plus independent timing, terminal envelopes and control/
programming-gate checks. Log:
`build/p40n32-pre-fine40-native-replay-300.log`. Zero, fine-60 and fine-40
points now pass individually for this exact SS40/310 MHz component circuit.
Coarse-one conservative overlap and the unshifted active numerical reference
remain pending, together with actual loading, routed RC, PVT and PHY gates.
No component pilot or PHY admission is granted.


### DCC watcher container-service probe corrected in a separate version

The first watcher unit `openlvds-dcc-source-watch-300-v1`, invocation
`89fa54ef0c9a48898cb95c3f0b9ee7d5`, completed receipt indexing but stopped
when its optional service probe attempted the unavailable `systemctl` binary
inside the simulation container. Attempt
`dcc_source_watch_300/a01eaafecba45c0b` remains retained with the full error
and progress snapshot (246 native completions / 234 verified cases, no native,
partial-replay or source-screen failures). No native solver was stopped,
restarted or modified. Log: `build/dcc-source-watch-300-v1.log`.

`scripts/watch_dcc_source_300_v2.py` treats an unavailable optional host-service
probe as unknown and continues using the native campaign's recorded state.
It reuses the unchanged first version's receipt verifier, native-case reader
and batch planner, and binds both code files. The original failed helper and
artifact remain unchanged. Ten combined tests pass in 0.017 s, including
missing executable, inaccessible service manager and valid service-state
handling. Log: `build/dcc-source-watch-300-v2-tests.log`. Actual container
preflight now returns `service_probe: None` without exception; log:
`build/dcc-source-watch-300-v2-environment-preflight.log`.


A second environment preflight confirmed that both `apptainer` and `systemctl`
are absent inside the container. The V2 observer was intentionally stopped
before relying on its nested `env.sh` child launcher; its incomplete attempt
`dcc_source_watch_300_v2/dd00124064b85712` remains preserved, including its
watching-state snapshot. Unit `openlvds-dcc-source-watch-300-v2`, invocation
`b1f085483c0d4dc8abdb41b5930c9dcf`, is no longer running. No native SPICE
process was stopped or restarted. Environment evidence:
`build/dcc-source-watch-300-container-launcher-preflight.log`.

`scripts/watch_dcc_source_300_v3.py` launches replay children with its current
Python interpreter and inherited scientific environment, without nested
container invocation. It reuses the tested V2 optional service probe and
original immutable receipt/batch helpers, binding all three code files.
Twelve combined tests pass in 0.340 s, including an actual consumer help
subprocess in the container, explicit case forwarding and full-replay command
selection. Log: `build/dcc-source-watch-300-v3-tests.log`. Previous observer
attempts and source captures remain unchanged.


### P40/N32 centered endpoints complete; fine range remains insufficient

Coarse-one case 3 completes without execution error and passes the original
point-level clock-interface screen. Rising/falling history are
**2.272336496 / 0.004120402 ps**, maximum period error **2.272350868 ps**,
and maximum slew **85.264910163 ps**. Independent receipt
`distributed_family_native_replay_300_v2/4fe4f7d0341a1e7d` reproduces every
original metric and independent timing, terminal envelopes and control/
programming-gate checks. Log:
`build/p40n32-pre-coarse1-native-replay-300.log`.

All four centered endpoint checks now pass for the exact P40/N32 circuit at
SS40/310 MHz, including the repaired zero-code quarter and fine-60 history
checks. The unchanged conservative overlap across fine-60/fine-40/coarse-one
cases 1/2/3 is nevertheless **−35.944543 ps rising / −60.021195 ps falling**.
The fine-delay range therefore remains insufficient on both edges; individual
point passes do not qualify this architecture. The unshifted reference and
fresh bidirectional/DC parity remain pending. This closes the centered
coverage decision without stopping the live reference or changing any bound.
The next fine-range intervention must preserve the demonstrated recovery and
quarter-period headroom, followed by actual loading, routing, PVT and PHY
qualification; no admission is granted here.

### Container-safe DCC replay watcher confirmed live

Unit `openlvds-dcc-source-watch-300-v3`, invocation
`7cdd65b647cc4665b676fb00748d98bc`, is confirmed live as
`dcc_source_watch_300_v3/d9c7e020af478d44`. Its actual verified index has
**234 replayed / 249 native-completed cases**, **15 pending**, and no native,
partial-replay or source-screen failures. It remains active through the
unavailable optional service probe. The first automatic child batch awaits
18 completed pending cases; direct child startup was tested in the actual
container, but no automatic batch result is claimed yet. Runtime log:
`build/dcc-source-watch-300-v3.log`. All earlier observer attempts, native
source captures, dispatcher caps and running solvers remain unchanged.


### Double-transmission-gate fine cell physically built and RC-qualified

The remaining P40/N32 range deficit motivates a controlled switch-strength
experiment: retain the 2×3 MIM, 2×2 control shunt and 0.42 µm discharge clamp,
while changing only the transmission NFET/PFET widths from **0.42/0.84 µm**
to **0.84/1.68 µm**. The hypothesis is that lower switch resistance may raise
the effective edge load and reduce observed capacitor-side lag. Neither gain
nor recovery improvement is assumed. Original units, models and running
captures remain unchanged; the distinct macro is
`openlvds_mim_switch_2x3_tg2_v1`.

New versioned schematic, primitive-inspection, direct routing, DRC/LVS,
extraction and independent-verification scripts use isolated artifact/model
namespaces. Routing uses its own unit binding rather than changing an existing
module's globals. Initial explicit placement is retained in
`configs/mim_switch_2x3_tg2_placement_v1.json`. Two tests pass in 0.002 s,
checking the exact two-width-only schematic difference and protection against
overwriting a partial primitive attempt. Log:
`build/mim-switch-2x3-tg2-v1-tests.log`.

Actual PDK geometry inspection completes in
`mim_switch_2x3_tg2_pcells_v1/304fca3dc4d5cd89`. Physical build
`mim_switch_2x3_tg2_physical_v1/fb967f0440b1844a` passes with **zero DRC
errors and independent LVS match**. Fresh GDS-derived extraction
`mim_switch_2x3_tg2_rc_v1/a34dbc3ef82ace31` passes the wire-collapsed topology
audit, with **235 raw resistors / 65 parasitic capacitors**, exactly reduced
to **204 resistors**. Independent receipt
`mim_switch_2x3_tg2_verification_v1/3b9096d4e7fd4aa9` binds the exact
schematic scope, GDS and raw/reduced netlists and repeats the topology check.

Component proof `mim_switch_2x3_tg2_rc_proof_300_v1/97729cdbade089d6`
passes exact reduction regeneration, elementwise passivity, native parameter/
topology preservation and independent Schur terminal-current equivalence.
It confirms five native primitives with all native dimensions and supplied
junction parameters preserved. This mathematical proof modifies no model
bytes and performs no additional extraction. The first proof launch stopped
before artifact creation because the general scientific environment lacked
KLayout; its log is retained. The existing physical-verification environment
completed the proof without changing any captured runtime or model.

Logs: `build/mim-switch-2x3-tg2-pcells-v1.log`,
`build/mim-switch-2x3-tg2-physical-v1.log`,
`build/mim-switch-2x3-tg2-rc-v1.log`,
`build/mim-switch-2x3-tg2-independent-rc-v1.log`, and
`build/mim-switch-2x3-tg2-schur-proof-300-v1-physical-env.log`.
The initial dependency failure is retained in
`build/mim-switch-2x3-tg2-schur-proof-300-v1.log`.
No bank timing simulation, electrical/PVT or PHY qualification is claimed;
all new artifacts retain `qualified_phy:false`. The next step is exact bank
substitution followed by fresh zero/fine/coarse and active-parity experiments.

### Double-TG switch intervention: native bank preparation

The P40/N32 split-one-plus-one baseline passes all four centered point screens,
but its conservative code overlap is still negative on both edges
(rise −35.944543 ps; fall −60.021195 ps). The next controlled intervention doubles
only the transmission-gate widths in each fine unit, using the independently
qualified `openlvds_mim_switch_2x3_tg2_v1` physical/native RC model. The off clamp,
MIM dimensions, pre-driver and fine-driver architecture remain the baseline.
Lower switch resistance is a hypothesis for more effective fine loading and
better switch-side recovery; component RC qualification is not evidence of
that timing effect.

`tg2_p40n32_bank_300.py` substitutes the 62 fine-unit calls and reconstructs all
actual native transistor and programming-gate observations. Its material loader
runs the original physical/native/Schur binding in the CAD environment and
requires the complete independent terminal-current witness and unchanged output
files. A direct integration check passed that full material proof (67 retained
paths). The transformed bank retains 2,056 MOS, 202 MIM, 86 controls and 266
programming-gate observations. Three integration tests passed in 2.089 s,
including rejection of changed split wiring and the requirement for a fresh
unshifted numerical reference.

`probe_tg2_p40n32_300.py` requires the exact four passing baseline points and their
measured both-edge coverage failure before capture. It tests zero code, maximum
fine code at 60% and 40% duty, the next coarse code, and a fresh unshifted 60%
fine reference at SS/40 °C/310 MHz. It retains the existing bidirectional
2 mV waveform / 0.25 ps crossing / 1 nV DC numerical-parity limits, all startup
events and original electrical gates. One worker uses the existing global
six-slot dispatcher. Neither component construction nor pilot preparation
admits whole-bank timing, shared routing, PVT coverage or the PHY.

### Container-safe DCC watcher: first completed automatic batches

The V3 watcher successfully launched its independent consumer directly in the
captured scientific environment. Automatic batches 234–251
(`dcc_source_native_replay_300/53837a6f083eb447`) and 252–269
(`dcc_source_native_replay_300/d23c9b6d35678669`) both completed with all selected
source screens passing. This verifies the actual child execution path after the
prior container/systemd and nested-Apptainer observer failures. The watcher now
owns new DCC replay scheduling. Its subsequent snapshot reached 289 native
completions and 288 independent replays with no native errors, partial replay
cases or failed replay cases. These are source-only point receipts; the fresh
810-case full-matrix replay is still required, and no physical DLL/PHY admission
is implied. The counter watcher separately reached 151 native completions and
151 corrected protocol replays with no errors or failed replay cases.

`replay_distributed_native_300_v3.py` adds the double-TG producer to the explicit
registered native-bank replay family. It retains the same independent timing,
terminal envelope and control/gate-settling checks and refuses incomplete,
unknown, duplicate or errored selections. Five refusal/registration tests passed
in 2.643 s. This new consumer does not alter the immutable V2 consumer used by
already captured campaigns; native double-TG timing proof awaits completed cases.

### Original distributed-fine campaign: final unshifted case retained

`distributed_fine_pilot_300_v1/f07675577cda70f9` naturally completed all 14 cases
with zero execution errors. The final split-two-plus-two unshifted/centered pair
(6/7) was independently reproduced in
`distributed_bank_active_parity_300/4408d49075a86ec1`: all original measurements
reproduced, all gate classifications matched, maximum all-voltage interpolation
difference 0.718026 mV across 7,638 vectors and maximum crossing difference
0.001352956 ps. Both physical point screens remain failed. No model, waveform,
parameter or tolerance was changed to obtain parity. The completed campaign
continues to reject split-one-plus-one and split-two-plus-two on conservative
rising overlap (−116.116961 ps and −102.078546 ps respectively); split-one also
fails falling overlap (−33.819311 ps), while split-two's positive falling overlap
(+132.829063 ps) does not repair its rising coverage or history failure.
This closes the long native numerical reference without admitting either bank.

### Double-TG bank pilot captured and launched

Preparation completed successfully in
`tg2_p40n32_pilot_300_v1/aae4b31d0e77445c`. Its content-addressed identity and all
five captured tasks were checked: centered zero/50%, fine/60%, fine/40%,
coarse-one/50%, then unshifted fine/60%. The bank library SHA-256 is
`2f2f1ab9cb83c9402377224eb5603e25e7b36fec0f4d979f9f9217186ed9572d`.
The same full component proof and exact 2,056-MOS/202-MIM inventory bind this
capture. The run was launched under user unit
`openlvds-tg2-p40n32-300-v1`, invocation
`429436ee81bc4327ab79e45b9629dd33`, with one worker and existing priority-one
six-slot dispatch. At the launch check the unit was active in initial evidence
validation; no native timing case had completed. The log is
`build/tg2-p40n32-300-v1.log`. This is an experiment launch, not a passing bank
or PHY result. Existing native reference and PVT jobs were not preempted.

### Actual next-bank materials bind the double-TG architecture

`next_bank_tg2_materials_300_v1.py` prepares the captured double-TG bank's
SS/40 °C/310 MHz zero-code diagnostic with a complete second bank attached to
its output. It uses the actual captured variant library and its 2,056 native
transistor maps, rather than the older restored-bank observations or a fitted
input capacitance. The original 20 fF first-bank capacitor is removed; the
second bank retains the 20 fF far-end load. Common inter-bank wiring is ideal,
so these materials cannot establish routed DLL loading or shared RC.

The material set is
`tg2_next_bank_zero_materials_300_v1/e0fb1a825657793f`. Four decks cover next-bank
fine codes 0 and 31, each with its own fresh unshifted/ramped current pair.
Every deck observes both banks (4,112 MOS total), independent next-bank control
nets, 172 logical control observations and 532 actual programming-gate
observations. Runner translation checks unique saved-vector names while retaining
all transistor-terminal probes. The unchanged first-bank controls remain zero
when the next bank is programmed to fine31.

Four integration tests passed in 5.415 s: full native probe coverage and runner
translation, exact pair stimulus/current-card equivalence, separate control
programming, and refusal to load an already loaded fixture. Preparation and a
separate `check` both passed. State is `prepared_unqualified`, simulations 0,
`qualified_phy:false`. No loaded simulation has launched; the single-bank pilot
must establish feasibility before spending solver slots on these diagnostics.

### Fresh ramped-family numerical-pair consumer prepared

`replay_distributed_pair_300_v1.py` accepts only the captured medium-pre,
P40/N32-pre and double-TG producers. It requires the same-variant, same-stimulus
unshifted case 4 and ramped case 1, reproduces each full original measurement,
and independently checks each run's timing, terminal envelope and actual
control/programming-gate settling. It then reruns the producer's bidirectional
all-voltage parity, crossing, DC and gate-classification comparison. The receipt
preserves failed physical point classifications and never admits a whole bank.

Three registration/refusal tests passed in 1.934 s, including rejection of a
pending reference before expensive binding or receipt creation and rejection of
a mismatched pair stimulus. An actual preflight against the still-live P40/N32
case 4 correctly refused with `Native active-pair case is still pending: 4`;
no numerical-pair receipt or passing result was created. The references remain
running and must finish naturally before this consumer can produce evidence.

### Native two-bank transport metrology and evidence-gated runner

`two_bank_native_measure_300_v1.py` evaluates the actual loaded first bank
against the ideal bench input and the second bank against the **measured** first
bank output. It preserves every startup pulse and all 10/50/90% crossings,
checks full swing, pulse order, positive unwrapped delays, 20 ps period/history,
250 ps input/output slew domains and the 300 MHz profile's fastest-quarter
budget for each bank programmed to zero. The downstream reference is explicitly
relative; it is not incorrectly required to match the ideal 2.1 ns bench epoch.
Each bank's terminal envelope and control/programming-gate checks use that
bank's own actual transistor map and programmed coarse/fine code. All samples,
including DC and startup stress, remain included. Both banks and the fixed
1.8 V supply check must pass the combined diagnostic.

Seven metrology tests passed in 0.478 s, including complete synthetic binary-raw
parsing and measurement, independent first/next control targets, the 700/750 ps
relative-stage distinction, startup pulse loss, downstream quarter failure,
startup terminal stress, supply error and missing DC sample. Synthetic unit
traces validate the analyzer only and are not circuit simulation evidence.

`probe_tg2_next_bank_300_v1.py` is the corresponding four-case native runner.
Preparation requires the naturally completed five-case single-bank pilot with
all original point screens passing, positive conservative overlap on both
edges, fresh bidirectional/DC numerical parity, and its matching independent
complete-pair receipt. It then binds the prepared actual next-bank decks and
full source evidence into a new immutable experiment. One priority-one worker
uses the existing global dispatcher. Both next-bank code settings require their
own unshifted/ramped pair, with all saved native voltage vectors, 2 mV
bidirectional interpolation, 0.25 ps crossing and 1 nV DC limits. Input, first
output and second output events all participate; no internal vectors or failed
gate classifications are excluded.

Four runner tests passed in 1.709 s, including refusal of an unfinished source,
refusal of negative overlap despite passing point screens, requirement for all
four loaded cases and both pairs, and preservation of internal-voltage, DC and
programming-gate differences. Actual preflight against the live pilot correctly
refused with `Single-bank native pilot has not completed all five error-free
cases`, before capture or solver launch. No actual loaded native result exists.
The runner is a component diagnostic, not shared-wire RC, delay-table, DLL/PVT
or PHY qualification; those gates remain open.

### Topology-derived recovery diagnostic supports the wider-switch cell

The new extracted cell assigns its NMOS transmission switch to `X1`, whereas
the original cell used `X3`. The original recovery helper's fixed `X3` MOS
assumption would select a MIM primitive in the new extraction, so it must not be
used on this bank. `diagnose_distributed_recovery_300_v4.py` adds the double-TG
producer through the V3 native-bank registry and resolves representative
switch-side MOS terminals from actual resistor connectivity. It identifies the
internal main-MIM plate separately from the control shunt and requires one
native PFET and one native NFET connecting that plate's resistor network to the
signal-node resistor network. It checks the actual observation maps against
the library and retains units 0, 15 and 30 on both pre/fine attachments.

Three actual-library integration tests passed in 0.498 s: both old (`X0/X3`)
and new (`X0/X1`) leaf assignments resolve 12 representative D/S observations,
a missing native switch cannot be substituted by a capacitor, and a mismatched
observed capacitor-side terminal is refused. The fixed 20 ps pre-edge samples,
all eight startup-inclusive events and voltage-only interpretation remain
unchanged. Old diagnostics and captured experiments were not modified. This is
metrology support, not a capacitor-charge or recovery-mechanism proof.

### Wider fine switches preserve the zero-code quarter budget

Double-TG pilot `tg2_p40n32_pilot_300_v1/aae4b31d0e77445c` case 0 naturally
completed without execution error. At SS/40 °C/310 MHz/50% duty, its complete
startup-inclusive zero-code screen passes: maximum rise delay 680.143119 ps,
maximum fall delay 750.016857 ps, fastest-quarter headroom **+56.434756 ps**,
rising/falling history spans 2.142949/0.003157 ps, maximum period error
2.142885 ps and maximum output slew 88.606410 ps. Native elapsed time was
1016.710 s. Compared with the original P40/N32 bank's +81.553246 ps headroom,
the wider switches consume 25.118490 ps while preserving this zero-code gate.
This comparison alone does not establish a fine-range gain or causal charge
mechanism.

Independent replay
`distributed_family_native_replay_300_v3/631be7991c7707dc` completed and
reproduced every original measurement plus independent timing, terminal envelope
and control/programming-gate settling. It covers all 2,056 MOS, 86 controls and
266 actual programming gates. The worst terminal envelope was 1.907318434 V
against a 1.95 V limit, passing. Log:
`build/tg2-p40n32-zero-native-replay-300-v3.log`.

The unchanged producer advanced to centered fine31/60% case 1, confirmed live
in native ngspice. Fine31/40%, coarse-one, both conservative overlap edges,
fresh unshifted numerical parity, actual next-bank loading, common routing,
15 PVT and DLL/PHY qualification remain open. No zero-code result admits a
bank or authorizes the gated actual-next-bank experiment; `qualified_phy:false`.

### Wider-switch zero-code recovery and stage cost reproduced

Topology-derived diagnostic
`distributed_voltage_recovery_300_v4/3c14399abd7fe3a0` naturally completed for
double-TG case 0. It reproduces the complete outer delays and all stage sums
with **0 ps residual**, retains all eight startup-inclusive events and resolves
the actual capacitor-side transmission-switch terminals. No native model or
waveform changed. Log: `build/tg2-p40n32-zero-recovery-300-v4.log`.

Against the original P40/N32 zero-code diagnostic
`distributed_voltage_recovery_300_v3/c8e3fe8e7a032294`, the last-event stage
changes are:

| Measured stage | Rising delay change (ps) | Falling delay change (ps) |
| --- | ---: | ---: |
| IN → selected | −0.006036 | −0.060885 |
| selected → pre_out | +11.539030 | +13.105228 |
| pre_out → fine_node | +13.838746 | +9.353826 |
| fine_node → OUT | +3.786921 | +2.718260 |

These last-event values describe where the zero-code cost appears; they do not
replace the complete eight-event extrema/history gates. The coarse-selection
contribution remains nearly unchanged, while the pre/fine stages account for
most of the added latency. Across all eight fixed pre-edge voltage samples,
pre_out's low level is −3.377124…−3.340997 mV (first-to-last change −0.035958 mV)
and fine_node's high level is 1.809315604…1.809337962 V (first-to-last change
+0.022240 mV). This zero-code observation does not demonstrate enabled-fine
recovery, added fine span, capacitor charge or a complete causal mechanism.
The pending fine31/60% run must supply that timing evidence; bank/PHY admission
remains false.

### Wider switches improve the native fine31/60% point

Double-TG pilot case 1 completed without execution error (native elapsed
1025.130 s) and passed its SS/40 °C/310 MHz/60% duty screen. All eight rising
delays are 978.315046…978.445058 ps and falling delays
977.283345…977.285504 ps. Rising/falling history spans are
**0.130012/0.002159 ps**, maximum period error 0.129689 ps and maximum output
slew 155.044901 ps. These are completed native point measurements, not a
conservative-overlap result: fine31/40% and the new coarse-one delays remain
required, together with fresh unshifted numerical parity and actual loading.

Independent replay
`distributed_family_native_replay_300_v3/22a131b8c09c7d4b` reproduces every
original metric and independent timing, terminal envelope and control/gate
settling checks for all 2,056 MOS, 86 controls and 266 programming gates. Its
worst terminal envelope is 1.907314195 V against a 1.95 V limit, passing.
Log: `build/tg2-p40n32-fine60-native-replay-300-v3.log`.

Recovery diagnostic `distributed_voltage_recovery_300_v4/b46ab7521f92c3e6`
reproduces the outer delays with 0 ps stage-sum residual and all eight events.
Compared with the original P40/N32 fine-60 diagnostic
`distributed_voltage_recovery_300_v3/6b5792e313a8636a`, the final pre_out low
sample improves from 12.095 mV to 4.551101 mV and the final fine_node high sample
from 1.787528 V to 1.797101093 V. The representative final pre capacitor-side
samples are 8.125419…8.473281 mV (previously 30.456506…31.773950 mV), and fine
capacitor-side samples are 1.784233575…1.784859054 V (previously
1.731105767…1.734353350 V). These are fixed pre-edge voltages, not measured
capacitor charge or an isolated causal proof. Log:
`build/tg2-p40n32-fine60-recovery-300-v4.log`.

The small total history span includes stage cancellation and must not be
attributed to every stage having 0.13 ps variation. Rising stage spans are
2.277995 ps (selection), 1.262957 ps (pre), 1.000101 ps (fine), and 0.114018 ps
(output). The first-to-last changes have mixed signs: +2.277703, −1.262564,
−0.999587 and +0.113835 ps. Pre/fine spans improve from 3.468418/5.503746 ps in
the original P40/N32 point, while their remaining variation is preserved in the
receipt. Full bank, continuous DLL/DCC, common RC, PVT and PHY admission remain
false.

### Early actual-loading diagnostic prioritizes the remaining zero-code risk

The verified +56.434756 ps zero-code headroom is sufficiently small that the
actual next-bank input could reject this architecture even if its artificial
20 fF endpoint coverage passes. The newly verified fine31/60% point improves
recovery but does not answer that loading question. A separate versioned
`probe_tg2_next_bank_early_300_v2.py` therefore permits an **unqualified early
loading diagnostic** after the independent zero and fine-60 point receipts,
without waiting for fine40/coarse-one coverage or the source's unshifted pair.
The original V1 runner's full-source-feasibility gate remains unchanged.

This changes experiment ordering, not acceptance of a bank. The early capture
explicitly records `source_full_bank_coverage_qualified:false` and
`source_active_numerical_parity_qualified:false`. It retains four complete
40 ns/eight-event native cases and the same actual two-bank transistor maps,
fixed supplies, stress, control, slew, period/history and quarter-budget checks.
The order is centered next-fine0, centered next-fine31, unshifted next-fine0,
unshifted next-fine31; both settings still require their own fresh bidirectional
all-voltage/DC/crossing comparison. A centered result alone cannot pass the
four-case diagnostic. One priority-two worker uses the unchanged six-slot
aging dispatcher, with no preemption of existing native jobs.

Four tests passed in 0.445 s: refusal of a missing source point before binding
or capture, exact preservation of the two centered/unshifted material pairs,
requirement for all four cases and both comparisons, and rejection of hidden
internal-voltage, DC and programming-gate differences. Preparation is gated on
both complete unchanged independent native point receipts; no source coverage,
source numerical-parity or PHY certificate is inferred from this diagnostic.

### Early actual-loading capture completed and controller launched

Early loading preparation passed its complete source-point/native-input binding
and captured `tg2_next_bank_early_zero_pilot_300_v2/23dee609d6ca5e51`.
The identity hash, material-case mapping and all four actual observation maps
were checked after preparation: each deck contains 4,112 MOS, with centered
next-fine0/31 cases 0/1 followed by their unshifted references 2/3. The bank
library remains byte-identical to the single-bank candidate, SHA-256
`2f2f1ab9cb83c9402377224eb5603e25e7b36fec0f4d979f9f9217186ed9572d`.
Both source full-bank coverage and source active numerical-parity qualification
flags are explicitly false in the captured identity.

The controller was launched under user unit
`openlvds-tg2-next-bank-early-300-v2`, invocation
`125073f504994a83bb7c5c1c033589ed`, one worker, priority two, with the unchanged
global six-slot dispatcher. The unit was confirmed active in its initial
captured-input verification; no loaded native result had completed at launch.
Log: `build/tg2-next-bank-early-300-v2.log`. Existing source, counter, long-clock
and numerical-reference jobs were not preempted or modified. A passing centered
point will remain an unqualified diagnostic observation until both loaded pairs
and the separate pending source/DLL/PVT/physical release gates are resolved.

### Independent actual-next-bank waveform reader prepared

`two_bank_independent_measure_300_v1.py` provides a second implementation of the
loaded-bank measurements: NumPy threshold interpolation and event arrays for
both stage references, all input/output 10/50/90% events, period/history,
quarter budgets and slew; pairwise terminal-voltage differences for stress;
and min/max extrema for each bank's own programmed controls and fixed supply.
It reads the complete native binary waveform including DC/startup. The second
bank is referenced to measured OUT, not the ideal IN epoch. Both passing and
failing point classifications must reproduce; no failed startup event is
removed and no native parameter is changed.

`replay_tg2_loaded_native_300_v1.py` accepts only the strict V1 and early V2
actual-next-bank producers. It binds the producer, captured library, actual
observation maps and every selected native witness; exactly remeasures the
original result; then independently compares the complete result and each gate
classification with the existing replay tolerance. Explicit completed case IDs
are required, and all inputs are rehashed after analysis. The receipt can only
prove selected point measurements, never numerical-pair, source coverage,
shared-RC, DLL/PVT or PHY qualification.

Four new checks passed in 1.020 s: complete binary-reader agreement for next
fine0/fine31 and a failed fixed supply; preservation of startup pulse loss;
refusal of missing native points before expensive binding or receipt creation;
and rejection of unknown, duplicate or empty selections. The agreement test
also refuses a modified recorded downstream delay. Synthetic binary fixtures
are analyzer unit tests, not circuit evidence. Actual preflight against the
running early loading case 0 correctly refused `Loaded native case is still
pending: 0`. No loaded timing receipt or admitted bank has been created.

### Wider-switch fine31/40% endpoint independently verified

Double-TG pilot case 2 naturally completed without execution error (native
elapsed 1043.210 s) and passes its SS/40 °C/310 MHz/40% duty point screen.
Across all eight events, rising delays are 978.315046…981.949956 ps and falling
delays 968.611693…968.777014 ps. Rising/falling history spans are
**3.634910/0.165321 ps**, maximum period error 3.634815 ps and maximum output
slew 154.888484 ps. The original waveform, startup events and limits are
unchanged; the history remains below 20 ps and the slew below 250 ps.

Independent replay
`distributed_family_native_replay_300_v3/0968cc348b4cab51` completed and
reproduces all original metrics, independent timing, terminal envelope and
control/programming-gate settling for all 2,056 MOS, 86 controls and 266 actual
gates. Worst terminal envelope is 1.907313803 V against a 1.95 V limit, passing.
Log: `build/tg2-p40n32-fine40-native-replay-300-v3.log`.

The zero-code and both fine-duty endpoints now have independently verified
passing point screens. Neither the fine-40 result nor their combined envelope
establishes conservative overlap before the new coarse-one result exists.
Fresh source unshifted parity, actual-next-bank comparisons, common RC, 15 PVT,
continuous DLL/DCC operation and PHY qualification also remain required. The
first early actual-next-bank case was confirmed live in native ngspice; no
loaded timing result is yet available. All bank/PHY admission flags remain
false.

### Wider-switch centered endpoint coverage becomes positive on both edges

Double-TG coarse-one case 3 naturally completed without execution error
(native elapsed 999.280 s) and passed its SS/40 °C/310 MHz/50% duty screen.
Rising delays are 893.736753…896.026045 ps and falling delays
929.513651…929.518204 ps. Rising/falling history spans are 2.289292/0.004553 ps,
maximum period error 2.289192 ps and maximum output slew 88.610180 ps.

Fresh combined independent replay
`distributed_family_native_replay_300_v3/e18df0801eda0298` completed all four
centered cases 0/1/2/3. It reproduces each full original measurement plus
independent timing, terminal envelope and control/gate settling for each case's
2,056 MOS, 86 controls and 266 programming gates. Worst terminal envelopes in
all four cases remain below 1.908 V against their 1.95 V limits. Log:
`build/tg2-p40n32-centered-endpoints-native-replay-300-v3.log`.

Using every measured delay from both fine31 duty points and the complete
coarse-one point, the same conservative min(fine40/fine60) − max(coarse-one)
calculation now gives:

| Candidate | Rising overlap (ps) | Falling overlap (ps) |
| --- | ---: | ---: |
| Original P40/N32 split one-plus-one | −35.944543 | −60.021195 |
| Qualified wider-switch component bank | **+82.289001** | **+39.093489** |

The zero-code and all other centered point screens pass. This is the first
positive complete **centered endpoint** coverage result for this intervention;
it remains conditional on the fresh unshifted source comparison. It is not a
dense-code monotonicity/gap, actual-loading, common-RC, all-PVT, DLL/DCC or PHY
certificate. The producer has advanced to its fresh unshifted fine60 reference,
confirmed live in native ngspice. The separate actual-next-bank native case is
also live. No bank/PHY admission flag is promoted.

### All-sample terminal-reader prototype measured; production reader retained

`native_terminal_blocks_300_v1.py` computes the same four-terminal voltage
span in bounded row blocks, without node or time exclusions. It resolves every
actual terminal and its own device limit, substitutes only literal ground, and
refuses missing/ambiguous maps, nonfinite samples and invalid limits. Three
checks passed in 0.439 s: exact six-pair envelope agreement across block sizes,
input immutability, DC/last-sample threshold handling, and invalid-input refusal.

A real completed-waveform comparison in
`native_terminal_block_benchmark_300_v1/99df59f7d8900fa6` exactly reproduces all
original terminal metrics and pass/fail flags for 2,056 MOS and all 20,015
samples, including DC/startup. The per-device scan took 5.539990 s and the
block scan 4.899911 s (recorded ratio 1.130631). The block scan ran second after
cache warming; this is a case-specific diagnostic, not a standardized speed
claim. The modest observed difference does not justify replacing the captured
production readers, and it does not establish the main full-closure validation
bottleneck. No solver, model, tolerance, native waveform or live producer was
changed. The prototype and benchmark are retained for reproducibility, with
all bank/PHY admission flags false. Log:
`build/native-terminal-block-benchmark-300-v1.log`.

### First actual-next-bank zero point passes independent verification

Early loading case 0 in
`tg2_next_bank_early_zero_pilot_300_v2/23dee609d6ca5e51` naturally completed
without execution error (native elapsed 2534.042 s). It contains two complete
native banks, both programmed to zero, at SS/40 °C/310 MHz/50% duty. The first
bank's artificial 20 fF capacitor is replaced by the actual second-bank input;
the second bank retains the 20 fF far load. All eight startup-inclusive events,
transistor terminals, separate controls and fixed supply checks pass.

| Measured property | First bank, actual next input | Second bank, 20 fF far load |
| --- | ---: | ---: |
| Maximum rising delay (ps) | 720.614827 | 716.041667 |
| Maximum falling delay (ps) | 769.239163 | 774.362096 |
| Fastest-quarter headroom (ps) | **+37.212450** | **+32.089517** |
| Rising history span (ps) | 2.023074 | 2.248569 |
| Falling history span (ps) | 0.002201 | 0.015564 |
| Maximum output period error (ps) | 2.021787 | 4.270356 |
| Maximum output slew (ps) | 197.534143 | 88.615882 |
| Maximum input slew (ps) | 100.035137 | 197.534143 |

The second bank is measured relative to actual OUT, not the ideal IN epoch.
The native supply error is 0 V. Worst terminal envelopes are 1.907318426 V
(first) and 1.907316928 V (second), each below its 1.95 V limit. Relative to the
single-bank artificial-load result, the real next input consumes 19.222306 ps
of the first bank's falling-edge quarter margin and increases its output slew
substantially, while preserving the 250 ps downstream domain at this point.

Independent receipt
`tg2_loaded_native_replay_300_v1/5a13c2fa7eabefdd` completed and exactly
reproduced the original complete measurement plus independent two-bank timing,
terminal envelope, separate control/gate settling and supply checks. It covers
all 4,112 MOS, 172 controls and 532 programming gates. Log:
`build/tg2-loaded-zero-native-replay-300-v1.log`.

This is one passing centered loaded point. The next-fine31 case is live; both
fresh loaded numerical pairs, source unshifted parity, the 20–250 ps entry
slew domain and duty extremes, complete four-section/fanout loading, common
wire RC, dense legal codes, PVT and PHY release remain open. The second bank's
far capacitor does not establish the load of a third bank. Source coverage and
source active numerical-parity qualification flags remain false in this early
experiment, and no bank/PHY admission is inferred.

### Explicit 10–90% entry reference and boundary metrology

The verified loaded zero point uses a 100 ps nominal entry slew and leaves
32.089517 ps of second-stage quarter margin. It does not cover the specified
20–250 ps entry range or 40/60% duty boundaries. New
`bank_entry_waveform_300_v1.py` defines eight linear pulses with explicit
10/50/90% breakpoints, 50% rising epochs at 2.1 ns plus each requested period,
and exact threshold-to-threshold duty. Its 20/250 ps settings mean **10–90%**,
not the full 0–100% ramp duration. This distinction must be retained when using
older source tests whose PULSE rise/fall argument denotes the full ramp.

`two_bank_entry_measure_300_v1.py` retains the full existing two-bank metrics
and verifies the ideal IN samples against this declared piecewise-linear
source within 1 nV, with no sample gap above the declared 2 ps step (apart from
floating-point roundoff). At the exactly 250 ps boundary, subtraction of
floating-point crossing epochs can exceed 250 by a few ULPs. A **1e-6 ps**
comparison allowance applies only to that verified ideal entry's slew-domain
predicate. All measured slew values remain unrounded and unclipped. Native
downstream input, every output slew, quarter budget, period/history, terminal
stress, control and supply comparisons retain their original limits. A changed
source waveform or a 250.01 ps measured entry is refused. Independent
reconstruction evaluates clipped linear ramps separately from the producer's
PWL interpolation.

Five fixture/reference checks passed in 2.219 s, including all eight source
events, independent voltage reconstruction, unchanged complete 4,112-MOS maps,
runner translation, preservation of every centered/unshifted pair, and
requirement for all domain settings and references. Three binary-reader checks
passed in 1.326 s: both implementations agree on every metric at all four
boundary settings, a changed source voltage is rejected, and the registry
refuses pending/unsupported cases. These synthetic fixtures test metrology and
wiring only; no entry-boundary native circuit result exists yet. Existing live
producers, waveforms and measurement code were not modified.

### Actual two-bank entry-domain experiment prepared for capture

`probe_tg2_entry_domain_300_v1.py` requires the passing independently replayed
actual-loaded zero point before constructing new diagnostics. It uses the exact
same bank library and two complete zero-programmed native banks, with the first
output driving the actual second input and 20 fF remaining only at the far end.
Four centered cases cover (250 ps,60%), (250 ps,40%), (20 ps,60%), (20 ps,40%)
at SS/40 °C/310 MHz; four fresh unshifted cases repeat those exact settings.
Every case retains 40 ns and all eight startup-inclusive events. All four
bidirectional all-voltage/DC/crossing comparisons and all eight physical point
screens are required for the diagnostic's aggregate pass.

The original DC-zero/4 ps ramp to a 1 mA external bench load remains explicit
and excluded from chip power. One priority-two worker uses the existing global
six-slot aging dispatcher. Source full-bank coverage and source active
numerical-parity qualification remain false in the identity and final report;
these entry diagnostics cannot substitute for those source gates or for the
four-section/fanout, common-RC, dense-code, 15-PVT and PHY requirements.
`replay_tg2_loaded_native_300_v2.py` registers this eight-case producer while
retaining explicit support for the earlier loaded-bank producers. It reproduces
each original result and independently reconstructs the entry waveform and
native two-bank metrics. The immutable V1 reader and all running producers are
retained.

### Entry-domain capture passed and controller launched

Preparation and full captured-input validation completed successfully for
`tg2_entry_domain_pilot_300_v1/b98f2003774d19d6`. Its eight tasks are centered
250 ps/60%, 250 ps/40%, 20 ps/60%, 20 ps/40%, followed by four exact unshifted
repeats. Every case uses two complete zero-programmed native banks (4,112 MOS),
the same qualified candidate library and full actual observation maps, fixed
supplies, SS/40 °C/310 MHz, and all eight events over 40 ns. Source coverage,
source active numerical parity, shared routing and PHY qualification remain
false.

The controller was launched under user unit
`openlvds-tg2-entry-domain-300-v1`, invocation
`6d5b797b6b1f49c2af7028dcbb2d9512`; it was confirmed active in initial input
verification. It uses one priority-two worker under the unchanged six-slot
aging dispatcher. No existing solver was stopped or changed. Log:
`build/tg2-entry-domain-300-v1.log`. No native boundary-case result exists at
launch. This capture defines the entry transition in 10–90% units and validates
its declared source; it does not retrofit that interpretation or a numerical
allowance into any older captured producer.

### Maximum-fine downstream loading independently reproduced

Receipt `tg2_loaded_native_replay_300_v1/f7a87a45948cd4a3` is complete
and passing for early-loading case 1: first bank at zero code, actual second
bank at fine code 31, SS/40 °C/310 MHz, 100 ps entry and 50% duty. Both the
original remeasurement and separate independent reader reproduce every saved
metric across 4,112 MOS, 172 controls and 532 programming gates. No parameters
changed. First-bank quarter headroom is 37.214261 ps; maximum output slew is
197.534103 ps. The second bank's rise/fall history spans are 1.906520/0.038515 ps,
maximum period error 3.920162 ps and maximum output slew 154.915795 ps.

Together with the independently replayed downstream-zero case, this verifies
two centered loading points. The fresh unshifted downstream-zero simulation is
now running; both numerical reference pairs remain required. The entry-domain
controller remains active behind the six-slot dispatcher, with no completed
boundary result. These receipts do not admit the whole bank or PHY: source
coverage/parity, four-section loading and fanout, shared routing, dense codes,
15-PVT calibration and full-link verification remain open. Preserve the
coarse-chain tail termination when investigating output loading; it terminates
tap 15 and is not an output load.

### Four-section native fixture construction

`four_bank_fixture_300_v1.py` constructs the next chain-loading experiment
from an untouched single-bank fixture and its exact native library. Three
complete independently coded banks replace the original output capacitor;
each intermediate output drives the actual following input, with 20 fF only
at the fourth output. Each added bank's flattened transistor map is checked
against a separate native-library traversal. All terminal, internal control
and programming-gate observations are retained, and canonical saved vectors
are unique and accepted by the actual binary runner's translation preflight.
The coarse-chain tail terminations and original source are preserved.

Two tests passed against the captured TG2 library: 8,224 distinct MOS devices,
344 controls and 1,064 programming gates; sequential input/output wiring;
independent mixed downstream codes; complete terminal probes; and identical
centered/unshifted decks except for the declared external bench-current card.
An already loaded fixture and an incorrect section count are refused. This
is fixture construction only: no four-section native simulation or timing
result exists. Detector/DCC fanout, common routing, reference parity and
calibrated phase accuracy remain separate required gates.

`four_bank_native_measure_300_v1.py` now provides the corresponding full-trace
reader. Every downstream section uses its actual preceding output as the
timing reference; the first section alone checks the ideal source epoch.
All sections retain their own code, quarter-cycle check at zero code,
20 ps period/history limits, 250 ps input/output slew limits, every native
terminal sample, settled internal controls and full-trace external controls.
Supply checks and the native DC sample are mandatory. Missing section maps,
duplicate device identities and inconsistent section wiring/codes are refused.
The reader can use the existing separately implemented threshold and electrical
algorithms for independent reconstruction. It never treats transport success
as calibrated quarter/half phase accuracy or detector/DCC fanout qualification.

Synthetic complete binary tests exercise all four sections and both reader
implementations, including a failing third-section delay, a failing third-bank
control and a fourth-bank startup terminal peak. These are reader checks only;
native four-section simulations and fresh numerical-reference comparisons have
not yet been performed.

### Four-section diagnostic controller and fresh-reference gate

`probe_tg2_four_bank_300_v1.py` captures two complete zero-code four-section
cases at SS/40 °C/310 MHz, 100 ps entry, 50% duty and 40 ns: centered first,
then an exact fresh unshifted reference. Preparation requires the existing
passing independent actual two-bank zero receipt and binds its evidence,
the native library, code, model inputs and reconstructed observation maps.
One priority-two worker uses the unchanged global dispatcher. Partial runs
cannot be overwritten or restarted by this controller.

`four_bank_numerical_pair_300_v1.py` checks both directions of all saved-voltage
interpolation (2 mV), every DC voltage (1 nV), eight rise/fall crossings at all
five clock nodes (0.25 ps), and every section's timing/electrical pass/fail
classification. Both physical point screens and this fresh pair are mandatory.
Source coverage/parity, detector/DCC fanout, shared routing and PHY flags remain
false. This experiment diagnoses serial loading; it is not a calibrated DLL.

Three tests passed in 8.277 s, covering actual 8,224-MOS fixture reconstruction,
fresh centered/unshifted symmetry, complete synthetic binary pair comparison,
preservation of fourth-section failure classifications, and refusal of a
missing case or native execution failure. The first test invocation exceeded
Apptainer's 64 MB `/tmp` while writing two synthetic traces; the passing run
used `TMPDIR=/work/OpenLVDS/build/test-tmp-four-section`, without changing any
scientific setting or limit. Actual captured-input hashing is in progress via
`build/tg2-four-section-prepare-300-v1.log`; no four-section native result exists.

`replay_tg2_four_bank_native_300_v1.py` separately consumes explicit completed
four-section cases. It validates producer closure, original task identity and
every native witness hash, reproduces the complete original result exactly,
then repeats all timing, terminal and control measurements with the independent
algorithms. Failed physical points remain failed even if their measurements
reproduce. The receipt binds all analysis inputs and rechecks their hashes
after analysis; whole-bank, fanout and PHY admission remain false. Two preflight
tests pass, requiring registered producers and unique case IDs, and refusing
pending cases before expensive provenance hashing. No actual four-section
replay receipt exists yet. The first native entry-domain boundary case has
started under its existing controller while four-section capture continues.

### Four-section capture validated and controller active

Capture `tg2_four_section_zero_pilot_300_v1/4bf88d17231064da` completed full
input hashing and reconstruction successfully. User unit
`openlvds-tg2-four-section-300-v1` was launched with invocation
`91eedc2f3cd04a7db2106d6d9bf1dcca` and confirmed active (initial main PID
2407741). Log: `build/tg2-four-section-300-v1.log`. The two 8,224-MOS cases
retain all eight startup-inclusive events and fresh centered/unshifted control.
The controller first validates captured inputs, then acquires one priority-two
lease under the unchanged six-slot dispatcher. No four-section native result
exists at launch and no running solver was interrupted.

The replay suite now passes four tests in 8.946 s. Added integration coverage
runs the complete original and independent measurement algorithms on synthetic
binary witnesses, verifies that a late-section physical failure remains false
in a successfully reproduced receipt, and rejects a modified raw witness by
hash before either reader runs. Only the producer-binding boundary is replaced
for these synthetic tests; actual producer closure was checked during capture.
Temporary binary fixtures use workspace storage because of the container's
64 MB `/tmp` limit. Native four-section replay, fresh numerical parity, fanout,
shared routing, calibrated phase accuracy and full PHY remain required.

### Actual source-DCC fanout fixture

`dcc_chain_fanout_300_v1.py` prepares the next loading topology by attaching
two complete clock-aware source DCCs to the four-section chain. Intended
phase-pair connections are IN/B1_OUT (0/180 degrees) and OUT/B2_OUT (90/270
degrees); B3_OUT remains the full-period endpoint. Those phase names describe
the intended calibrated roles, not achieved timing at zero code. Both DCC
outputs have their own 20 fF loads. The original far-chain 20 fF load remains,
and intermediate inputs retain their actual downstream bank loads. A common
ideal reset is held low to 1 ns and released over 20 ps, before the first
source event. Detector inputs and shared wire RC are still absent.

The fixture uses the captured source DCC cells and hold1 topology from
`dcc_source_300_v1/1a4f4e8eabb896e4`; it does not claim admission from the
unfinished source matrix. A namespace adapter changes subcircuit names only
to avoid collisions with bank standard cells. All primitive models, numeric
parameters, nodes and instance order are preserved. A separate mapper handles
the source library's explicit SKY130 polysilicon resistor leaves, retaining
their voltage nodes as well as every MOS terminal; existing bank mappers and
captured simulation libraries are unchanged.

Three tests pass in 0.342 s against the actual captured libraries: both phase
connections and all observation nodes, runner translation with unique saved
vectors, namespace preservation of every primitive and parameter, identical
flattened native devices before/after renaming, and refusal of unknown leaves,
changed ports or repeated attachment. This is fixture preparation only; no
combined DCC/four-section simulation, calibrated phase or fanout timing result
exists. The live serial-chain experiment remains byte-preserved and active.

`dcc_chain_materials_300_v1.py` now captures and reconstructs both combined
loading decks, using the exact validated chain and source-DCC libraries. It
binds transitive code/model evidence and static parent fixtures without binding
either active campaign's changing state. Library bytes, namespace conversion,
complete observations, both fresh-reference cases and every captured hash are
checked again before a `prepared_unqualified` record can be written. Source
chain/DCC qualification, detector presence, shared routing and PHY flags are
explicitly false; the material preparation performs zero simulations.

The actual-library fixture test passes in 0.396 s. It checks centered/unshifted
symmetry, unchanged original four-bank maps, both actual DCC connections and
globally distinct device identities. Captured-input validation has started;
log `build/dcc-four-section-materials-300-v1.log`. Combined simulation and its
startup-inclusive event/terminal metrology remain to be implemented and run.

`dcc_chain_measure_300_v1.py` adds combined native transport metrology. It
retains the existing four-section checks, all DCC transistor terminal samples
and passive-node observations, and verifies the declared ideal reset waveform
within 1 nV. Both DCCs must start high under reset and produce all sixteen
alternating output transitions, one after each measured source rising event
and before the following event. Output swing, 250 ps slew and 20 ps period
limits apply from the first event. Missing startup events, colliding maps and
changed phase connections cannot pass. Mean high/low half-cycle errors are
reported separately with the 50 ps limit; transport success cannot imply phase
accuracy, and all calibration/detector/routing/PHY qualification flags stay
false. Internal pulse-generator hold timing and independent combined replay
remain additional required checks.

Three tests pass in 6.681 s using workspace temporary storage. Complete
synthetic binary traces check all four sections and both DCCs together, with
startup terminal overstress and a reset-source discrepancy causing failures.
Event tests retain all sixteen checks and demonstrate that valid transport can
still fail mean-half-cycle accuracy; missing initial events are rejected.
These are measurement tests, not combined native circuit results. Captured
combined material validation remains active and no combined simulation has
been launched.

### Combined materials validated; internal pulse integrity added

Material capture `dcc_four_section_materials_300_v1/30fcd6cff3a7457d`
completed validation and is `prepared_unqualified`, with zero simulations.
Its two fresh-reference decks include 8,224 bank MOS and 272 DCC MOS, plus
the four source tie-cell resistor leaves. All eight internal pulse/reset nodes
required by the new reader are present in the captured native observations.
No source-chain or DCC timing admission is implied by preparation.

`dcc_chain_measure_300_v2.py` retains V1 and adds both pulse generators in
both DCCs to the combined transport gate. All eight rising/falling input and
internal pulse events must be present. Each pulse must rise and end after its
own source edge and before that clock falls, without retriggering before the
next edge. Reset must be high over the 40–20 ps pre-edge interval and low
through a nonempty interval from 20 ps after pulse end to 20 ps before the
source clock falls. Missing intervals cannot pass vacuously. First events are
included, and every pulse-generator failure rejects combined transport even
when final output transitions look correct. Phase/routing/PHY flags stay false.

Three tests pass in 4.656 s: complete startup-inclusive internal histories,
first-event retrigger/early release/unarmed failures, and complete synthetic
binary analysis showing an internal reset fault overrides unchanged correct
output transport. These remain reader tests; the combined native simulation,
fresh numerical pair and independent replay are still outstanding.

### Combined native controller and fresh-reference comparison

`probe_dcc_chain_300_v1.py` captures the validated combined materials and V2
internal-pulse metrology as a new two-case native experiment. Centered and
fresh unshifted cases retain all devices, observations and 40 ns stimuli;
only captured library paths change. One priority-two worker uses the existing
six-slot dispatcher. It refuses any prior/partial execution and preserves
every native witness and failed point. Both physical transport screens and
the numerical reference must pass the aggregate diagnostic gate.

The fresh comparison uses bidirectional all-voltage interpolation (2 mV),
all DC voltages (1 nV), chain/DCC/internal pulse crossings (0.25 ps, eight
rise/fall events at every checked node), and every boolean classification in
the full combined result, including each internal hold/rearm event. A numerical
agreement cannot erase a physical failure. Calibration, detector fanout,
shared routing and PHY qualification remain false regardless of transport.

Two tests pass in 9.374 s: exact material preservation apart from include paths,
fresh-reference symmetry, complete synthetic binary comparison, rejection of a
changed internal pulse classification, failed transport, missing case and
native error. Experiment preparation is running; log
`build/dcc-four-section-prepare-300-v1.log`. No combined native result exists.

`dcc_independent_events_300_v1.py` adds a separately implemented vectorized
threshold/event witness. It reconstructs source ordering, alternating output
events, every latency, 10/50/90% swing and slew, high/low widths, mean half-cycle
errors and period errors without calling the producer's event algorithm. Two
tests pass in 0.140 s and compare every result field for balanced and unbalanced
phases, missing startup events, incorrect initial output and transitions after
the next source event. Independent pulse-hold and complete combined replay
remain to be added; this helper alone is not an independent native receipt.

The older medium-pre and P40/N32 unshifted reference simulations have now
finished with error-free native point records. Medium retains its failing
physical screen; P40/N32's unshifted fine-60 point passes, while that family's
known endpoint coverage failure remains unchanged. Independent fresh-pair
replays were started for both completed references using the retained reader,
with logs `build/medium-active-pair-independent-300-v1.log` and
`build/p40n32-active-pair-independent-300-v1.log`. No replay result or family
admission is asserted while those analyses are active.

`dcc_independent_pulses_300_v1.py` reconstructs internal pulse hold/rearm
with separate vectorized threshold crossings and indexed interval searches.
Two tests pass in 0.059 s, comparing all metrics for valid histories,
first-event retrigger/early-release/unarmed faults, and an explicitly empty
held interval. Empty intervals remain failures.

`dcc_chain_independent_measure_300_v1.py` combines the independent event/pulse
algorithms with independent bank timing/electrical reconstruction and explicit
six-pair terminal differences for each DCC MOS. It independently reconstructs
the reset reference and complete combined result without calling either
producer's DCC measurement function. A full synthetic binary test passes in
5.042 s: every result field agrees for valid transport and an internal reset
fault whose output waveform remains unchanged. Both readers reject that fault.
This establishes reader agreement on the tested fixtures; actual completed
combined native receipts, fresh-reference parity and full qualification remain
outstanding. All captured experiment files and active solvers are unchanged.

`replay_dcc_chain_native_300_v1.py` now records independently reproduced
completed combined native points. Explicit unique case IDs and a registered
producer are required; pending cases are refused before large input hashing.
It binds both native libraries, every witness and analysis source, exactly
remeasures the original result, compares the complete independent result and
rechecks all input hashes afterward. Receipts preserve physical failures and
keep bank/fanout/PHY admission false. Two preflight tests pass in 0.002 s.
The complete reader algorithms were tested separately on binary fixtures;
no combined native replay receipt exists yet.

The medium-pre fresh-pair receipt
`distributed_family_active_pair_300_v1/7a92865c6008483c` is now complete and
passing for numerical parity. Original and independent metrics reproduce for
both native cases. Maximum all-vector difference is 0.310641 mV across 6,670
voltage vectors and 36,375 reference samples; maximum crossing difference is
0.000528336 ps, and all gate classifications agree. Its physical fine-history
failure is preserved and whole-bank/PHY admission remains false. The P40/N32
pair replay and combined experiment capture validation are still active.

### Combined capture dispatched; P40/N32 numerical reference verified

Capture `dcc_four_section_pilot_300_v1/7c2674e516231ffb` completed full
validation. The controller was launched as user unit
`openlvds-dcc-four-section-300-v1`, invocation
`824d41f36c4441fbbbf9bfcb8e720d2c`, and confirmed active (initial main PID
2411091). Log: `build/dcc-four-section-300-v1.log`. Both cases retain all
8,496 MOS, complete observations and all startup events. One priority-two
worker uses the unchanged six-slot dispatcher after initial input validation.
No existing job was preempted and no combined native result exists at launch.

The combined replay suite now passes three tests in 11.865 s. Added integration
coverage creates a complete receipt from synthetic binary data with both real
measurement readers, repeats it with a physical internal-reset failure and
preserves that failure, then changes the binary witness and verifies rejection
before remeasurement. Only the synthetic producer-binding boundary is replaced;
receipt hashing and both scientific algorithms remain active. These synthetic
receipts do not qualify the actual combined circuit.

P40/N32 reference receipt
`distributed_family_active_pair_300_v1/217ad19334496545` is complete and
passing for independent reproduction and numerical parity. Across 6,734
voltage vectors, forward/reverse maximum differences are 0.187635/0.137324 mV;
DC error is zero and maximum crossing difference is 0.000762805 ps. Every gate
classification agrees. Its known endpoint-coverage failure remains unchanged;
neither numerical parity nor the passing fine-60 point admits this family or
the PHY. The newer TG2 candidate retains its separate pending reference gate.

### Direct four-section phase diagnostics

`four_bank_phase_measure_300_v1.py` reports all startup-inclusive rise/fall
phases relative to the original input without modulo reduction. It records
each section's measured delay, per-event section spread, errors at the
quarter/half/three-quarter/full-period taps and full-period closure error.
Observed 50 ps phase-grid and 20 ps closure predicates are separate from
transport, and calibration/PHY flags remain false even if both are observed.
Missing events and nonpositive section ordering cannot pass the phase grid.
This is a measurement helper; no actual phase-grid result exists yet.

Three tests pass in 0.147 s: exact quarter spacing, an incorrect intermediate
phase despite correct full-period closure, and missing startup/full-cycle alias
failures. The retained detector's completed 540-point source proof remains
historical source evidence; routing, physical matching and integration at the
new profile remain required. The serial-chain and combined controllers were
confirmed active, with neither producing a completed native point at this
observation. No captured experiment or active solver was modified.

`diagnose_four_section_phase_300_v1.py` now consumes explicit completed native
points from the serial or combined controller. It validates the original
producer, all witness hashes and the full captured-input closure, retains
native DC/startup samples, computes unwrapped phase errors and binds a new
diagnostic receipt to its complete analysis inputs. Original transport pass/fail
decisions are preserved separately, and input hashes are rechecked after
analysis. Pending cases are refused before expensive hashing; changed binary
witnesses are rejected before phase measurement.

Two tests pass in 3.990 s, including a complete synthetic binary receipt whose
transport passes but phase grid fails, and changed-witness rejection. Actual
producer validation is replaced only at the synthetic fixture boundary.
No actual native phase receipt exists yet. The dispatcher has granted the
serial four-section case 0 its existing priority-two lease; initial guarded
validation precedes solver launch. The combined controller remains active
under the same dispatcher and no running job was changed.

### Combined verification-tool regression

At source revision `115d1df`, all 37 tests across the fifteen new chain/DCC
fixture, material, metrology, independent-reader, replay/controller and phase
diagnostic test modules pass together in one Python process (71.259 s).
Log: `build/chain-dcc-integrated-tests-300-v1.log`. The run uses the existing
exact-RC Python environment and workspace `TMPDIR`; it invokes no simulator.
This checks cross-module import and temporary patch restoration in addition
to the individually recorded tests. It is software/fixture verification only,
not native circuit, physical or PHY evidence.

The serial and combined four-section solver PIDs were independently confirmed
live after the regression. The entry-boundary trace advanced to 26.235895 ns
of its required 40 ns during this observation; no partial trace was promoted
to a timing or electrical result. All captured model, solver and stimulus bytes
remain unchanged, and all six SPICE slots remain occupied by existing jobs.

### First native entry-boundary point complete

Case 0 of `tg2_entry_domain_pilot_300_v1/b98f2003774d19d6` completed its
entire 40 ns trace without a numerical error and passes the original two-bank
screen: SS/40 °C/310 MHz, 250 ps ideal-entry 10–90% slew, 60% duty, both banks
at zero code with actual next-bank input loading. All eight startup-inclusive
events and the full native electrical observations are retained.

First-bank quarter headroom is **6.206228 ps**, maximum output slew
197.525181 ps, rise/fall delay spans 3.921687/0.015327 ps and maximum period
error 3.921566 ps. The second bank has **37.384497 ps** headroom, maximum
output slew 88.592703 ps, delay spans 4.673207/0.006801 ps and maximum period
error 8.594773 ps. The declared ideal entry retains its raw measured maximum
250.00000000000364 ps; only the previously documented 1e-6 ps comparison
allowance on the independently verified ideal-source boundary applies.
Downstream native slew and all other limits remain strict and unchanged.

Independent replay has started through the retained V2 reader; log
`build/tg2-entry-250ps-duty60-independent-300-v1.log`. No passing replay receipt
is asserted yet. The 6.21 ps first-bank margin is narrow: common routing and
additional fanout remain unqualified, as do the other boundary cases, fresh
unshifted references, all-PVT coverage, calibration and the PHY. The serial
and combined four-section simulations remain separate active experiments.

### Entry-boundary independent replay and stage localization

Receipt `tg2_loaded_native_replay_300_v2/0c774319d495dae9` is complete and
passing for entry case 0. Both the original full remeasurement and independent
reader reproduce the complete result, including 4,112 MOS, 172 controls and
532 programming gates. Parameters are unchanged, the source point passes and
whole-bank/PHY admission remains false. This independently confirms the
6.206228 ps first-bank headroom, without replacing the remaining domain points
or fresh numerical references.

An exploratory read-only stage comparison used the retained
`bank_stage_history_300_v2.stages` helper on the completed actual-loaded zero
reference and entry case 0. Every saved outer delay reproduces and stage sums
have zero residual. At the last falling edge:

| Stage | 100 ps / 50% reference (ps) | 250 ps / 60% entry (ps) | Change (ps) |
| --- | ---: | ---: | ---: |
| Input to selected node | 333.305196 | 369.592547 | +36.287351 |
| Selected to pre output | 243.441520 | 238.804002 | -4.637517 |
| Pre output to fine node | 111.090950 | 110.514225 | -0.576726 |
| Fine node to output | 81.400728 | 81.334612 | -0.066116 |

Log: `build/tg2-entry-stage-comparison-300-v2.log`. The preceding exploratory
invocation failed to locate the scripts directory and produced no measurement;
V2 explicitly supplies that import path. Neither command changes circuit bytes.
The observed added delay is concentrated before the selected node, making
input/selection-path experiments more relevant than another fine-stage change
for this specific margin. This is localization, not mechanism proof: source
shape, slew and duty all differ between the two points. A controlled comparison
and actual fanout/routing results are needed before selecting a circuit repair.

### Matched-source isolation fixtures

`bank_entry_waveform_300_v2.py` adds a declared 100 ps linear 10–90% entry
to the versioned reference implementation. Existing 20/250 ps PWL points and
source cards remain identical. `two_bank_entry_measure_300_v2.py` applies the
same full waveform verification and original physical limits, retaining the
independent reader. Running V1 sources and readers are unchanged.

`matched_entry_materials_300_v1.py` constructs four additional diagnostic
fixtures: 100 ps linear entry at 50% and 60% duty, followed by fresh unshifted
references for both. Compared with the completed 250 ps/60% point, 100 ps/60%
isolates entry slew within the same linear source family. The two 100 ps cases
isolate duty, while the prior 100 ps/50% tanh fixture provides a separate shape
comparison. All cases retain SS/40 °C/310 MHz, actual two-bank zero loading,
40 ns, eight startup events and all 4,112 MOS maps. Only the known ideal source
and declared external bench-current reference differ. No extra simulation has
been launched and these fixtures are not a replacement for boundary coverage.

Two source/fixture tests pass in 1.823 s, preserving every old boundary source,
independent 100 ps reconstruction, complete maps and both reference pairs.
A complete binary-reader test passes in 1.905 s: original/independent metrics
agree at 100 ps, and a changed source voltage rejects the point. Captured
materials, native runs and the controlled stage comparison remain outstanding.

`probe_matched_entry_300_v1.py` captures and runs those four matched-source
cases under one priority-two worker and the existing six-slot dispatcher.
Preparation requires both the original independently verified actual-loaded
zero point and the exact passing independent 250 ps/60% entry receipt. All
proof inputs, new V2 source/reader bytes, circuit libraries and reconstructed
fixtures are bound to the capture. Its aggregate gate requires all four point
screens and both fresh bidirectional numerical pairs. It keeps source
coverage/parity and PHY qualification false and refuses partial-run overwrite.

Two controller tests pass, requiring exact 100 ps/50–60% coverage, both fresh
references, unchanged pair specifications and preservation of physical failures.
Capture preparation has started with log
`build/matched-entry-prepare-300-v1.log`; no matched-source native case has run.
The existing simulations and captured V1 implementations are unchanged.

`replay_tg2_loaded_native_300_v3.py` adds explicit matched-source support while
retaining the strict/early loaded and original entry-domain producers. Matched
cases use their own task specifications and V2 source metrology for both
original and independent reconstruction. Complete native witness/input hashes
are checked before and after analysis; failed points stay failed and all
admission flags remain false. Existing V1/V2 readers and captured producers
are unchanged.

Three tests pass in 7.814 s: exact registry/case preflight, refusal of pending
data before hashing, and complete synthetic 100 ps binary receipts through
both real readers. The binary test preserves a changed-source physical failure,
checks that task specifications are used, and rejects a subsequently changed
raw witness. Only the synthetic producer-binding boundary is replaced. No
actual matched-source native result or replay receipt exists yet; capture
validation remains active.

### Matched-source capture validated and dispatched

Capture `matched_entry_pilot_300_v1/c852a81c96f1e17c` completed full input
validation and fixture reconstruction. The four cases are 100 ps linear entry
at 50%/60% duty, followed by the corresponding fresh unshifted references,
with the unchanged actual two-bank circuit and 4,112 MOS observations.
The controller was launched as user unit `openlvds-matched-entry-300-v1`,
invocation `3dc1a6f7ccdf4ae19ccddaa0590c058e`, and confirmed active (initial
main PID 2414840). Log: `build/matched-entry-300-v1.log`.

It validates captured inputs before acquiring a single priority-two lease in
the existing six-slot dispatcher. No existing native job was preempted. No
matched-source native point or independent receipt exists at dispatch; the
controlled delay comparison and all previous source, routing, calibration and
PHY gates remain open. The two four-section solvers were separately confirmed
live throughout capture validation and were not changed or restarted.

### Combined DCC/chain startup convergence failure

Case 0 of `dcc_four_section_pilot_300_v1/7c2674e516231ffb` terminated with
`TRAN: Timestep too small` at 4.10937e-14 s (0.041094 ps), reporting trouble
with `bin#branch`; final attempted timestep was 2.5e-24 s. Total reported
elapsed/analysis times are 3379.332/194.053 s. The original failed files and
error record are preserved. No physical timing result exists for this case.
The controller remains active for its original next task; healthy jobs were
not stopped or restarted.

The failure precedes every clock edge (first at 2.1 ns), reset release (1 ns)
and the existing supply bench-current ramp (starts at 2 ps). A source-branch
convergence issue is therefore worth testing, but the reported trouble node
alone does not prove the mechanism or a DCC functional fault.

`input_current_origin_300_v1.py` prepares a separate diagnostic by adding only
`I_BENCH_INPUT_CENTER IN 0 DC 0 PWL(0 0 2p 1m 40n 1m)` at the ideal input.
It leaves BIN's voltage expression, every model/device, the existing supply
card and the complete 40 ns stimulus unchanged. It refuses current feedback,
duplicate attachment and a shortened fixture, then checks actual runner
translation. The new external load's current/power must be excluded from chip
power; it is not a physical input-driver change. DC-zero construction and
ideal-source reasoning do not substitute for native numerical parity.

Two tests pass in 0.415 s against actual two-bank and combined decks, verifying
exact single-card insertion and refusal of current feedback/incomplete traces.
No diagnostic simulation has been launched and no convergence fix is claimed.
Full native voltage/DC/crossing parity and all original gates remain required;
the failed combined point and every source/physical/PHY qualification flag stay
unqualified. Serial-chain and entry-boundary simulations continue unchanged.

`probe_input_current_origin_300_v1.py` prepares a bounded native validation
against the complete independently verified actual two-bank zero reference.
Only the new DC-zero input-current card and library include path change.
Before simulation the original result must reproduce. The trial then requires
agreement of both full native readers, bidirectional all-voltage error <=2 mV,
DC error <=1 nV, all eight input/intermediate/output crossings <=0.25 ps, and
every original gate classification unchanged. No samples or observations are
discarded. One priority-two worker uses the existing dispatcher and partial
execution cannot be overwritten.

Even a pass validates only this exact completed reference case; the controller
explicitly leaves the combined circuit and PHY unadmitted. Input-bench current
and power are excluded from chip power, and no solver tolerance or source
voltage expression changes. Two tests pass in 3.712 s, checking exact native
deck preservation and complete synthetic binary parity with rejection of a
changed DC sample or electrical classification. Capture preparation is running;
log `build/input-current-origin-prepare-300-v1.log`. No new origin trial has
executed yet, and the combined startup failure remains unresolved.

### Failed-prefix electrical inspection

The aborted combined raw file declares zero points but contains six complete
stored rows from t=0 through 4.109375e-14 s. It remains invalid for normal
native trace verification. A separate read-only inspection of all stored rows
and all 8,496 MOS found a maximum DC terminal span of 1.8 V, zero prefix stress
violations and a maximum prefix span about 1.8000000000000007 V. DC VDD/IN/reset
are 1.8/0/0 V; both DCC outputs are 1.7999999914095635 V, as expected under reset.
Log: `build/dcc-four-section-failed-prefix-inspection-300-v2.log`.

This finds no obvious DC voltage/stress anomaly in the available failed prefix;
it does not establish the convergence mechanism or transient correctness.
The initial inspection refused the zero-point header rather than treating it
as a complete trace. Normal native verifiers and all 40 ns requirements remain
unchanged.

`inspect_failed_dcc_prefix_300_v1.py` makes the forensic read reproducible. It
requires the original terminal numerical failure, validates captured producer
and witness hashes, reads every complete stored record without trimming, and
limits its report to the pre-clock failed prefix. Its result explicitly sets
`complete_qualification_trace=false` and `qualified_phy=false`. Two tests pass,
rejecting complete-trace headers, partial records and nonfinite samples.
The bound inspection is running separately with log
`build/dcc-four-section-failed-prefix-bound-inspection-300-v1.log`; input-origin
capture validation and healthy native jobs continue unchanged.

### Input-current reference experiment dispatched

Capture `input_current_origin_pilot_300_v1/9c9574a3140858b3` passed full
input validation and fixture reconstruction. User unit
`openlvds-input-current-origin-300-v1` was launched with invocation
`e0e1092a575244a7a78be9b36b0c1789` and confirmed active (initial main PID
2418020). Log: `build/input-current-origin-300-v1.log`. It remeasures the
original complete two-bank reference before executing the new full 40 ns
trial, using one priority-two worker under the unchanged six-slot dispatcher.
No existing solver was stopped or preempted. No numerical-origin pass or
combined-circuit recovery is claimed at launch.

The bound failed-prefix inspection also completed successfully. After original
producer and witness-hash validation it reproduced the six stored rows,
8,496 MOS, 1.8 V maximum DC span, zero prefix stress violations and the original
reset/output levels. `complete_qualification_trace` and `qualified_phy` remain
false. The failed combined point remains failed, and its next original task
and the healthy serial/entry-boundary runs remain under their own controllers.

### Full 250 ps / 40% entry point complete

Case 1 of `tg2_entry_domain_pilot_300_v1/b98f2003774d19d6` completed all
40 ns without a numerical error and passes the original native two-bank screen
at SS/40 °C/310 MHz, 250 ps linear 10–90% entry and 40% duty. All startup events,
terminal samples, controls and original limits are retained.

First-bank quarter headroom is **6.378762 ps**, maximum output slew
197.525181 ps, rise/fall delay spans 4.582951/0.004242 ps and maximum period
error 4.582951 ps. The second bank has **37.569986 ps** headroom, maximum
output slew 88.592028 ps, delay spans 5.790409/0.020610 ps and maximum period
error 10.372769 ps. Both 250 ps duty extremes now pass their original point
screens with similarly narrow first-bank headroom; this does not establish
fanout, routing, all-PVT or full-domain admission.

Independent V2 replay was started for case 1; log
`build/tg2-entry-250ps-duty40-independent-300-v1.log`. No passing receipt is
asserted yet. The 20 ps boundary points, fresh unshifted references, source
coverage, calibration and full PHY remain open. All other running jobs and
captured circuit/model bytes are unchanged.

Independent receipt `tg2_loaded_native_replay_300_v2/99e7e94c5dd6b1a5`
is complete and passing for entry case 1. The original full result reproduces
exactly, and the independent reader reproduces timing, all 4,112 MOS terminal
checks, 172 controls and 532 programming gates. Parameters are unchanged and
the source point passes; whole-bank/PHY admission remains false.

Both 250 ps entry duty extremes now have independent passing point receipts:
6.206228 ps first-bank quarter headroom at 60% and 6.378762 ps at 40%.
These remain narrow-margin actual two-bank points, without fresh unshifted
parity, shared routing or detector/DCC loading. The 20 ps cases, matched-source
isolation, all-PVT/code coverage, calibration and full-link release requirements
are unchanged. The input-current diagnostic has no completed result yet.

### Four-section observation defect and immutable correction

The first centered four-section V1 simulation completed its full 40 ns
transient in 6,981.504 s, but metrology correctly rejected it with missing
requested native vectors. B1_OUT, B2_OUT and B3_OUT were omitted from the
saved observation list. These public ports can connect through extracted R/C
without appearing as MOS terminals; complete terminal coverage did not imply
complete measurement coverage. This is a fixture defect, not a measured
physical timing failure or pass. No missing waveform is reconstructed.

Only the pending V1 serial controller was stopped, after verifying that its
second native case had not started. The original result/state files remain
unchanged; `controller_stop.json` in artifact
`tg2_four_section_zero_pilot_300_v1/4bf88d17231064da` records the stop and
`native_process_stopped:false`. The already-running combined V1 case remains
untouched; its fixture is also missing B3_OUT.

New immutable V2 fixtures explicitly save public phase ports. The actual
serial fixture adds exactly three vectors; the actual combined DCC fixture
adds exactly B3_OUT. All non-observation circuit statements and observation
maps remain identical. New contract tests obtain vector requirements from
the real measurement readers (including all three combined reader layers)
and verify that the translated native deck saves every requested vector.
Both fixture tests pass. Corrected serial capture and combined materials
preparation are in progress; neither is a qualification result. Numerical
parity, physical timing, full PVT/code coverage, routing and PHY requirements
are unchanged.

Corrected-fixture consumers are versioned as well. Independent four-section
replay V2 explicitly registers the old and corrected serial producers, keeps
full witness binding, and repeats both original and independent measurement
without changing physical failure classifications. Four tests pass, including
complete binary pass/failure preservation, witness tampering, registry and
pending-case rejection. Captured phase diagnostic V2 accepts the corrected
producer and preserves unwrapped phase measurement and original transport
classification; its two binary receipt/tampering tests pass. The existing V1
consumers and captured/running experiment dependencies remain unchanged.

Corrected serial capture completed full validation as
`tg2_four_section_zero_pilot_300_v2/ab47d513bae05d29`. It is dispatched by
`openlvds-tg2-four-section-300-v2`, invocation
`5c7f8cd0f6e4402384a4fa1a1296fd14` (initial host MainPID 2422562).
The controller retains one priority-2 native worker under the global six-slot
lease mechanism, and requires both fresh centered/unshifted cases and full
numerical parity. Dispatch is not a completed simulation or qualification.
The corrected combined materials preparation remains separate and runs no
simulation; further combined recovery runs await the input-current-origin
reference experiment. Existing native jobs remain untouched.

### Independent input-current convergence-reference consumer

Corrected combined materials preparation completed as
`dcc_four_section_materials_300_v2/64b5f8c41cb4eddd`; it remains a
`prepared_unqualified`, zero-simulation artifact. Existing combined V1 native
execution is unchanged. The corrected serial V2 controller remains active.

`replay_input_current_origin_300_v1.py` independently consumes the completed
input-current-origin reference experiment. It requires terminal receipts and
an error-free complete native point, binds all producer inputs and native
witnesses, repeats the original baseline and candidate measurements, repeats
the independent candidate measurement and full bidirectional numerical
comparison, and checks all hashes again after analysis. An unsuccessful
numerical comparison remains unsuccessful in the replay receipt. Both
combined-circuit admission and PHY qualification remain false, even when the
single-reference comparison passes; each new circuit still requires its own
fresh parity and physical gates.

Three tests pass using complete binary fixtures: passing and deliberately
DC/parity-failing native comparisons reproduce with the same classification;
a modified native witness is rejected; pending results are rejected before
expensive binding. No SPICE experiment or existing captured dependency was
changed. The actual input-current experiment is confirmed live and has no
completed result yet, so no native replay receipt or convergence repair is
claimed.

### Gated combined input-current experiment

`probe_dcc_chain_300_v2.py` prepares the next combined convergence test from
corrected materials `dcc_four_section_materials_300_v2/64b5f8c41cb4eddd`.
Preparation first requires a complete, passing independent receipt for the
exact input-current reference trial. The gate verifies receipt identity,
classification, every bound native witness and post-analysis evidence; it
cannot use a pending or failing experiment as authorization to proceed.
No such native receipt exists yet, so no combined V2 capture or simulation is
claimed or launched.

The centered trial adds only the declared DC-zero input-current bench load
to the existing VDD-current numerical load; the fresh unmodified reference
retains neither numerical load. All actual circuit/model bytes, stimulus
voltage expressions and device/observation maps are preserved apart from
library include paths. External input-bench power is excluded explicitly.
Both complete 40 ns runs and the original full-vector bidirectional 2 mV,
1 nV DC, 0.25 ps crossing and all-boolean-classification parity gates remain
mandatory. Failure of either run remains failure, without substituting a
previous trace. The runner retains one priority-2 worker and the global six
SPICE slots. No native tolerances or physical criteria are changed.

Five tests pass: actual corrected decks change only declared loads/include
paths; complete binary pair checks retain internal-pulse/classification
failures; pending and failing receipts block preparation before material
validation; a changed native reference witness is rejected; and the fresh
unmodified case cannot accidentally receive the intervention. A new version
of the independent combined native replay consumer registers both original
and V2 producers, retaining all independent terminal, timing and pulse checks.
All source-chain/DCC, calibrated phase, detector, shared-RC and PHY admission
flags remain false.
The independent combined V2 replay consumer's three tests also pass, using
complete binary passing/failing receipts, pending-case preflight and changed
witness rejection. These tests verify the consumer; they do not constitute a
native combined-circuit result.
