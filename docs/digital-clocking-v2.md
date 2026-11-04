# Calibrated digital clocking, v2

This is the implementation contract for the architecture selected from the two
new papers in `../refs`. The machine-readable policy is `clocking_v2.json`.
All v2 evidence starts unqualified. Existing analog DLL artifacts and producer
sources remain immutable; they do not establish v2 performance.

Chen et al., CICC 2013 (10.1109/CICC.2013.6658549), motivates separately balanced
quarter-period delay sections and the symmetric rising-event DCC in Fig. 10(a).
Choi et al., A-SSCC 2016 (10.1109/ASSCC.2016.7844181), motivates coarse-first,
back-off, then fine training. Neither paper supplies SKY130 delay values or fixes
our detector's unequal-slew bias by itself. Its PODL driver is not adopted.

## Clock islands

TX: OpenPLL -> four independently programmable noninverting sections -> two
symmetric DCCs -> data DDR plus dedicated forwarded clock -> existing LVDS I/O.
RX clock: existing receiver -> deskew DCDL -> one four-section DLL and two DCCs
-> capture. RX data retains the existing analog receiver and DDR sampler.
The forwarded clock no longer traverses a constant-data DDR mux. The current
DCC release controller aligns delivered rising clocks with their respective
raw PH0/PH90 rising phases, preserving positive quadrature. This supersedes the
initial inverted-output startup assumption. Native startup and input-port timing
still need qualification; changed clock latency is included in RX training.

During calibration a section sees the common reference, then the sections are
cascaded. Increment the fastest section, validate an unwrapped tagged-burst
one-period measurement, and require 64 valid confirmations. The current detector
candidate uses analog edge conditioning followed by a retained-event
regenerative arbiter, input swapping and repeated votes; both extreme
unequal slews must still bracket zero within +/-20 ps. Clock codes update only
while outputs are invalid and become immutable during payload.

Each DCC ORs the outputs of identical pulse FFs driven by opposite rising
phases and toggles a final FF. The repaired pulse reset stays asserted until
its input clock falls, preventing repeated events during the high phase.
The 780--820 MHz event stream, including
minimum jittered event spacing, pulse widths, startup polarity, CQ asymmetry
and real loads, must pass native simulation. A standard-cell implementation is
a candidate, not an assumed solution. Small custom timing cells are allowed if
that candidate fails. Ideal behavioral clocks never grant native admission.

Select the smallest qualified extracted-area configuration, then power, then
configuration order. TX coarse counts are 16/32/64; RX 64/128/256; fine counts
16/32. Require overlapping coarse/fine ranges, a common monotonic legal sequence
across all 15 PVT, and no legal delay gap above 20 ps (target 10 ps). RX deskew
must cover at least the longest period plus 500 ps. The TX sections must span
609.8--641.1 ps with headroom. These are search bounds, not measured delays.

## Lab protocol and interfaces

Both ends add `mgmt_clk_25`, `train_req`, `cal_busy`, `cal_fail`, `failure_code`.
RX adds `rx_ready`. Management clock is independent of the forwarded clock.
A lab controller holds training until RX readiness; there is no return lane.
OpenPLL TRACKING is a controller state, not proof of clock lock.

1. Calibrate TX; allow at least 256 switching cycles before training is valid.
2. Repeat a 256-bit frame: `ffff0000`, followed by 224 PRBS7 bits using
   x^7+x^6+1, seed 7f, MSB first. Prove cyclic marker uniqueness.
3. Calibrate RX DLL and scan every qualified deskew code. Discard samples during
   update/settling. Require four complete matching frames per candidate. Resolve
   both pair orientations using the marker.
4. Choose maximum worst physical clearance using characterized delay intervals,
   not the midpoint in code indices. Require >=250 ps training clearance on
   both sides and >=200 ps aperture-subtracted native payload margin.
5. Assert `rx_ready`. Controller preloads the first payload word before ending
   training. TX emits `0000ffff`, then payload; RX exposes valid only after the
   recognized end boundary. There is no payload backpressure.

Use atomic request/acknowledge CDC for multi-bit codes and status. Reset,
disable, retraining or clock loss invalidates outputs. Timeout is 100 ms on the
25 MHz management clock. Confirmed clock loss clears readiness within eight
management cycles. Explicit retraining follows frequency/operating-point
changes; seamless temperature tracking is outside this startup architecture.

## Migration and qualification

Use `scripts/drain_legacy_clocking.py` on exact legacy Python coordinator PIDs.
It verifies UID/argv/open artifact lock, stops only dispatch, archives only that
PID's pending tickets under the shared queue lock, and leaves solvers/exporters
running. Once children exit it inventories original files in separate receipts
and retires the stopped coordinator. Incomplete campaigns remain incomplete;
unrecorded terminal exports need independent measurement. Original artifacts
are never rewritten. Keep the 54-case analog source survivor and 480-condition
capture aperture as retained evidence, not v2 certificates.

Implement in meaningful commits: contract/drain; reference algorithms/protocol;
clock primitives and native feasibility; calibration/CDC/training RTL; fresh
physical implementation; native integration and release. Each diagnostic uses
at most two workers and the existing six-slot fair priority/aging dispatcher.
Do not change its bound implementation or lock inodes.

V2 release gates derive from its architecture descriptor, not the old fixed
8-block/336-case analog stage. Analog I/O stability/reference/stress checks
remain required. Digital convergence replaces only analog DLL control-loop
checks. Verify all five process corners at 0/25/40 C, 390/400/410 MHz, fixed
supplies, actual loads/slews and injected jitter. RX reference duty coverage is
30--70%; widen the slew domain if actual gates exceed 250 ps. Native selected
and boundary codes must validate the characterized models used for long
behavioral calibration scans. Full-link checks require actual qualified phases,
45 cases, 4096 nominal/512 corner bits, two OpenPLL traces, 200 ps margins,
one million behavioral bits and fresh joint-RC release proofs.

## Running the new work

The implementation is versioned under `rtl/v2/` and `sky130/v2/`. The executable
reference algorithms are `scripts/clocking_v2.py`. Run focused checks with:

```sh
scripts/env.sh --ngspice python3 -m unittest discover -s tests -p '*v2*.py'
```

`probe_digital_dcc_v2.py`, `probe_digital_dcc_drive_v2.py` and
`probe_digital_dcc_output_v2.py` retain separate source circuit revisions.
`expand_digital_dcc_v2.py prepare <complete-output-screen>` independently
remeasures the selected source before preparing the 270-case PVT expansion.
`probe_digital_dcdl_v2.py` measures single pulses without modulo-period ambiguity;
`probe_digital_dcdl_smooth_v2.py` is a separate numerical diagnostic.

For a completed source context, run:

```sh
scripts/env.sh --ngspice python3 scripts/verify_digital_clocking_v2.py <artifact>
```

The consumer locks out concurrent execution, checks bound input and output
hashes, compares binary and exported samples exactly, and remeasures every
successful case. It retains numerical failures and writes a separate receipt.
Its reports are source feasibility only. In particular, the proposed inverted
DCC output is high during reset and falls on its first phase0 event; invalidation
and identical phase conventions are required during integration. Sparse DCDL
samples cannot generate a production code table. No physical certificate is
transferred from the legacy architecture or from these source experiments.

## DLL configuration and control integration

`openlvds_dll_control_v2` connects the actual calibration FSM, Gray-counter clock
watch, complete isolated measurement engine and atomic configuration bridge.
The bridge transfers all four legal-code indices and separated/cascaded mode
as one generation-tagged bundle into the raw-reference domain. Its digital
mailbox acknowledgement is deliberately insufficient to enable measurement.
The physical backend must acknowledge `raw_sequence` through `raw_settled` and
`raw_settled_sequence` only after the delay-ROM outputs, switches and mode route
have settled. It permits commits through `raw_update_allowed` only while the
physical clocks are invalid. These signals are raw-reference-domain inputs;
their exact acknowledgement returns through a second bundled-data mailbox.

The management side requires the acknowledged configuration to match its
current desired bundle. Retraining, disable and clock loss invalidate that
proof. Old transactions drain intact, but an acknowledgement from before
retraining cannot qualify the new generation. Mode changes between the
separated tournament and independent period test also require fresh physical
settling. Locked codes remain frozen. The public DLL lock is masked by current
configuration validity and clock presence; it is not DCC, warmup or RX readiness.

The composed test uses the real controllers, CDC mailboxes, launch logic and
event guards with explicitly synthetic external delay/arbiter paths. It
converges through all 64 confirmations, checks every launch against actual
committed code/mode, freezes after lock, and invalidates after source-clock
loss. Additional cases reject stale/pre-retrain settling, hold unsafe commits,
time out a backend that never settles, and prove default model admission stays
closed. These are control proofs, not physical delay models or native convergence.

Integration exposed an end-to-end clock-loss budget error in the shared clock
watch: eight stale samples after the CDC pipeline exceeded eight management
cycles overall. It now uses four stale samples, reserving three pipeline cycles
and one downstream registered-status cycle. Stop-phase tests cover 80 phases
at each of 390/400/410 MHz and require registered readiness low within eight
management cycles. The eight-cycle contract is unchanged.

## DCC startup and transmitter training

`openlvds_clock_startup_v2` accepts actual raw PH0/PH90 and delivered DCC clocks.
It generates no clock and has a separate, default-false DCC-model admission
parameter. Own-phase reset release is followed by at least 256 actual delivered
rising edges on each clock. Both counters must finish, their synchronized flags
must arrive, and independent clock watchers must report both clocks running
before management `clocks_ready` asserts. Delivered-domain `ready0`/`ready90`
assert through their own two-stage synchronizers and invalidate asynchronously,
including when that clock itself stops. Parameters below 256 hardware warmup
cycles are rejected; absent clocks time out. This startup stage retains the
100 ms timeout parameter; whole-PHY startup budgeting remains to be integrated.

Each clock watch resets with its own DCC release generation. In particular, an
edge produced by the DCC reset output cannot count as fresh running-clock
history after a restart. Clock loss latches failure and resets both DCCs;
disable or a new DLL calibration clears the stage for explicit retraining.
Native DCC CQ/recovery/removal and propagated loads still require qualification.

`openlvds_tx_training_control_v2` connects startup to the existing frame generator
on delivered PH0. Management `train_req` is synchronized into that domain and
remains a level held by the lab controller until RX ready. The first valid pair
starts a complete training frame only after startup. The existing generator's
additional minimum training duration and frame-boundary end-marker rules are
retained. Payload must be preloaded in the pair-clock domain. The dedicated
forwarded clock remains the physical DCC output, not a data mux constant.

The composed protocol test uses the actual clock-hold DCC gate topology with
explicit test-only cell delays. It independently checks 432 transmitted pairs
against three full training frames, the end marker and payload; proves both
delivered warmups; stops each phase independently; and checks asynchronous
disable/source-loss invalidation and fresh reacquisition. Missing both clocks,
one clock never starting, default admission and shortened hardware warmup are
separate rejection cases. These tests do not establish native clock timing.

`openlvds_tx_control_v2` now composes the actual DLL controller, DCC startup and
training generator. A management training edge invalidates output immediately,
issues one DLL-start pulse, waits for calibration and both delivered warmups,
and then retimes the final management grant into the pair-clock domain. The
same training request remains a level for the frame generator, so the lab can
hold training until RX readiness without repeatedly restarting calibration.
DLL/delay and DCC admission remain separate default-false parameters. Backend
ROMs, code/mode settle acknowledgement, physical routes/offsets, observers,
raw phases and delivered DCC clocks are all explicit physical interfaces.

`openlvds_clock_sequence_v2` supplies one 100 ms management deadline across DLL
calibration and DCC warmup. DLL lock cannot restart that budget. Failure reasons
are latched before disabling stages, so their later cleared local flags cannot
erase the cause; a fresh training edge or disable clears the overall failure.
Unadmitted DLL measurements map to the public unqualified-model reason. Clock
loss invalidates the final grant independently of a clock domain's ability to
advance. Completed payload codes and measurement launches remain frozen.

The complete composition test exercises 64 real-controller confirmations,
atomic configuration/physical-settle CDC, actual isolated launch/event logic,
clock-hold DCC gate topology, both warmups and 432 independently checked frame/
end-marker/payload pairs. Separate unit tests cover a deadline spanning both
stages, success at the deadline, held requests, latched stage errors and explicit
retraining. External delay/threshold/arbiter paths and published raw-phase
delays are synthetic; the phase model derives delays from committed codes and
publishes cascaded phases only after DLL lock. These tests do not qualify
pre-lock physical switching, analog transients, SKY130 timing or a full PHY.

## RX scan and capture integration

`openlvds_rx_scan_v2` scans all legal code indices through an admitted delay-ROM
port. The scan records four-frame results, with an independent per-code marker
timeout. It searches contiguous passing runs and maximizes the conservative
minimum distance from both measured eye boundaries using delay intervals. It
then reapplies the selected code and requires a fresh frame test before
`rx_ready`. The model-admission parameter defaults false. No fabricated ROM is
provided as a production implementation.

`openlvds_rx_training_v2` connects the scan, code mailbox, capture training and
tagged command/result mailboxes. Results carry both generation and code index.
Raw and capture clocks are watched independently, and management status masks
public validity when a stopped clock cannot advance capture-domain logic. The
current integration test uses a synthetic eye mask explicitly for protocol/CDC
verification; actual timing-model and native integration remain required.

## DCDL fine-bank correction

The original fine-load source pilot has insufficient coarse/fine overlap. The
new `dcdl_cap_bank_v2.py` uses complementary transmission gates and native MIM
capacitors; disabled branches discharge explicitly. `probe_digital_dcdl_cap_v2.py`
checks two bounded geometries and observes all custom MOS terminal pairs.
`dcdl_cap_strong_v2.py` strengthens the return merge to reduce the unit delay.
`probe_digital_dcdl_batch_v2.py` measures dense code sets in separate tagged pulse
windows, amortizing device-model elaboration without reducing the integration
accuracy or reusing incomplete outputs.

The producer's internal-control 10 mV check was inappropriate for digital
inverter outputs. `analyze_dcdl_batch_v2.py` retains those failures and performs
separate reanalysis with explicit digital logic margins; source inputs, pulse
integrity and thin-oxide stress remain strict. Both that consumer and
`verify_dcdl_mim_v2.py` check exact binary/export agreement and retain receipts
outside producer artifacts. Code-path selection uses conservative intervals
through `digital_delay_path_v2.py`; it cannot supply missing PVT coverage or
turn source data into physical qualification.

## Edge-detector feasibility

`openlvds_bbpd_v2` and `probe_digital_bbpd_v2.py` test matched input swapping,
conditioning and two native edge-sampling FFs at SS40. The native pilot includes
both +/-20 ps and +/-150 ps at matched and unequal slews, and records ambiguous
and unresolved outputs separately from correct signs. Twelve pilot votes do
not qualify 64-confirmation lock or remove the independent tagged-epoch check.
`verify_digital_bbpd_v2.py` remeasures the completed curves with exact waveform
witness checks. A detector with a dead zone or slew-dependent sign failure must
be repaired before it is used by the DLL calibration measurement engine.

## Native repairs and next admission gates

The original 270-case DCC matrix completed without numerical errors, but all
54 SF cases failed. Its reset released while the input clock was still high,
retriggering the native pulse FF. The failed source and independent receipt
`digital_clocking_v2_verification/3c04509edf48618f` remain unchanged.
`openlvds_dcc_clock_hold_v2` adds a clock-aware reset latch. Its 24-case SF40/SS40
pilot preserves one pulse per source edge, including +/-140 ps spacing offsets;
balanced half-cycle error is about 29.7 ps at SF40 and 0.224 ps at SS40.
The new 270-case expansion is `dcc_clock_hold_pvt_v2/8b83d935bd2d01f3`.

`harden_dcc_v2.py` requires a complete independent passing source receipt before
starting fresh placement, DRC/LVS and GDS RC extraction. It checks the exact
reset-feedback topology and rejects inserted signal cells. Physical success
alone cannot admit electrical timing. `openlvds_dcc_release_v2` independently
releases the two DCC resets after their own raw rising phases. Logic regression
sweeps 25 startup offsets and checks positive quadrature; native recovery,
removal, CQ and actual loads remain open.

Physical-flow preflight found that LibreLane's Python lacks NumPy. Before any
physical artifact was prepared, the DCC flow was revised to invoke the unchanged
source-admission checks through `/usr/bin/python3` in the scientific container
environment. It strips foreign Python package paths and checks the exact source
witnesses again when binding physical inputs. The physical manifest now records
both interpreters and LibreLane package hashes. The actual LibreLane constructor
accepts the configuration; this preflight does not run layout or grant source
admission. Original failed-import and successful-preflight logs remain under
`build/dcc-v2-physical-preflight-*.log` and
`build/dcc-v2-physical-config-constructor-preflight.log`.

The mutual-FF detector completed 60 cases and exposes a dead zone near zero.
`openlvds_tag_arbiter_v2` retains isolated input events before a cross-coupled
NAND race, removing that FF setup aperture. Its standard-cell conditioner still
introduces roughly 45 ps of unequal-slew bias. Moving the buffer before the
swap mux did not fix it. The retained `tail140_w20` analog frontend restores all
six +/-20 ps signs, but its new arbiter load initially pushes local reference
ripple 255 uV beyond the 10 mV limit. Increasing only the native reference MIM
from 22x22 to 30x30 um passes all six sign, stress and reference checks; peak
reference is 0.905723 V. Independent receipt:
`clock_repairs_v2_verification/3d4ed08666f410c4`.
`expand_analog_arbiter_v2.py` expands this exact topology to 180 source cases:
15 PVT, both input swaps and matched/unequal slews at +/-20 ps. Low-level tagged
trial control and the six-pair/vote sequencer are now implemented as described
below. Characterized tolerance perturbations, physical routing and detector
integration still need native qualification.

Dense DCDL reanalysis found real SS40 control-device stress at 1.95726 V,
above the unchanged 1.95 V limit. Strengthening the complementary-control
inverter worsens it to 1.97904 V. A native 2x2 MIM shunt reduces it to 1.93214 V
in the first eight-code source test, preserving delays. The separate
`dcdl_control_margin_v2/4a4181e6cbb757d0` tests 2x2/4x4 shunts, both code
directions and large jumps at 20/100/200 ps control slew. All six cases are
complete without numerical errors. Both geometries fail at 20 ps (1.96278 V
for 2x2, 1.96118 V for 4x4), while 100/200 ps pass. Independent receipt:
`dcdl_control_margin_verification_v2/7f57360f2f2b99f7`.
The fastest bulk falling update pulls r0 to -0.16278 V; the worst terminal pair
is the switch PMOS r0/body, not its complementary gate. The separate
`dcdl_charge_kick_v2/a802a32a83c0b5ee` compares adding native 2x2/4x4 MIM at r0
against one-bit thermometer updates near both ends of the fine bank. Both
retain 2x2 complementary-control shunts and 20 ps source slew. No delay ROM is
admitted; a serialized update policy would require its own controller and
native all-code/all-PVT proof before selection. All four charge-kick source
repairs pass, independently remeasured in
`dcdl_charge_kick_verification_v2/702b10e5862a3a2e`:

| Source repair at SS40, 20 ps control slew | Maximum terminal difference |
| --- | --- |
| Single-bit updates near fine 0 | 1.93223 V |
| Single-bit updates near fine 31 | 1.87948 V |
| 2x2 MIM at r0, bulk updates | 1.94795 V |
| 4x4 MIM at r0, bulk updates | 1.91815 V |

`dcdl_node_bank_pvt_v2/e307e4f382060f33` explores the 4x4 node shunt across
150 source runs: every PVT, coarse 0/1, all 32 fine codes and an additional
bidirectional bulk-update run at each coarse/PVT. It retains the 2x2 EB shunts,
coarse-count 16 topology, 20 ps control transitions and unchanged stress limits.
This is source range/health exploration, not final minimum-area selection.
RX coarse-count/range and actual periodic pulse transport remain separate.
The independent consumer keeps repeated/history-dependent delay extrema;
these observed ranges are not quantified numerical uncertainty or a legal ROM.

Next gates, in dependency order: finish independent source repair matrices;
select a stress-safe fine bank and characterize a common all-PVT code path;
qualify tagged measurement paths, offsets and clock primitives physically;
connect TX/RX clock islands; then run the native full-link and release matrix.
Supplies remain fixed throughout.

## Isolated measurement trials

`openlvds_tag_launch_v2` accepts one management command through an atomic CDC
mailbox. Enables change on falling raw-reference edges. A separated trial
launches source and comparison pulses together; a period trial launches its
comparison pulse on the next raw rising edge. A second mailbox acknowledges
that the pulse sequence ended. This acknowledgement is not detector settling
or DLL lock. Disable and clock loss cancel outstanding commands.

`openlvds_phase_trial_v2` holds section routes and input swap through result
consumption. It clears prior event history, arms the retained detector, starts
the launcher, waits for the configured characterized settling interval and
samples synchronized decisions. Each conditioned pre-swap input must contain
exactly one rising event and return low. Missing/duplicate events, unresolved
decisions, timeout and frontend loss reject the trial. Results retain request
sequence tags and survive management backpressure. Failure cancels the launcher
so a delayed command cannot contaminate a later trial.

Admission defaults closed. Physical wrappers must connect the actual routing,
conditioner, arbiter and event observers, qualify minimum event widths and the
worst path/settling window, and provide frontend readiness. Protocol tests use
explicit synthetic paths only. They test both input swaps, a 2.4/2.6 ns period
bracket and a 5.1 ns delay that remains long rather than aliasing at 400 MHz.
No simulated logic delay is admitted as native timing evidence.

`openlvds_dll_measure_v2` compares all six section pairs at both signed
threshold offsets, with three valid votes for each input-swap orientation.
Both normalized swap majorities must agree. A section is eliminated from the
minimum candidates only when another is faster outside the threshold bracket;
ties select the lowest eligible index. Thus the chosen section is within the
characterized bracket of the true minimum, rather than claiming sub-threshold
ordering. All six pairs must lie inside the bracket to report balance; a chain
of locally close adjacent pairs cannot hide a wider overall spread.

Period mode uses the same signed bracket with the next-epoch reference. It
reports short, in-window or long; swapped-input disagreement, a reversed
bracket, stale sequence or missing/duplicate events reject the measurement.
Only explicit unresolved-detector decisions can retry, at most three times
per voting block. Route acknowledgement must carry the current sequence.
One level request produces one response and then must deassert. The existing
calibration FSM still requires 64 complete confirmations and freezes codes.

`openlvds_dll_measurement_v2` connects this sequencer to the actual phase-trial
controller and pulse launcher. The physical wrapper supplies acknowledged
routes, the two conditioned pre-swap event inputs and retained arbiter outputs.
Its offset branches must be characterized together with detector bias, bounded
inside +/-20 ps and checked against legal code steps for convergence. Admission
defaults closed in both constituent modules. Event observers receive an
explicit per-trial reset assertion before their synchronized flags are trusted;
their idle values cannot initialize or certify a measurement.

Tests cover the composed pulse/event path, normalized input swaps, majority
votes, bounded retries, stale route/result tags and multi-period rejection.
A separate transaction model drives the real calibration FSM through code
increments and all 64 confirmations. These synthetic external models prove
control behavior only. Yosys process/check passes for default and admitted
configurations do not replace physical/native timing qualification.

`phase_threshold_pair_v2.py` now supplies a native source candidate for the
signed threshold. Both branches use matched buf_8 drivers, one switched native
2x2 MIM load, explicit off-state discharge and buf_4 outputs. Complementary
selection adds load to reference or feedback; it does not advance an edge.
The branches follow the analog conditioner and precede the exchanged-input
retained arbiter. Their absolute thresholds, including detector bias, are
measured rather than assigned an ideal delay.

`phase_threshold_v2/b5b100243bdaa8b1` runs 18 new-load SS40 source cases:
raw offsets -20/0/+20 ps, matched and both unequal slew directions, and both
threshold polarities. At zero raw offset, opposite threshold selections must
produce opposite decisions; both selections must retain correct outer signs
at +/-20 ps. All custom MOS terminals, native branch pulse transport, digital
control stability and the unchanged 10 mV local-reference limit are checked.
Independent remeasurement is queued after completion. Static controls in this
pilot do not qualify route updates, all-PVT thresholds, extracted matching,
calibration convergence or the PHY.

The first two threshold cases have correct signs and reference ripple, but
fail the unchanged 1.95 V custom-device limit. The off-branch buf_8 node reaches
-0.15631 V immediately before its rising edge; the PMOS node/body difference
is 1.95631 V. This is an electrical failure, not a waived numerical tolerance.
`phase_threshold_load_v2/f8c2416efc6cd197` changes only the two always-connected
base MIMs from 2x2 to 4x4. It retains the switched units and control shunts.
Six matched-slew SS40 cases check -20/0/+20 ps and both threshold selections.
All six pass sign, custom-device stress and reference checks, independently
remeasured in `phase_threshold_load_verification_v2/aaa5f22c61533cda`. Unequal
slews, all-PVT and physical thresholds remain unqualified. Its parent failure
cases were read independently with exact
binary/export and before/after witness checks while other parent cases continued.

`phase_prefix_v2/52fb82044646fca1` repeats all six passing repair cases with
only the quiescent simulation prefix shortened from 200 ns to 20 ns. Native
1 ps precision, supplies, devices, pulse shapes and measurement windows remain
unchanged. Independent paired receipt
`phase_prefix_verification_v2/15be3c82462f9f28` passes voltage (10 mV), individual
edge (0.25 ps), stress-difference (1 mV), sign and health checks. Aggregate native
runtime improves 3.31 times. This is measured matched-slew SS40 equivalence;
hardware warmup remains unchanged, and other loads/PVT remain unqualified.

The next cohort, `phase_threshold_slew_v2/1a45576caa4bab48`, uses that simulation
prefix for the 30 remaining SS40 combinations: matched 100/100 ps with swap 1,
20/250 and 250/20 ps with both swaps, all -20/0/+20 ps offsets and both threshold
selections. Its independent consumer keeps the two swap orders separate and
requires every three-offset bracket and every device/reference health check.
It runs through the shared six-engine dispatcher with two campaign workers;
existing healthy long-prefix jobs continue unchanged.

## Physical fine-switch primitive and early RC screening

`mim_switch_unit_v2.py` defines the actual five-port unit: transmission-gate
NMOS/PMOS, off-state discharge NMOS, a native 2x2 fine MIM and 2x2 control shunt.
The topology test compares its switch terminals and W/L directly against the
native fine-bank source. The node-wide base MIM and control inverter remain
outside the unit. No ideal capacitor or placeholder transistor is used.

The primitive geometry inspection is
`mim_switch_pcells_v2/62cb2bbcbc49aef2`. Native Magic PCells are placed compactly,
with M1 fanout/M2 drops and separate M3 rails. MIM top plates escape on M4 before
descending outside the capacitor. Three failed routing placements remain intact:
the first two expose the 1.34 um MIM-to-unrelated-M3 rule, and the third a local
M2 spacing violation. The current source is `build_mim_switch_unit_v3.py` with
`constraints/v2/mim_switch_unit_legal.json`. Result
`mim_switch_unit_physical_v2/9ee573b2d67b6ab9` has zero Magic DRC errors and a
unique independent LVS match. GDS/LEF generation does not qualify a whole bank.

Fresh GDS extraction in `mim_switch_unit_rc_v2/b1438bbf3193eb2f` contains
199 resistors and 55 parasitic capacitors. Its wire-collapsed audit retains the
intentional MIM devices and matches the source. Independent receipt
`mim_switch_unit_verification_v2/e0f493e7d69328f9` reruns that topology audit and
binds the same exact GDS/netlist bytes. Use its `verified_model`: the original
producer accidentally placed a scope description in the scope-hash field;
the separate receipt retains that value and records the actual schematic SHA
without rewriting the producer or extracted circuit.

The integration LEF in `mim_switch_unit_abstract_v2/e1049520c33a5145`
restricts public routing access to the five designated M3 rails. Other routing
rectangles, including contacts and MIM plates, become obstructions; the routing
geometry multiset, macro origin/size and GDS bytes are preserved. OpenROAD
OpenDB independently reads the derived LEF and confirms the five signal/power/
ground pin types and M3-only access. This is an integration view of the same
DRC/LVS-clean unit, not an array, timing or electrical qualification.

The measured upper bound on interconnect capacitance at NODE is about 3 fF per
unit. This excludes intentional MIM and intrinsic MOS capacitance and is not a
transient timing reduction. `dcdl_unit_rc_v2/fd1d622597ea4be3` therefore tests
31 exact extracted unit models in the retained source coarse core at SS40,
using fine codes 0/31/0. It measures minimum/maximum delay and every extracted
MOS terminal during code updates. This early diagnostic omits inter-unit and
coarse-core routing, so it cannot qualify a full physical bank or delay ROM.
Independent receipt `dcdl_unit_rc_verification_v2/d44e7b19d8358afc` confirms
that unit stress passes, but the minimum rising delay is 711.88 ps at SS40.
This is above both ends of the 609.8--641.0 ps quarter-period range. The first
and repeated fine-0 delays are 713.63/711.88 ps; fine 31 rises at 1302.33 ps.
This hybrid is insufficient for the intended quarter-period clock sections;
whole-bank routing of the present driver configuration is held.

`dcdl_rc_drive_v2/7d81b2af858f05f5` retains the exact unit RC and tests three
source compound-gate alternatives: two merge gates; two turn plus two merge
gates; or three merge gates. Each uses matched parallel copies of existing
native cells with identical logical inputs. The 0/1/16/31/0 sequence checks
minimum/range, a fine step and bulk-update stress. No tolerance, supply or
one-period target changes. Any survivor still needs compound-cell physical
proof, coarse/fine overlap, full PVT and full-bank extraction.

All three cases completed without solver errors and pass custom-device stress;
independent receipt `dcdl_rc_drive_verification_v2/cc13670b539c43b5` confirms
the measured outcomes. Double-turn/double-merge is the sole range survivor:
its fine-0 first/repeated rising delays are 609.24/607.32 ps. The first edge
leaves only 0.52 ps below the fastest quarter period, which is insufficient
to select it for routing.

`dcdl_balanced_drive_v2/ebaad5ef41119fe1` instead doubles every coarse-core
standard cell with identical-input native parallel copies, including all forward,
turn, pass and merge stages. Two variants use double or quadruple output drive.
Both coarse codes 0/1 use the same hardware, with fine codes 0/1/16/31/0,
the unchanged extracted 31-unit bank and unchanged 4x4 shared-node MIM. The
independent consumer measures the worst first/repeated fine-0 rising delay and
conservative rising/falling overlap between coarse 0/fine 31 and coarse 1/fine 0.
This sparse SS40 pilot cannot admit a dense code table, compound-cell layout,
full-bank routing or all-PVT timing, even if its feasibility checks pass.

The first two terminal `core2` cases recover the required minimum-delay
headroom: coarse 0/fine 0 rises at 556.41 ps initially and 554.65 ps on repeat.
However coarse 0/fine 31 is only 832.95 ps, while coarse 1/fine 0 is
858.19/857.68 ps. Even the most favorable repeat leaves a 24.73 ps rising
range gap. Device stress passes, but this is not an overlapping legal code
path. These two completed cases were independently remeasured with exact
binary/export agreement and before/after witness checks while the other two
output-drive cases remained live. Their original files are unchanged.
The complete four-case campaign is now independently verified in
`dcdl_balanced_drive_verification_v2/ca2ad9a4ffc2cf92`. Both variants pass
custom-device stress. Conservative rising overlap is -25.24 ps for `core2`
and -27.11 ps for `core2_output4`; worst first/repeated minimum-code headroom
is 53.35/63.88 ps respectively. The stronger output does not close the gap.

The separate `openlvds_mim_switch_2x3_v2` keeps every MOS and its control shunt
unchanged, increasing only the switched native MIM from 2x2 to 2x3 um.
Actual PCell inspection is `mim_switch_2x3_pcells_v2/4a3bbfab8fe0c7b9`;
the larger MIM has the same width and an additional 1 um total height. Placement
moves its center upward 0.5 um and raises M4 escapes and upper buses 1 um.
`mim_switch_2x3_physical_v2/7635bb0cb7abe0c4` passes zero-error Magic DRC and a
unique LVS match. Fresh GDS extraction
`mim_switch_2x3_rc_v2/942b90d393388692` has 198 resistors and 55 parasitic
capacitors; its metadata contains the actual schematic scope hash. Independent
receipt `mim_switch_2x3_verification_v2/26f440d15e6e9da1` reruns the strict
wire-collapsed topology check. NODE interconnect is about 2.97 fF/unit; this
excludes intentional MIM and MOS capacitance. No old 2x2 model is relabeled.
Its separate M3-only integration view passes actual OpenDB checks in
`mim_switch_2x3_abstract_v2/d61830e948bc02dd`.

`dcdl_larger_unit_v2/b22eb8e365e6d65a` tests 31 exact extracted larger units
with the same `core2` coarse hardware and 4x4 shared-node MIM. Six native tasks
cover SS40, FS40 and FF0, each at coarse 0/1 with fine 0/1/16/31/0. The consumer
requires both-edge overlap, worst first/repeated minimum-code delay and every
custom-device stress check independently at each pilot PVT. This experiment
does not qualify dense steps, common all-PVT ROMs, a physical compound gate,
inter-unit routing or a full bank. Whole-bank routing remains on hold.
The first two SS40 cases have completed without numerical errors and pass
custom-device stress. Their coarse-0 fine-0 first/repeated rising delays are
555.80/554.05 ps; fine 31 is 892.10 ps. Coarse-1 fine-0 is 857.59/857.08 ps,
giving 34.51 ps conservative rising overlap and about 54 ps first-edge headroom.
Full pilot verification still waits for FS40 and FF0. This is early extracted-
unit evidence, not admission of the whole bank or an all-PVT code path.

All these artifacts remain component evidence. Full-array extraction, periodic
pulse transport, native selected/boundary codes, all-PVT models and whole-PHY
qualification remain required. No active layout/model selection is published.

Verification follow-ups use `verify_clocking_when_idle_v2.py` for live contexts.
It retries only contention on the existing execution lock; witness, terminal
state and measurement failures remain errors. Service startup ordering alone
does not imply producer completion. Original early lock-rejection logs remain
retained; no producer is restarted to obtain a proof.

## Superseded source campaigns and current physical work

The source-only `analog_arbiter_pvt_v2/e6ec7847a89bd52b` and
`dcdl_node_bank_pvt_v2/e307e4f382060f33` campaigns are archived incomplete. The
former lacks the new threshold load; its frontend/bias/arbiter library bytes
match the loaded pilot, which must supply its own full-PVT proof. The latter
uses the identical single-drive source whose extracted-unit minimum failed at
711.88 ps. Neither old campaign can qualify the replacement circuit.

`drain_superseded_clocking_v2.py` verifies the exact Python coordinator's UID,
argv, start identity and open artifact-lock device/inode. Run it on the host
with that Python PID, not the Apptainer service parent. Queue ownership uses
the coordinator's open ticket-owner lock inodes: namespace-local PID 14 is
shared by unrelated containers and cannot identify a campaign. No dispatcher
implementation or lock inode changes. Only future dispatch stops; solvers and
exports finish before the stopped coordinator is retired. Reasons and exact
superseding evidence hashes are retained separately.

Receipts `superseded_clocking_drain_v2/1598271_440984732` and
`superseded_clocking_drain_v2/1603762_441209628` retain 54/43 original summaries
and 55/45 cases respectively, including final exports without original case
summaries. Their original campaigns remain incomplete. Unrecorded exports need
independent measurement before any timing claim.

The loaded threshold pilot now independently passes all 30 cases in
`phase_threshold_slew_verification_v2/7061a3cc4f520556`. The six-case larger-unit
pilot independently passes SS40/FS40/FF0 in
`dcdl_larger_unit_verification_v2/8c6234e034c425d5`; minimum conservative rising
overlap is 32.48 ps and minimum first-edge headroom is 53.95 ps. Dense code
steps, other PVT and complete bank routing remain unqualified.

`phase_threshold_pvt_v2/7f2eeea8cd9e0678` is the new 540-point source matrix for
the actual repaired threshold load: all 15 PVT, three slew pairs including
20/250 and 250/20 ps, both swaps, all -20/0/+20 ps offsets and both threshold
selections. Fast and mixed stress corners run first. It retains 1 ps precision,
the verified 20 ns simulation prefix and two workers through the same global
six-engine dispatcher. Independent verification requires 180 complete signed
brackets and all device/reference checks. No voltage sweep or hardware warmup
change is introduced.

### Shared shunt and full-bank topology

`build_mim_base_4x4_v3.py` builds the real shared 4x4 MIM in
`mim_base_4x4_physical_v2/d32143aff2efa2c7`, with zero Magic DRC errors and a
unique LVS match. Raw and restricted-access LEFs are retained. The first
`4a9e84595335b2c5` attempt had clean geometry but its abstract parser expected an
existing obstruction block. A two-port capacitor has no internal signal net,
so Magic exposed all routing as pins and omitted that block. The versioned
replacement adds it while preserving every routing rectangle and the GDS.

`dcdl_mim_bank_v2.py` generates the 16/32 bank: the exact 128-cell paired core,
real coarse/fine control buffers and complement inverters, 31 larger fine units
and one shared shunt. Every legal coarse setting is compared to the measured
native source. That direct parallel-gate RTL is retained as a failed P&R
prototype: Yosys reports 64 multiple-driver nets, so it cannot be passed through
digital hardening as ordinary independent cells.

`dcdl_mim_bank_physical_v2.py` instead groups each pair into a single-output
compound-macro interface. Its 174-instance view expands to the exact retained
238 native instances; Yosys reports zero problems. The 64 compound instances
use four types: paired buf4, NAND2-4, NAND2-8 and NAND2B-4. These now have actual
GDS, native taps, zero Magic DRC and unique LVS matches in
`compound_driver_physical_v2/e526d97182ddb6c5`. Restricted LEFs preserve all
routing geometry and expose only declared metal-3 rails. Earlier sticky-label
parsing and narrow-track/notch failures are retained separately. Fresh native RC
and independent topology audits pass for all four in
`compound_driver_rc_v2/ff754f3ebf571140`.

`dcdl_bank_assembly_v2/cbcead194f7cc775` checks all six macro types in OpenDB,
including the fine unit and shared shunt. Every pin direction/use/layer and all
174 instance connections are present; the 96 macro placements fit without
overlap. The other 78 instances require standard-cell row placement. This
materializes a concrete macro configuration and placement, not a routed bank.
Whole-bank power/signal routing, extracted range/overlap/stress, dense code
characterization and an admitted ROM remain open. Logical blackboxes and
isolated RC proofs supply no bank timing admission.

### Completed DCC source and recovered physical extraction

The repaired 270-case DCC source matrix independently passes all 15 PVT in
`dcc_clock_hold_pvt_verification_v2/f1d1e1e39c014c23`; its worst balanced mean
half-cycle error is 29.70 ps. The queued LibreLane run completed with zero
routing/Magic/KLayout DRC, LVS and antenna counts in
`dcc_physical_v2/75fb1becc16e8a41`. Its strict summary writer then rejected two
infinite unconstrained timing slacks. The original failed state and all files
remain unchanged.

`recover_dcc_physical_v2.py` creates the separate receipt
`dcc_physical_recovery_v2/5b37b88a57c9d32d`, binding the exact GDS consumed by
signoff stages. The new topology policy recognizes true constant-high tie
clones feeding the two pulse FF D pins and power-only decap row endcaps; all
pulse/reset/toggle/output connections remain checked. Altered signal wiring
and signal-connected endcaps are rejected. The actual cloned ties and power
devices remain in the native RC and topology audit.

Fresh extraction contains 6,890 resistors and 734 parasitic capacitors; its
independent wire-collapsed transistor-topology check passes. The actual source
schematic hash is bound explicitly. Nonfinite timing remains named diagnostics,
never zero slack; the original unrecorded producer return code is not invented.
This is physical/RC evidence only. The following native timing experiment
exposes a failure; this backend remains unqualified.

### Native DCC failure and replacement experiments

`dcc_native_rc_v2/3c67e55b2d7e08a2` tests the exact routed network at SS40/SF40,
410 MHz, 20/100/200 fF output load, 20/250 and 250/20 ps input slews, and common
30%/70% input duty. Input-source delays compensate the different rise times so
their actual 0.9 V crossings are exactly half a period apart. Reset releases
150 ps after a PH0 rising crossing while PH0 is high. Every MOS terminal is
saved; all six terminal-pair voltages are screened at 1.95 V. These diagnostics
do not widen the fixed supplies or replace the existing clocking contract.

The first cases miss output events and exceed the terminal screen. Independent
raw-waveform receipt `dcc_native_failure_v2/a8e252ff2a35af3d` binds cases 0/1.
At 30% duty, the phase pulses last about 2.77–2.80 ns, longer than the 1.22 ns
input-event spacing. At 70%, both pulse FFs still fire, but their OR never
crosses below 0.9 V during the measured steady window; the final toggle receives
no new rising edges. Retained failures, rather than the earlier source-only
pass, determine the current hold.

The 24-case `dcc_toggle_pair_v2/9cc8e5acc822a14e` compares the exact routed
transistor network with wire R/C removed against two independent toggle FFs
and a native XNOR. The collapsed controls preserve events; several still fail
half-cycle or terminal screens. The direct two-toggle candidate exposes a
second issue: with feedback `D=!Q`, the master latch can retain a 1 during
reset and toggle when reset deasserts while its clock is high. A simple logical
FF model would miss this startup event.

The 24-case `dcc_toggle_pair_v2/0a6ed067a47953ae` changes feedback to
`D=RESET_N & !Q`. It passes startup and output-event checks in completed cases,
but a single XNOR has excessive duty bias even with matched input slews
(about 67 ps for the first SS40/drive-1 pair). Terminal excursions also remain
above the screening limit. `dcc_toggle_pair_v2/af5834ab76e4deca` tests two native
XNOR2-2 cells with opposite input assignments and tied outputs, retaining equal
aggregate output drive and testing both FF strengths. This is a physical
compound-gate candidate, not a production multi-driver RTL net.

The five-cell reset-qualified drive-2 candidate is separately placed/routed in
`dcc_toggle_pair_physical_v2/59c37db357dc5b9b`, with all six physical check counts
zero and the exact two feedback loops verified. Its fresh network has 6,692
resistors and 586 parasitic capacitors; an independent wire-collapsed topology
audit passes. Nonfinite untimed STA values remain explicit diagnostics.
`dcc_toggle_pair_rc_v2/9cdb701177c3b82b` contains four matched-slew SS40 native
tests at 20/100 fF and 30%/70% duty to separate actual routing effects from the
source candidate's timing/stress limitations. It is not admitted.

The balanced XNOR macro has actual native cells/taps, one public output,
zero Magic DRC and a unique LVS match in
`balanced_xnor_physical_v2/8444c61422ffa5c2`. Fresh extraction and an independent
wire-collapsed topology check pass in `balanced_xnor_rc_v2/7279d17009af8771`
(439 resistors, 247 parasitic capacitors before exact resistor reduction).
The first matched-slew SS40/drive-1 source cases improve mean half-cycle error
from about 67.23 ps to 40.49 ps, but still exceed the terminal screening limit.
That is evidence for testing the symmetric combiner, not electrical admission.
Next admission work must establish symmetric-combiner timing, reset release,
internal stress and actual permanently loaded clock-conditioning interfaces
before full-PVT native DCC qualification or integration into TX/RX. Do not
replace the production backend or assert its admission bits from these pilots.
