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

### Static NAND storage and isolated transmission gates

The routed five-cell diagnostic completes all four tests in
`dcc_toggle_pair_rc_v2/9cdb701177c3b82b` without numerical errors. At SS40,
100/100 ps input slew and 20 fF, its mean half-cycle error is about 108.8 ps and
its worst observed terminal difference is 2.049 V. The 100 fF cases also fail
event association. The actual RC therefore does not rescue this candidate.

Native-source terminal inspection finds charge kick on private storage nodes,
not a changing supply. The 1.95 V screen remains in force; the
[SkyWater device documentation](https://skywater-pdk.readthedocs.io/en/main/rules/device-details.html#v-nmos-fet)
lists that bound for the 1.8 V NMOS model's operating range. No voltage sweep or
relaxed device threshold is introduced.

`dcc_nand_latch_v2/f43da8a77c38ea09` replaces the reset FFs with static NAND
master/slave storage. Internal state initializes through raw clocks while a real
output NAND holds clock_out HIGH in reset. The first matched SS40 cases preserve
events and have about 8.6 ps mean error, but an internal NMOS stack node reaches
roughly -0.40 V. Native 2x2 MIM stack shunts in
`dcc_nand_mid_shunt_v2/973f16363c3657c6` suppress that peak and expose positive
excursions on lightly loaded gate outputs. Adding one native output shunt per
logical net in `dcc_nand_node_shunt_v2/a742d47d1d4db6e6` reduces the first
peak to 1.957 V but makes some events too late for the next-source-event window.
All three 24-case cohorts and their failures remain intact.

`dcc_tg_combiner_v2/4d0f303e86443b69` shortens the combiner to two real CMOS
transmission-gate XOR muxes fed by complementary storage outputs. Direct loading
prevents SF storage from switching. Four matched native buf8 isolation drivers
in `dcc_tg_buffered_v2/5d5df5f8b9f6a416` restore startup and event integrity.
Independent receipt `dcc_static_verification_v2/23edcfb662ca029c` regenerates the
native libraries and decks and remeasures all binary waveforms: **all 24 cases
pass startup, event integrity and terminal screening**, with maximum terminal
difference 1.933721 V. Each of its two TG-size variants still fails the agreed
mean half-cycle requirement in four of twelve cases. Neither is admitted.

The first verifier's extra 50 ps per-individual-cycle criterion is retained in
`dcc_static_verification_v2/882f93591267bc4b` as an obsolete stricter diagnostic.
The frozen descriptor explicitly names `mean_half_cycle_error_ps = 50`.
Versioned verifiers v3/v4 use that agreed mean criterion and preserve individual
half-cycle excursions separately for the full-link margin work. A small mean
does not establish eye margin, and the diagnostic does not add a new release
requirement. No bound producer or prior receipt was rewritten.

Two targeted experiments accompany the 540-case threshold matrix:

- `dcc_tg_ratio_v2/955c8dbc75673e14` changes only the eight custom TG widths,
  retaining every native storage/buffer transistor and MIM. Its 12 matched-slew
  SS40/SF40 cases test P/N ratio headroom and have completed without numerical
  errors. N=1/P=3 µm passes all four of its cases, with 17.2–17.7 ps mean error
  at SS40 and a worst SF40 value below 37.5 ps. N=1/P=4 also passes but reaches
  46.95 ps at SF40; N=0.5/P=2 fails all four mean-error checks. N=1/P=3 is the
  next joint-source integration candidate, not a full-PVT/physical selection.
- `continuous_clock_conditioner_v2/c3bbd0dec4ab33a1` tests the exact retained
  tail140_w20 conditioner and distributed-RC bias continuously at 410 MHz.
  Real buf8 clock drivers feed the actual buffered DCC input circuitry held in
  reset, plus permanent buf8 monitor inputs and fixed native 4x4 MIM rails.
  All twelve SS40/SF40 cases pass clock integrity, common-mode and terminal
  screens. Their largest conditioned phase-spacing error is 4.21 ps, including
  both 20/250 and 250/20 ps raw input slew and both 30%/70% duty. Independent
  receipt `conditioned_clock_verification_v2/94097d668b5de414` regenerates the
  libraries, decks and MOS coverage and remeasures every raw waveform.
  This proves neither DCC run
  timing nor a complete five-channel conditioner; integration remains required.

Native layout access is now concrete. Inspection
`nand_stack_native_inspection_v2/bab67e2b837d7a07` preserves actual NAND GDS/MAG
and extracted device geometry. Label-only proof
`nand_mid_access_v2/9627a8f5d45d42e4` exposes the drive-2 and drive-8 stack nodes
as MID ports, obtains unique transistor-level matches, and identifies existing
local-interconnect landing rectangles on those exact nets. No native mask changed.

Two actual shunted NAND macros now pass DRC, unique transistor-level LVS and
fresh RC topology checks. Physical receipt
`nand_shunt_physical_v2/e81ae766c2d4bf14` adds contacts to existing stack LI,
native 2x2/4x4 stack MIM and 2x2 output MIM, with M3 signal/power interfaces.
Extraction `nand_shunt_rc_v2/ef0d175bd6be9bcb` contains 121 R/68 C for drive-2
and 384 R/197 C for drive-8 before exact resistor reduction. The original
geometry `ea63ebb142230ada` remains preserved: it matched schematics but failed
M1 enclosure and MIM-to-unrelated-M3 clearance rules. The corrected geometry
passes both checks. These are component results, not DCC admission.

`nand_shunt_native_v2/1ac6dd7fabd5ca7d` is the original 48-case electrical pilot:
each extracted gate at SS40/SF40/FF0, 410 MHz, both input pin orders, 20/250 ps
slew and two external loads. A/B clocks offset by a quarter period exercise
610 ps NAND pulses. It checks actual input/output crossings, full-swing logic
settling and all six MOS terminal differences. The first two drive-2, SS40,
20 ps, 5 fF cases preserve output events but fail the terminal screen at
1.980/1.956 V. The first peak combines a 1.959 V output with a -20 mV local
body excursion. Heavier 20 fF drive-2 loading can also miss the full-swing
settling check despite preserving crossing counts. These are explicit load
limits/failures, not a relaxed voltage bound. A separate output-3x3-MIM layout
experiment tests additional damping without changing any transistor size.
Its first geometry `nand_shunt_physical_v2/e6936ac0b1d21df1` preserves unique
LVS but fails one MIM/M3 clearance rule per gate. Raising the output escape
from 10.0 to 10.8 µm produces
`nand_shunt_physical_v2/54edb7bb83c9c87a`: both gates pass DRC/LVS, and fresh
RC/topology receipt `nand_shunt_rc_v2/2bfbb5b632ecca00` passes. The new 48-case
electrical comparison is `nand_shunt_native_v2/85a89de29ccff159`. Its first two
drive-2 SS40/20 ps/5 fF cases now pass events, full-swing settling and terminal
screening: peaks fall from 1.980/1.956 V to 1.931/1.924 V. A subsequent
passivity audit invalidates these RC models (see below). The finite-transient
numbers remain diagnostics, not component timing/stress qualification.
Both isolated-gate cohorts are archived incomplete. Passing geometry does
not select this variant.

### Joint conditioned DCC and native reset release

The joint source pilot now connects the continuous conditioner to the actual
running buffered-TG DCC. A static native two-register controller asynchronously
clears both master/slave states and requires two new conditioned-clock edges
before reset release. A matching controller loads the other phase. The only
external ideal startup stimulus is REQUEST; RESET_N comes from real native
storage. Clock-stop/retrain tests cover stopped HIGH and LOW states. This
source experiment does not replace the production clock-hold control topology
or shorten the 256-actual-clock hardware warmup.

The first controller in `conditioned_dcc_v2/b72aae608fddc043` used redundant
tied REQUEST NAND inputs. The first two cases passed events and mean timing
but exceeded the terminal limit inside that controller only. Versioned
`native_clock_release_v3.py` uses REQUEST directly as first-stage data and one
inverter for its complement. Both asynchronous internal clears remain. The
replacement `conditioned_dcc_v2/96f84f2b4b28c340` tests both TG ratios N1/P3 and
N1/P4, SS40/SF40, three slew pairs and 30%/70% duty at 410 MHz/20 fF. Its first
twelve N1/P3 cases at SS40/SF40 pass startup, events, actual two-edge reset release,
common-mode, mean timing and every MOS terminal screen. The first four mean
half-cycle errors are 16.9–23.1 ps; the worst across all twelve is 38.93 ps,
with a 1.9402 V maximum low-voltage MOS terminal difference. N1/P4 cases are
running; no full-PVT
selection or native RC timing is claimed. Independent raw verification waits
for the whole cohort to finish.

The superseded controller cohort was drained through receipt
`superseded_clocking_drain_v2/1648525_443551665`: exact coordinator identity and
held lock inode were verified, future dispatch stopped, healthy solver/export
children finished, and four completed summaries plus six retained case folders
were inventoried before coordinator retirement. The original artifact remains
incomplete and unchanged. Neither running replacement nor threshold campaign
was restarted. Bound producers and failed geometries remain immutable.

### Native component RC clock assembly

`clock_cell_access_v2/134f0db87cf54b71` proves existing private-node LI access
against exact native transistor sources for NAND2_4, NAND3_2, INV1, INV8 and
BUF8. The NAND3's two private stacks remain distinct and both have LI access.
The inverters need only output shunts; BUF8 also needs its internal inverter
node shunted. These are label-only proofs with no modified native masks.

Physical family `clock_cell_shunts_physical_v2/5b3cb85905697901` passes zero
DRC and unique LVS for six variants: NAND2_4/NAND3_2 with 3x3 output MIM,
INV1 with 2x2, INV8 with 4x4, and BUF8 with either 2x2 or 4x4 output MIM.
Every private stack/buffer node has its own native 2x2 MIM. The buffer variants
serve the DCC isolation and the continuously loaded clock/monitor paths.
The failed first geometry `942016c151757a71` and next `de37deaad4a72bcd`
remain intact: generic pin/contact placement shorted NAND3 B/Y and A/stack
nets, then the narrow inverter's output/input escapes. Selecting separated
native LI contact locations and separating input/output vertical routes fixes
the actual shorts. The original jobs terminated at the strict LEF interface
guard; their stale `routing` state files are not evidence of live jobs.

Fresh family RC/topology receipt `clock_cell_shunts_rc_v2/0730f91e2238a256`
passes all six. Before exact resistor reduction, the respective R/C counts are
215/100, 174/102, 65/25, 214/88, 275/114 and 274/102. All bulk connections and
the RC-separated terminal nodes remain present; no body-node alias removes
the local excursions observed in the first NAND pilot.

The complementary TG pass network now has actual guarded-MOS layouts for
N1/P3 and N1/P4: `tg_xor_physical_v2/cd7f1e9ec225297f`, both zero DRC/unique
LVS. They retain exactly the eight source-sized MOS devices and the native
2x2 XOR-output MIM; storage and buffers are separate components. Their initial
layouts are about 134 x 37 µm. Fresh RC/topology receipt
`tg_xor_rc_v2/66a14c9b49abe012` passes both, with 796 R/137 C and 900 R/137 C
before reduction. This layout is an electrical experiment, not an area or
interconnect timing claim.

`native_clock_components_v2/5e946e50652708ef` assembles those actual component
RC models with the larger-output-shunted NAND2_2/NAND2_8 models from
`nand_shunt_rc_v2/2bfbb5b632ecca00`. The DCC, both native two-edge reset
controllers and all four clean/monitor buffers are now hierarchical extracted
components. It retains the analog conditioner source and actual distributed
bias RC. Every extracted instance maps ports by name. Recursive MOS coverage
retains separate drain/gate/source/body RC vertices: **880 MOS per case**,
including 280 in the DCC and 192 in each reset-controller replica.

The eight-case pilot tests both TG ratios, SS40/SF40 and 30%/70% duty at
410 MHz/20 fF with matched raw slews. Its decks and complete device coverage
regenerate successfully. Its first cases fail numerically before clock startup;
this cohort is archived incomplete following the passivity finding below.
Inter-component wires are still ideal; the next routed backend needs
fresh whole-layout RC. No whole-backend, all-PVT or PHY admission follows from
these component proofs. The software regression passes all 1,698 tests without
skips (`build/native-clock-components-v2-full-tests.log`).

### Passivity repair before native timing qualification

`rc_passivity_v2/b7f074f8e2f99245` identifies negative parasitic capacitors in
seven of the ten first component models. Their capacitor matrices have
negative diagonal entries, giving explicit negative-energy basis-vector
witnesses at internal vertices. In NAND8, `B.n15` has a -3.81621 fF capacitor
to VGND and no intrinsic MOS or MIM terminal on that vertex. The first joint
RC simulations abort near 17.3 ps, before raw clocks start at 22 ns. Isolated
NAND8 runs also spend hundreds of thousands of steps near 17–18 ps.
`rc_passivity_v2/651ae98a9ba3bb5c` binds the issue to both isolated-gate
cohorts. Their timing/stress diagnostics are **not qualification evidence**,
even where the transient finished.

This does not invalidate source-only cells or DRC/LVS. Bias receipt
`rc_passivity_v2/daf4709e5246a6fe` confirms positive R/C elements in the
unchanged bias library. Receipt `rc_passivity_v2/72f07ac0eb6b515d` separately
confirms all four retained DCDL compound RC models have positive elements.
The earlier routed clock-hold DCC is also passive in
`rc_passivity_v2/66feb64fa88260ba`; its prior timing failure is not explained
by this particular defect. These certificates concern RC signs, not whole-chain
timing.

The versioned flat extraction experiment uses `extract no resistance` before
initial extraction, one explicit unsimplified `extresist` pass with zero
threshold/mindelay/minres, and `ext2spice hierarchy off` plus an explicit top
subcircuit. This removes negative capacitors from all ten regenerated
components without deleting, clipping or relocating any element. The pinned
tool is Magic 8.3.623. The upstream [command documentation](https://github.com/RTimothyEdwards/magic/blob/master/doc/html/extresist.html)
describes these controls; a later [upstream issue](https://github.com/RTimothyEdwards/magic/issues/557)
also reports capacitance problems with hierarchical output on another PDK.
That report motivated this controlled experiment, not a conclusion about our
specific root cause. Several extraction controls change together, so this
does not isolate which one caused each former defect.

Flat output appends `$ **FLOATING` comments to some parasitics. The old
topology collapser recognized only four-token R/C lines, leaving commented
parasitics in the wire-collapsed netlist and causing false LVS mismatches.
A versioned auditor strips inline comments before the unchanged collapse,
preserving every native MOS/MIM. Fresh independent topology receipts now
pass with positive R/C elements:

- NAND2_2/NAND2_8: `passive_clock_rc_verification_v2/6e12628bd8ac8bc9`.
- Six qualifier/NAND3/inverter/buffer variants:
  `passive_clock_rc_verification_v2/92eed0de8314254e`.
- Both guarded TG XORs: `passive_clock_rc_verification_v2/b6bca7b2eadf7928`.

The original flat-extraction receipts `acde423833429b59`, `92f2004644d6f040`
and `ecd1efe7bfaab12c` remain preserved with their false topology failures.
No original extracted file or report was edited to make the new audit pass.
`extract_native_flat_v4.py` rejects nonpositive resistors or negative
capacitors before marking extraction successful. Tests cover that gate,
comment handling, and refusal to signal unrelated or unfrozen jobs.

Three separate drain receipts preserve the invalid cohorts:
`1652238_443753319` retains 24 summaries/26 case folders;
`1653853_443788595` retains 26/28;
`1657643_443902568` retains 7/8. Each exact coordinator was verified and
frozen before future dispatch stopped. Four owned SPICE leaves using the
proven-nonpassive libraries were terminated with per-PID/start/argv and partial
raw-time receipts; adapters exited and all files were inventoried before
coordinator retirement. Source/threshold solvers were not signalled, and no
dispatcher lock inode changed. These are archived incomplete campaigns.

Replacement `native_clock_components_v2/fab3576c6ca5b3c8` uses only the ten
positive-element, independently topology-verified RC models. It retains all
880 MOS witnesses, the same eight-case matrix and source startup stimulus.
Its first two simulations have advanced beyond 4.5 ns, past the old pre-clock
failure. They are still running; native timing/stress results are unproven.
Independent whole-cohort raw verification is queued. The complete software
suite passes **1,706 tests without skips** in
`build/passive-native-clock-components-v3-full-tests.log`.

The next integration must finish the joint source matrix and independent
waveform verification, then qualify the component-RC assembly and route the
physical DCC/reset/clock backend. Whole-backend RC, all 15 PVT and
390/400/410 MHz, actual permanent
measurement loading, and closed-loop DLL/RX/full-link qualification remain
required. Production control RTL still has its clock-model admissions closed.

### Approved duty range and native integration status (2026-11-04)

The user-approved reference-clock input duty range is now **40%–60%**.
`clocking_duty_v2_2.json` applies only that override to the SHA-bound original
descriptor. The output mean half-cycle error limit remains **50 ps**;
390/400/410 MHz, all 15 process/temperature combinations, fixed supplies and
all other requirements remain unchanged. Earlier 30%/70% campaigns retain
their original identities and continue without restarting healthy solvers.
The four-case stronger-storage native pilot
`native_clock_components_v2/363a482d0837cc35` tests both new duty endpoints
at SS/40 C, 410 MHz with one or three actual clock drivers. It is running;
neither that pilot nor its queued independent verifier has admitted the PHY.

The source conditioner/DCC matrix `conditioned_dcc_v2/96f84f2b4b28c340`
passes all 24 cases. Independent receipt
`conditioned_clock_verification_v2/d2819f2b5a574d05` regenerates libraries,
decks and MOS coverage and remeasures the raw waveforms: worst mean
half-cycle errors are 38.921 ps (P3) and 48.482 ps (P4), with a worst
low-voltage MOS terminal difference of 1.94012 V. This is a two-PVT source
pilot, not physical or all-PVT qualification.

The passive component-RC baseline now reaches clock startup. Its first two
SS/40 C cases fail reset release rather than numerical convergence.
`native_clock_release_failure_v2/d2139c60ceb19998` binds the raw/deck
identities and diagnoses saved MOS terminals through the extracted resistor
graphs: at 30% duty the master sets but the slave does not latch; at 70%
the master does not set. The stronger native-storage experiment retains
these failures. Its 70% one-driver case releases reset and meets steady
half-cycle timing (9.624 ps mean error), but misses the first expected P0
event. Startup and event-integrity requirements remain enforced.

Whole-bank routing now preserves all 174 intended instance connections,
passes detailed routing and antenna checks, and reaches GDS DRC/LVS.
Metadata receipt `dcdl_macro_boundaries_v2/ec13d360f6f77457` supplies the
required placement boundaries. Frame receipt
`dcdl_macro_frames_v2/7dcd08948d158942` then normalizes all six macro
GDS/LEF coordinate frames, preserving native geometry under a verified rigid
translation. This fixes an observed mismatch between streamed GDS placement
and routed OpenDB pins. The resulting bank run
`dcdl_bank_physical_v2/ea909f46b30b7d57` still fails signoff: 143 Magic DRC,
36 KLayout DRC and 33 LVS errors remain. It is not a clean physical bank;
fresh whole-bank passive RC and native delay/ROM qualification remain pending.

The complete software regression passes **1,722 tests without skips** in
`build/approved-duty-and-bank-frames-v2-full-tests.log`. This validates the
software checks and generators, not the unfinished native timing or layout.

### Clean whole-bank physical signoff

Bank run `dcdl_bank_physical_v2/3a29043d4903f11c` completes successfully
with zero routing DRC, Magic DRC, KLayout DRC, LVS errors and antenna
violating nets/pins. Netgen reports a unique match, and the independent final
OpenDB connection check preserves every intended instance and signal/power
connection. Clock timing, delay range and the legal-code ROM remain unqualified.

The fixes preserve all native devices: frame/keepout receipt
`dcdl_macro_frames_v2/a2fc8fb180bdd025` adds M3 routing obstructions around
MIM markers with 1.34 um clearance (0.14 um plate enclosure plus 1.2 um
unrelated-metal spacing), without changing any physical mask or pin. Run
`dcdl_bank_physical_v2/90abcc8ddeefe82a` proves that this clears the capacitor
spacing errors, but retains two untapped nwell islands and fails signoff.
The clean successor uses actual `tapvpwrvgnd_1` row endcaps to supply local
well contacts. Earlier failing layouts and their metrics remain preserved.

`extract_dcdl_bank_rc_v2.py` requires the clean physical gates, repeats the
final connection check, and checks continuity of both final power grids before
fresh flat extraction. Its native reference expands the actual final OpenDB
instances, including routing-added diodes and filler/decap cells, through each
macro's own schematic scope. It preserves primitive parameters and unit
suffixes without resizing or splitting devices. The preflight on the earlier
bank expands 1,214 routed instances to 2,884 native primitives; this is a
reference-generation check, not an extracted topology result. Whole-bank
extraction must separately pass positive-element screening and strict Netgen
comparison after comment-aware RC collapse. Macro-level LVS alone does not
replace that expanded audit.

Whole-bank RC campaign `dcdl_bank_rc_v2/4b6f1c51ef43e238` completes and passes.
Its fresh final-OpenDB check passes, and OpenROAD confirms all shapes on each
of VPWR and VGND are connected. The clean bank reference expands 1,205
placed instances into 2,684 native primitives. Fresh extraction from the actual
clean GDS produces 87,565 resistors and 22,956 capacitors, with positive-element
screening passed. Exact positive-conductance star-mesh reduction retains
61,876 resistors; a separate reread of the hash-checked simulator-facing model
also passes elementwise passivity. All 50 formal ports are retained. Strict
Netgen comparison of the wire-collapsed model against the fully expanded
native reference reports a unique match. This qualifies the bank's extracted
DC topology and passive RC, not its delay range or timing. The
complete pinned-environment software suite passes **1,730 tests without
skips** (`build/whole-bank-rc-admission-v2-full-tests.log`). Earlier host-only
and tools-Python regression attempts lack the required scientific Python
dependencies; they are retained as failed environment attempts, not regression
evidence. Use `make test-full` for the pinned complete suite.

The original passive component-RC clock cohort `fab3576c6ca5b3c8` has now
finished: six cases fail reset release; the remaining SF/40 C cases fail event
integrity and exceed 50 ps mean half-cycle error (82.699 ps P3, 135.504 ps P4).
The stronger-storage 30%/70% cohort `786085a1def9aeb4` also completes without
a qualifying case: two reset-release failures, a one-driver 70% startup/event
failure, and a three-driver 30% event failure despite 13.346 ps steady mean
half-cycle error. The approved 40%/60% cohort is separate and remains running.
These results keep reset release and first-event timing as active native-clock
work; they do not relax either requirement.

### Routed-bank timing pilot and phase-qualified reset prototype

`routed_dcdl_bank_v2/5dadafbb1d5d8a27` is the first timing campaign using
the complete clean bank's native RC model. Six cases cover SS/40 C and FF/0 C
at (coarse, fine) = (0,0), (0,31), (1,0), with 20 fF output load and 100 ps
input slew. Each static code receives two isolated pulses in separate 10 ns
windows, retaining absolute rising/falling delay epochs. The independent
consumer regenerates the decks and all 2,609 MOS witnesses, rereads every raw
trace, checks minimum quarter-period headroom, and conservatively compares
both polarities of coarse/fine overlap across the repeated pulses. The
campaign is running; timing and overlap results are not yet available. These
six cases do not provide dense fine-code steps, code-update stress, all-PVT
coverage or a legal-code ROM.

New native runs use `run_native_binary_v2.py` to retain and validate complete
ngspice binary waveforms without exporting every internal terminal to ASCII.
It retains the same model, Gear/tolerance/KLU settings and full transient
duration, checks the pinned runtime, rejects pre-existing outputs, and checks
all requested vectors, time ordering and finite samples. The memory-mapped
reader avoids loading duplicate multi-gigabyte arrays. Existing bound runs
and the shared six-engine dispatcher remain unchanged; both new campaigns
use at most two workers each. Physical receipt validation still executes under
its exact recorded tools-Python interpreter before scientific-Python waveform
work, preserving the original tool identity.

The approved-duty one-driver cases 0/1 in `363a482d0837cc35` now finish.
At 40%/60% duty they pass terminal stress, two-clock readiness and steady mean
half-cycle error (10.683/9.448 ps), but fail startup/event integrity: release
occurs at 34.0885/34.0488 ns, and the first subsequent P0 event produces no
output transition. The three-driver cases are still running. Narrowing the
duty range fixes these two cases' failure to release reset, but does not fix
release-phase alignment; the event analyzer and 50 ps output limit remain
unchanged.

`native_phase_clock_release_v2.py` retains the native two-register readiness
chain and replaces its direct output qualifier with low-phase arming followed
by sticky high-phase release. All added storage clears asynchronously from
REQUEST, including with a stopped clock. This is 28 real NAND/inverter gates
per controller, assembled from the existing passive, DRC/LVS/topology-verified
component RC models. Boolean tests cover late readiness and stopped-clock
clear; they do not establish native setup/hold or release latency.

Native campaign `native_clock_components_v2/802cabc7d3ad7564` binds both
retained failed raw/deck identities and tests the new controller at 40%/60%,
SS/40 C, 410 MHz, 20 fF, with one/three actual clock-driver instances. The
two variants retain 1,560/1,648 MOS witnesses. It is queued under the shared
dispatcher, with independent library/deck/MOS regeneration and raw
verification scheduled. Both the analog conditioner source plus native bias
RC and ideal inter-component wiring remain explicit limitations. Whole
clock-backend routing, full-PVT timing and PHY admission remain open.

The complete pinned regression passes **1,739 tests without skips** in
`build/phase-armed-release-v2-full-tests.log`. This is software verification;
neither new simulation campaign has supplied a native timing qualification.

### Routed timing limits and narrower repair experiments

The first two complete SS/40 C routed-bank cases have no numerical errors and
pass all 2,609 MOS terminal screens. At minimum code (0,0), the initial/repeated
rising delays are 950.018/947.087 ps and falling delays are
1072.075/1072.062 ps. These miss the required 609.756–641.026 ps quarter-period
range. At (0,31), rising delay is 1375.090/1372.137 ps and falling delay is
1596.760/1596.771 ps. Their worst terminal differences are 1.938652 and
1.938491 V. The remaining coarse/PVT cases and independent whole-cohort
verification are still running. Clean layout, passive RC and correct pulse
epochs therefore have not established a usable quarter-period section.

Loading receipt `routed_bank_loading_v2/4f1ca4e225edbbc6` identifies the path
nets through resistor connectivity without changing the simulation network.
The return net r0 has 238.982 fF of external passive capacitance, including
169.768 fF to VGND, compared with 28.494 fF on f0 and 30.503 fF on t0. Its
native fanout includes 55 drain, 55 source and four gate terminals plus the
direct 4x4 MIM shunt. These passive totals exclude intrinsic nonlinear MOS/MIM
capacitance; they identify a loading concentration rather than proving an
exact attribution of transient delay. The bank's redundant input/output
buffers and fine-bank placement/loading now need joint investigation before
another full implementation is selected.

`weighted_fine_bank_v2/43447c0bbcb6ec85` tests a five-bit fine-bank alternative
while the complete thermometer-bank runs continue. It retains every native
coarse stage and the four actual compound-core RC models. Five switched MIMs
have nominal areas 6/12/24/48/96 square micrometres, preserving the former
31-unit total of 186. Two switch-size profiles compare fixed widths with
1/2/2/3/4 scaling. Both retain native complementary control buffers,
discharge switches, 2x2 control shunts and the shared 4x4 node shunt. Four
SS/40 C cases cover both profiles and coarse 0/1 with fine codes
0/1/16/31/0, input slew 100 ps, control slew 20 ps and load 20 fF. All 2,375
MOS witnesses per profile are saved, including code-update intervals.
The campaign and independent regeneration/raw verifier are queued under the
unchanged six-engine dispatcher, with at most two workers. Fine switches,
control cells and common wiring are source-only here. Binary MIM areas alone
do not prove binary electrical weights, monotonicity or 20 ps legal gaps;
dense common-code, physical RC and all-PVT qualification remain necessary.

The complete 40%/60% stronger-storage clock cohort `363a482d0837cc35` has now
finished. Independent receipt
`native_clock_components_verification_v2/30873f09970e20ea` regenerates all
libraries, decks and MOS coverage and remeasures all four raw waveforms.
Every case passes steady mean timing, voltage screening and two-clock reset
readiness, but fails first-event integrity. Mean errors are 10.683/9.448 ps
for one driver and 10.694/9.479 ps for three drivers at 40%/60%. The latter
pair passes first-phase polarity but still misses startup events. None is
admitted. The phase-armed NAND prototype `802cabc7d3ad7564` is still running;
preliminary traces show no release in its first case and multiple releases in
its second. Those observations are not final whole-run measurements and do
not justify selecting that architecture.

Alternative `native_clock_components_v2/acc8cd8e1df679ed` uses two unmodified
source `dfrtp_1` or `dfrtp_2` asynchronous-clear readiness FFs per controller,
followed by the existing actual output-buffer RC macro. Both FFs clear from
REQUEST; second-stage data comes from first-stage Q. This data saturates
after readiness, unlike the earlier continuously toggling FF/XNOR DCC that
failed private-node stress. The unchanged passive-RC DCC and one actual
clock driver per phase remain connected. Four SS/40 C, 410 MHz, 20 fF,
100 ps slew cases test both FF drives at 40%/60% duty, retaining 852/860 MOS
witnesses. The experiment and independent verifier are queued. Native FF
private-node stress, first-event timing and fresh FF physical RC are required;
standard-cell provenance is not a substitute for those proofs.

The complete pinned software suite passes **1,749 tests without skips** in
`build/native-ff-and-weighted-fine-v2-full-tests.log`. All old and new failed,
partial and running artifacts remain intact. Production model admissions stay
closed, and full DLL/RX/link/OpenPLL qualification remains unfinished.

### Direct-port bank reaches clean native RC

`dcdl_mim_bank_direct_v2.py` removes only the two compound input/output
buffers from the 174-instance bank, connecting IN to the former f0 net and OUT
to the former r0 net. Every coarse stage, fine switch, control buffer, tie and
shared MIM remains unchanged. The external thermometer-control interface is
retained. This is a separate 172-instance physical variant, not an edit to the
old bank or its bound timing evidence. Its eventual upstream driver, downstream
load and multi-section clock propagation still need native qualification.

Preflight `dcdl_bank_direct_assembly_v2/759e6c27363975af` checks all 172
instances, 94 macro placements and 78 native standard cells in OpenDB. It
reuses the exact normalized macro views from the clean retained bank, including
their MIM keepouts. Fresh run `dcdl_bank_physical_v2/a04b1f6612f4d8c4` then
passes detailed routing, Magic/KLayout DRC, LVS and antenna checks with zero
errors. The final database check preserves all intended connections and rejects
unrequested signal buffers; none was inserted to restore the deleted stages.

Fresh extraction `dcdl_bank_direct_rc_v2/1d3adf1f73d5cc61` verifies continuity
of both final power grids and yields 88,872 resistors and 22,759 capacitors,
all passing the elementwise passivity gate. Exact positive-conductance reduction
retains 62,482 resistors. Strict comparison against the fully expanded native
reference, containing 2,643 primitives from 1,238 final placed instances,
matches uniquely. This is physical/passive-RC/DC-topology proof, not a timing
or ROM admission.

Timing campaign `routed_dcdl_bank_direct_v2/88e8378abb06e188` is queued with
seven cases and 2,569 MOS witnesses per case. It retains the original two-PVT
SS/40 C and FF/0 C minimum, maximum-fine and next-coarse tests at 100 ps input
slew, and adds an early SS/40 C minimum-code case at 250 ps input slew. All
use two absolute-epoch pulses and 20 fF load. The independent consumer requires
all seven raw cases, deck/MOS regeneration and the maximum-slew stress/range
check. This matrix does not cover the 20 ps input-slew boundary, dense codes,
actual upstream-driver loading, a four-section chain or full PVT; those remain
open. Timing benefit from removing the buffers has not yet been demonstrated.

The first two native-FF release cases in `acc8cd8e1df679ed` also complete.
At 40%/60% duty they pass first-phase polarity and show mean half-cycle errors
of 10.687/9.470 ps, but miss the first two expected output events. Their public
reset releases at 33.4618/33.4566 ns, leaving only about 389 ps before the
following P180 edge. Native-FF private-node screening fails: the 1.8 V FF
terminal-pair peaks reach 2.248545/2.248538 V. For example, XR180 first-stage
PFET X12 has about 0.00062 V on one terminal and 2.24917 V on another near
30.376 ns in the 40% case. These are distinct from the permitted larger
terminal differences in the 5 V analog devices. Native FF provenance therefore
does not establish electrical safety or first-event setup. Private-node
guarding/physical RC and separation of internal data preparation from public
clock release need investigation before another release controller is selected.
All unfinished and failed clock runs continue to retain their own evidence.

The full pinned software suite passes **1,754 tests without skips** in
`build/dcdl-direct-bank-coverage-v2-full-tests.log`. All model-admission bits
remain closed while native timing, DLL/RX/link and OpenPLL integration are open.

### Guarded native FF preparation: reset stress versus release latency

The approved input-duty endpoints remain **40% and 60%**, as recorded in
`clocking_duty_v2_2.json`. This narrows the reference-clock input check only;
the output mean half-cycle-error limit remains 50 ps. Existing bound 30%/70%
experiments retain their original identity and results.

Diagnosis `native_ff_guard_targets_v2/9a19ac3ff6a7d9eb` regenerates the first
two completed native-FF release decks and accounts for all 34 violating FF
devices per case. It selects six actual private nodes for native MIM guards;
it does not resize or replace native transistors. The new source controller
uses three asynchronous-clear native FFs: internal PREPARE rises after two
clock edges and the buffered public mask releases after three. A separate DCC
source variant enables its two data gates with PREPARE while retaining the
public output mask. That DCC variant has not yet been jointly simulated.

Isolated campaign `guarded_clock_prepare_v2/78ecab6164cb0fd9` tests 1 x 1 and
2 x 2 um guards at both duty endpoints and both stopped-clock levels, at
SS/40 C, 410 MHz and 100 ps input slew. It connects real passive-RC clock and
output buffers, two native NAND data-input loads and one public-mask load,
retaining 192 MOS witnesses. All eight complete waveforms pass the two-/three-
clock counts, asynchronous clearing and reassertion with a stopped clock.
All eight fail the 1.95 V terminal-pair screen, reaching 2.193--2.232 V.
Independent receipt `guarded_clock_prepare_verification_v2/4f3b294c97046382`
regenerates and remeasures all eight cases; neither guard profile passes.

Reset-specific diagnosis `native_ff_reset_guard_targets_v2/945463b891af84e7`
retains those six guards and identifies four additional actual private nodes:
`a_1270_413#`, `a_193_47#`, `a_639_47#` and `a_805_47#`. These excursions
arise in reset/clock-stop states absent from the original release-only sample.
Matched campaign `guarded_clock_prepare_v3/5eff041b5135f471` therefore adds
ten guards per FF and repeats the same eight cases without changing the old
producer or its artifacts. All eight complete without numerical errors and
retain the expected counts and stopped-clock clearing.

The smaller guards pass stress only when the clock stops high; low-stop cases
still reach 2.008672 V. Their public-release latency is approximately 891 ps.
The larger guards pass stress in all four cases, with peaks below 1.910 V,
but release 1,233.854--1,235.012 ps after the qualifying edge. This exceeds
the 410 MHz half-period by 14.341--15.500 ps; internal preparation has only
66.547--67.513 ps of margin to that half-period. Neither profile therefore
passes the complete isolated-counter feasibility gate. Independent receipt
`guarded_clock_prepare_verification_v3/f2d4cc5fc5e5dccf` regenerates and
remeasures all eight complete waveforms and confirms both profile failures.
No actual first DCC event, physical guarded-FF extraction, full PVT or PHY
admission follows from these source-level experiments. A faster phase-qualified
release path or selectively sized guards needs a fresh versioned experiment;
uniformly increasing guard capacitance has exposed a timing tradeoff.

The original buffered-bank campaign `routed_dcdl_bank_v2/5dadafbb1d5d8a27`
also finishes all six cases. Independent receipt
`routed_dcdl_bank_verification_v2/b5d120ed0fcffceb` confirms its failure:
SS/40 C minimum rising delay is 947.087 ps, above the required quarter-period;
the maximum-fine to next-coarse rising gaps are 168.561 ps at SS/40 C and
39.917 ps at FF/0 C. Both next-coarse cases fail terminal stress. The separate
direct-port bank and weighted-fine campaigns remain in progress; neither is
admitted on the basis of these results.

The full pinned software suite passes **1,764 tests without skips** in
`build/guarded-clock-prepare-reset-v3-full-tests.log`. These are software checks;
the circuit failures above remain qualification failures. All failed and
partial artifacts are retained and all production admissions remain closed.

### Strong NAND2 phase-qualified release experiment

The next source controller, `guarded_phase_clock_release_v2.py`, retains two
native asynchronous-clear readiness FFs and all ten diagnosed MIM guards per
FF. It replaces the third release FF and its output buffer with two sticky
phase-qualified states made from already extracted, passivity-checked native
NAND2_8 macros. The first state arms after readiness while CLK is low; the
second sets the public release on the next high phase. REQUEST asynchronously
clears both readiness FFs and both sticky states, including stopped-clock
operation. This is a fresh diagnostic candidate, not a production selection.

The earlier phase-armed prototype used NAND3 feedback with one input tied to
VPWR. Its Boolean function is NAND2(Q, REQUEST); using the actual strong NAND2
macro removes the redundant transistor stack. Both phase setters also use
NAND2. Their readiness/armed inputs are cleared by REQUEST; no new asynchronous
set permission is introduced. Actual reset races, arming setup and loaded
release latency still require waveform evidence.

Campaign `guarded_phase_clock_release_v2/61817fe170bad6b5` is running eight
SS/40 C, 410 MHz, 100 ps input-slew cases: two guard sizes, 40%/60% duty and
both stopped-clock levels. All two data-gate NAND inputs and the output-mask
NAND input now load the public release together, matching the original DCC
reset fanout; PREPARE is only the diagnostic second-FF readiness node. Each
case saves all 350 actual MOS terminal witnesses. The consumer retains the
two-/three-clock counts, full-waveform voltage screen and stopped-clock clear
and reassertion checks, and additionally requires arming while CLK is low,
before the release clock, with a cleared arm after stopped-clock reset.
An independent consumer is watching this exact immutable campaign.

This assembly uses extracted NAND/inverter/clock-buffer components and source
guarded FFs with ideal inter-component wires. Fresh guarded-cell geometry/RC,
actual DCC first-event behavior, joint routing and all-PVT qualification remain
required. The new tests explicitly reject high-phase arming and uncleared
sticky state; they do not establish analog feasibility.

Meanwhile six of seven direct-port bank cases have completed. The SS/40 C
minimum-code repeat pulse measures 452.997/455.386 ps rising/falling delay at
100 ps input slew, and 481.525/511.306 ps at 250 ps slew; both pass the voltage
screen and fit below the fast quarter-period. SS maximum-fine rising delay is
792.894 ps, while next-coarse minimum rising delay is 1,024.654 ps, leaving a
231.760 ps gap. That next-coarse case fails stress at 2.015353 V. These are
producer measurements pending completion and independent verification of the
seven-case matrix. Removing port buffers therefore shows useful minimum-delay
headroom but does not yet solve coarse/fine overlap or coarse-stage stress.

The full pinned software suite passes **1,767 tests without skips** in
`build/guarded-phase-release-v2-full-tests.log`. The live circuit campaign and
its independent consumer have not yet established feasibility or admission.

### Localize stopped-clock reassertion stress and buffer REQUEST

The first two completed strong-NAND2 phase-release cases keep the expected
two-/three-clock counts, low-phase arming and stopped-clock clearing. Public
release takes 552.357 ps after its qualifying clock, versus approximately
891 ps for the smaller-guard three-FF counter. Both still fail voltage screening.
Diagnosis `guarded_phase_release_failure_v2/cccc41ace02b794e` independently
regenerates both complete decks, libraries and MOS coverage, checks retained
file hashes and localizes every failed terminal pair. It covers these two
completed cases only; the remaining campaign cases keep running.

All worst excursions in those two cases occur at the 23 ns REQUEST reassertion
with CLK stopped. The first low-stop FF reaches 2.008672 V across native
private nodes at 23.0103 ns. The sticky feedback NANDs also fail: for example,
the high-stop release feedback NFET reaches 1.969990 V at 23.0405 ns, with
approximately 1.8443 V on an output terminal and -0.1257 V on its actual
R-separated body terminal. This is local extracted body bounce despite a
stable external supply. These waveforms suggest testing a slower *physical*
REQUEST driver; they do not prove the repair works.

`guarded_phase_clock_release_v3.py` inserts the already extracted buf8_o4
between external REQUEST and all readiness-FF and sticky-feedback REQUEST
consumers. External REQUEST retains its 20 ps transition stimulus. No input
edge is numerically slowed, no voltage is clipped and every added buffer MOS
is included in screening. This tests a circuit change under the same stimulus.
Both buffer polarities, stopped-clock reassertion and reset clearing remain
covered by the complete-waveform checks. Buffered REQUEST itself must retain
two causal rising events and one falling event.

Matched campaign `guarded_phase_clock_release_v3/25c69fe1471210ba` is running
the same eight SS/40 C, 410 MHz, 40%/60% duty and low-/high-stop cases with
1 x 1 and 2 x 2 um guards. Its independent consumer is watching. Feasibility
has not yet been established. In particular, the completed 60%-duty cases of
the unbuffered candidate also fail the low-level arming check even though they
retain the two-/three-clock transition counts; REQUEST buffering alone is not
assumed to repair that separate phase-path timing issue. A shorter arming
path, such as a native inverting-input NAND replacing the separate clock
inverter and setter, needs a new experiment if this limit persists.

The full pinned software suite passes **1,769 tests without skips** in
`build/buffered-request-phase-release-v2-full-tests.log`. All electrical and
physical qualification failures remain retained, and no production model is
admitted by these diagnostic changes.

### Native NAND2B arm setter and physical FF-access evidence

The unbuffered strong-NAND2 release campaign now completes all eight cases.
Independent receipt `guarded_phase_release_verification_v2/61f35903007a843f`
regenerates and remeasures every waveform and confirms that neither guard
profile passes. The larger guards still reach 1.969996 V in the extracted
feedback NANDs, and the 60%-duty cases fail the low-level arming check. The
buffered-REQUEST comparison remains running. Its first six completed cases
remove the NAND stress failures; smaller-guard low-stop FFs still reach
1.982827 V, while the two larger-guard 40%-duty cases pass the isolated
counter checks. Completed 60%-duty cases still fail low-level arming.

`guarded_phase_clock_release_v4.py` replaces only the separate CLK inverter
and arm setter with `openlvds_nand2b_4_pair_v2`: A_N=CLK, B=PREPARE and
Y=arm_sn. It preserves buffered REQUEST, both guarded source FFs, every
sticky feedback element and the public release path. This uses the exact
existing native compound GDS/RC, not a Boolean or ideal timing replacement.
`phase_release_rc_families_v2.py` requires the four compound physical and
strict-topology receipts, native source/GDS identities and positive-element RC
in addition to the retained clock-cell receipts. Its read-only bound check
uses the exact recorded Magic/Netgen binary paths without rerunning a physical
job or changing any existing extraction.

Campaign `guarded_phase_clock_release_v4/eb9bf06cd78f4ceb` is running the
matched eight cases with its independent consumer watching. The first four
completed cases all pass low-level arming, including 60% duty; public-release
latency is approximately 536--547 ps. They remain electrical failures: the
smaller-guard low-stop FFs still exceed 1.95 V, and the new native NAND2B arm
setter reaches approximately 1.9715 V in high-stop cases. These are producer
measurements, not a verified all-profile feasibility result. The faster arm
path therefore addresses one timing mechanism while leaving voltage and
physical-FF issues open.

Physical access probe `guarded_ff_access_v2/45be9f96a32eec57` retains an
unsuccessful diffusion-only label attempt. The native FF node `a_761_289#`
has its coordinate anchor on polysilicon, so that assumption is invalid.
The separate corrected producer `inspect_guarded_ff_access_v3.py` labels the
actual native N/P diffusion or polysilicon at each selected coordinate and
rejects ambiguous crossings. It changes labels/ports only, preserves every
native mask rectangle and compares the extracted circuit to the exact native
MOS source with the ten selected private-node ports exposed.

Corrected receipt `guarded_ff_access_v2/31e9072b18035154` passes unique LVS
and proves all ten selected nodes distinct. Six have surveyed existing LI
landing rectangles. Four do not: `a_1217_47#`, `a_1270_413#`, `a_639_47#`
and `a_805_47#`. This is a failed access-admission result under the current
landing rules, not a proof that no possible new contact or layout can reach
them. It prevents treating the source-level ten-guard FF as an already
implementable unchanged-mask cell. Added-contact/layout work or a different
readiness storage architecture must resolve those nodes before a guarded-FF
physical RC campaign can qualify this controller. A phase counter built from
the existing static macros is another architecture to investigate; it must
retain startup edge ordering, stopped-clock reset and all voltage checks.

The direct-port routed bank also completes and passes independent raw
regeneration/remeasurement in
`routed_dcdl_bank_direct_verification_v2/902ae2bfdcf4fde2`. Minimum-code
quarter-period headroom is at least 154.245 ps at SS/40 C with 100 ps input
slew, 98.450 ps at 250 ps slew, and 356.790 ps at FF/0 C. Coarse/fine gaps
remain: SS rise/fall 231.760/206.815 ps and FF rise/fall 46.370/78.897 ps.
The next-coarse cases fail stress at 2.015353 V (SS) and 1.990872 V (FF).
Both PVT groups fail sparse feasibility, and no legal-code ROM is admitted.

The full pinned software suite passes **1,774 tests without skips** in
`build/nand2b-and-guarded-ff-access-v3-full-tests.log`. Native electrical,
guarded-cell geometry/RC, whole-clock routing and full PHY qualification remain
open. All failed access attempts and circuit waveforms are retained.

### Alternating static-phase readiness architecture

The buffered-REQUEST comparison completes all eight cases. Independent receipt
`guarded_phase_release_verification_v3/46b9d505a4f9488c` regenerates and
remeasures the complete matrix. The larger guards pass all voltage screens,
with maximum terminal-pair difference 1.928114 V, but neither guard profile
passes full feasibility because 60%-duty low-level arming still fails. The
native NAND2B arm-setter candidate remains a separate running experiment.

`static_phase_clock_release_v2.py` now implements an alternative readiness
architecture entirely from the existing physical/passive-RC macros. It uses
six alternating sticky states: low0, high1, low1, high2, low2 and public high3.
Low0 qualifies a low phase after REQUEST before the first counted high phase.
High2 supplies diagnostic PREPARE; low2 supplies the sticky arm; high3 opens
the public mask. The initial low state is intended to prevent a REQUEST
asserted during a high phase from counting that partial high phase. Real
setup/hold and analog races remain waveform requirements, not consequences
of the Boolean description.

All six feedback paths share a real buf8_o4 REQUEST driver. High setters use
native shunted NAND2 macros; low setters use the actual NAND2B4-pair macro.
Drive-4 and drive-8 variants compare state-path speed against the real clock
and REQUEST fanout. Both retain the drive-8 public setter and output gate.
There are no source readiness FFs or private FF guard connections in this
candidate. Its individual macros already have native geometry, strict topology
and passive-RC receipts; the complete controller still needs physical routing
and fresh extraction. Component proof alone does not qualify this architecture.

Campaign `static_phase_clock_release_v2/2fe84bb44161f56d` is running eight
SS/40 C, 410 MHz, 100 ps input-slew cases: both drives, both approved duty
endpoints and both stopped-clock levels. Each case retains the original 20 ps
external REQUEST transitions, 2 ns reset/reassertion interval, seven real
loaded clock pulses and all three DCC reset-input loads on the public mask.
The two variants save 488/696 actual MOS terminal witnesses. In addition to
the retained two-/three-clock transition counts and 1.95 V voltage screen,
measurement checks low0/high1/low1 ordering, low-phase qualification and
clearing of intermediate states after a stopped-clock reset. Low0 may arm
again after reassertion with a stopped-low clock; high1, low1, PREPARE, arm
and public release must remain cleared until new clock activity.

The independent consumer watches this exact immutable matrix. It requires all
eight regenerated libraries/decks and complete raw waveforms, retaining any
reproducible event failures as negative evidence for the affected drive profile.
The candidate has not yet established native feasibility or an actual DCC
first event. No source FF repair, controller physical-RC, full-PVT, DLL or PHY
admission is inferred from it.

The full pinned software suite passes **1,777 tests without skips** in
`build/static-phase-release-v2-full-tests.log`. The new tests reject missing
profile coverage, bad intermediate phase ordering and uncleared stopped-clock
state. All prior failed and running artifacts remain intact.

### Return-mux delay bank and physically reachable NAND2B guards

The native NAND2B arm-setter campaign finishes all eight cases. Independent
receipt `guarded_phase_release_verification_v4/25d225f32860b5ba` confirms
the faster arming result but rejects both guard profiles: their maximum
terminal-pair differences remain 1.982825/1.972642 V. This does not repair the
guarded FF's physical-access limitation or admit a controller.

The all-static phase-counter campaign also finishes all eight cases, with
independent receipt `static_phase_release_verification_v2/b4731b4ce1f9a6cb`.
Every case retains the two-/three-clock transition counts. Drive-4 passes
phase ordering and stopped-clock logic, but only its 60%-duty low-stop case
passes full feasibility; voltage rejects the other three. Drive-8 reduces
some voltage excursions but introduces late initial-low qualification, and
its high-stop cases also fail reset clearing and voltage. Neither complete
drive profile passes; maximum voltage differences are 1.967293/1.967572 V.

Diagnosis `static_phase_release_failure_v2/d03a3298db2f7239` regenerates and
remeasures the three complete failed drive-4 cases. The 40%-duty low-stop
case peaks at 1.950415 V during initial qualification near 3.8565 ns, including
local body bounce. Both high-stop cases have floating NFET series nodes in
all three NAND2B low setters: initial setter stack nodes reach approximately
-0.1681 V while its output stays near 1.7992 V, and the following setters
retain approximately -0.1570 V against 1.8000 V near 25.04 ns. Slowing only
REQUEST is therefore not assumed to fix every failing setter. These results
remain electrical failures at the unchanged 1.95 V screen.

Native access proof `nand2b_access_v2/389725ef7a1d1742` passes exact-source
unique LVS and proves both NAND2B4 private nodes distinct with existing LI
landings: inverter node `a_27_47#` and series-stack node `a_215_47#`.
Unlike the four problematic FF nodes, these permit a concrete shunt layout
without adding diffusion contacts or changing native transistor masks.

Two native NAND2B4 shunt macros now add a 2 x 2 um MIM to each private node
and compare 1 x 1 versus 2 x 2 um public-output MIMs. The first physical
attempt `nand2b_shunts_physical_v2/ef841c7df56f6b98` preserves two LVS
passes but fails two Metal2 spacing checks per variant. Corrected producer
`build_nand2b_shunts_v3.py` chooses another independently surveyed inverter
LI landing away from the left rail straps. Fresh physical run
`nand2b_shunts_physical_v2/c94c88d0d7ffd713` passes DRC with zero errors
and unique LVS for both variants. No native transistor is resized or removed.

Fresh GDS extraction `nand2b_shunts_rc_v2/99b3d8b0d58b1782` uses the retained
flat, single-pass extraction and elementwise passivity gate. The variants
contain 291/292 resistors and 98/94 capacitors before exact positive-conductance
reduction. Both primary wire-collapsed topology comparisons pass against the
actual guarded source. Independent receipt
`nand2b_shunts_rc_verification_v2/dc43c73ad540c75b` confirms both complete
GDS/source/interface identities, elementwise passivity and unique topology
matches using comment-aware collapse. Native controller timing with these
models remains untested; adding
guards may consume arming margin and must not be inferred safe from geometry.

In parallel, `dcdl_mux_return_v2.py` replaces the old turn/pass/merge return
structure with a native inverting mux. It realizes
`r_i = coarse_i ? !r_(i+1) : f_i` using `MUX2I(!f_i, r_(i+1), coarse_i)`.
The last return retains two native inversions, preserving a two-stage final
turnaround. All sixteen coarse choices, fifteen gated forward stages and
thirty-one extracted 2 x 3 fine units remain. Native turn inverters are paired;
return muxes are paired, with four copies at the root to match its stronger
nominal drive. New compound mux/turn geometry is still required.

Campaign `dcdl_mux_return_v2/1eb79ae5fb488676` is running six SS/40 C and
FF/0 C minimum, maximum-fine and next-coarse cases, each with two isolated
pulses, 100 ps input slew, 20 fF load and 2,269 native MOS witnesses. Forward
drivers and fine units use their exact independently checked passive RC;
muxes, turn/control cells and common wires remain source-only. Internal
thermometer controls must also retain logic margins. Its independent consumer
is watching. This tests whether a shorter coarse increment can bridge the
measured gaps; it does not supply a physical bank, dense/common ROM, full-PVT
or periodic-clock admission. Source tests verify polarity and selected actual
depth at every coarse code, including the restored final turnaround.

The full pinned software suite passes **1,780 tests without skips** in
`build/dcdl-mux-and-nand2b-shunts-v2-full-tests.log`. Physical shunt DRC/LVS
and fresh RC checks are additional native evidence; all production admissions
remain closed pending electrical and integrated qualification.

### Apply independently extracted NAND2B guards to the static counter

`static_phase_clock_release_v3.py` keeps the drive-4 static counter and replaces
only each low-phase NAND2B4 pair with two independently extracted guarded
NAND2B4 macros. The first variant uses 1 x 1 um output guards; the second uses
2 x 2 um output guards. Both use the physical 2 x 2 um private-node guards.
REQUEST conditioning, high-phase setters, all state feedback, public-output
strength and the loaded clock driver remain the same. Correct mapping follows
the extracted port order, including the explicit power/ground terminals.

`static_release_rc_families_v2.py` requires both exact guarded macro names,
their complete independent RC receipt, clean physical reports, stored binary
identities, source/GDS hashes and passive-element checks. It also retains the
earlier native clock and compound receipts. No voltage trace, MOS or passive
element is clipped, removed or aliased when constructing this candidate.

Matched campaign `static_phase_clock_release_v3/3b8f6d1c2c2f9989` is running
eight SS/40 C, 410 MHz, 40%/60% duty and low-/high-stop cases, comparing the
two physical shunt variants. It retains the original seven pulses, 20 ps
external REQUEST transitions, 2 ns reset/reassertion interval and all three
DCC reset-input loads. Its independent consumer reuses the complete phase
ordering, stopped-state, count and voltage checks and regenerates both actual
guarded libraries. Feasibility remains unproven: the guards add real loading
and may reduce low-phase arming margin. Whole-controller wires, actual DCC
first-event behavior, full PVT and PHY admission remain open.

Both guarded variants retain 488 actual MOS witnesses per case. The full
pinned software suite passes **1,782 tests without skips** in
`build/guarded-static-phase-release-v2-full-tests.log`; matched analog cases
and their independent consumer continue running. These software checks and
the isolated macro RC proofs do not admit the integrated controller or PHY.

### Lower the native NAND2B body-return impedance

The guarded static-counter campaign completes all eight cases. Independent
receipt `static_phase_release_verification_v3/433b099a7794d47a` regenerates
and remeasures the whole matrix and rejects both variants. The maximum
terminal-pair differences are 1.969781 V for o1 and 1.956287 V for o2.
Completed 60%-duty cases pass voltage screening but fail low-level phase
qualification. Thus private-node guards alone do not establish controller
feasibility, and neither voltage nor timing failures are waived.

Diagnosis `guarded_static_phase_release_failure_v2/6a864d359568130b`
reproduces both first o1 failures. The remaining worst pair is now output
versus body, rather than the original unguarded floating stack: the initial
low setter has approximately 1.931505 V on Y and -0.038276 V on its actual
R-separated NFET body at 4.0055 ns. Both parallel macros show the same pair.
This identifies body-return impedance and output overshoot as the next
electrical mechanisms to test; stable external VGND does not force local
extracted body terminals to be ideal ground.

`build_nand2b_bodytap_v2.py` adds a complete row of thirteen native tap cells
below each guarded NAND2B4. The row is mirrored so its substrate contacts
face the native NFET region, with ground-rail location -0.4 um. Its separate
lower nwell rail is connected to VPWR at -3.12 um through a lower power trunk.
All native transistor masks, the two private MIM guards and each variant's
public output MIM remain unchanged. The new macros have distinct names and
fresh GDS; no retained prototype or RC model is edited in place.

Fresh physical run `nand2b_bodytap_physical_v2/1f230175810cee8a` passes zero
DRC and unique LVS for both o1/o2 tap-row variants. Fresh extraction
`nand2b_bodytap_rc_v2/d46e4b8f65596f09` retains 488/489 resistors and
121/117 capacitors before exact positive-conductance reduction. Both raw
element gates and primary topology comparisons pass. Independent receipt
`nand2b_bodytap_rc_verification_v2/bc0db584463b32eb` confirms exact two-variant
coverage, source/GDS/interfaces, positive passive elements and unique topology.

Read-only comparison `nand2b_body_resistance_v2/c18a95f510a9e8df` uses the
actual verified resistor networks. Maximum shortest-series-path bounds from
NFET bodies to VGND decrease from approximately 5,203.956 ohms to 2,748.999
ohms; the PFET-to-VPWR bound remains approximately 1,515.755 ohms. These are
upper bounds from one positive resistor path, not effective resistances or
transient predictions. Parallel paths and intrinsic junctions remain in the
unaltered simulation models. This diagnostic does not replace electrical
screening or admit a reduced model.

`static_phase_clock_release_v4.py` connects those actual tap-row RC macros
to the same drive-4 static counter, changing only the low-setter physical
models. Campaign `static_phase_clock_release_v4/c0bf7f7c59e1f899` is running
the matched eight SS/40 C, 410 MHz, 40%/60% duty and low-/high-stop cases,
with 488 native MOS witnesses per case. It retains seven loaded pulses,
20 ps external REQUEST transitions, the 2 ns reset/reassertion interval,
all three DCC reset-input loads and all earlier phase/count/reset/voltage
checks. Its independent consumer requires both complete regenerated variant
matrices. Whether the new contacts reduce peak voltage sufficiently remains
unproven, and the earlier 60%-duty timing failures remain an open requirement.

The full pinned software suite passes **1,785 tests without skips** in
`build/bodytap-static-phase-v2-full-tests.log`. The tap-row physical/RC proofs
and resistor-path analysis are additional scoped native checks. Actual DCC
first events, whole-controller RC, full-PVT and full PHY qualification remain
open; production admissions stay closed.

### Retain the stack guard while reducing inverter-node loading

The tap-row counter campaign completes all eight cases without numerical
errors. Independent receipt
`static_phase_release_verification_v4/a5e19eac8926fdb1` regenerates and
remeasures the whole matrix. Every case passes terminal screening; maxima are
1.943492 V (o1) and 1.946248 V (o2). Both 40%-duty cases in each variant pass
the complete isolated-counter gate. The 60%-duty cases still fail low-level
phase qualification, so neither variant passes the complete four-case profile.
The new contacts therefore address the measured voltage problem in this
SS/40 C matrix; full-PVT voltage qualification remains open.

`build_nand2b_stack_guard_v2.py` retains the mirrored thirteen-tap row and
2 x 2 um series-stack MIM, and removes only the added inverter-node MIM and
its route. It preserves the original native inverter node `a_27_47#` and
every transistor. The series node `a_215_47#` remains explicitly connected to
its physical guard through the proven MID0 access. The two variants retain
1 x 1 and 2 x 2 um public-output MIMs. This tests the timing cost of guarding
an inverter node that was not the localized failure in the retained drive-4
diagnosis. It does not presume that the native inverter is safe at every PVT;
all its actual MOS terminals remain screened at the same 1.95 V limit.

Fresh physical run `nand2b_stack_guard_physical_v2/597f324ab7f4a8d5` passes
zero DRC and unique LVS for both variants. Fresh extraction
`nand2b_stack_guard_rc_v2/cf3503a5a3efb48a` retains 479/480 resistors and
120/116 capacitors before exact positive-conductance reduction. Both primary
passivity and topology gates pass. Independent receipt
`nand2b_stack_guard_rc_verification_v2/62a9e4b71323a44a` confirms both exact
source/GDS/interfaces, positive elements and unique topology matches. These
are distinct macros and artifacts; earlier guards, failed waveforms and
running experiments remain intact.

`static_phase_clock_release_v5.py` applies these actual RC models to only
the three low-phase setters in the same drive-4 counter. All high setters,
feedback, REQUEST conditioning, public output and loaded clock driver remain
unchanged. Campaign `static_phase_clock_release_v5/69d0acd654522289` is
running the matched eight SS/40 C, 410 MHz, 40%/60% duty and low-/high-stop
cases with 488 MOS witnesses per case. The first two o1 cases complete and
pass the full isolated-counter gate, with peaks 1.940187/1.909628 V. The
60%-duty cases and complete profile proof are still pending. The independent
consumer is watching and retains every earlier phase/count/reset/voltage check.
No joint DCC first event, whole-controller RC, full-PVT or PHY admission
follows from these initial results.

The full pinned software suite passes **1,787 tests without skips** in
`build/stack-guard-static-phase-v2-full-tests.log`. Source tests verify that
only the series node is exposed for guarding, that both native transistors
in the test fixture remain unchanged and that all sequencing checks are
retained. The native layout/RC checks above independently cover the real cell.

### Complete stack-only guarded release counter result

The eight cases in `static_phase_clock_release_v5/69d0acd654522289`
complete without numerical errors. Independent receipt
`static_phase_release_verification_v5/7b739b8137745f14` remeasures every
case: both o1/o2 physical guard variants pass at 40%/60% duty and both
stopped-clock levels, SS/40 C and 410 MHz. This supersedes the pending
60%-duty status above. The original phase-order, three-clock release,
asynchronous clear, stopped-clock reassertion and 1.95 V terminal limits
remain enforced.

`verify_static_phase_profile_v2.py` additionally permits preselection only
of a complete four-case positive variant, binding all retained files and
independently regenerating and remeasuring both duties and stop levels.
The selected o1 receipt is
`static_phase_profile_verification_v2/c657a2d449809d32`. Its scope is the
isolated loaded counter, without whole-controller RC, full-PVT or PHY
admission. This allows joint DCC experiments without waiting for unrelated
variant results; the full eight-case independent receipt remains available.

### Joint conditioner/DCC restoration with static release

`probe_native_static_dcc_v2.py` binds the positive o1 counter receipt above
and restores both static controllers in the analog-conditioned clock/DCC
chain. Campaign `native_static_dcc_v2/8f73e3a90f1d54b3` has four declared
SS/40 C, 410 MHz cases: common release versus early internal data prepare,
each at the approved 40% and 60% duty endpoints. Supply voltages remain
fixed at 3.3 V and 1.8 V. This focused pilot does not replace the required
390/400/410 MHz and 0/25/40 C qualification matrix.

Each phase uses three actual extracted clock-driver components. In common
mode the public RESET_N qualifies both DCC data and its output mask. In
prepare mode only the two data qualifiers use PREPARE_0; the public output
mask still uses RESET_N. A separate own-phase counter produces
PREPARE_180/RESET_180. Both masks must follow at least three actual clocks;
preparation must follow REQUEST and precede its own public mask. The
original first-P180 startup, one correctly directed output per source
interval, common-mode and every MOS terminal-pair voltage check remain.
The mean output half-cycle error limit remains **50 ps**; individual
half-cycle excursions remain diagnostic.

The producer retains every complete raw waveform and failed result. The
independent `verify_native_static_dcc_v2.py` regenerates component libraries,
actual MOS witnesses and all decks, then remeasures every completed case.
The pilot and verification watcher run under
`openlvds-native-static-dcc-v2-pilot.service` and
`openlvds-native-static-dcc-v2-verify.service`, using the shared six-engine
dispatcher with at most two workers. Existing healthy solvers continue.

The conditioner is source circuitry with extracted bias; DCC, clock drivers
and counter use native component RC. Common wires and parallel-driver
routing remain ideal. There is no whole-backend RC, 256-clock hardware
warmup, full-PVT, link or PHY admission from these four cases. The original
release/deadline and qualification requirements remain open.

Validation: `make test-full` passes **1,789 tests without skips**
(`build/native-static-dcc-v2-full-tests.log`). New synthetic waveform checks
reject early masks, late prepare, missing output events and overstress.
A separate read-only regeneration check matches all four decks and all
1,588 actual MOS witnesses per case. At this checkpoint the joint pilot
is running with its first two cases queued for engine capacity; no joint
waveform result is claimed.

### Matched transient iteration allowance experiment

The original return-mux cases remain live. A read-only look at their flushed
binary prefixes found case 0 at 0.874060 ns (10,402 complete records) and
case 2 at 0.465713 ns (7,054 records), before the first 2.1 ns input edge.
Across the last 128 flushed records, the largest voltage range was only
5.3e-11/8.4e-11 V, despite accepted time steps down to 0.000244 ps. This is
non-gating progress telemetry, without complete-waveform or electrical
qualification. It motivates a numerical experiment rather than a conclusion
that these quiet intervals demonstrate a functional oscillation.

`probe_dcdl_iterations_v2.py` prepares two matched full-duration cases from
`dcdl_mux_return_v2/1eb79ae5fb488676`, retaining exact case 0/2 models,
component RC, tolerances, 2 ps maximum step, two input pulses, saved MOS
terminals and 20 ns stop. The only numerical change is `.options itl4=100`.
The [ngspice manual](https://ngspice.sourceforge.io/docs/ngspice-manual.pdf)
defines ITL4 as the transient time-point iteration limit (default 10).
No supply, circuit, device model, initial condition, voltage limit or timing
requirement is changed by this experiment.

Campaign `dcdl_iterations_v2/a994d04ddcc0bdbb` runs with two lower-priority
workers under the existing six-engine dispatcher. The original solvers
continue. Units `openlvds-dcdl-iterations-v2-pilot.service` and
`openlvds-dcdl-iterations-v2-verify.service` retain independent complete raw
remeasurement. The consumer regenerates every parent library and MOS
witness and checks every altered deck. Comparisons to original waveforms
are reported only for original cases that have completed, and include
maximum pulse-delay and individual MOS-peak differences. Missing baseline
results are explicit; no speed or equivalence claim follows from partial
traces. This experiment cannot admit a legal-code ROM or PHY.

The joint static-release DCC cases 0 and 1 have acquired simulator slots;
read-only prefixes reach approximately 5.09/4.46 ns. These are still before
the raw clocks start at 22 ns. There is no complete joint result yet.

Validation: `make test-full` passes **1,791 tests without skips** in
`build/dcdl-iterations-v2-full-tests.log`. Tests ensure the matched deck
changes only its title and iteration allowance, and reject pulse-epoch or
MOS-coverage mismatches in numerical comparisons. The matched simulations
remain queued at this checkpoint; no runtime improvement is claimed.

### Direct-port weighted fine bank with an actual guarded NAND2B comparison

The original weighted bank still contains the two compound port buffers.
Their cost is already established separately by the buffered/direct routed
bank measurements; that original weighted campaign is retained and continues.
`dcdl_weighted_direct_v2.py` now removes only those port buffers, aliases
f0/r0 to IN/OUT and retains all sixteen coarse choices. Its five root-sized
switches preserve the original 6/12/24/48/96 um2 MIM weights, total 186 um2,
with the same 4x4 shared base and 2x2 complementary-control shunts.

A second mode replaces all 31 paired NAND2B core cells (both turn and pass)
with two actual o1 stack-guard/body-contact macros per pair. It retains their
original named input/output connections and all native MOS. Both the original
compound library and the guard library have independent passive-RC, DRC and
unique-LVS proofs. Guarding is a candidate for the observed terminal-voltage
failure, not an assumption that isolated-counter results transfer to a bank.
The source root fine-switch/control geometry and common/parallel wires still
need their own physical implementation and extraction.

`probe_weighted_direct_v2.py` prepares campaign
`weighted_direct_v2/70fd8cd26309c493`: guarded/plain modes at coarse 0/1,
SS/40 C, fixed 1.8 V, 100 ps input slew and 20 fF load. All four cases retain
2,335 actual MOS witnesses and the complete coarse topology. The six 10 ns
pulse windows use fine codes **0, 1, 15, 16, 31, 0**, explicitly covering
both sides of the binary carry and the return to minimum code. Every pulse
must have exactly one correctly ordered rise and fall, and both external and
native buffered controls must settle before it. Full 60 ns traces and every
MOS terminal pair remain required, without initial conditions or clipping.
ITL4=100 raises the iteration allowance only; the original numerical
tolerances and 2 ps maximum step remain. Its runtime benefit is unproven.

`verify_weighted_direct_v2.py` regenerates every native library, component
connection, MOS witness and deck, then independently remeasures all four
complete raw traces. The sparse screen requires minimum-delay quarter-cycle
headroom, coarse0/fine31 to coarse1/fine0 overlap in both polarities, sampled
fine ordering, 0->1 and 15->16 observed increments in (0,20] ps, and the
unchanged 1.95 V terminal limit. The repeated code-zero delay is reported.
A failed observed carry is evidence about that pair; it does not prove that
no filtered common legal-code table exists. Dense all-PVT code selection is
still required even if every sparse observation passes.

The pilot and consumer run as `openlvds-weighted-direct-v2-pilot.service`
and `openlvds-weighted-direct-v2-verify.service`. They use at most two workers
and the shared six-engine dispatcher. The four cases are queued while older
healthy solvers continue. Independent read-only preflight regenerates all
libraries, 2,335 MOS witnesses per mode and all four decks exactly. No whole
bank RC, dense ROM, periodic-clock, full-PVT, DLL or PHY admission follows.

Validation: `make test-full` passes **1,795 tests without skips** in
`build/weighted-direct-v2-full-tests.log`. New tests preserve every coarse
connection across guard replacement, exercise the carry/repeat fixture,
retain native tie resistors while mapping distinct private MOS nodes and
reject incomplete coverage, reversed/oversized carry, lost overlap,
insufficient quarter headroom and terminal-stress failures. All production
model and ROM admissions remain closed pending complete electrical results.

### Physical guarded NAND2B pair for native backend integration

The counter and guarded weighted-bank prototypes use two guarded NAND2B4
outputs in parallel. Their ideal shared wires are not a physical macro.
`build_nand2b_guard_pair_v2.py` imports the exact o1 guarded cell GDS twice
and routes all five public nets on M4, preserving both child hierarchies,
private shunts and body-contact rows. Its first placement,
`nand2b_guard_pair_physical_v2/6fcc7ef0cd46a890`, passes unique LVS but has
22 DRC violations around compact signal vias and their native M3 neighbors.
The failed geometry and source are retained.

Revision `build_nand2b_guard_pair_v3.py` moves signal landings to the right
of the dense native contacts and uses 0.32 um via paint with 0.44 um metal
landings. Its fresh result,
`nand2b_guard_pair_physical_v2/d9d269bff28ee670`, has **zero DRC violations
and unique LVS**. The two source cells and native masks are unchanged;
the source schematic hashes are identical across both wrapper revisions.
The new public macro is `openlvds_nand2b_4_o1_stack_guard_pair_v2`, with
A_N/B/Y/VGND/VPWR ports and a single public output for implementation tools.

`restrict_macro_rails_v5.py` selects designated M3 or M4 access shapes while
preserving the exact union of routing/obstruction geometry and native antenna
metadata. Earlier bound M3-only interfaces remain unchanged. The paired
macro exposes its shared M4 buses and keeps its child M3 shapes obstructed.
This geometry/connectivity result does not establish electrical timing,
whole-controller RC, full PVT or PHY admission.

### Fresh passive RC proof for the physical guarded pair

`extract_nand2b_guard_pair_v2.py` extracts the clean paired GDS in a new
namespace: `nand2b_guard_pair_rc_v2/2e6cb776c0315f4a`. The unmodified flat
model has **988 positive resistors, 292 nonnegative capacitors and all 36
native MOS**. Exact positive-conductance star-mesh elimination removes 193
unprotected algebraic nodes, leaving 789 resistors and the same capacitors
and native terminals. This includes the real shared M4 routes and vias.
No extracted device, guard, supply path or negative element is discarded.

`verify_nand2b_guard_pair_rc_v2.py` independently binds the physical GDS,
source, ports, extractor and raw/reduced files, repeats the passivity audit
and runs strict fresh Netgen LVS. Receipt
`nand2b_guard_pair_rc_verification_v2/8df7c5f5a7ab600e` passes. Inline-comment
aware wire collapse is used only for the LVS comparison; the simulation
RC library remains unchanged. The preceding single-cell pilots continue to
use their bound libraries. Substituting this paired RC into the counter and
bank requires new timing experiments, then whole-controller routing and
fresh extraction. No electrical or PHY admission follows from RC topology.

Validation: `make test-full` passes **1,797 tests without skips** in
`build/nand2b-guard-pair-v2-full-tests.log`. Source tests preserve the actual
child pin order and schematic and check that M4 access restriction retains
every routing shape while rejecting wrong-layer/absent access. Actual Magic
DRC, unique Netgen LVS, positive-R/nonnegative-C audit and independent fresh
RC topology verification provide the physical evidence above.

### Loaded counter experiment with actual routed low-setter pairs

`static_phase_clock_release_v6.py` replaces only the three low-setter
parallel connections in the positive o1 counter with the new physical
`openlvds_nand2b_4_o1_stack_guard_pair_v2` RC. All high setters, feedback,
REQUEST buffer, public output, clock driver and three public DCC input loads
remain unchanged. This adds the actual shared pair M4/via RC while retaining
all 488 MOS witnesses in the loaded harness. Inter-macro wiring outside
each pair remains ideal and still requires whole-controller routing.

`guard_pair_release_rc_families_v2.py` requires the independently verified
pair GDS/source/passivity/LVS identity and retains the original component
family checks. Campaign `static_phase_clock_release_v6/d88c3462d0e8e585`
is queued for four SS/40 C, 410 MHz cases: 40%/60% duty and both stopped
levels. It binds the complete positive original o1 profile
`static_phase_profile_verification_v2/c657a2d449809d32`. No old solver,
fixture or extracted library is changed.

`verify_static_phase_clock_release_v6.py` regenerates every component,
counter and harness, checks every requested actual MOS terminal and full
26 ns stop, and independently remeasures all four cases, including any
reproducible complete-waveform event-count failures. The original alternating
phase order, two/three clock counts, margin to the following half phase,
asynchronous clear, stopped-clock reassertion and 1.95 V screen remain.
It also independently remeasures each exact matching original baseline raw
and reports prepare/public-release time and terminal-peak changes. No result
from another temperature, duty or stop level can substitute for a missing
case.

The pilot and verifier run as
`openlvds-routed-pair-static-phase-v2-pilot.service` and
`openlvds-routed-pair-static-phase-v2-verify.service`, using two workers and
the existing shared six-engine dispatcher. Independent read-only preflight
regenerates all four decks and their 488 MOS witnesses exactly. Timing,
actual DCC first event, whole-controller RC, full-PVT and PHY admission are
still pending. `make test-full` passes **1,799 tests without skips** in
`build/routed-pair-static-phase-v2-full-tests.log`.

### Numerically failed original baseline is retained without timing comparison

Original return-mux case 2 has now terminated at 0.654404 ns, before its
first input edge at 2.1 ns. Its ngspice log reports `Timestep too small`,
a final 2.5e-24 s step and an aborted transient. All raw/deck/log evidence
remains in `dcdl_mux_return_v2/1eb79ae5fb488676/2`. This is a numerical
failure, not a complete pulse/timing verdict. The other original solvers
and the ITL4=100 comparison campaign continue.

The original iteration-test consumer rejected an experiment if an original
baseline row had any error. `verify_dcdl_iterations_v3.py` now retains and
hashes that failed baseline evidence, records the comparison as unavailable,
and still requires complete regenerated decks, full-duration new waveforms,
every MOS terminal and independent new raw remeasurement. A valid baseline
still requires exact independent remeasurement before pulse/peak differences
are reported. No timing equivalence is inferred for the failed baseline.

Only the read-only v2 verification watcher was retired; its source remains
intact. Replacement unit `openlvds-dcdl-iterations-v3-verify.service` watches
the same unchanged producer artifact. No simulation was stopped or restarted.
Two focused tests pass: the failed-baseline path must not attempt a raw
comparison, inconsistent failed rows are rejected, and a valid baseline
requires matching independent measurement. The routed-pair full suite above
completed before this isolated new consumer was added.

### Complete native static release-counter physical backend

`build_static_phase_backend_v2.py` constructs the complete tested nineteen-
macro counter from its exact component-RC topology: fourteen ordinary native
logic/driver macros, two stronger release gates and three routed guarded
low-setter pairs, across four actual macro types. Each output net has one
public driver. Native GDS, private guards and body contacts remain intact.
The first artifact `static_phase_backend_physical_v2/0755686519e08e14`
stops during route construction because a floating-point rail-boundary
comparison rejects a coordinate differing by less than a layout grid.
It is retained as an incomplete artifact, not a running physical job.

Revision `build_static_phase_backend_v3.py` makes that boundary check grid
aware and records terminal exceptions explicitly. Whole-counter artifact
`static_phase_backend_physical_v2/81e0989798b29f0d` completes with **zero DRC
violations and unique LVS** against the full native schematic. All nineteen
macros and every feedback, clock, request and supply connection are routed.
M3 spines use empty macro corridors; M4 local escapes join per-stage M5
buses. The six public CLK/REQUEST/PREPARE/RESET_N/VPWR/VGND ports expose M5
access. `restrict_macro_rails_v6.py` supports that layer while preserving
all routing/obstruction geometry and antenna metadata. No STA timing model,
production controller selection or electrical admission is fabricated.

The structural route binds exact native port orders, rejects conflicting
source definitions across reused cells and refuses different nets sharing
a spine interval. Native schematic definitions are deduplicated only when
their complete tokenized bodies agree. Actual full-block DRC/LVS, rather
than structural software checks alone, establishes geometry/connectivity.
The preceding paired-component and joint clock simulations continue with
their immutable libraries; this backend does not replace them silently.

Validation: `make test-full` passes **1,805 tests without skips** in
`build/static-phase-backend-v2-full-tests.log`. Focused checks require all
nineteen unique output drivers, preserve complete clock/request/prior-state
fanout, reject conflicting native source bodies and preserve every routing
shape when selecting M5 access. The reported DRC evidence is from Magic;
independent whole-block DRC/antenna checks and physical timing remain open.

### Full-counter passive RC, preserving every native terminal

`extract_static_phase_backend_v2.py` freshly extracts the entire routed
counter from its GDS, rather than concatenating component RC. Artifact
`static_phase_backend_rc_v2/9191dc88414e60d0` retains **402 native MOS,
7,933 positive resistors and 2,141 nonnegative capacitors**, including its
feedback, clock/request spines, M4 escapes, M5 buses, shared supplies and
all device body paths. Exact positive-conductance star-mesh reduction of
unprotected algebraic nodes leaves 5,765 resistors and the same capacitors
and MOS terminals. No parasitic thresholding, device removal or supply-path
alias is used to obtain passivity.

`verify_static_phase_backend_rc_v2.py` independently reaudits the flat model,
checks exact GDS/source/interface hashes and repeats strict topology LVS.
Receipt `static_phase_backend_rc_verification_v2/2998abbb3942aa22` passes.
The normalized RC interface order is
`REQUEST VGND VPWR CLK PREPARE RESET_N`; consumers must map by port name.
Wire collapse is used only for independent LVS; the electrical RC remains
intact. This is a whole-counter geometry/connectivity/passivity result,
without native timing, independent DRC/antenna, actual DCC first-event,
full-PVT, full-clock backend or PHY admission. Its four-dimension native
loaded-counter timing cases must be prepared separately and retain the
approved 40%/60% duty endpoints and all stopped-clock checks.

### Completed common-release startup misses are late data preparation

Both common-release cases 0/1 in
`native_static_dcc_v2/8f73e3a90f1d54b3` complete without numerical errors.
They pass every terminal-voltage check, common mode, preparation/mask order,
at least three actual release clocks and the mean half-cycle limit
(11.6835/8.1492 ps for 40%/60% duty). They fail exactly the first expected
P180 and following P0 output events; subsequent measured output intervals
pass. This is not a device-overstress failure or an incomplete transient.

`diagnose_common_dcc_startup_v2.py` independently regenerates and remeasures
both complete cases, then observes every actual output drain/source terminal
connected to each native gate's output through resistor-only paths. It does
not introduce ideal logical aliases or choose one favorable finger. Receipt
`common_dcc_startup_diagnosis_v2/35194dbd49c1ca42` binds all retained files.
B's master first crosses high **1,789.8--1,801.6 ps** after its first expected
P180 clock at 40% duty, and **2,262.8--2,274.2 ps** after that clock at 60%.
The real data/master/slave terminal event lists localize the missed first
sample: data qualification arrives too late to establish the initial B
master state in its first acquisition window. The common enable starts data
preparation and the public mask together. The separately queued early-data
prepare mode is the existing direct test of that startup cause; a repair
pass is not inferred before its complete waveforms are available.

### Unloaded physical observations preserve full-counter phase checks

A flat full-counter model needs real observation points for its internal
phase-order and stopped-clock checks. The characterization view exposes the
existing low0/high1/low1/armed/request_i M5 conductors as five unloaded test
ports, alongside the six original functional ports. No devices, routing,
voltage sources, shorts or external loads are added. The original six-port
GDS/RC and its immutable proofs remain unchanged.

`observe_static_phase_backend_v2.py` first imports and flattens the actual
clean GDS, rather than synthesizing a logical replacement. Artifact
`static_phase_observed_physical_v2/64e64b3269c11645` retains zero DRC but
fails interface qualification: GDS label import loses the six original
Magic port numbers. Revision `observe_static_phase_backend_v3.py` explicitly
restores those original ports before flattening and appending the five
observation labels. Fresh artifact
`static_phase_observed_physical_v2/8ca98eafae7d6aa9` passes **zero Magic DRC
and unique eleven-port LVS**. The flattened mask-geometry prefix hashes
before/after annotation are identical. Only labels and port attributes
change. Internal source names are exposed by extending the source interface;
every native instance and connection remains intact.

Fresh extraction `static_phase_observed_rc_v2/2fc7d6d1a2ace804` has 6,405
positive resistors, 2,136 nonnegative capacitors and 402 native MOS. Exact
algebraic-node elimination leaves 5,255 resistors. Independent receipt
`static_phase_observed_rc_verification_v2/e71c1b13b0b4547c` passes the sign,
GDS/source/interface and strict fresh LVS audits. Its eleven declared ports
protect the observation conductors during exact reduction. Flattening and
labeling can change extraction partitioning, so timing equivalence to the
six-port extraction is not assumed from element counts. This freshly
extracted characterization view must pass its own full native timing checks.

### Full routed-counter loaded timing pilot retains every phase check

`static_phase_clock_release_v7.py` connects the eleven physical RC ports by
name inside a six-port test wrapper. The five observation nets stay unloaded;
no ideal source, extra device or internal electrical alias is inserted.
`whole_counter_rc_families_v2.py` requires the independently verified full
counter and retains the native clock-driver/load RC family checks.

Campaign `static_phase_clock_release_v7/d08f71c9cc098f2b` declares four
SS/40 C, 410 MHz cases: 40%/60% duty crossed with low/high stopped clock.
It retains the real clock driver and all three DCC reset-input loads, with
**488 actual MOS witnesses** per case. The 26 ns fixture still includes
asynchronous clear and request reassertion with the clock stopped. Source
counter states are replaced by the complete distributed physical RC;
harness wires outside that block remain ideal.

`verify_static_phase_clock_release_v7.py` independently regenerates all
libraries, wrappers, decks and actual MOS mappings. It retains the original
alternating phase/order, two/three clock counts, next-half-phase margins,
stopped-clock clear/reassertion, buffered REQUEST and 1.95 V checks. It also
remeasures the matching complete original o1 baseline and reports timing
and voltage changes, rather than treating routing/LVS as timing evidence.
The pilot/consumer run as `openlvds-whole-counter-static-phase-v2-pilot.service`
and `openlvds-whole-counter-static-phase-v2-verify.service`, under the same
six-engine queue and two-worker campaign limit. Cases are queued, not passed.
Independent preflight exactly regenerates all four decks and 488 MOS witnesses.

`make test-full` passes **1,809 tests without skips** in
`build/whole-counter-static-phase-v2-full-tests.log`. Tests preserve native
mask/source bodies during observation, select only resistor-connected real
MOS output terminals, map all eleven physical ports and reject a missing
monitor or incomplete/failed timing profile. Native timing, early-data DCC
repair, full PVT, independent physical/antenna and full-chain PHY admission
remain pending.

### Independent full-counter macro DRC and installed partial antenna check

`check_static_phase_klayout_v2.py` runs the unmodified installed SKY130A MR
runset against the exact complete counter GDS. Artifact
`static_phase_klayout_v2/0bdae5d1739762aa` reports **zero violations** with
FEOL, BEOL, off-grid and floating-metal checks enabled, two checker threads
and no SRAM exclusion. The run uses the parameter names actually implemented
by that pinned deck (`top_cell`, `floating_met`, `thr`), binds its content hash
and checks the selected top and enabled-group confirmations. This is macro
DRC, without die seal/density or antenna coverage from that deck.

`check_static_phase_antenna_v2.py` separately runs the installed Magic antenna
rules after extracting the full counter. Artifact
`static_phase_antenna_v2/87f3306ba8932cb2` reports **zero antenna feedback
entries**, with all **402 native MOS** in its extraction. Successful command
completion and complete device coverage are required; an empty/missing report
cannot count as a pass. The pinned technology explicitly selects its
**partial** antenna model and notes that diode diffusion is not modeled.
This check therefore does not establish cumulative/foundry antenna signoff.
The [Magic command reference](https://opencircuitdesign.com/magic/commandref/antennacheck.html)
requires extraction before checking so that sensitive gates can be enumerated;
the retained logs confirm the actual extraction and antenna execution.

`verify_static_phase_geometry_v2.py` independently reparses the raw KLayout
XML, Magic result, feedback and extracted devices; checks the exact run
command and enabled rule groups; and rejects reports for different counter
GDS inputs. Receipt
`static_phase_geometry_verification_v2/020baf11a08a6301` passes. No routing,
parasitic model, live simulation or production-admission bit is changed.
Native timing, full PVT, cumulative/foundry antenna and full-chain PHY
qualification remain open.

`make test-full` passes **1,811 tests without skips** in
`build/static-phase-independent-checks-v2-full-tests.log`. New parser tests
reject incomplete/wrong-top DRC reports, count each violation record and
require successful antenna execution with every native MOS before accepting
zero feedback. The combined audit above was also run against the actual
complete physical reports.

### First original weighted-bank result: minimum range and fine-control stress

Original buffered weighted-bank case 0 (unit-sized switches, coarse 0),
`weighted_fine_bank_v2/43447c0bbcb6ec85/0`, now completes without numerical
errors. At fine code 0 its first rise/fall delays are 661.737/770.299 ps,
leaving **-160.543 ps** fast-quarter headroom. Fine code 31 reaches
735.607/868.790 ps: this sparse unit-switch case alone does not establish
coarse overlap or a legal fine-code table.

Terminal failures include the turn0 core (2.033147 V), native source fine
buffers (up to 2.087355 V), fine inverters (1.988506 V) and fine switches
(1.978124 V), all above the retained 1.95 V limit. Thus port-delay and turn
repairs alone cannot qualify this completed case: the control/fine network
also needs investigation. The direct-port guarded root-switch comparisons
already running retain their own scope; no result for them is inferred from
this original unit-switch trace. All failed and unfinished artifacts remain.

### Isolated weighted fine-control repair experiment

The completed original weighted-bank failure includes the native source
buf_1/inv_1 controls and fine switches as well as the turn cell. The next
experiment isolates that network, rather than attributing every failure to
the coarse path. `weighted_fine_control_v2.py` compares the original source
controls with the existing physically extracted BUF8-o4 and INV8-o4 shunted
macros. The fine root-switch geometry, MIM weights, keeper transistors and
2x2 ENB shunts are unchanged. The swap selects complete native components;
it is not a scalar transistor resize or a new behavioral timing model.

`probe_weighted_fine_control_v2.py` binds the completed full-bank case-0
failure and its exact files as motivation. Campaign
`weighted_fine_control_v2/a522d5d58a738970` declares four SS/40 C cases:
source/guarded driver selection crossed with DATA held at logic 0/1.8 V.
Supply remains fixed at 1.8 V. All five fine loads are connected, and 20 ps
control transitions apply codes **0,31,0,16,15,0** in six 2 ns windows.
The 12 ns trace covers maximum loading, discharge/reassertion and the
16->15 carry. Every EN/ENB and fine CAP node must reach its expected rail
within the retained 1.5--1.9 ns settled window of each word. Every actual
MOS terminal pair is still screened at 1.95 V, including the entire input
edge, with no clipping, initial conditions or tolerance change.

The guarded profile has 205 MOS witnesses; the source reference has 45.
`verify_weighted_fine_control_v2.py` independently regenerates every native
library, fine load, device witness and deck, checks complete raw file hashes,
and remeasures all four cases. Both DATA biases are required per driver
profile. A failed source reference remains negative evidence and cannot
hide a guarded failure or count as its repair. These are source fine-device
bias tests with actual guarded-driver RC, without full-bank delay/range,
physical fine/control/common-wire RC, active-clock, full-PVT or PHY admission.

Units `openlvds-weighted-fine-control-v2-pilot.service` and
`openlvds-weighted-fine-control-v2-verify.service` queue the cases under the
existing six-engine/two-worker limits; earlier healthy jobs continue.
Independent read-only preflight regenerates all four decks and 205/45 MOS
witnesses exactly. `make test-full` passes **1,814 tests without skips** in
`build/weighted-fine-control-v2-full-tests.log`. Tests reject transient
overstress, failed keeper discharge and missing DATA-bias coverage, preserve
the fine source geometry and map actual driver port order. Component repair
and subsequent full-bank results remain pending.

### Physical root-weighted fine cells

`weighted_fine_unit_v2.py` preserves the five existing root-profile device
schematics, including the 6/12/24/48/96 square-micron MIM weights, switch
scales 1/2/2/3/4, keeper transistors and 2x2 ENB capacitors. The physical
builder generates actual SKY130 PCells and derives placement from their
native bounds. Each cell exposes NODE, EN, ENB, VDD and VSS on metal3.

The first artifact, `weighted_fine_unit_physical_v2/9a153bea1d4b611f`, is
retained with its failed largest cell. The first four cells passed DRC/LVS;
the largest exposed a shared-height CAP/ENB escape short and a bottom-plate
ground drop crowded against the CLR signal columns. Its sources remain
unchanged. `build_weighted_fine_units_v3.py` and
`weighted_fine_unit_layout_v3.py` separate the capacitor escape planes and
select a compatible existing ground column when the larger plate requires
one. No transistor or capacitor dimensions change.

Artifact `weighted_fine_unit_physical_v2/59dd66c845aa3f2f` completes all five
cells with zero Magic DRC errors and successful unique Netgen LVS. Source,
PDK, tool, GDS and LEF identities were checked again after completion.
Regression tests preserve the original device connectivity and exercise the
largest-cell escape clearance and ground-column choice that caused the
first failure. These are physical component results only: fresh extracted
RC, timing, full-bank integration and PHY admission remain pending.
`make test-full` passes 1,817 tests without skips; the log is
`build/weighted-fine-units-physical-v2-full-tests.log`.

The approved duty amendment remains `clocking_duty_v2_2.json`: input
endpoints are 40% and 60%; the output mean half-cycle error limit remains
50 ps. The frozen base descriptor and previous bound experiments are
retained. No supply sweep is introduced.

### Fresh RC for all five root-weighted fine cells

`extract_weighted_fine_units_v2.py` extracts from each actual GDS in the
completed five-cell physical family, using single-pass unsimplified native
resistance extraction. Artifact `weighted_fine_unit_rc_v2/74761bf55657275c`
passes the positive-resistor/nonnegative-capacitor gate and a fresh strict
Netgen comparison for every cell. Wire collapse is used for topology
comparison only; the simulation models retain their distributed R/C.
The established algebraic star-mesh reduction protects device and capacitor
nodes and introduces no empirical timing approximation.

| Fine bit | Native resistors | Native capacitors | Reduced resistors |
| --- | ---: | ---: | ---: |
| 0 | 194 | 58 | 170 |
| 1 | 250 | 68 | 208 |
| 2 | 250 | 68 | 206 |
| 3 | 292 | 62 | 238 |
| 4 | 324 | 61 | 267 |

`verify_weighted_fine_units_rc_v2.py` independently checks exact coverage,
physical/source/interface identity, both raw and reduced network passivity,
the raw hash recorded by reduction, and fresh strict topology comparisons.
Receipt `weighted_fine_unit_rc_verification_v2/c433d849b89e6612` passes all
five cells. Missing, duplicated, reordered or dirty physical cells are
rejected before extraction. These models retain actual native MOS junction
geometry and MIM devices. The scope remains component RC/topology; native
timing, control-driver safety, full-bank integration, dense PVT mapping and
PHY admission remain open. Earlier source-fine experiments are preserved
and do not acquire physical-fine coverage from this separate receipt.
`make test-full` passes 1,820 tests without skips, recorded in
`build/weighted-fine-units-v2-rc-full-tests.log`.

### Isolated control repair with physical fine-cell RC

`weighted_fine_rc_families_v2.py` admits only the complete independently
verified five-cell fine family. It rechecks the bound source/PDK/tool and
physical identities, raw and reduced RC hashes/passivity, exact coverage and
the independent topology logs before returning simulator models. This is a
read-only check; no physical job is rerun. The existing source-fine pilot and
its failed/unfinished artifacts remain unchanged.

`weighted_fine_control_v3.py` connects each actual fine macro by its own
extracted port order. It identifies the switched MIM by its exact dimensions
and follows resistor connectivity to every physical plate node, requiring
all three native MOS plate terminals to remain connected and isolated from
public rails/signals. No ideal CAP alias or electrical observation port is
introduced. All 11/17/17/14/13 plate nodes for bits 0 through 4 are retained
in the waveform and checked for settling. Capacitive coupling is not treated
as a wire. Regression tests reject a disconnected keeper, a plate short,
negative resistance, wrong plate dimensions, hidden far-node settling
failure and transient MOS overstress.

Campaign `weighted_fine_control_v3/f276c77a9801f293` compares the native
BUF8-o4/INV8-o4 guarded drivers with source buf_1/inv_1 controls, both driving
the same actual fine-cell RC. Four SS/40 C cases cover DATA held at 0 or
1.8 V for each driver profile, fixed 1.8 V supply, 20 ps control edges and
codes 0,31,0,16,15,0 over 12 ns. Every physical plate node must settle within
0.18 V of its expected rail during each retained 1.5--1.9 ns window; all
MOS terminal pairs retain the 1.95 V whole-waveform limit. The guarded and
source profiles contain 205 and 45 MOS witnesses respectively.

`probe_weighted_fine_control_v3.py` binds the native fine receipt, guarded
driver receipt and completed original weighted-bank failure. The independent
`verify_weighted_fine_control_v3.py` regenerates the libraries, device/plate
witnesses and decks before checking complete raw waveforms. Services
`openlvds-weighted-fine-control-v3-pilot.service` and
`openlvds-weighted-fine-control-v3-verify.service` queue and verify this work
under the unchanged six-engine/two-worker policy. This is a fixed-data
component experiment with ideal intercell wires; active-clock, full-bank
timing/range, full-PVT and PHY admission remain open. A passing physical RC
receipt or deck preflight does not establish a passing electrical result.
Independent read-only preflight regenerated all four decks and all native
MOS/plate witnesses exactly. `make test-full` passes 1,824 tests without
skips in `build/weighted-fine-control-v3-full-tests.log`.

### Full-bank candidate with physical guard pairs and fine/control RC

`dcdl_weighted_direct_v3.py` retains the full sixteen-choice coarse topology
and direct input/output ports. All 31 turn/pass compound drivers now select
the actual routed guarded NAND2B pair model, replacing the earlier ideal
parallel connections between two separate guarded cells. Forward/merge
connections and every coarse choice remain. Each of the five fine loads
uses its independently verified physical RC macro, and all five fine-control
buffer/inverter pairs select the native BUF8-o4/INV8-o4 guarded models.
Connections use each extracted macro's port order. The selected macros retain
their extracted device geometry; voltage limits and fine-MIM area are unchanged.

`probe_weighted_direct_v3.py` prepares two SS/40 C cases at coarse settings
0 and 1, each with codes 0,1,15,16,31,0 over 60 ns. The full native hierarchy
contains 2,495 MOS witnesses. Campaign
`weighted_direct_v3/8d170377b3a7a963` binds all four physical RC families,
PDK/model files, generated libraries/decks, solver settings and source.
The 100 ps isolated input pulses, 20 ps controls, fixed 1.8 V supply,
20 fF output load, ITL4=100, 2 ps maximum timestep and existing tolerances
are retained. All six MOS terminal-pair voltages retain the 1.95 V screen;
LSB/carry steps, both edge polarities, quarter-period headroom, adjacent
coarse overlap and repeated code-zero delay are still measured.

This campaign is **prepared, not started or passed**. The run command
requires `--control-receipt` pointing to the independent physical-fine
control verifier's receipt. `weighted_bank_control_gate_v2.py` checks its
identity, bound raw/deck/result witnesses, matching fine/driver families,
complete four-case coverage and a guarded-driver pass at both DATA biases.
A failed source-driver reference cannot stand in for a guarded pass. The
gate is checked again before each solver starts; its receipt/hash is saved
in `control_gate.json` and rechecked by the full-bank verifier. Missing,
unsafe, incomplete or mismatched prerequisites cannot launch this campaign.

`verify_weighted_direct_v3.py` regenerates the full native library and MOS
witnesses, then remeasures both complete raw traces and all existing sparse
feasibility checks. No new solver tickets are queued at this checkpoint.
Source coarse-control cells and the source 4x4 shared base MIM remain;
intercell wires are ideal. Whole-bank routing/RC, active periodic clocks,
dense common code mapping across all 15 PVT points, upstream/downstream
chain integration and PHY qualification remain required. Sparse pilot
success would not admit a code ROM or establish a usable PHY.
Independent read-only preflight regenerated both 60 ns decks and all 2,495
MOS witnesses exactly. An attempted run without `--control-receipt` was
rejected before creating execution state or raw output.
`make test-full` passes 1,829 tests without skips, recorded in
`build/weighted-direct-v3-full-tests.log`.

### ITL4 increase reproduces the original coarse-1 numerical failure

Case 2 of `dcdl_iterations_v2/a994d04ddcc0bdbb` has now completed with a
numerical error. `diagnose_dcdl_iterations_v2.py` binds the completed case
and original `dcdl_mux_return_v2/1eb79ae5fb488676/2` failure, checks every
retained output hash, verifies the exact title/ITL4-only deck change and
regenerates both translated solver decks. Diagnosis
`dcdl_iteration_failure_v2/fe0c114ee910ccca` confirms that the raw binary
payloads are bit-for-bit identical: 2,671 variables, 8,629 records, with the
last accepted sample at **0.6544043994140895 ns**. Header title/date metadata
is excluded from the payload comparison; complete raw files remain bound.

Both terminal logs report timestep collapse at 0.654404 ns, timestep
2.5e-24 s, with `bin#branch` named by the solver. The translated ITL4=100
option is present. This rules out simply raising this allowance as the fix
for this matched case. It does not prove that the reported branch is the
underlying cause, and it does not establish a simulator speed comparison.
The first input pulse is at 2.1 ns; neither run reaches it. Partial raw
prefixes are explicitly marked incomplete and unqualified, never passed to
the full-waveform timing/safety gate as successful traces. The original
failure and new failure remain intact; the other healthy matched case is
not restarted or stopped. The dispatcher filled the naturally released
slot with the next existing return-mux case.
`make test-full` passes 1,832 tests without skips, recorded in
`build/dcdl-iteration-failure-v2-full-tests.log`. Parser regressions reject
truncated records, invalid native formats and nonterminal/ambiguous failure
logs, and keep aborted prefixes explicitly unqualified.

### Physical NAND2 pair for forward-stack conditioning experiments

Read-only inspection of the immutable coarse-1 failed prefix finds IN at
exactly 0 V throughout and a maximum saved-node excursion of about 3.03 nV.
The largest excursions occur at native forward-NAND stack terminals around
1.337 V. The accepted trajectory is therefore nearly static before failure;
this is not evidence of a data-edge timing violation. These observations
motivate testing stack conditioning, but do not establish the underlying
solver/model cause or prove that a guard capacitor will fix it.

`build_nand2_guard_pair_v2.py` assembles two unchanged native
`openlvds_nand2_4_o3_shunted_v2` GDS cells with real shared M4 wiring. Each
child already has its own 2x2 MID MIM guard and 3x3 output MIM shunt, with
native transistor geometry and side body contacts retained. The new model
is `openlvds_nand2_4_o3_shunted_pair_v2`, exposing A/B/Y/VGND/VPWR. The
noninverting A input must not be confused with the separate NAND2B guard
pair's A_N input. No native mask or device dimension is edited inside a
child; the shared pair interconnect is drawn and checked physically.

Artifact `nand2_guard_pair_physical_v2/e1fa9ef6fbb91a5e` has zero Magic
DRC errors and successful unique Netgen LVS. Fresh extraction
`nand2_guard_pair_rc_v2/75cf8ac0c93e10ea` contains 32 native MOS, four native
MIM devices, 556 positive resistors and 218 nonnegative parasitic capacitors;
the exact algebraic reduction retains 388 resistors. Independent receipt
`nand2_guard_pair_rc_verification_v2/b9ec344c4af3618b` checks both raw and
reduced passivity/hashes and a fresh strict topology comparison.

`forward_guard_rc_families_v2.py` checks the receipt, bound source/PDK/tools,
actual physical GDS/source and topology logs before providing this model to
later experiments. Other native RC families remain distinct. The existing
full-bank v3 candidate, active solvers and queued control tests are unchanged.
The extra output/MID loading must be characterized; no convergence repair,
coarse step, headroom, common-code ROM or PHY admission is inferred from
the physical/passive/topology results. The next electrical comparison must
retain the original paired NAND as a reference and measure both inactive
bias behavior and loaded transition timing before any bank substitution.
Read-only model-reader preflight verified the bound receipt and loaded all
32 native MOS and four MIM devices. `make test-full` passes 1,834 tests
without skips in `build/nand2-guard-pair-v2-full-tests.log`.

### Matched electrical comparison of original and shunted forward pairs

`probe_forward_pair_v2.py` binds the original extracted NAND2 pair, the new
independently verified shunted pair, and the completed matched pre-input
failure diagnosis. Campaign `forward_pair_v2/f74f825112bc7310` declares four
SS/40 C cases: shunted/original crossed with B/A as the switching input.
The other input is held at 1.8 V. The B-switching case therefore begins at
A=1.8 V, B=0 V, the inactive stack state motivating the experiment. Both
models retain their actual complete 32-MOS geometry and distributed RC.

Every case uses the same fixed 1.8 V supply, 20 fF load, 100 ps 10--90%
tanh edges, 20 ns duration, 1 ps maximum timestep, Gear integration,
RELTOL=1e-4, ABSTOL=1e-12 and ITL4=100. Pulses rise at 2.1/12.1 ns and
fall at 6.1/16.1 ns. The measurement checks the complete source waveform,
initial settled high output and all subsequent settled truth levels,
exactly four output edges of the correct polarity/epoch, both propagation
directions, and all six terminal-pair differences on every native MOS at
the unchanged 1.95 V limit. Initial 0--1 ns terminal excursion is reported
as a diagnostic, not used as a new pass threshold. Extra initial glitches,
stuck output levels and transient overstress remain failures.

`verify_forward_pair_v2.py` independently regenerates both libraries, all
four decks and native MOS witnesses, validates hashes and translated decks, and
remeasures successful complete raw traces. A completed timestep-collapse
case is retained with its failure log and unqualified partial raw file; it
cannot supply an electrical result or propagation difference. Infrastructure
errors cannot masquerade as a known numerical failure. Both input
orientations must pass for a shunted component pass. A failed original
reference does not conceal a shunted failure; no timing difference is
reported unless both compared isolated cases pass. Elapsed wall time is
retained without a simulator-speedup claim.

Independent read-only preflight regenerated all four exact decks and all
32 MOS witnesses per case. Services `openlvds-forward-pair-v2-pilot.service`
and `openlvds-forward-pair-v2-verify.service` queue/verify under the unchanged
six-engine/two-worker policy. This is an isolated component comparison with
ideal upstream sources; it cannot establish full-bank convergence, coarse
step/headroom, dense common PVT mapping, periodic-clock operation or PHY
admission. The existing bank candidate and healthy solvers remain unchanged.
`make test-full` passes 1,838 tests without skips in
`build/forward-pair-v2-full-tests.log`. Regression cases reject initial
glitches, incomplete output settling, transient stress and changed supply,
retain both pin orientations and prevent failed-reference timing comparisons.

### Full candidate physical hierarchy and OpenDB assembly

`weighted_bank_physical_v2.py` supplies the physical hierarchy for the staged
v3 weighted-bank candidate. It preserves all sixteen coarse choices, the 31
routed NAND2B guard pairs, original forward/merge compound cells, five native
fine cells and ten native fine-control drivers. The shared 4x4 MIM is wrapped
in its existing physical macro. The hierarchy has 94 instances: 78 macros
from eleven exact types, plus the fifteen standard coarse-control buffers
and one tie cell. Standard-cell body pins are explicitly connected.

`assemble_weighted_bank_v2.py` regenerates the native candidate library and
compares complete flattened leaf multisets against the physical hierarchy.
The proof includes every R/C statement, native MOS/MIM/passive primitive,
internal node path, parameter and multiplicity. Only leaf-device labels and
the root VPWR/VGND versus VDD/VSS naming convention are adapted. The shared
MIM wrapper adds no device or electrical change. No device or parasitic is
collapsed to obtain this source equivalence.

Assembly `weighted_bank_assembly_v2/da87ad589530ae49` passes the real OpenDB
check. Actual LEF dimensions drive a provisional 305x468 um placement; the
larger guard/fine macros do not reuse the old fixed pitches. All 78 macros
are placed without overlap, and OpenDB confirms all 94 instance identities,
473 instance-terminal connections, 24 public ports and their direction/use,
and the actual M3/M4 macro-access layers. The complete native source,
generated structural Verilog/SPICE, macro configuration, physical views,
PDK/tool identities and saved database are bound in the artifact. No SPICE
engine ticket is consumed by these physical-tool checks.

`verify_weighted_bank_assembly_v2.py` regenerates the native library and leaf
proof, derives expected connections from the rendered SPICE and reloads the
saved database in a separate OpenROAD process. Receipt
`weighted_bank_assembly_verification_v2/31b0f9559cd509d6` independently passes
all instance/model/connection, public-interface, actual macro geometry,
placement status, access-layer and serialized die checks. Output hashes
and regenerated Verilog/SPICE are checked by the assembly binding consumer.
Regression cases retain the complete coarse/fine hierarchy, all native
passives and dimensions, reject duplicate/wrong-pin-count instances, and
exercise placement with deliberately oversized guard/fine macros.

This is an assembly preflight, not a routed bank. The 16 standard cells
and top-level I/O pins are not placed; rows, power routing, signal routing,
whole-bank DRC/LVS/antenna/RC and timing still remain. The staged electrical
candidate's control-repair prerequisite is unchanged, and no qualified
model, legal code ROM, configuration or PHY is selected by this result.
`make test-full` passes 1,843 tests without skips, recorded in
`build/weighted-bank-assembly-v2-full-tests.log`.

### Routing-ready macro frames with actual placed-pin equivalence

`normalize_weighted_bank_frames_v3.py` consumes the independent full-bank
assembly receipt. It checks its exact source/PDK/tool bindings and serialized
connectivity/model/interface readback before adapting all eleven macro types.
Every macro receives a zero-origin LEF/GDS coordinate frame and an exact
235/4 PR boundary. Existing native MIM markers generate conservative metal3
routing obstructions expanded by 1.34 um, using the retained native frame
helpers. Source GDS, LEF, SPICE and their physical/electrical records remain
unchanged; no native transistor, capacitor or routing mask is redrawn.

Artifact `weighted_bank_macro_frames_v2/04ede2e3d90cc5de` passes fresh GDS
reload/XOR checks on every physical layer except PR metadata. All cell
hierarchy, transforms and labels match the exact rigid translation. Two
separate OpenROAD processes then read the original and normalized LEFs and
place all 78 actual macro instances. Their 377 placed public-port rectangles,
layers, direction/use and all 78 macro bounding boxes are identical. This
uses actual instance origins and shape coordinates from OpenDB, rather than
assuming a LEF-origin sign convention. The bound consumer also checks all
adapted output hashes, unchanged source views/configuration and the exact
complete eleven-type set. Regression cases reject one-DBU pin/box shifts,
duplicated port records and failed tool runs even when saved rectangles match.

The first producer, `normalize_weighted_bank_frames_v2.py`, passed those
physical checks but wrote into the older directory namespace. Its source
and `dcdl_macro_frames_v2/28010e726741bfa7` output are retained and held for
the binding mismatch. Revision v3 fixes the producer namespace and binds
both helper revisions; the corrected artifact passes its own consumer.
No original or failed/partial evidence is overwritten.

These are physical-view preparation results, not whole-bank routing or
signoff. Standard-cell/I/O placement, rows, power and signal routing,
whole-bank DRC/LVS/antenna/RC, native timing and code admission remain open.
No new SPICE ticket was added by this work.
The corrected consumer revalidated all eleven macro types and reports 18
MIM keepout boxes. `make test-full` passes 1,845 tests without skips in
`build/weighted-bank-frames-v3-full-tests.log`.

### Return-mux FF minimum-code numerical failure

Original return-mux case 3 (FF/0 C, coarse 0/fine 0) has now completed with
timestep collapse at 0.129134 ns, timestep 2.5e-24 s, reporting `bin#branch`.
It does not reach the first 2.1 ns input pulse. This extends the observed
pre-input numerical problem beyond the retained SS/40 C coarse-1 failure;
it supplies no pulse-delay, safety or legal-code result. Its failed raw,
decks and logs remain intact. The dispatcher naturally reassigned the
released engine to early-prepare joint-DCC case 2; all other healthy solvers
continue without restart. The isolated original/shunted forward-pair
comparison is still queued, so no conditioning repair is inferred yet.

### Full-bank CAD placement bring-up and retained PDN failures

`weighted_bank_flow_v3.py` renders the exact staged hierarchy for LibreLane.
It retains all instance/model identities and signal connections. The sixteen
standard cells use the flow's global supply/body connections; the adapter
refuses to omit any body/power pin whose source connection differs from its
expected rail. Eleven hard macro interfaces retain explicit power pins and
their actual port directions. Only five internal net names are renamed to
avoid sharing the Verilog namespace with fine-cell instance names. The
reversible map is bound in the manifest and applied during the post-flow
connection comparison. Public ports and instance names are unchanged.

`harden_weighted_bank_v4.py` consumes the bound normalized macro frames,
places all sixteen controls on native 0.46x2.72 um sites above the fine bank,
and runs the Classic flow through `OpenROAD.DetailedPlacement`. It retains
the existing macro coordinates and disables input/output repair, delay-cell
replacement and CTS. The SDC supplies a 20 fF nominal output load and does
not claim STA admission for the calibrated asynchronous delay paths. The
post-flow reader checks every original signal/body/supply attachment,
macro model/position/orientation, public direction/use, all original cell
placement states, I/O shapes and OpenROAD placement legality. Physical
fill/tap/diode cells and real constant cloning are accounted for; extra
functional buffers or changed body rails are rejected.

All attempts remain separate and immutable:

| Producer | Artifact under `weighted_bank_bringup_v2` | Result |
| --- | --- | --- |
| `harden_weighted_bank_v2.py` | `00e6c00d855ce374` | Held at lint: five internal net/instance name collisions produced 20 errors. |
| `harden_weighted_bank_v3.py` | `f63e6c5a46de12f5` | Renaming fixed lint and synthesis; PDN stopped at PDN-0179, an unrepairable narrow right-edge channel. The saved partial DB retains the original connections. |
| `harden_weighted_bank_v4.py` | `739e945fe80c24fe` | A 35 um right-edge extension, to 340x468 um, removed the channel failure and reached detailed placement. All original placement/interface checks pass, but deferred power-grid errors keep the run held. |

The latest saved database has all 94 original cells placed, unchanged macro
boxes/orientations and 22 signal I/O pins with actual geometry. Its instance
and public-interface checks and `check_placement -verbose` pass. The CAD
return code is nevertheless 2: the grid checker reports **8,892 power-grid
violations**, including 62 disconnected guard-pair supply pins/shapes and
failed M4-to-M5 via insertions. Logical ITerm/net assignment is not proof of
physical supply continuity. `placement_bringup_passed` and
`physical_implementation_passed` remain false. The tool's suggestion that
grid warnings may be ignored if LVS passes is not adopted.

The next physical fix must provide legal, connected access from the guard
pairs' narrow M4 power rails to the external grid and recheck the full grid.
Signal routing, whole-bank DRC/LVS/antenna/RC and native timing remain open.
The candidate's electrical control-repair prerequisite and all PHY/code-ROM
admission flags remain unchanged. Six healthy SPICE solvers continue; these
CAD attempts consume no SPICE tickets. `make test-full` passes 1,850 tests
without skips in `build/weighted-bank-flow-v3-full-tests.log`, including
negative body/power, instance-substitution and reversible net-alias checks.

### Existing guard-pair M3 power access and held grid replay

`weighted_bank_power_access_v2.py` promotes exactly four existing M3 power
rectangles from the guarded NAND2B pair's obstructions to their original
named power pins. The candidate is
`weighted_bank_power_access_v2/1df6952c90cd499a`. Each promoted rectangle is
an exact original extracted PG shape, is fully contained in the native M3
GDS, and contains an existing via3 cut completely inside its intersection
with the original named M4 rail. Both child rails are covered for both
supplies. The complete routing-geometry multiset, all signal pin text,
macro boundary and GDS are unchanged. The consumer regenerates the view,
checks the native mask proof again and rejects changed source/output hashes
or any changes to the other ten macro views. This is access preparation,
not grid, timing or PHY admission.

`harden_weighted_bank_v5.py` consumes that bound view and retains the earlier
340x468 um floorplan and all macro positions. Artifact
`weighted_bank_bringup_v2/2c9a89458f8122ee` reaches detailed placement with
all original interface/placement checks passing, but returns 2 because the
power grid remains disconnected. Merely exposing M3 does not resolve the
chip-wide strap phase and M4 signal-obstruction problem. This failed run
and all earlier artifacts remain immutable; all physical/electrical/PHY
admission flags remain false. The next experiment adds local M5 escapes
rather than inferring physical connectivity from logical supply nets.

`make test-full` passes 1,852 tests without skips in
`build/weighted-bank-power-access-v2-full-tests.log`. New negative checks
reject missing, duplicated, shifted and incorrectly named supply rails;
positive checks preserve signal pins and the routing-geometry multiset.

Early-prepare joint-DCC case 2 (SS/40 C, 410 MHz, 40% duty) has completed
with its startup/event, mean half-cycle and terminal-voltage pilot checks
passing. Mean half-cycle error is 8.252 ps and the largest individual
half-cycle error is 46.719 ps. This is a single component-RC pilot result;
the corresponding 60% case and independent four-case receipt remain
pending. It does not qualify full-PVT startup, hardware warmup or the PHY.

### Wider native guard-pair power rails

`build_nand2b_guard_pair_v4.py` widens only the shared M4 supply rails from
0.8 to 1.6 um. Their original x envelope is retained, so the native macro
footprint does not grow. Child devices, guard capacitors, signal routing,
port centers and the native schematic are unchanged. Physical artifact
`nand2b_guard_pair_physical_v2/5946b21d55ad3174` passes zero-error Magic DRC
and unique Netgen LVS. Earlier narrow-rail evidence remains unchanged.

Fresh extraction with `extract_nand2b_guard_pair_v3.py` produces
`nand2b_guard_pair_rc_v2/e88c835f6f468a6b`: 988 resistors and 286 capacitors,
with positive resistors/nonnegative capacitors and a fresh topology match.
Exact protected-node reduction retains 789 resistors. Independent receipt
`nand2b_guard_pair_rc_verification_v2/9360f971d6120228` reaudits the raw and
reduced networks, native GDS/source/interface identities and fresh strict
LVS. These receipts qualify component geometry and extracted topology
only. They do not establish clock timing, voltage safety or legal codes
for the changed metal. No old timing result or candidate admission is
transferred to this variant.

### Local power-grid experiments and native frame integration

`weighted_bank_wide_power_frames_v4.py` produces the bound replacement
view `weighted_bank_wide_power_frames_v2/21af22833c328beb`. It preserves
all eleven macro placements, compares the schematic byte-for-byte,
checks every non-M4 mask layer by XOR, and requires the M4 XOR to equal
exactly the two intended PG width increments. Hierarchy, labels, signal
pin text and the macro footprint are unchanged. MIM M3 keepouts are
retained. Its consumer regenerates the geometric proof and view mapping.
The two initial view artifacts `1bc0f34ca440089d` and `85af602beaad6edc`
are held: their JSON round-trip proof comparison mishandled tuple/list
containers. Their physical comparisons passed, but their own binding
failed. Revision v4 canonicalizes the full proof before comparison; the
older sources and outputs are retained.

`weighted_bank_row_strip_v2.py` derives the control extent from all sixteen
source cells and actual native LEF dimensions. Its Tcl retains the unique
row segment containing that full extent and removes only generated
`tapvpwrvgnd_1` instances outside that segment. It refuses to remove an
original instance and compares all 94 original model/terminal/net
attachments before and after trimming. The replay removed 345 empty row
segments and 2,117 generated taps; the retained row is
(178.940,296.480)-(334.420,299.200) um. The macro hierarchy, including its
internal body taps, remains intact. All controls retain their planned
positions. Supply connectivity is not inferred from this reduction.

`probe_weighted_bank_pdn_v2.py` through v7 retain distinct harness and grid
attempts. The first two harnesses lacked LibreLane's SCRIPTS_DIR and
VDD_NET/GND_NET initialization; the corrected bootstrap binds the actual
installed global-connection Tcl. The local-grid replay
`weighted_bank_pdn_replay_v2/163839f24f1d7653` encounters PDN-0179 with the
original unused rows. Single-row replay `b1d8301c50d412b7` generates a grid
but both supply checks fail. Its initial report filename accidentally
contains a literal `$net`; revision v6 separates the two supply reports.
The source and output of every attempt remain unchanged.

With the wider pair and original local-strap offset, full-flow v6 artifact
`weighted_bank_bringup_v2/c04aa6ed721dae74` stops at PDN-0233: all 31 local
guard grids are empty after generation. All original connections remain
intact in the partial database. V6 and successors also require a fresh
power-grid check after detailed placement, in addition to the original
placement and interface checks. Failed/partial database checks cannot
admit the design.

The explicit-domain experiment v7,
`weighted_bank_bringup_v2/7fa32d9d426587cb`, fails earlier at PDN-0190
(unable to determine row pitch). A separate direct OpenDB check shows
that the original core boundary actually remains
(5.520,2.720)-(334.420,456.960) um after row trimming. The hypothesis that
the domain shrank is therefore unsupported, and this variant is held.
Untrimmed diagnostic `3039cc7f9be17887` retains that explicit-domain
failure. Diagnostic `e8e62398748bfea1`, using the default domain, writes
separate supply error reports and actual DEF/ODB geometry. Both supply
checks fail, and disabling trimming is explicitly nongating.

The latter diagnostic identifies a concrete local-strap offset error:
its M5 ground stripe overlaps the wider M4 pin only over
12.900--14.300 um, rather than the complete 12.700--14.300 um pin. The
nominal 1.6 um landing is reduced to 1.4 um by a 0.2 um offset. The next
normal-flow experiment centers the straps at native relative Y=3.5 and
7.9 um; it retains all power-grid and failed-via checks.

`make test-full` passes 1,854 tests without skips in
`build/weighted-bank-local-power-v2-full-tests.log`. New row checks reject
missing controls, multiple rows, unexpected cell heights and orientation
changes. No routed-bank DRC/LVS/antenna/RC, native timing, code-ROM or PHY
admission follows from these physical preparation experiments.

Early-prepare joint-DCC case 3 (SS/40 C, 410 MHz, 60% duty) also completes
with startup/event, terminal-voltage and mean half-cycle pilot checks
passing. Mean half-cycle error is 4.042 ps; the largest individual error
is 50.248 ps (the approved limit applies to the mean). The independent
four-case verifier remains live, and the common-prepare negative controls
still fail their initial events. No full-PVT or hardware-warmup admission
is inferred. Original return-mux case 0 also finishes with numerical
collapse at 8.98872 ns, after the first input pulse; it supplies no complete
20 ns timing/safety result. Its raw and logs remain intact, and the shared
dispatcher naturally assigns the released engines to queued work.

### Centered local straps: legal landing, unresolved grid attachment

`harden_weighted_bank_v8.py` corrects the macro-local M5 offset to 3.5 um.
Artifact `weighted_bank_bringup_v2/f5cc0a306bae5804` again reaches detailed
placement with all original instances placed, all 22 signal I/O pins
shaped, unchanged macro boxes and the full original interface intact.
The supply check still fails for all 62 guard-pair PG pins. The generated
DEF now has correctly centered M5 stripes, but they run only from each
macro's left boundary to its right boundary. They do not reach the main
grid. The normal flow and its post-placement check remain held; local
via legality is not a power-connectivity pass. All earlier source and
failure artifacts remain intact.

Independent joint-DCC receipt
`native_static_dcc_verification_v2/613812473724653c` is now complete. It
regenerates the four original decks/libraries, validates the raw hashes
and independently remeasures the results. Both early-prepare cases pass
at the approved 40% and 60% endpoints. Both common-prepare negative
controls retain their failed startup-event checks, so the all-four-case
receipt is deliberately not an aggregate pass. The early-prepare subset
is SS/40 C, 410 MHz, component-RC evidence only; full PVT, hardware warmup,
whole-backend RC and PHY admission remain open.

### Native-pitch chip-wide grid: supply continuity restored

`harden_weighted_bank_v9.py` replaces the isolated macro-local grids with
chip-wide M5 ground/power stripes aligned to the native guarded-bank
rows. M5 ground centers are 13.5+28.6*n um and power centers are
17.9+28.6*n um. The 1.6 um-wide M4 supply pins overlap these stripes
fully. This preserves the fixed native macro coordinates and avoids
separate local-grid attachment paths. M4 stripes and native M3/M4/M5
connections remain physically generated by OpenROAD.

Artifact `weighted_bank_bringup_v2/20cdfcda3ad15424` passes PDN generation
with **zero power-grid violations** for both supplies. OpenROAD reports
all shapes on VPWR and VGND connected. This is the first complete supply
connectivity result for the wider physical bank; it is not a whole-bank
route, geometry or electrical qualification.

Detailed placement is still held. The row reduction introduced overlapping
control/tap instances and padding failures; all 94 original instances,
connections, macro boxes and 22 placed signal I/O pins are nevertheless
preserved in the partial database. No placement check is bypassed. The
next variant retains the successful chip-wide grid and restores the
original complete row/tap context so the legalizer can place the controls.
The earlier row-reduced and disconnected-grid artifacts remain immutable.

The physical fine-control repair pilot also completes its guarded DATA=0
case with settling and native terminal screening passing; the maximum
terminal difference is 1.895250 V. The complementary DATA=1 case and
independent complete receipt remain prerequisites for starting the staged
whole-bank electrical experiment. One case is not a control-repair gate.

### Connected PDN and legal full-bank placement

The successful producer is `harden_weighted_bank_v15.py`, consuming native
wide-power frame `weighted_bank_wide_power_frames_v2/21af22833c328beb`.
Artifact `weighted_bank_bringup_v2/28a6b803538e79b7` completes the normal
Classic flow through detailed placement with return code 0. PDN metrics
report **zero violations on VPWR and VGND**. A fresh OpenROAD process
reloads the final database and independently passes `check_placement`,
both `check_power_grid` calls, all original model/terminal/net identities,
all public directions/uses, placement of all 94 original instances, all
78 unchanged macro boxes/orientations and geometry on all 22 signal I/O
pins. `placement_bringup_passed` is true. `physical_implementation_passed`,
`route_complete`, electrical qualification and PHY admission remain false.

The row/power requirements are separated by phase. During PDN generation,
`weighted_bank_row_strip_v3.py` retains the active control row and the
original boundary row segments: four segments in total. It removes 342
unused segments and 2,067 generated taps, preserving every original
functional instance and all macro-internal taps. The native-pitch global
M5 grid supplies the guarded pairs directly. A bottom M5 power/ground
pair supplies the retained boundary row below the first macro row.

For placement, `weighted_bank_row_restore_v3.py` restores all **346 exact
original row records**, including name, site, origin, orientation,
direction, site count, spacing and bbox. Rows are placement metadata;
unused taps and unnecessary M1 rails are not reintroduced. The callback
requires the complete before/after row signature multiset to match and
checks that the instance count and all 94 original circuit attachments
are unchanged. It executes only after successful normal PDN generation,
before LibreLane writes the database and checks power. Failed generation
and report/check-only PDN commands cannot trigger successful restoration.
The final legalizer can therefore use the original floorplan, while
post-placement power checks require every actually placed cell to have
connected supplies. No placement or supply check is suppressed.

The installed Classic flow has no dedicated post-PDN hook. The bound
configuration registers a single-use Tcl command-leave callback on
`pdngen`; no installed tool script or shared solver dispatcher is edited.
The loader executes configuration in a Tcl procedure, so the retained
metadata variables are explicitly scoped for that callback. The initial
callback's scope failure is retained unchanged.

The remaining attempts explain the final phase separation:

| Producer | Artifact under `weighted_bank_bringup_v2` | Held result |
| --- | --- | --- |
| v10 | `c30bc2d12cad9bd8` | Restoring all rows before PDN restores PDN-0179 channel failures. |
| v11 | `427ce7dd5eedf7ba` | Boundary rows plus a bottom power strap leave one ground channel failure. |
| v12 | `3601494654cf1213` | Separate single-net bottom strap specifications still leave that ground channel failure. |
| v13 | `9bf0bf463081a70c` | A conventional two-net bottom pair gives zero PDN violations, but permanently sparse rows produce fourteen macro padding failures in the legalizer. |
| v14 | `46fdad265e618de0` | The restoration callback reaches generation but fails because configuration-loader-local variables are unavailable to it. |
| v15 | `28a6b803538e79b7` | Explicit callback scope plus exact post-PDN row restoration passes both placement and supply connectivity. |

Native contract receipt
`weighted_bank_row_restore_contract_v2/d5798b4241e89f77`, produced by
`check_weighted_bank_row_restore_v3.py`, independently exercises the actual
OpenDB metadata under a procedure-scoped loader. It reproduces the old
scope error, verifies the corrected 346-to-4-to-346 row transformation by
comparing complete serialized native row records, and proves that an
injected generation failure retains the four-row state. This contract
stubs PDN and is explicitly not a power-grid or physical qualification;
the real full-flow result above supplies that evidence. Initial contract
`c40e71298c53379b` is held for its output parser dropping an empty trailing
result field; revision v3 preserves that field. All failed source and
output variants are retained.

The regression suite passes 1,854 tests without skips in
`build/weighted-bank-row-restore-v14-full-tests.log`. The final source set
is also checked by `build/weighted-bank-placed-power-v15-full-tests.log`.
Signal routing, complete bank GDS DRC/LVS/antenna, fresh intercell/grid RC,
native timing across the required PVT matrix, legal code admission and
full link qualification remain required. The electrical candidate is not
started without its independent complementary fine-control repair proof;
these placement results do not waive that prerequisite or reuse timing
results from the narrower power rails.

The complementary guarded DATA=1.8 V fine-control case has now completed.
Terminal screening passes (peak 1.895253 V), but settling fails for the
largest fine bit at codes 31 and 16. Its maximum CAP-node error is
0.226052/0.226045 V against the unchanged 0.18 V limit, while the control
driver error is only 0.001571 V. This localizes the next investigation to
the largest capacitor/switch branch rather than accepting the controls as
repaired. DATA=0 passes. The whole-bank electrical gate remains closed;
inspect the completed charge curves and strengthen or revise that branch,
then repeat native geometry/RC and both bias checks before admission.
The final regression run passes 1,854 tests without skips in
`build/weighted-bank-placed-power-v15-full-tests.log`.

### Largest fine-cell charge diagnosis and stronger native transmission gate

`diagnose_weighted_fine_charge_v2.py` binds the completed guarded DATA=1.8 V
case from `weighted_fine_control_v3/f276c77a9801f293`, validates its complete
raw/deck hashes and independently repeats the original measurement.
Receipt `weighted_fine_charge_diagnosis_v2/cc501aa4c8cf3fa5` reproduces only
the two bit-4 settling failures (codes 31 and 16), while terminal screening
passes. Every one of the thirteen resistor-connected CAP nodes is observed.
The minimum plate voltage is 1.573948 V at 1.5 ns after selection and
1.716844 V at 1.9 ns. All plate nodes reach the unchanged high-state limit
at 1.5955 ns after either selection. The control-driver error is about
1.57 mV in the original settled window. This is evidence of continued
charging after the 1.5 ns deadline, not evidence of a permanent voltage
ceiling. It does not itself prove a repair.

`weighted_fine_repair_v2.py` doubles only the bit-4 transmission gate:
NMOS width 1.68 -> 3.36 um and PMOS width 3.36 -> 6.72 um, retaining
0.15 um length. The clear NMOS remains 1.68 um wide, and the 8x12 um
weighted MIM and 2x2 um control shunt are unchanged. The other four fine
bits are unchanged. No settling window, voltage limit or supply changes.
Source regression checks verify exactly these two width changes and
preserve all other devices, connections and primitive parameters.

`build_weighted_fine_repair_v2.py` produces native geometry
`weighted_fine_repair_physical_v2/cba9bb198826abb7`, with zero Magic DRC
errors and unique Netgen LVS. It retains the model name and five-port
interface inside a separate immutable physical artifact; no earlier
source, GDS or RC file is overwritten. The PCell dimensions and junction
geometry are generated from the actual larger devices.

Fresh extraction `weighted_fine_repair_rc_v2/84611c007287da47` contains
443 resistors and 64 capacitors. Exact protected-node reduction retains
368 resistors. Independent receipt
`weighted_fine_repair_rc_verification_v2/85ccacc712f50848` verifies raw and
reduced passivity, native mask/source/interface identity and fresh strict
LVS. The actual three-MOS/two-MIM topology is preserved, including native
junction areas/perimeters; the old small-device parasitics are not scaled
or reused for the larger transmission gate. These are geometry and RC
proofs only. New settling, terminal-voltage and whole-bank timing results
remain required. `make test-full` passes 1,856 tests without skips in
`build/weighted-fine-repair-v2-full-tests.log`.

### Matched native bias pilot for the stronger largest fine switch

`weighted_fine_repair_rc_families_v2.py` consumes both the original complete
five-cell RC receipt and the independent single-cell repair receipt. It
requires matching original physical provenance, identical bit-4 public
port order, clean native DRC/LVS, both raw/reduced passive networks and
fresh strict topology proof. It replaces exactly bit 4 in the selected
five-model family; the other four RC models are retained unchanged.
The repair remains a separate experimental physical variant, and the
previous successfully placed bank is unchanged.

`probe_weighted_fine_control_v4.py` prepares
`weighted_fine_control_v4/bf80210dbae10cb1`: four SS/40 C, fixed-1.8 V
cases crossing guarded/source drivers with DATA=0/1.8 V. The original
12 ns stop, 20 ps control stimulus, code sequence [0,31,0,16,15,0],
1.5--1.9 ns settled windows, 0.18 V errors and 1.95 V terminal limits are
unchanged. Native mapped-device counts remain 205 for guarded and 45 for
source mode. The changed layout has fourteen resistor-connected bit-4
plate observation nodes; all are probed, together with all other fine
plate and native MOS terminal nodes. A direct comparison of the prepared
old/new RC libraries confirms that only `openlvds_weighted_fine_root_b4_v2`
changes. No favorable single plate finger or ideal CAP alias is used.

The pilot and independent verifier run persistently under
`openlvds-weighted-fine-control-v4-pilot.service` and
`openlvds-weighted-fine-control-v4-verify.service`. Two worker tickets are
queued through the existing six-engine priority/aging dispatcher; the
remaining two cases follow within the same two-worker campaign. Healthy
existing solvers are not stopped or restarted, and the dispatcher or lock
inodes are not edited. Queue ticket PIDs are container-local; service and
host process state, not a different container's `/proc`, identify liveness.

The verifier regenerates every selected library, pin order, MOS/plate
witness and fixture, validates complete raw/deck hashes, and independently
remeasures all four numerically complete cases. The changed-cell source
and its results are not production admission. No settling repair, active
clock, whole-bank range, full-PVT timing, legal-code ROM or PHY pass is
claimed while these transients are pending. The existing whole-bank gate
and prior failed measurements remain unchanged. The regression suite
passes 1,856 tests without skips in
`build/weighted-fine-repair-v2-full-tests.log`.

### Repaired full-bank candidate and matching control-proof gate

`probe_weighted_direct_v4.py` prepares the full sixteen-choice direct-port
bank with the verified wide-power NAND2B pair and stronger bit-4 fine RC.
Artifact `weighted_direct_v4/c466d6eb048d9e82` retains both coarse 0/1
pilots, all six LSB/carry/repeat words [0,1,15,16,31,0], the original 60 ns
fixtures, fixed 1.8 V, 100 ps data input, 20 ps control, 20 fF load, 2 ps
maximum step and ITL4=100. Its native topology has all 94 original root
instances; no input/output buffer, coarse choice or fine bit is removed.
Only the top-level model identity changes; the selected component RC is
updated explicitly through typed independent receipts.

`wide_guard_pair_rc_families_v2.py` requires the wide-power pair's distinct
verification revision and checks both raw and reduced passivity, native
source/GDS identity and strict topology. The old narrow-rail receipt
cannot stand in for it. The fine family similarly selects exactly the
independently verified stronger bit-4 cell and retains the other four.

`weighted_bank_control_gate_v3.py` requires the independent v4 fine-control
receipt for the exact clock, original-fine-family and repair identities.
Both guarded DATA biases must pass settling and terminal screening, and
all four declared cases must finish without numerical errors. Reference
driver passes cannot replace a failed guarded high-data result. A direct
negative run with an unrelated completed receipt is rejected before any
execution state, control admission file or SPICE worker is created. The
full-bank candidate remains **prepared and unstarted** while the new
control proof is pending. The previous gate and artifacts are unchanged.

`verify_weighted_bank_repair_network_v2.py` produces
`weighted_bank_repair_network_v2/40bd36174ccc813b`. It regenerates every
selected candidate library/order/MOS witness and compares the complete
native leaf multiset against the full physical root hierarchy, including
all connections, parameters and multiplicities. The proof retains 38,162
resistors, 16,993 capacitors and 2,647 native primitive calls, all 94 root
instances and 24 public ports. No passive clipping, favorable node
selection or dimension normalization is used. This is structural/native
component identity, not intercell RC, timing, code-ROM or PHY admission.
The independent full-bank verifier is updated to require the same repair
identity and to remeasure complete regenerated waveforms before reporting
sparse feasibility.

Regression checks reject mismatched repair/clock/fine identities, missing
or failed high-data coverage, numerical failures and old-profile receipts.
They also preserve the complete bank topology and all sixteen turn choices.
`make test-full` passes 1,863 tests without skips in
`build/weighted-bank-repaired-integration-v4-full-tests.log`.

### Repaired fine cell integrated without moving global access rails

The stronger native bit-4 cell is 45.38 um tall rather than 43.70 um, and
its five public M3 access rails move upward by 1.68 um within the cell.
`weighted_bank_repaired_fine_frames_v2.py` computes the common pin motion
from the actual LEFs and moves only `fine4` downward by 1.68 um, from
Y=224.80 to 223.12 um. Its top edge and every external access rectangle
are preserved. The bottom extends into the existing empty gap; the
complete placement passes the existing non-overlap check. Native antenna
metadata is retained from the new geometry rather than copied from the
smaller device.

Frame `weighted_bank_repaired_fine_frames_v2/4c57007a2e3eb994` binds the
complete repaired-bank network proof, the prior wide-power physical family
and the actual stronger cell. Normalization adds only the zero-origin
translation, exact PR boundary and native MIM M3 keepouts: every physical
layer has zero XOR against the translated new native source and hierarchy/
labels match. It is not an assertion that the old/new transistor geometry
is unchanged. Two independent OpenROAD reads verify all 377 global pin
rectangles identical across all 78 macros; all other macro boxes are
unchanged, and the intended bit-4 body/placement change is recorded.
Regression tests reject non-rigid pin motion, altered supply-pin geometry,
changed public types and missing pins, while allowing regenerated antenna
area metadata.

`harden_weighted_bank_v16.py` consumes that frame and the prior successful
bank placement checkpoint. It regenerates the original RTL/blackbox views
without changing a public name, instance or logical attachment, then runs
the normal row-preserving PDN/I/O/detailed-placement flow. Artifact
`weighted_bank_bringup_v2/b2f5392bcbc09a9f` exits 0 and passes a fresh final
OpenROAD reload: all 94 original instances placed, all 22 signal I/O pins
shaped, original model/terminal/net/public-interface checks passing, all
macros at their newly declared positions, legal placement and both supply
connectivity checks passing. The earlier successfully placed cell variant
remains intact. These are CAD bring-up results only; settling, whole-bank
signal routes/GDS DRC/LVS/antenna/RC, native timing, code admission and PHY
qualification remain open.

### First repaired-bank signal route: zero router DRC, held diode supplies

`harden_weighted_bank_v17.py` runs the repaired bank through normal detailed
signal routing. Artifact `weighted_bank_bringup_v2/7890e1ccbecadcb4`
reaches that target with return code 0, 15,506 um routed wire length,
zero final router DRC errors and zero reported routing antenna violations.
The router clears 86 initial DRC markers over four iterations. Original
interfaces, instances, declared macro positions and I/O geometry remain
intact. A separate stream read also confirms zero physical-layer XOR and
matching hierarchy/labels between the written repaired-cell GDS and its
translated native source, in
`build/weighted-bank-repaired-frame-stream-xor-v2.json`.

The routing result is nevertheless **held**: the final power checker finds
unpowered antenna diodes added after the sparse PDN was generated.
`ANTENNA_3` is on net `low`, at (22.54,451.52) um, and lacks its lower
VPWR rail. `ANTENNA_4` is on `lvds_fine0_net`, at (257.60,38.08) um, and
lacks both supplies. Their logical PG attachments are correct; actual M1
supply shapes are disconnected. All five antenna diodes are retained and
no supply check is waived. `routing_bringup_passed`, route completion and
physical/electrical/PHY admission remain false despite zero router DRC.
The next fix must prevent later physical cells from occupying unpowered
sites while retaining the full row metadata needed by the legalizer.

### Powered placement sites restore routed-bank supply connectivity

`weighted_bank_row_restore_v4.py` restores all 347 row records after
successful sparse PDN generation and adds hard placement blockages over
exactly the 343 restored, unpowered row segments. The four powered segments
remain available for later physical cells. No antenna diode is disabled,
and no power check is waived. Native contract receipt
`weighted_bank_row_restore_contract_v2/5144c8659e85cbef` verifies exact row
metadata, exact blockage bounding boxes and hardness, unchanged original
circuit attachments, and no restoration/blockages after injected PDN failure.
This contract uses stubbed generation and does not itself qualify power.

`harden_weighted_bank_v18.py`, using PDN configuration v19, completes normal
detailed routing in `weighted_bank_bringup_v2/96f389f143f5b827`. A fresh final
database read passes both VPWR and VGND connectivity checks, the original
interfaces, all declared macro positions, all 22 signal I/O shapes, and
placement of every physical instance, including inserted cells. Final
router DRC errors are zero. Placement and routing bring-up are accepted;
independent conductor completeness, full GDS DRC/LVS/antenna/RC, native
timing, code ROM and PHY admission remain open. The matched repaired-cell
electrical control campaign remains required before full-bank simulation.
`make test-full` passes all 1,863 tests without skips, recorded in
`build/weighted-bank-powered-sites-v18-full-tests.log`.

### Repaired-bank GDS physical checks

`signoff_weighted_bank_v2.py` continues the accepted detailed-routing state
in a separate artifact, binding every initial view and the original source/
PDK/tool chain. Artifact `weighted_bank_signoff_v2/d7f594787b9c9899` runs the
unchanged Classic steps from routing-obstruction removal through `Checker.LVS`.
The actual step reports show zero critical disconnected pins, zero antenna
violating nets/pins, zero Magic and KLayout DRC errors, zero illegal overlaps,
zero GDS stream XOR differences and zero standard LVS errors; Netgen reports
a unique match. Filler insertion adds 274 cells, making 430 total instances.
A separate fresh filled-database read in `build/weighted-bank-filled-db-check-v2`
passes both supply grids, all physical placements, original interfaces and
declared macro positions. The generic disconnected-pin reporter emits one
noncritical diagnostic for the ground-only shared MIM macro; its exact native
port/connection checks remain enforced, with no ignore-list addition.

This standard LVS stage does not replace fully expanded native-device LVS.
Macro timing models are absent and the existing SDC excludes the native analog
paths, so flow STA/RCX results do not qualify delay or code selection. The full
software suite passes 1,865 tests without skips in
`build/weighted-bank-full-signoff-v2-full-tests.log`; two additional targeted
extraction-admission tests pass separately.

`extract_weighted_bank_rc_v2.py` requires successful physical checks and exact
bindings of all actual state/output files before extraction. It repeats final
OpenDB interface/placement/power checks, expands every actual inserted and
original instance through its own schematic scope, and requires fresh flat RC
to match that native primitive reference under strict Netgen comparison.
Both raw and simulator-facing reduced networks must pass elementwise passivity;
all public terminals must survive. No extracted bank is admitted by route-only
success or by standard macro-level LVS alone. Delay range, legal-code ROM,
all-PVT clock timing and full PHY qualification remain open.

### Fresh routed weighted-bank RC and strict native topology

`weighted_bank_rc_v2/6329bc664bdd5ab3` completes successfully from the clean
repaired-bank physical artifact. Its fresh final-database check passes original
interfaces, all physical placements, macro positions and both supply grids.
The actual 430 routed instances expand to 2,651 native primitive calls, including
the four inserted antenna diodes; empty filler/tap schematic scopes remain
represented in the per-instance count record.

Flat GDS extraction produces 86,395 resistors and 18,445 capacitors, all passing
the positive-element passivity screen. Exact positive-conductance star-mesh
reduction leaves 58,762 resistors and preserves all 24 public ports. A separate
reread of the simulator-facing reduced netlist also passes passivity. Strict
Netgen comparison after comment-aware resistor collapse reports a unique match
against the fully expanded native reference. The extraction namespace is
`build/extracted/5c5dd057603db840/openlvds_weighted_bank_physical_v2`.

This establishes fresh whole-bank passive RC and native DC topology only.
Independent consumer verification, repaired-cell settling admission, routed
native timing/range/monotonicity, legal-code ROM, all fifteen PVT conditions and
the complete clock/link qualification remain required. No timing, electrical
qualification or PHY admission flag is set by this result.

### Independent routed-bank RC consumer verification

`verify_weighted_bank_rc_v2.py` produces receipt
`weighted_bank_rc_verification_v2/b768f526ef43c1d8`, passing a new read of the
actual final OpenDB and both power-grid checks. It reconstructs all 430 instance
scopes and 2,651 native primitive calls, reproduces the exact native-reference
bytes, independently regenerates the 58,762-resistor simulator model from the
86,395-resistor raw extraction, and repeats strict flat LVS with a unique match.
Both raw and reduced networks pass passivity, and all 24 public ports survive.
The receipt's consumer validates its source chain, actual output hashes,
regenerated reference/model and strict LVS log. This closes independent RC
consumer verification for this bank variant; native timing and PHY remain open.

### Staged native timing using complete routed-bank RC

`probe_weighted_routed_v2.py` prepares
`weighted_routed_v2/9bbfa0849b136d25` directly from the independent RC receipt.
Its `bank.spice` is byte-for-byte identical to the verified simulator-facing
model, retaining all 2,651 native primitive calls, all 24 public ports and the
complete sixteen-choice coarse topology. Two SS/40 C cases select coarse 0/1
and apply codes `[0,1,15,16,31,0]` with the prior 100 ps input transitions,
20 ps control transitions, 20 fF output load, 2 ps maximum step and ITL4=100.
These are isolated diagnostic pulses, not a periodic clock or all-PVT result.

`weighted_routed_observation_v2.py` resolves actual native pin aliases from the
flat extraction and groups the actual resistor-connected control nodes. It
observes all 2,495 low-voltage MOS devices for every terminal pair, and all
2,291 distributed nodes of 15 coarse and ten fine/complement control nets.
Missing or disagreeing pin aliases, disconnected control components, control
shorts and unknown native primitive types are rejected. This grouping changes
observation metadata only; it neither shorts nor edits the simulated network.
The model's four antenna diodes, 150 native MIM calls and two native resistor
calls remain present.

Execution requires the independent physical fine-control v4 receipt for the
exact clock/fine/repair components selected by the routed physical source
chain. The unrelated completed DCC receipt is rejected in
`build/weighted-bank-routed-pilot-v2-negative-gate.log`, before creating a lock,
run state, control-gate record or solver request. The matched repair campaign
is still waiting on the shared dispatcher, so the routed pilot remains prepared
and unstarted. Existing live solvers and dispatcher policy are unchanged.

`verify_weighted_routed_v2.py` regenerates the full RC copy, native observations
and each deck, checks every retained raw/deck/log hash, remeasures complete raw
traces, and repeats the exact settling prerequisite before publishing a sparse
screen. It reports missing/extra pulses, distributed control errors, terminal
stress, LSB/carry direction and size, sampled monotonic order, coarse overlap,
minimum-quarter headroom and code-zero repetition. A 20 ps repetition guard is
an additional diagnostic screen; sparse success still cannot admit a dense
code table, periodic clocks, all-PVT timing or the PHY.

The full software suite passes 1,873 tests without skips in
`build/weighted-bank-native-rc-consumer-v2-full-tests.log`. Three subsequently
added raw-verifier assessment tests pass separately in
`build/weighted-bank-routed-verifier-v2-tests.log`.

### Matched settling-to-routed-timing continuation

`continue_weighted_routed_v2.py` prepares
`weighted_routed_followup_v2/dc345835ff7729e3` and runs as
`openlvds-weighted-routed-v2-followup.service`. It binds the exact staged
routed model, repaired fine-control campaign, source files, libraries, decks
and both live producer/verifier systemd invocation IDs and main PIDs. Its
current state is `waiting_physical_fine_control`; no routed solver has started.
Transient owner-observation failures retry without declaring the producer
stopped. An owner replacement, incomplete/error case coverage, missing receipt
after verifier exit or ambiguous matching receipts holds the continuation.

After all four native control cases finish, the coordinator selects only the
matching independent v4 receipt and executes the original physical settling
gate for the exact clock/fine/repair inputs. A failed gate cannot request a
routed solver. A passing gate starts the already prepared routed pilot through
its unchanged shared-dispatch leases, followed by independent full-raw timing
verification. It never takes over an already started pilot, retries simulations,
changes dispatch policy or admits a code table/PHY. Sparse failures remain
retained diagnostic results.

The failed whole-counter v7 read-only verifier was also recovered. Its journal
shows it exited at startup because the pilot's `state.json` did not yet exist.
The pilot is now actually running with that state present; restarting only the
failed verifier restores its wait on the original pilot. No solver, pilot,
native model or existing artifact was restarted or modified. This is observer
recovery, not new counter timing evidence.

`make test-full` passes 1,879 tests without skips in
`build/weighted-bank-routed-followup-v2-full-tests.log`, including exact-owner,
missing-state, failed/incomplete coverage and receipt ambiguity checks.

### Completed post-pulse ITL4 comparison: identical terminal failure

The SS/40 C minimum-code matched iteration case finishes with a numerical
abort, so both cases in `dcdl_iterations_v2/a994d04ddcc0bdbb` are now terminal
failures. `diagnose_dcdl_iterations_v3.py` extends the earlier pre-input-only
diagnostic to the explicitly supported interval after the first input fall
and before the second input rise. It regenerates both decks and solver
translations, verifies every terminal output hash and preserves all failed
artifacts. Printed abort times are compared at the precision actually emitted
by the solver; binary record/payload comparisons remain exact.

Receipt `dcdl_iteration_failure_v3/89668a2c13e79181` proves that the default
and ITL4=100 case-0 waveforms contain exactly the same 36,611 records across
2,671 variables, ending at 8.98871830810505 ns. Their binary payload SHA256 is
`025b959c221e4aaf1db8ce217baa08718d5465e85f148b069057706355059e78`.
Both report time 8.98872 ns, timestep 2.5e-24 s and `bin#branch`. Thus increasing
the iteration allowance does not resolve this retained post-first-pulse
failure, in addition to the earlier identical pre-input case-2 failure.
The reported source branch is not established as the circuit root cause.
Elapsed wall times of these individual runs do not establish a speed comparison.

These are incomplete 20 ns experiments; no complete pulse/timing, voltage
safety, legal-code or PHY gate is passed. This negative result does not alter
the separate guarded repaired-bank source, prepared routed timing pilot,
settling prerequisite or healthy solvers. The two additional diagnostic tests
pass in `build/dcdl-iteration-inter-pulse-failure-v3-final-tests.log`.

### Routed-pair phase counter: low-clock margin regression

The routed-pair counter campaign `static_phase_clock_release_v6/d88c3462d0e8e585`
now completes all four SS/40 C, 410 MHz, 40/60% duty and stop-level cases with
zero numerical errors. Its failed read-only verifier had the same startup
missing-state race as v7; restarting only that failed verifier after the
running pilot's state existed produces independent receipt
`static_phase_release_verification_v6/873bb7ac75a7b2ee`. Every declared raw
waveform is verified, but the combined profile fails. The two 40% cases pass;
the 60% cases fail the phase qualification screen. This is retained negative
electrical evidence, not a numerical abort or a missing case.

`diagnose_static_phase_levels_v2.py` produces
`static_phase_level_diagnosis_v2/45e90e9ca55898dd` for case 2 and its exact
passing o1 component baseline. It verifies all case output hashes, regenerates
both native fixtures and independently remeasures both complete 26 ns traces.
The actual intermediate and arming event orders pass in both models. The
failure is the delivered clock voltage when the three low-phase state
outputs cross their decision threshold:

| State | Passing baseline CLK | Routed-pair CLK | Baseline margin to CLK leaving 0.18 V low region | Routed-pair margin |
| --- | ---: | ---: | ---: | ---: |
| low0 | 0.037997 V | 0.224060 V | 62.777 ps | -19.827 ps |
| low1 | 0.017285 V | 0.184179 V | 76.852 ps | -1.888 ps |
| armed | 0.052317 V | 0.233408 V | 56.027 ps | -23.942 ps |

The near-event CLK samples show the next rising transition already in progress
at the routed-pair assertions. All three violate the unchanged CLK <0.18 V
low-phase condition. Terminal voltage remains within the 1.95 V screen, peaking
at 1.945427 V, versus 1.941526 V in the passing baseline. This distinguishes
late low-phase qualification from reordered counter events and terminal-stress
failure for this case. It directs the next circuit experiment toward native
clock-drive/fanout and local clock-path timing, with the level and voltage limits
retained. Stronger drive is a hypothesis requiring a matched native experiment;
it is not an accepted fix. Whole-counter RC, actual DCC first events, hardware
warmup, all-PVT and PHY qualification remain separate open gates.

### Matched native clock-drive experiment for the 60% low-phase regression

`probe_static_phase_clock_drive_v2.py` prepares
`static_phase_clock_drive_v2/5b5e068d257c374b` from the completed independent
routed-pair baseline receipt. It inserts exactly one additional call to the
existing certified BUF8_o4 RC model, on the same RCLK/CLK/power nets. Every
original counter, buffer and reset-load device witness is unchanged; exactly
22 private MOS witnesses are added, making 510 total. The complete second
native RC instance retains its own internal nodes, private MIM shunts and
parasitics. Devices are not resized and no node is clipped or clamped by a
new ideal source. Shared inter-driver wiring remains ideal in this diagnostic.

The four SS/40 C cases retain 410 MHz, 40/60% duty, both stopped-clock levels,
100 ps RCLK transitions, the original REQUEST sequence, 26 ns duration, 1 ps
maximum step, numerical tolerances, actual reset-input loads, CLK <0.18 V
qualification and the 1.95 V all-terminal limit. The measured clock voltage
at low0/low1/armed assertions and the minimum low-level voltage margin are
recorded alongside all original timing/event/reset/stress checks.

The pilot and independent consumer are live as
`openlvds-static-phase-clock-drive-v2-pilot.service` and
`openlvds-static-phase-clock-drive-v2-verify.service`, waiting on shared
dispatch slots with at most two pilot workers. No healthy solver or existing
campaign is restarted, and the six-engine policy is unchanged.
`verify_static_phase_clock_drive_v2.py` regenerates the native libraries,
single-added-instance topology, complete MOS coverage and every deck, then
remeasures every complete new raw waveform and all four matching single-buffer
baselines. It records event/time, voltage-peak and low-clock-margin comparisons.
An electrical failure can be retained as negative evidence; an incomplete
26 ns waveform cannot become a verified timing result. The watcher also waits
for initial state-file creation, avoiding the older observer startup race.

The candidate has no electrical result yet. Stronger clock drive remains a
repair hypothesis; it does not qualify joint DCC first events, hardware warmup,
all-PVT clocking or the PHY. The software suite passes 1,884 tests without skips
in `build/static-phase-clock-drive-v2-full-tests.log`.

### Physical parallel clock-buffer macro and fresh shared-wire RC

`build_clock_buffer_pair_v2.py` constructs
`clock_buffer_pair_physical_v2/3fc2cda807ff39a4` from the exact v4 producer
of the existing BUF8_o4 shunted cell. An initial pre-artifact attempt used the
older v3 producer and correctly rejected the mismatched source context; its log
is retained. The corrected build imports the actual child GDS twice and connects
A, X, VGND and VPWR on real common M4 rails with legal M3/via3 landings. The
two native child origins are (4.00,5.00) and (32.93,5.00) um. Both child
device/private-shunt hierarchies remain intact. The macro passes zero DRC and
unique LVS without waiving a check or changing a native device dimension.

A separate written-GDS reread in
`build/clock-buffer-pair-native-mask-proof-v2.json` verifies zero native-child
polygon-union XOR across all 31 layers and identical direct child hierarchy,
and confirms exactly the two declared native child instances. Native source
tests also retain separate private nodes and exact original dimensions while
sharing only the four public nets.

`extract_clock_buffer_pair_v2.py` produces
`clock_buffer_pair_rc_v2/6edaf2564cd39759` from the actual new GDS. It extracts
693 resistors and 231 parasitic capacitors, retaining 44 native MOS calls and
four native MIM calls. The raw network is positive-element passive. Exact
positive-conductance reduction retains 550 resistors and all four public ports
`A X VGND VPWR`; the simulator-facing model independently passes passivity.
Strict comment-aware flat LVS reports a unique native-source match.

Independent receipt
`clock_buffer_pair_rc_verification_v2/75e8452c193c91e7` regenerates the two
native source scopes, checks GDS/source/interface identity and both passivity
screens, reproduces the exact raw-to-simulator reduction, and repeats strict
flat LVS. Its consumer `bound()` also passes in
`build/clock-buffer-pair-rc-consumer-v2.log`. The simulator-facing pair is
`openlvds_buf_8_o4_shunted_pair_v2` in extraction namespace
`build/extracted/07f281758c4d2e63`.

These are physical/passive-RC/topology results for the proposed drive change.
They do not replace the queued clock-drive experiment or establish its phase
repair. A later integrated candidate must explicitly select the real shared-wire
model and requalify native timing, voltage, reset and clock startup before any
clock-island or PHY admission. `make test-full` passes 1,886 tests without skips
in `build/clock-buffer-pair-v2-full-tests.log`.

### Bounded voltage-PWL representation of the retained tanh input

The input-representation hypothesis is separate from a hardware repair.
Completed return-mux failures occur before input activity as well as between
pulses; the reported source branch is not a proven root cause. The live native
logs already confirm KLU is in use, so adding its option is not a new remedy.
The existing Xyce parser receipt `xyce_compatibility/ba10c72ce84ed18a` records
release 7.10.0 parsing successfully while substituting requested BSIM4 4.5 with
4.6.1. That is parser capability, not native-model equivalence or a speed result.
No engine, model version, numerical tolerance or existing solver is changed.

`tanh_voltage_pwl_v2.py` represents the original two-pulse tanh input with a
voltage PWL table. Each interpolation interval has an analytic error bound
`max(abs(f'')) * h^2 / 8`, including the sparse tails; the first-derivative error
is also bounded. The four 0.9 V midpoint epochs remain 2.1, 6.1, 12.1 and
16.1 ns, and each 10--90% rise/fall remains exactly 100 ps in the generated
table. No voltage clipping or waveform rescaling is applied.

The selected representation has 9,753 points, with 0.5 ps spacing within
600 ps of each transition and sparse samples elsewhere. Its certified maximum
voltage interpolation bound is 10.452486 uV, below the fixed 50 uV representation
limit; its slope-error bound is 0.083620 V/ns. The original ideal-source
waveform and this approximation are not asserted to be mathematically identical.
Tests sample every interval at three interior locations, preserve the complete
pulse epochs/slews and reject under-resolved tables rather than relaxing the bound.

### Full-native source-representation convergence isolation queued

`probe_dcdl_pwl_source_v2.py` prepares
`dcdl_pwl_source_v2/974118b4fe0abc11` from retained failed return-mux case 2:
SS/40 C, coarse 1, fine 0, 20 fF output load and 100 ps input slew. Preparation
regenerates the original native component libraries, full sixteen-coarse/
thirty-one-fine prototype and all 2,269 MOS witnesses. The copied library bytes
are unchanged. Only the fixture title and the behavioral tanh input source's
replacement by the bounded voltage-PWL representation differ; supplies, control
levels, two pulse epochs, 20 ns stop, 2 ps maximum step, integration method,
tolerances and saved terminal coverage remain intact. This legacy prototype
still has source mux/control/common wiring; it is not the repaired routed bank.

The one-worker diagnostic and independent verifier are active as
`openlvds-dcdl-pwl-source-v2-pilot.service` and
`openlvds-dcdl-pwl-source-v2-verify.service`, waiting under the unchanged six-engine
dispatcher. No existing source, model, live solver or admission gate is modified.
Its purpose is to test a numerical source-representation hypothesis; another
abort is a valid negative outcome, not a reason to substitute a partial pass.

`verify_dcdl_pwl_source_v2.py` regenerates libraries, native witnesses, both the
prepared and translated solver decks, and the analytic source certificate.
On a complete 20 ns run it independently remeasures the actual IN waveform
against the certified error, midpoint and slew bounds, and repeats all original
native pulse/control/terminal checks. Electrical measurement failures remain
separate from numerical completion. On a terminal timestep abort it verifies
the log, exact output hashes and incomplete raw-prefix time, publishing only a
failure diagnosis. Missing/incomplete waveforms cannot gain a complete-trace
or native pulse-screen verdict. The aborted baseline provides no full-trajectory
timing equivalence or speedup comparison in either outcome.

No numerical or electrical result is available yet. The repaired-bank settling
gate, routed timing continuation, clock-drive experiment, ROM admission,
all-PVT and PHY gates remain unchanged and open. The full software suite passes
1,891 tests without skips in `build/dcdl-pwl-source-v2-full-tests.log`.

### Repaired guarded fine-cell charging: completed bias evidence

Guarded cases 0/1 of `weighted_fine_control_v4/bf80210dbae10cb1` complete
numerically and pass settling and terminal stress at DATA=0 and DATA=1.8 V.
`diagnose_weighted_fine_repair_bias_v2.py` creates
`weighted_fine_repair_bias_diagnosis_v2/2604c09df777f191` by regenerating the
old/repaired native libraries and independently remeasuring all four completed
guarded traces. It verifies that only the bit-4 fine-cell RC block differs;
the remaining library bytes, source/guarded wrappers, port orders and stimulus
specifications match. All output/raw/deck hashes are bound.

At DATA=1.8 V, largest-plate errors at codes 31 and 16 improve from about
0.22605 V to 0.007501 V under the unchanged 0.18 V bound. All fourteen repaired
plate nodes enter and remain within that bound after 0.9775 ns, versus
1.5955 ns for all thirteen old nodes. Thus the repaired guarded cases meet the
original 1.5 ns settling deadline with about 0.5225 ns margin. The largest
remaining cap error across either repaired bias is 0.067718 V. Maximum MOS
terminal difference is 1.895252 V, below the unchanged 1.95 V limit.

This diagnoses the intended guarded DC-bias repair; it is not a four-case
campaign receipt. The two source-driver comparisons remain queued, and the
original independent four-case settling gate and routed-bank follow-up are
unchanged. No active-clock, whole-bank delay/ROM, all-PVT or PHY admission follows.

### Completed repaired fine-control gate and two-buffer pilot (2026-11-05)

`weighted_fine_control_v4/bf80210dbae10cb1` completes all four declared
12 ns cases without numerical errors. Independent receipt
`weighted_fine_control_verification_v4/598d971bfc6c62af` verifies every raw
waveform. Both guarded DATA biases pass settling and the 1.95 V terminal bound
(peak 1.895252 V). The ideal-source comparisons remain negative controls:
both exceed the terminal limit (peak 2.090524 V), and the high-DATA source
case also fails settling. The existing gate requires all four complete traces
and both guarded cases to pass; it does not require the ideal-source comparison
to be electrically safe. No gate was relaxed. Follow-up
`weighted_routed_followup_v2/dc345835ff7729e3` binds this exact independent
receipt and has advanced `weighted_routed_v2/9bbfa0849b136d25` to its original
sparse timing pilot under the unchanged shared dispatcher. No routed timing
pass or code-ROM admission is available yet.

`static_phase_clock_drive_v2/5b5e068d257c374b` also completes all four
26 ns cases. Independent receipt
`static_phase_clock_drive_verification_v2/b2ffb8be4df997f4` regenerates and
remeasures all new and matched single-buffer traces. The two-buffer component
model passes both approved 40%/60% duty endpoints and both stopped-clock levels
at SS/40 C, 410 MHz. Minimum clock-low voltage margin is 0.171854 V at 40%
and 0.185960 V at 60%; worst native terminal difference is 1.945490 V. The
previous single-buffer 60% cases remain failed in the comparison. The minimum
prepare/public-release margins are 489.848/683.660 ps. These results support
the drive-repair hypothesis in this fixture only: shared inter-driver wires
are ideal, and whole-controller routed RC, joint DCC first events, all-PVT
qualification and hardware warmup are still required.

### RX deskew update transaction with explicit physical settling

`openlvds_rx_deskew_transaction_v2` implements the missing per-code protocol
between the management-domain scanner and the source-clock deskew backend.
An accepted request holds the real DCC/startup path, waits for old clock
readiness to drop, and transfers code plus a new generation through the atomic
mailbox. Publication occurs only on a source-clock edge while the backend
permits updates and the hold has synchronized. Digital capture alone cannot
complete the transaction: the backend must report an unsettled level at or
after that physical commit, then assert settled with the matching sequence.
A low observed only before publication cannot refresh a stale matching high.
The tagged settling reply crosses back to management before the hold releases.
The existing startup controller must then provide fresh readiness after both
actual delivered clocks complete at least 256 warmup cycles.

One deadline spans hold, transport, physical settling and warmup. Source loss,
startup failure and timeout latch failure and hold the clocks. Model admission
defaults false. Enable-off cancels transport while retaining the last physical
code; only global reset clears that word. Canceled generations are not reused
on the next enable. The module emits no generated clocks and is not yet wired
into a production RX wrapper. In particular, the old training wrapper's digital
mailbox acknowledgement is not upgraded merely by adding this module. A new
RX coordinator still needs the single overall startup/training deadline,
controlled-update versus unexpected clock-loss handling, and actual backend
settling integration.

The composed bench `tb_rx_deskew_transaction_v2` uses the existing startup
controller and clock-hold DCC topology with explicit test-only cell delays.
Twelve scenarios cover consecutive safe updates, withheld update permission,
wrong/stale settling tags, missing settling, a low seen only before commit,
source loss, missing model admission, stale clock readiness and cancellation
both before and after physical publication. Each completion independently
checks both delivered-edge counts, physical acknowledgement and code identity.
These are control/CDC protocol checks, not SKY130 electrical timing evidence.

Final verification passes all 1,892 software tests without skips
(`build/rx-deskew-transaction-v2-final-full-tests.log`). Yosys process/optimization/
check reports zero problems with admission enabled and with the default closed
(`build/rx-deskew-transaction-v2-final-yosys-admitted.log` and `-default.log`).
A separate negative-control run deliberately restores the precommit-only low
guard in a temporary source copy; the unchanged bench rejects its stale-high
completion (`build/rx-deskew-transaction-v2-negative-guard.log`). No retained
producer, live solver, clock-duty descriptor or electrical admission gate changes.

### RX training now composes physical update transactions and real startup

`openlvds_rx_training_v3` replaces the old wrapper's digital-capture-only code
acknowledgement with `openlvds_rx_deskew_transaction_v2`. Each scanner request
holds both actual DCC reset paths, waits for a safe source-domain physical code
commit, requires a fresh matching physical-settle acknowledgement, and then
waits for both actual delivered clocks to complete 256 new cycles. Only then
can the scanner start its four-frame measurement. The forwarded source clock
remains independently monitored during intentional capture-clock holds; an
intentional hold is not reported as a missing delivered clock. Unexpected
clock loss still invalidates readiness and payload.

The wrapper emits one `dll_train` pulse and `dll_enable` for an external DLL
controller. Its single management deadline begins at the request edge and
covers DLL lock wait, initial warmup, every code transaction/measurement, eye
selection and final-code reapplication/revalidation. Successful intermediate
codes do not renew this deadline. The existing scanner still enforces the
physical-delay interval/250 ps training-clearance rules. The selected code
freezes during payload. This wrapper does not itself instantiate the DLL
calibration/measurement controller or qualify a physical delay table; that
connection remains required in the full RX control wrapper.

Capture command/result mailboxes and training/payload state reset whenever
capture stops, including retraining and intentional updates. Command generations
persist across cancellation; stale results cannot qualify the new code. The
physical deskew word retains its last value during cancellation, while each
new physical request receives a new transaction generation. Held training
levels cannot retrigger acquisition. ROM, deskew and DCC admissions independently
default false; invalid dimensions/deadlines and revoked tables fail closed.

Integration testing found that forwarding the registered startup-failure status
through a second sticky status register reports some clock losses after nine
management cycles. `openlvds_clock_startup_v3` preserves the v2 startup/reset/
warmup implementation and additionally exposes its existing combinational
clock-loss decode. The enclosing RX coordinator consumes that decode directly,
reserving one management edge within the original eight-cycle budget. No extra
heartbeat counter, reduced warmup count or relaxed loss limit is introduced.
The v2 startup and legacy RX wrapper remain unchanged.

`tb_rx_training_v3` composes the actual scanner, transaction, startup, atomic
mailboxes and training TX/RX with clock-hold DCC topology and explicit test-only
cell delays. Fifteen scenarios check complete 101-code scans, code 55 selection
with 349 ps clearance in the synthetic eye fixture, final revalidation, 64
payload pairs after the end marker, frozen code, intentional holds, stale/missing
settling, retraining cancellation, independent admissions, source/DLL/table
failures and one overall timeout spanning multiple successful updates. The
capture command checks physical settling and both delivered-edge counts at
every code. The final-revalidation and no-eye cases remain required failures.

`tb_rx_clock_loss_v3` stops either actual delivered phase at 80 offsets at each
of 390/400/410 MHz while initial warmup is incomplete: all 480 cases must report
sticky failure within eight management cycles with readiness, payload and DCC
resets invalid. The tests force no scan result, warmup counter or status signal.
The deliberately delayed-status negative control fails at nine cycles, as
retained in `build/rx-training-v3-delayed-status-negative.log`. All fifteen
integration scenarios and all 480 loss cases pass in
`build/rx-training-v3-targeted-tests.log`. These are protocol results using a
synthetic eye and settling backend, not native electrical timing certificates.

The complete software suite passes 1,894 tests without skips in
`build/rx-training-v3-full-tests.log`. Yosys process/optimization/check reports
zero problems at the production 13-bit/8,192-code dimensions with admissions
enabled and with default admissions closed (`build/rx-training-v3-admitted-synthesis.log`
and `build/rx-training-v3-default-synthesis.log`). These checks do not establish
mapped area, physical timing or electrical admission. The full routed-bank
SPICE pilot remains live; no retained native producer or gate was changed.

### Complete RX control composition

`openlvds_rx_control_v2` connects `openlvds_dll_control_v2` to
`openlvds_rx_training_v3`. The request edge starts actual four-section DLL
calibration and the same overall acquisition deadline. Real configuration
mailboxes, separate physical-settle acknowledgements, signed/swapped pair
measurements and the unwrapped period check remain in the calibration path.
After lock, the DLL codes and measurement engine freeze while the deskew scanner
performs each physical update, DCC restart/warmup and four-frame test. The final
selected code is physically reapplied and revalidated before readiness; payload
still waits for the end marker. Retraining disables outputs and initiates a new
DLL calibration and complete scan, retaining the prior physical deskew word
until the next safe source-clock commit.

The interface distinguishes `source_clk` before deskew from `raw_reference`
after deskew. `raw_phase0`/`raw_phase90` are actual DLL phases; `clock0`/`clock90`
are actual DCC outputs. Source presence and post-deskew DLL-reference presence
are separately observable. The physical backend still supplies both independent
configuration/deskew settling grants, the admitted delay ROM, measurement routes,
signed observer decisions and captured pairs. This wrapper generates no ideal
clock or delay. ROM, DLL, deskew and DCC admissions default false. Invalid DLL
code bounds, fewer than 64 confirmations, invalid vote/settle/trial dimensions
and deadlines exceeding the 100 ms management budget fail closed.

The composed bench `tb_rx_control_v2` uses actual calibration/configuration/
measurement/launch, scanner, transaction, startup and TX/RX framing RTL, with
clock-hold DCC topology and explicit test-only cell delays. Only external bank
propagation, signed paths, arbiter, settling and eye mask are synthetic. Unlike
the RX training-only bench, no external lock assignment can bypass calibration:
every lock checks all 64 actual period confirmations. The test post-deskew
reference also shifts with the physical code fixture, while the pre-deskew
source continues independently. DLL codes, commits, measurement launches and
period results must remain frozen throughout the scan and payload.

The complete-control targeted run passes ten scenarios, with a separate passing
reduced-confirmation rejection case (`build/rx-control-v2-targeted-tests.log`
and `build/rx-control-v2-parameter-rejection.log`). Nominal fixture lock occurs
at management age 111,190 (about 4.448 ms after the request), and RX readiness
at age 119,926 (about 4.797 ms). Retraining repeats actual DLL calibration and
the full scan. These durations describe the synthetic fixture, not native
acquisition guarantees. Timeout fixtures retain all 64 confirmations and place
the single overall deadline 200/1,000 management cycles after the measured
nominal DLL lock; they respectively withhold deskew settling or interrupt a
partially completed scan. They verify that no child deadline caused the failure.
The first test attempt placed its fixed deadline before DLL lock; that fixture
error and a too-short retrain test-runner timeout are retained in
`build/rx-control-v2-initial-tests.log`. No hardware confirmation, warmup or
100 ms limit was relaxed to make these tests pass.

The final complete suite passes 1,895 tests without skips, including all eleven
complete-controller scenarios (`build/rx-control-v2-full-tests.log`). Yosys
process/optimization/check reports zero problems for the production dimensions
with all admissions enabled and with defaults closed
(`build/rx-control-v2-final-admitted-synthesis.log` and
`build/rx-control-v2-final-default-synthesis.log`). These checks qualify control
composition only; admitted native delay ROMs, electrical backend timing, mapped
physical control timing and whole-PHY integration remain open.

### Live routed-bank negative voltage observation

A read-only bounded snapshot of routed pilot case 0 reaches 29.924282 ns of
the required 60 ns with 14,984 complete records and 11,306 saved variables.
`build/routed-live-prefix-observation-20261105T032426Z.json` binds the manifest
and exact consumed payload (SHA-256
`77d6123e8073f0d29c5c239be2ce3f8d21802f4310ccbf4cb81f7e360e6a11c0`).
A separate host-handle attestation is retained beside it; the prefix helper's
container PID namespace must not be used to interpret host-process liveness.
The solver remains running and neither its fixture nor outputs are modified.

The prefix is finite and monotonic, but already contains **40 MOS terminal-limit
violations**: 24 native NFET and 16 native high-threshold PFET devices whose
named terminals involve `turn0`. Re-reading the same hashed records produces
`build/routed-prefix-terminal-detail-20261105T032633Z.json`. The worst is
`XD:X2142` at 2.14456 ns, during the first input rise with all fine-control
inputs at zero: `turn0.Y.t3` is 1.964222686 V and its local body terminal is
-0.009396776 V, giving 1.973619462 V across terminals under the unchanged
1.95 V bound. Thus this observation concerns the return-mux region during a
clock transition, separately from the previously repaired fine-control charging
problem. Feedthrough/load and local ground movement need isolation; the prefix
alone does not establish the physical cause.

The first two complete input slots each contain one input/output edge of each
polarity. Code 0 rise/fall delays are 588.242695/609.203188 ps; code 1 gives
589.255901/615.623132 ps. The conservative maximum-edge zero-code headroom
against a 410 MHz quarter period is only about 0.553 ps. A repair that merely
adds load therefore needs a joint delay/headroom check. These are bounded-prefix
observations, not a complete timing/voltage pass, dense legal-code table, PVT
qualification or PHY admission. Keep the full pilot and independent verifier
running and retain the unchanged electrical gates before selecting a repair.

### Reproducible return-net diagnosis and native drive/shunt isolation

`diagnose_weighted_routed_prefix_v2.py` regenerates the whole-bank RC and native
MOS/control observations from the independently verified extraction, checks the
matched physical fine-control gate and actual translated solver deck, and binds
an explicit number of complete raw records. It excludes changing raw point-count
metadata and partial tail bytes from the consumed payload. Append-only growth
therefore cannot change the observation; any change to a consumed record,
semantic vector header, static source or native witness is rejected. It never
acquires a solver lease or changes the live producer's lock/state/output files.

`weighted_routed_prefix_diagnosis_v2/94a76e509964d699` reproduces the original
14,984-record observation, including all 2,495 native MOS devices and all six
terminal differences per device. An explicit recheck passes after the raw file
has grown (`build/weighted-routed-prefix-diagnosis-v2-recheck.log`). The 40
violations involve `turn0.Y`: 32 have that net as their highest-voltage gate
terminal (downstream merge loading), and eight involve return-mux drain/source
terminals. This distinction avoids assigning every affected device to the
return-mux itself merely from a shared extracted net name. The worst difference
remains 1.973619462 V during the first input rise at all-zero fine controls.
All complete-waveform, electrical, legal-code-table and PHY admission flags stay
false in this bounded diagnosis.

The original whole-bank RC includes `C304 turn0.Y IN 10.827f`; the separately
verified native guard-pair RC includes `C13 Y B 10.5944f`. Their comparable size
makes coupling within the macro a strong isolation target. It does not prove
that public-bus geometry, rather than another part of the extracted macro,
causes all of the transient. Extra drive also brings extra native coupling, so
the effect must be measured rather than inferred from a driver-strength label.

`probe_routed_return_drive_v2.py` prepares
`routed_return_drive_v2/9863a48a58472c31`. It retains every byte of the original
flat bank's R/C/native-device statements and adds one complete independently
verified wide-power NAND2B guard-pair RC at the existing `turn0` input/control/
output anchors. Magic pin aliases are checked against the actual model nodes.
All 2,495 original MOS witnesses remain identical; 36 native boost MOS witnesses
are added with separate private nodes and all four true terminals. Case 0 adds
only this pair; case 1 also adds an explicit source native 2x2 MIM at the return
output. No PDK transistor, existing parasitic, electrical limit or control source
is resized, removed or relaxed.

Both cases retain SS/40 C, fixed 1.8 V, 100 ps tanh input slew, original solver
settings and the 2 ps maximum step. The retained 60 ns stimulus is clipped to
an explicitly diagnostic 8 ns stop, covering the same complete first rising/
falling pulse before the first code change. External controls remain zero;
distributed control settling must satisfy the original 0.18 V bound. A candidate
must independently pass pulse integrity, every MOS terminal's 1.95 V limit and
positive conservative 410 MHz quarter-period headroom. Tests separately reject
overvoltage, delay/headroom failure, quiet internal-control error and an
incomplete trace that already contains the apparent pulse.

`verify_routed_return_drive_v2.py` waits for both complete numerical-error-free
8 ns cases, regenerates the actual pair/bank/decks/native witnesses, rereads each
raw trace and rechecks the exact original prefix. Comparisons use the original
bounded first-pulse window and report voltage, affected-device counts and delay
headroom independently. Any numerical abort or missing evidence cannot produce
a complete-waveform receipt. Even a passing first-pulse diagnostic cannot admit
a physical repair: new shared interconnections and the optional source-MIM
routing are ideal here. New geometry, DRC/LVS, fresh joint RC, full-code and
periodic-clock/PVT tests are still required.

The pilot and observer are active as
`openlvds-routed-return-drive-v2-pilot.service` and
`openlvds-routed-return-drive-v2-verify.service`, with at most two workers under
the unchanged six-engine priority/aging dispatcher. Healthy existing solvers
are retained. No new electrical result is available yet; the native bank/PHY
gates remain closed.

The full suite passes 1,902 tests without skips in
`build/routed-return-drive-v2-full-tests.log`. The prepared producer is now
immutable; later changes require a new version/context. The queued scientific
experiments have no numerical or electrical outcome yet.

A complementary physical isolation candidate should retain the native gate
masks, stack-guard MIM dimensions and body-contact row while separating the
public B/Y escape routes. In the current child builder, the signal M3 rows are
0.72/1.40/2.08 um and VPWR is at 3.6 um. A new child/context can test moving Y
above that rail, for example to 5.0 um, so the existing PG metal lies between
B and Y. This is a proposed geometry experiment, not a proven shield: native
mask identity, DRC/LVS, pin-access/obstruction checks and fresh extracted B-Y
coupling must decide whether it is legal and effective. Changed physical pin
coordinates must then propagate through a newly routed full bank; old frames,
routes or RC cannot qualify it. Do not edit the retained child/pair producers or
substitute a removed coupling capacitor for the required physical proof.

After that checkpoint, the original routed coarse-0 solver finishes its full
60 ns transient: the terminal raw header declares 30,052 records, exactly that
many whole real records are present with no partial tail, and the last time is
60 ns. The solver log reports 2,776.247 s elapsed and no timestep abort. Its
producer remains active calculating full electrical measurements; no case-0
summary or full independent receipt exists yet. Coarse 1 is live as host PID
1789676. This is numerical completion only, with the retained earlier terminal
violations still negative evidence. Both new return-drive cases remain queued.

The original full-waveform terminal loop scans many strided columns repeatedly
in a roughly 2.72 GB raw file. If postprocessing remains slow, a new read-only
streaming case diagnostic can reuse the bounded diagnosis's row-block/range
calculation (max minus min equals the maximum of the six absolute terminal
differences). It must preserve the existing producer and publish a separate
receipt; it cannot overwrite a live campaign's summaries or bypass the required
complete two-case gate.

### Completed drive/shunt diagnostics remain failed candidates

`routed_return_drive_v2/9863a48a58472c31` completes both declared 8 ns
transients without numerical errors. Independent receipt
`routed_return_drive_verification_v2/a9e90316064fea3a` regenerates the native
libraries/witnesses and remeasures all raw traces against the exact first-pulse
baseline. Both candidates pass pulse integrity and distributed-control settling,
but fail the unchanged 1.95 V terminal limit:

| First-pulse model | Peak terminal difference | Violating MOS | Quarter headroom |
| --- | ---: | ---: | ---: |
| Original routed bank | 1.973619 V | 40 | 0.553 ps |
| Extra native guard pair | 2.018768 V | 48 | 74.176 ps |
| Extra pair plus source 2x2 MIM | 2.010466 V | 48 | 64.002 ps |

More drive improves delay here but does not repair voltage stress. The small
extra shunt only partly reduces the larger peak. Neither candidate is selected;
all electrical/ROM/PHY admission flags stay false. Their complete negative
results are retained rather than replacing any original model or acceptance
limit.

### Physical separated-output guard cells and pair

`build_nand2b_separated_output_v3.py` implements the routing candidate as a new
immutable producer/context. The child Y escape moves from y=2.08 to 5.00 um,
above the existing VPWR rail at y=3.6 um; B remains at y=1.4 um. Both original
output-shunt variants retain their exact transistor source, stack-guard MIM,
output MIM and mirrored body-contact row. Geometry
`nand2b_separated_output_physical_v3/96544ed14eef87a9` passes zero DRC and
unique LVS in both variants. Independent source/mask proof
`nand2b_separated_output_proof_v3/579b90b91171bc01` proves every native child
mask and placement unchanged, identical source except the root model name, and
only M2/via2/M3 output routing changes. Only the Y public pin moves.

Fresh child extraction `nand2b_separated_output_rc_v3/9b32d22a45e49dcf`
and independent RC receipt
`nand2b_separated_output_rc_verification_v3/240eabc960a062d1` pass native
flat topology and elementwise passivity with exact positive-resistor reduction.
The o1 child's extracted B-Y coupling falls from 2.46091 to 0.32118 fF.

`build_nand2b_separated_pair_v3.py` joins two of the new o1 children with the
original placement and wide shared PG buses. Its Y bus/port is at y=10.00 um,
above shared VPWR at y=8.6 um, replacing the old Y coordinate of 7.08 um.
Geometry `nand2b_separated_pair_physical_v3/357ec85ae78da03e` passes zero DRC
and unique LVS. Independent proof
`nand2b_separated_pair_proof_v3/50d08b62ede20dfe` checks the exact two-child
placement, unchanged native masks and source, and only the permitted child/
pair routing layers. All other public pin locations remain unchanged.

Fresh pair RC `nand2b_separated_pair_rc_v3/7ae985e7b379500c` has 988 positive
resistors and 292 nonnegative parasitic capacitors; exact degree-at-most-four
star-mesh reduction retains 791 resistors. Independent receipt
`nand2b_separated_pair_rc_verification_v3/56a111f6ff565e9e` repeats strict flat
LVS, native source/GDS/interface identity and raw/reduced passivity checks. Its
bound consumer refuses changed physical/native-proof inputs.

`compare_nand2b_separated_coupling_v3.py` creates
`nand2b_separated_pair_coupling_v3/e3a4ac127b23f215` from the exact old and
new independently verified receipts. It groups actual R-connected nodes without
altering either circuit, checks native primitive counts and identical coupling
summaries before/after resistor reduction, and handles the native inline-comment
syntax. Both pairs contain exactly 18 NFET, 18 high-threshold PFET and four MIM
primitives. Extracted B-Y coupling drops **10.5944 -> 0.67189 fF (93.658%)**.
Explicit parasitic capacitance incident on the Y net drops **48.5484 ->
33.89315 fF**. These sums exclude intrinsic transistor/MIM-model capacitance;
they do not assert a measured delay or voltage improvement.

Negative-control GDS copies in `build/nand2b-separated-negative-controls-v3`
deliberately alter a native poly polygon or move a guarded child. The unchanged
proof functions reject each for the expected mask/placement violation. The
three new software tests check distributed-node coupling, native-source edits,
inline comments, pin shorts and nonpassive/unknown elements. The final complete
suite passes 1,905 tests without skips in
`build/nand2b-separated-pair-v3-final-full-tests.log`.

This is a real routed/mask-verified reduction in extracted coupling, not yet an
electrical repair certificate. The recovered complete bank results below expose
range/carry failures that prevent selecting the existing recursive bank even
if its overvoltage is repaired. Retain `weighted_direct_v4/c466d6eb048d9e82`
as a component-model baseline; an old/new pair transient comparison may isolate
voltage behavior, but cannot establish usable delay coverage. Any adapter must
explicitly bind the new pair's ordered ports/model name and regenerate every
native witness. Its ideal shared wiring cannot substitute for physical
integration. Changed Y coordinates require new frames/access views and a fresh
route/DRC/LVS/RC flow in whichever backend architecture is selected. Complete-
code, periodic-clock and all-PVT qualification remain required; no retained
model or admission gate is replaced by this component result.

### Routed reporter failure and complete-waveform recovery

The original routed coordinator terminates at 04:28 UTC with a reporting error:
`TypeError: Object of type bool is not JSON serializable`. A per-sample pulse
flag produced by NumPy remains a NumPy Boolean inside the result dictionary.
Both original simulations have nevertheless completed 60 ns: each native raw
header and solver log report 30,052 records, with exactly that many whole
records and no tail. Their elapsed solver times are 2,776.247/2,615.544 s.
The original coordinator is authoritatively failed/held-for-diagnosis; the pilot's
old `running` state is stale. Neither original source/state nor missing case
reports are rewritten, and no solver is restarted.

`weighted_routed_measurement_v3.py` performs the same six pulse windows, 1.5--9.5
ns stable-control windows, 0.18 V control bound, six-pair 1.95 V MOS screen and
conservative quarter-headroom calculation using row blocks. For finite four-
terminal voltages, max-minus-min equals the maximum of all six absolute pair
differences. This avoids repeatedly paging wide columns for every device. Flags
are constructed as built-in Booleans; ordinary JSON serialization is required,
without a permissive string/default encoder. Complete data must start at zero,
reach 60 ns, remain finite/monotonic and include every requested native vector.
Streaming SHA-256 uses bounded read buffers rather than allocating a multi-GB
raw file as one byte string.

`recover_weighted_routed_v3.py` first requires the exact retained terminal JSON
failure and both complete native log/raw pairs. It regenerates the full passive
bank RC, all 2,651 native primitives, all 2,495 MOS witnesses, 25 distributed
control groups, original decks/actual solver translation and unchanged matched
four-case physical fine-control prerequisite. It hashes every consumed input
before/after remeasurement and publishes a separate recovery receipt. It does
not take over the old campaign, change its lock/state/reports or reinterpret an
incomplete trace as completion.

`weighted_routed_recovery_v3/c5bfbbcf79e57211` recovers both cases. Numerical
completion, pulse integrity and routed-control settling pass. The full original
sparse screen still **fails**:

| Recovered property | Coarse 0 | Coarse 1 |
| --- | ---: | ---: |
| Maximum terminal difference | 1.973619 V (40 violations) | 1.919541 V (zero violations) |
| Code 15 -> 16 rising step | -6.587549 ps | -6.874088 ps |
| Code 15 -> 16 falling step | 0.031868 ps | 0.869227 ps |
| Zero-code rising repeat difference | 8.939630 ps | 0.007909 ps |

The conservative zero-code quarter headroom is 0.552909 ps. Code-zero repeats
remain within the existing 20 ps limit. Coarse-0 fine-31 reaches only
807.253092/750.342403 ps rising/falling, while coarse-1 fine-0 starts at
1,462.215455/1,318.021588 ps. Their overlap is therefore **-654.962363/
-567.679185 ps**. The first coarse increment is about 873.973/708.818 ps,
beyond what 32 ordered fine settings with at-most-20-ps steps can bridge.
Voltage shielding alone cannot repair this architecture's delay coverage.
Native data, acceptance limits and all ROM/PHY admissions remain unchanged.

The next backend architecture experiment must replace the large recursive
forward/return coarse increment. A forward chain of uniform native delay taps
with a balanced selection tree makes the selection depth independent of tap
index; characterize actual mux/tree base delay before choosing among the frozen
coarse-count candidates. Compare uniform/thermometer fine units against the
weighted switch bank so that code 15 -> 16 does not exchange several differently
loaded switches. Preserve the specified fine-count candidates, max legal-code
gap, all-PVT common ordering, voltage, quarter-range and full RX-span gates.
The separated-output native macro remains useful as a qualified geometry/RC
candidate, but is not selected as a complete solution to these range/carry
failures. All new circuit/physical producers require distinct immutable contexts.

The independent recheck of `weighted_routed_recovery_v3/c5bfbbcf79e57211`
passes after rereading every retained input and recomputing both full traces
(`build/weighted-routed-recovery-v3-recheck.log`). Recovery took 4:04 wall time
in the recorded invocation (`build/weighted-routed-recovery-v3.log`); this is
an observed processing duration, not a simulator speedup claim. Tests compare
its results exactly with the original six-pair/window calculation on complete
synthetic traces, including multiple control nodes, distinct device peaks,
late body overvoltage, quiet control faults and missing pulses. They reproduce
the old JSON failure and require the new plain-JSON schema to serialize without
custom defaults. Short, nonfinite or late-starting traces, mismatched solver
record counts, abort logs and unrelated/live failures are rejected. The final
complete suite passes 1,909 tests without skips in
`build/weighted-routed-recovery-v3-full-tests.log`.

### Uniform-tap balanced-tree native prototype (2026-11-05)

`scripts/dcdl_uniform_tree_v3.py` implements the replacement architecture:
uniform noninverting native buffer taps, a balanced radix-four selection tree
(a final radix-two level for odd binary widths), and equal thermometer-enabled
2x3 MIM fine units. Every tap sees one selection input and one identical next
buffer input, including an explicitly retained final dummy buffer. This
equalizes direct fanout, not extracted parasitics or effective transistor loads.
All paths have equal selection depth; no ideal delay or behavioral clock
element implements the bank. Supported coarse dimensions remain
16/32/64/128/256, and fine dimensions remain 16/32. These are topology candidates,
not admitted legal-code tables or a revised TX/RX dimension policy.

`probe_dcdl_uniform_tree_v3.py` prepares the immutable native context
`dcdl_uniform_tree_v3/486381e17636fb87`: complete 16 coarse taps, 31 identical
fine units, 120 instances and 875 native MOS devices. Buffer and fine-unit
models retain the independently verified component RC. Mux4 and control
buffers/inverters use actual SKY130 source transistor definitions with explicit
port orders. Common wiring remains ideal. The SS/40 C, fixed 1.8 V, 100 ps
input, 20 fF load pilot runs coarse 0/1 against fine 0/1/15/16/31. Each case
retains two isolated pulses over 20 ns with a 2 ps maximum step, every native
MOS terminal and real internal control signals. Voltage screening retains the
1.95 V six-terminal-pair limit; control deviations retain the 0.18 V limit.
The first zero-code case reports actual base-delay headroom against 410 MHz's
609.756 ps quarter-period requirement. Static repeat pulses do not establish
code-change settling or repeatability after returning from another fine code.

The pilot and separate `verify_dcdl_uniform_tree_v3.py --watch` service have
been launched. The independent verifier regenerates libraries, topology and
native device coverage, checks translated decks, complete raw/log counts and
input hashes, then remeasures all ten cases. Its comparison explicitly reports
the 15->16 carry, adjacent sampled gaps and coarse overlap while keeping dense
coverage unproven. Both producers retain failures and keep all PHY/electrical/
legal-code admissions false. Existing healthy solvers and the six-engine,
two-worker dispatcher policy remain unchanged. Logs are
`build/uniform-tree-v3-prepare.log`, `build/uniform-tree-v3-pilot.log` and
`build/uniform-tree-v3-verify.log`. Periodic qualification still uses the
approved 40%/60% endpoints at 390/400/410 MHz; isolated pulse screening does
not replace those checks.

### Native mux private-node access before tree routing (2026-11-05)

The initial label-only native inspection
`mux_tree_access_v3/9a5718f9054d70d3` fails exact-source private-port matching:
the reused clock-cell probe assumed n-diffusion at every source coordinate.
The native muxes also have private p-diffusion nodes. All original masks,
source, extraction, mismatches and the producer remain retained unchanged.

The separate `inspect_mux_tree_access_v4.py` selects the actual diffusion layer
containing each private coordinate. It rejects missing or ambiguous diffusion
and never treats overlapping upper metal as an electrical connection. The new
context `mux_tree_access_v4/25a5825516d981ea` passes unique exact-source LVS
with all 13 mux4_4 and six mux2_4 private nodes exposed and distinct. No native
masks, transistor sizes or placements changed. The existing LI search, which
requires a rectangle at least 0.17 um in both dimensions, finds candidates for
five mux4 and four mux2 private nodes. Complete private-node access remains
false; missing candidates do not prove that no possible custom contact/route
can be built.

`verify_mux_tree_access_v4.py` independently reimports the pinned native GDS,
requires byte-identical native Magic geometry, regenerates exact source and
labels, extracts again and repeats strict unique LVS. Receipt
`mux_tree_access_verification_v4/bd92d6d6bb512d60` confirms all native masks,
private-net separation and candidate observations. It keeps complete LI access,
electrical and PHY admissions false. This receipt supports subsequent native
tree layout work, not a timing or voltage repair. Inspect native transient
stress before deciding whether particular private nodes require shunts; nodes
without proven existing access would require new contact/layout proofs.

Logs: `build/mux-tree-access-v3.log`, `build/mux-tree-access-v4.log` and
`build/mux-tree-access-v4-verify.log`. Tests reject native-mask/property changes,
missing or duplicate label sections, absent/ambiguous diffusion and accidental
selection of unrelated overlapping metal. The preceding uniform-tree full
regression passes 1,917 tests (`build/uniform-tree-v3-full-tests.log`); three
subsequently added sparse-comparison tests also pass in the focused run.

The earlier bounded-PWL source diagnostic
`dcdl_pwl_source_v2/974118b4fe0abc11` is now terminal, with
`numerically_completed=false`. Its retained log reports timestep too small at
0.805081 ns (2.5e-24 s attempted step, reported node `ve29#branch`), before
the first 2.1 ns input midpoint. Recorded solver wall time is 5,421.915 s.
This does not establish the reported branch as the circuit root cause, native
equivalence or a speedup. It does show that the certified source-representation
change alone did not restore a complete transient through that legacy bank.
The separate uniform-tree campaign is still live and is not restarted or
modified on the basis of this older diagnostic.

The expanded regression passes 1,922 tests in 379.092 s with no skips
(`build/mux-tree-access-v3-full-tests.log`). The two layer-selection tests added
after that run started also pass independently. Fresh real-GDS reimport and
exact-source LVS succeed for both mux cells in the independent receipt above.

### Structural physical view of the complete uniform bank (2026-11-05)

`uniform_tree_netlist_v3.py` exports a distinct physical top
`openlvds_dcdl_uniform_tree_c16_f32_physical_v3`. It preserves the exact native
component graph from the bound pulse pilot, with mandatory VPWR/VGND top ports,
explicit native SC body ties, 18 guarded buffer macros (including the final
balancing load), 31 fine macros, five mux4 cells and 66 source control cells.
All 120 components and internal wires have preservation attributes. Instance
names have a `u_` prefix so source tags such as `input` and `output` remain valid
Verilog identifiers. Blackboxes declare interfaces only and contain no
behavioral delay, clock generation or admitted timing models.

`export_uniform_tree_netlist_v3.py` binds the native pilot's immutable manifest,
component libraries and bank source, validates each native SPICE pin by name,
then imports the generated Verilog with the pinned Yosys. Context
`uniform_tree_netlist_v3/11cd16824e8785a8` passes exact native graph checks for
all 120 components and 39 public ports. The checker rejects missing or merged
internal nets, altered primitive interfaces, wrong model/pin/direction/body
connections, unexpected hierarchy and removed preservation attributes.

`verify_uniform_tree_netlist_v3.py` regenerates the physical views and repeats
the Yosys import. Receipt
`uniform_tree_netlist_verification_v3/46218d038aded0a4` verifies an identical
graph and retains eight rejected copies of the actual imported JSON: dropped
tail load, wrong root select, shorted buffer ground, wrong fine attachment,
wrong native body tie, lost preservation attribute, merged select wires and
replacement of a native blackbox. Original native pilot files are untouched.

The default view and native interface declarations are checked in at
`sky130/v2/openlvds_dcdl_uniform_tree_c16_f32_physical_v3.v` and
`sky130/v2/uniform_tree_physical_blackboxes_v3.v`. All ten combinations of the
declared coarse/fine dimensions compile with Icarus; tests also reject native
SPICE component/wiring loss and missing power/body interfaces. Compilation and
graph identity establish structural correspondence, not component timing.

Existing guarded-buffer and fine-unit geometry can support a new physical
frame, but the fine macro's broad raw LEF access still needs explicit routing
and power-grid treatment. A fresh bank frame, powered-row exclusions, native
GDS/macro identity checks, DRC/LVS, joint RC and native electrical timing remain
required. The current electrical pilot must establish base-delay budget and
sampled coarse/fine coverage before selecting this candidate for a full routed
bank. Logs are `build/uniform-tree-netlist-v3.log`,
`build/uniform-tree-netlist-v3-verify.log` and
`build/uniform-tree-netlist-v3-full-tests.log`. No PHY, ROM or electrical
qualification gate is opened by this export.

The complete current suite passes 1,928 tests without skips in 372.869 s
(`build/uniform-tree-netlist-v3-full-tests.log`), including every mux-access
and structural-view test. The actual Yosys reimport and all eight retained
graph corruption controls pass in the independent receipt above.

### Complete uniform-bank zero-code failure and parasitic isolation (2026-11-05)

Case zero of `dcdl_uniform_tree_v3/486381e17636fb87` completes the full 20 ns
and both isolated pulses with no numerical error. Coarse/fine zero has repeated
rising/falling delays 1,656.670/2,500.423 ps, conservative fast-quarter headroom
-1,890.667 ps, and 24 MOS voltage violations with peak 2.310979 V. Both source
pulses and internal control settling pass. No quarter-delay or voltage gate
is relaxed to admit this bank. Other healthy cases continue unchanged.

Using the original schematics as the only comparator would also remove their
extracted MOS junction parameters. Instead,
`uniform_tree_parasitic_isolation_v4.py` deliberately idealizes the two verified
flat component models: collapse positive extracted wire resistors, remove
nonnegative explicit parasitic capacitors, and preserve every native primitive
instance, model and complete parameter list, including AD/AS/PD/PS and every
native MIM. Public ports cannot be merged; unknown active elements and native
resistor devices are rejected. The native switch/clock topology, data/control
stimulus, device census and voltage limits remain fixed. This diagnostic
removes physical parasitics and cannot provide physical timing equivalence or
be consumed as an admitted RC model.

`probe_uniform_parasitic_v4.py` prepares distinct immutable context
`dcdl_uniform_parasitic_v4/01316b2624a9d75c`, retaining the full native bank and
all 875 MOS devices. Each of 18 buffer instances removes 233 explicit wire
resistors and 88 parasitic capacitors; each of 31 fine instances removes 169
resistors and 55 parasitic capacitors. All 98 native MIM devices remain. The
ten matched SS/40 C, 100 ps, 20 fF, fixed-1.8 V, 20 ns cases use the unchanged
six-engine dispatcher with at most two campaign workers. The first preparation
attempt rejected the extractor's dollar-delimited floating-cap comments before
creating any artifact; its log is retained. The parser was corrected and tested
before the immutable successful context was created.

The idealized zero-code case also completes both pulses but fails: repeated
rising/falling delays 1,118.379/2,031.964 ps, headroom -1,422.208 ps, 28 MOS
violations and peak 2.342269 V. Control settling passes. Native source mux
devices remain unchanged in both fixtures. Removing the component routing R/C
therefore does not recover this architecture's quarter-period budget or voltage
margin.

`diagnose_uniform_zero_v4.py` regenerates the idealized library from its exact
native RC parent, checks both final case summaries, saved-vector completeness,
translated decks, raw/log record counts, both full native remeasurements and
consumed-file hashes before/after. It consumes only terminal case-zero files
while the two campaigns may be active on other cases; no parent state, lock or
raw file changes. Receipt `uniform_zero_diagnosis_v4/2961120aa3611ff5` passes,
including a second full read-only recheck. All admissions remain false.

Measured first falling-edge stage delays (ps):

| Stage | Component RC | Idealized component wiring |
| --- | ---: | ---: |
| Input to first tap | 306.769 | 217.808 |
| First tap to mux level zero | 691.161 | 675.748 |
| Mux level zero to selected fine node | 1,066.313 | 861.834 |
| Selected node to output | 436.154 | 276.574 |

The two native mux4 levels alone account for about 1.54 ns in the idealized
falling path; their hidden series-node devices also include the highest stress
observations. This identifies a data-path architecture problem beyond the
component wire parasitics; the exact transistor-level voltage mechanism still
needs targeted diagnosis. The structurally verified mux4 bank is retained as a
failed candidate and is not selected for a new routed bank.

The next native circuit experiment replaces the mux4 data path with a balanced
transmission-gate tree, static one-hot controls and a separately sized fine-bank
driver, retaining the equal fine capacitors and declared bank dimensions.
Measure base delay, all six MOS terminal differences, coarse coverage and fine
ordering before committing to physical tree routing. This is a new experiment,
not a demonstrated fix. No descriptor, voltage, quarter-range, dense-code,
all-PVT, periodic 40%/60% or PHY requirement changes.

Logs: `build/uniform-parasitic-v4-prepare.log` (failed pre-artifact attempt),
`build/uniform-parasitic-v4-prepare-recheck.log`,
`build/uniform-parasitic-v4-pilot.log`, `build/uniform-zero-diagnosis-v4.log`
and `build/uniform-zero-diagnosis-v4-recheck.log`.

Inspecting the worst RC-model sample identifies root mux PMOS
`XD:Xmux1_0:X18` (native `pfet_01v8_hvt`): at 19.691737 ns its D/G/S/B
voltages are -0.102021/1.793795/2.208958/1.800000 V. The 2.310979 V maximum
is drain-to-source stress across two oppositely displaced internal nodes.
Its source is native private node `a_373_413#`, which is MID8 in the verified
mux4 access map and has no existing LI candidate meeting the current size
filter. This is a measured sample and a physical-access limitation, not proof
of the complete capacitive-coupling mechanism. It explains why neither a stable
external supply nor an assumed label-only guard insertion resolves the observed
terminal stress. A new data path must be measured against the same limit.

The idealized producer's completed fine-one case also indicates that replacing
only the selector is insufficient: its repeated 0->1 delay step is 33.211 ps
rising and 40.349 ps falling, above the 20 ps adjacent-gap requirement. This is
a sparse diagnostic observation, not a physical or dense-code qualification.
The new fine-bank driver must address that load sensitivity as well as the
selector's base delay and terminal stress.

The full current suite passes 1,933 tests without skips in 411.770 s
(`build/uniform-parasitic-v4-full-tests.log`). New tests retain MOS junction
parameters/native MIMs and reject public-terminal shorts, negative R/C,
unexpected active/hierarchical/resistor devices and broken wire aliasing. The
matched two-waveform native checkpoint and its full recheck both pass their
evidence checks while retaining the electrical failures.

### Native TG selector and independent fine driver (2026-11-05)

`dcdl_tg_tree_v5.py` implements the replacement data path: a guarded native
inverter at the input, uniform native paired-buffer taps, balanced radix-four
TG selection (a final radix-two stage for odd binary widths), and a separate
guarded native inverter driving 31 equal fine units. The two data inversions
preserve clock polarity. Real native buffers, inverters and AND gates decode
the binary word into complementary one-hot enables. Under each static legal
word, every TG group selects exactly one input, including groups unselected by
the following level. This static property does not qualify transitions between
codes or remove the native update/settling gate.

Four profiles compare 0.42/0.84 um and 0.84/1.68 um NFET/PFET TG widths, each
with a paired-buffer output restorer or with the fine-driver output connected
directly to the declared 20 fF load. All profiles retain every coarse choice,
all 31 fine units and the final tap's balancing buffer. Fine capacitors load
the driver output, not the selector node. TG MOS devices have explicit nonzero
AD/AS/PD/PS estimates using a 0.29 um diffusion extension; these are prelayout
estimates requiring new PCell/layout/extraction proof, not established geometry.

`probe_dcdl_tg_tree_v5.py` binds the failed complete-waveform mux4 checkpoint,
regenerates verified component RC families, and preserves all native MOS/MIM
parameters while deliberately idealizing the paired-buffer, inverter and fine
component routing R/C. Native SC source controls remain separate from those
component models. The experiment contains no behavioral clock/delay element in
the bank. Context `dcdl_tg_tree_v5/88d4f72c48c8e1b5` runs 24 SS/40 C cases:
four profiles against (coarse,fine) = (0,0), (0,1), (0,15), (0,16), (0,31),
(1,0), each with both full isolated pulses over 20 ns. Restored profiles have
923 native MOS devices; direct-output profiles have 903. Every MOS terminal is
saved and checked at 1.95 V, including devices outside the selected data path.
All decoded true/complement controls are measured at the unchanged 0.18 V limit.

`verify_dcdl_tg_tree_v5.py` independently regenerates the four banks and native
device coverage, verifies translated decks, successful native log/raw counts,
all waveform measurements and consumed hashes before/after. `--available`
binds only already terminal cases while other cases continue; the full
`--watch` service waits for all 24. Each profile requires every sparse point
before a sparse screen can pass, and dense legal-code coverage and all PHY/
electrical admissions remain false. Receipt
`dcdl_tg_tree_verification_v5/2d21722f18cb5037` verifies complete cases 0--7
(zero/fine-one for all profiles). The earlier two-case receipt
`dcdl_tg_tree_verification_v5/d16f6b2a29053e9d` is retained.

Repeated zero-code delay and first fine-step observations (ps):

| Profile | Rise | Fall | Fast-quarter headroom | Fine 0->1 rise/fall |
| --- | ---: | ---: | ---: | ---: |
| Unit TG, restored | 754.165 | 891.965 | -282.209 | 18.018 / 16.498 |
| Double TG, restored | 579.621 | 718.924 | -109.168 | 15.251 / 13.181 |
| Unit TG, direct | 596.011 | 680.509 | -70.754 | 13.175 / 7.601 |
| Double TG, direct | 428.019 | 520.509 | 89.247 | 10.191 / 5.249 |

The wider-TG direct-output candidate passes the source experiment's zero-code
quarter budget and measured first fine-step maximum-gap check. It is not yet
qualified for the 15->16 carry, coarse overlap, dense codes, code updates,
component/joint physical RC, periodic duties, all PVT or the PHY. Every
available profile still fails voltage at the unused balancing-buffer output.
For the wider-TG direct zero case, all eight violations belong to `Xtail_load`;
worst PMOS `X0` at 17.878310 ns has D/G/S/B =
-0.155849/0.637870/1.800000/1.800000 V. Its public `unused_tail` drain is
unloaded. The proposed next fix is a real native MIM termination on that output
in a new immutable revision, preserving the balancing input load and every MOS.
Removing the buffer or waiving its stress is not a valid repair.

Topology tests evaluate every coarse word through 256 taps, one-hot exclusivity
and complementary controls, equal TG depth, output polarity/driver separation,
nonzero junction parameters and retained tail/fine loads. Waveform tests reject
a bad decoded enable even with a correct external binary word and fine
controls. The complete suite passes 1,939 tests without skips in 409.544 s
(`build/dcdl-tg-tree-v5-full-tests.log`). Native records and independent proofs
remain separate from those software checks.

The pilot and full independent verifier run under the existing six-engine,
two-worker policy; no healthy older solver was stopped or restarted. Logs are
`build/dcdl-tg-tree-v5-prepare.log`, `build/dcdl-tg-tree-v5-pilot.log`,
`build/dcdl-tg-tree-v5-available-verify.log`,
`build/dcdl-tg-tree-v5-available-recheck.log` and
`build/dcdl-tg-tree-v5-verify.log`. Reference qualification still requires
390/400/410 MHz at the approved 40%/60% endpoints, with fixed supplies and all
15 process/temperature combinations.

### Real MIM termination closes the sparse native TG screen (2026-11-05)

`dcdl_tg_terminated_v6.py` retains the exact `double_direct` data/control graph
and all 903 native MOS devices, adding one native 2x2 MIM from public
`unused_tail` to VGND. Only the top model name and that passive instance change.
The balancing buffer and its load on the final tap are retained. The source
transform and all ten declared coarse/fine dimension combinations are tested
for exact unchanged active connectivity. This is a distinct immutable revision;
the original 24-case TG campaign and its evidence remain untouched.

`probe_dcdl_tg_terminated_v6.py` requires the independently verified,
timing/control-passing zero-code baseline with all voltage violations confined
to the balancing buffer. It regenerates the bank and requires every mapped MOS
name, model, limit and terminal connection to match the baseline exactly. It
runs all six matched SS/40 C points, two full pulses per point over 20 ns,
100 ps input, 20 fF load and fixed 1.8 V. Context
`dcdl_tg_terminated_v6/36524d260790b5b9` completes with six numerical-error-free
cases and no native voltage or control failures.

The tail undershoot improves from -0.155849 V to -0.120544 V at zero code;
the highest observed native MOS terminal difference across all six cases is
1.931542 V, below the unchanged 1.95 V limit. Zero-code propagation remains
428.019/520.509 ps rising/falling, with conservative 410 MHz quarter headroom
89.247 ps. This matched result supports the passive termination as a repair to
the measured unloaded-output fault in this source experiment.

Repeated pulse delays (ps):

| Coarse | Fine | Rise | Fall |
| ---: | ---: | ---: | ---: |
| 0 | 0 | 428.019 | 520.509 |
| 0 | 1 | 438.210 | 525.758 |
| 0 | 15 | 604.206 | 599.634 |
| 0 | 16 | 617.185 | 604.912 |
| 0 | 31 | 821.141 | 684.075 |
| 1 | 0 | 594.557 | 634.977 |

The sampled 0->1 and 15->16 adjacent steps are respectively
10.191/5.249 ps and 12.978/5.278 ps rising/falling, both positive and below
20 ps. Coarse-zero fine31 overlaps coarse-one fine0 by
226.585/49.099 ps. All static true/complement controls and repeated-pulse
checks pass. Unsampled adjacent steps and the other coarse codes are not
proven by these sparse points.

`verify_dcdl_tg_terminated_v6.py` independently regenerates the single-MIM
change, verifies every consumed native deck/raw/log hash and successful record
count, and remeasures all six complete traces. Receipt
`dcdl_tg_terminated_verification_v6/f9ec6c58d7b7315d` verifies all six and
reports `sparse_native_screen_passed=true`; dense-code, electrical and PHY
admissions stay false. The earlier four-case partial receipt
`dcdl_tg_terminated_verification_v6/7ced68e3c919d16f` remains retained.
A second complete read-only recheck reproduces the same full receipt.
Both pilot and full verifier finish normally; no prior solver was stopped.

The complete current suite passes 1,943 tests without skips in 409.151 s
(`build/dcdl-tg-terminated-v6-full-tests.log`). Tests include exact active
graph preservation, real MIM connection/geometry, explicit tail-range reporting
and rejection of an over-limit unused-tail MOS. Logs are
`build/dcdl-tg-terminated-v6-prepare.log`,
`build/dcdl-tg-terminated-v6-pilot.log`,
`build/dcdl-tg-terminated-v6-available-verify.log`,
`build/dcdl-tg-terminated-v6-verify.log` and
`build/dcdl-tg-terminated-v6-recheck.log`.

This is the first clean sparse native checkpoint for this TG topology, not a
usable-PHY release. Its component wiring is still idealized and new TG junction
geometry is estimated. The next electrical experiment must restore the actual
verified buffer/inverter/fine RC, preserving the termination and native devices,
to measure physical component loading before committing to bank routing. New TG
PCell/GDS and passive-RC proofs, a real tail-cap route, fresh whole-bank
extraction, dense/common legal codes, safe code updates, all 15 PVT points,
390/400/410 MHz at 40%/60%, actual DCC/DLL integration and full-link qualification
remain required. Neither the source headroom nor these six points establish
those gates.

### Restored component RC: safe voltage, insufficient timing (2026-11-05)

`tg_component_rc_families_v7.py` restores the exact verified flat paired-buffer,
guarded-inverter and fine-unit RC models around the terminated TG bank. Each
restored model must reduce to the exact parameter-preserving source model used
by v6; no native instance, model, junction/MIM parameter or unrelated TG/control
definition changes. All extracted R/C elements are retained byte-for-byte at
the component level. The complete bank restores 8,801 resistors and 3,737
explicit parasitic capacitors: 16 buffer pairs at 200 R/116 C, two inverters at
181 R/88 C and 31 fine units at 169 R/55 C.

`probe_dcdl_tg_component_rc_v7.py` binds the complete passing v6 sparse receipt
and all original CAD/RC witnesses. It keeps the bank source, 903 MOS devices,
2x2 tail termination and six SS/40 C conditions fixed. Actual R-separated
switch/clamp gates are mapped through the fine-unit wire connectivity: all
93 gates are checked against their true/complement word targets, not just the
public buffer outputs. Context
`dcdl_tg_component_rc_v7/e84805cb2ff2a439` completes all six 20 ns simulations.
These are verified component parasitics, not whole-bank RC: new TG junctions
remain estimated, and TG/control/common/tail-cap routes are unextracted.

The first producer inherited v6's request for the passive public node
`XD:unused_tail`, but its fixture saved only actual MOS terminals. Once real
buffer output resistance separates that public node from the transistor
drains, the public node is not automatically saved. The six numerical runs
therefore end in the known reporting error `Missing requested native vectors`.
The frozen producer, decks, raw traces, original error summaries and state are
retained unchanged. Its `errors=6` denotes that reporting fault, not six
ngspice convergence failures.

`measure_tg_component_rc_v8.py` retains every active-terminal pulse/voltage and
control check and explicitly reports the unavailable public-tail range as
null; it does not infer that voltage from nearby nodes. Every balancing-buffer
MOS remains in the 1.95 V screen. The same helper adds the explicit public probe
to future fixtures without changing a bound deck or rerunning this campaign.
Tests reproduce the separation between a real transistor drain and its passive
public output and require missing active terminals to remain fatal.

`recover_tg_component_rc_v8.py` requires the exact retained reporting failure,
regenerates all restored libraries/witnesses, checks successful native logs,
translated decks and complete raw record counts, reproduces the old failure,
then rereads all active terminal/control measurements. Consumed hashes are
checked before/after. Complete receipt
`dcdl_tg_component_rc_recovery_v8/c051828d34e445bb` verifies all six traces;
the earlier three-case receipt
`dcdl_tg_component_rc_recovery_v8/ef6edae6f791e0bd` remains retained. No SPICE
job or source artifact is changed by recovery. All admissions remain false.

Repeated complete-waveform delays (ps):

| Coarse | Fine | Rise | Fall |
| ---: | ---: | ---: | ---: |
| 0 | 0 | 681.361 | 755.655 |
| 0 | 1 | 699.661 | 763.005 |
| 0 | 15 | 1,007.004 | 872.481 |
| 0 | 16 | 1,031.167 | 880.117 |
| 0 | 31 | 1,409.160 | 958.918 |
| 1 | 0 | 890.956 | 909.959 |

All six pass native voltage (global peak 1.891679 V), public and distributed
control settling, one-hot controls, repeated pulses and coarse overlap
(518.204/48.959 ps rising/falling). Zero-code fast-quarter headroom is
-145.899 ps. Fine 0->1 is 18.299/7.349 ps, but fine 15->16 is
24.162/7.636 ps, failing the rising 20 ps maximum. The component-RC sparse
screen therefore fails even though voltage, control and range overlap pass.

First zero-code stage delays (ps), matching each inverter's opposite edge:

| Stage | Source rise/fall | Component RC rise/fall |
| --- | ---: | ---: |
| Input inverter | 58.682 / 113.444 | 76.975 / 152.278 |
| Both TG levels | 151.201 / 230.503 | 189.059 / 284.375 |
| Fine driver to output | 218.136 / 176.563 | 415.328 / 319.002 |

The loaded fine driver accounts for most added delay, while the input and
selector also contribute. The next circuit experiment must improve driver and
selector strength while preserving enough falling fine range for the measured
coarse step. Evaluate faster/stronger native CMOS data drivers with explicit
new-device/layout scope; do not reuse the old source headroom, waive the
quarter/gap limits, or remove verified parasitics to declare a fix. Full dense,
PVT, periodic-clock and PHY gates remain open.

The original restoration tests pass in the 1,949-test suite
(`build/dcdl-tg-component-rc-v7-full-tests.log`, 407.887 s). The full current
suite, including the passive-probe recovery and corrected future-fixture tests,
passes 1,953 tests without skips in 420.905 s
(`build/dcdl-tg-component-rc-v8-reader-full-tests.log`). Native electrical timing
failures remain separate from those software checks.

Logs: `build/dcdl-tg-component-rc-v7-prepare.log`,
`build/dcdl-tg-component-rc-v7-pilot.log`,
`build/dcdl-tg-component-rc-v8-available.log`,
`build/dcdl-tg-component-rc-v8-recovery.log` and
`build/dcdl-tg-component-rc-v8-recheck.log`.

### Native driver and selector isolation (2026-11-05)

`tg_driver_experiment_v9.py` and `probe_tg_driver_experiment_v9.py` implement
the next experiment from the measured loaded-driver/selector bottleneck. The
terminated 16-tap/32-fine graph, controls, native fine units, tail MIM and buffer
component RC remain intact. Three variants separate the changes:

| Profile | Input/fine-driver PMOS | Selector N/P width (um) |
| --- | --- | ---: |
| `hvt_quad` | Original HVT | 1.68 / 3.36 |
| `regular_double` | Regular threshold, same geometry | 0.84 / 1.68 |
| `regular_quad` | Regular threshold, same geometry | 1.68 / 3.36 |

Each regular variant changes only the model of the sixteen PMOS fingers across
the input and fine drivers. Their W/L, junction parameters, native guard MIM,
terminal connections and original inverter wiring RC remain unchanged. This
is explicitly a borrowed-RC flavor isolation: changing threshold implant
invalidates the old inverter layout/RC equivalence. A promising variant needs
its own real geometry, DRC/LVS and fresh extraction before physical admission.
Wider TG junctions remain explicit nonzero prelayout estimates scaled with
width, and TG/control/common/tail-cap routing remains unextracted.

Prepared context `tg_driver_experiment_v9/bf8c0a4abc4024a1` binds all source
and inherited native evidence before launch. Its eighteen cases are the same
six sparse codes for each profile at SS/40 C, fixed 1.8 V, 100 ps input slew,
20 fF load and two pulses in 20 ns. All 903 MOS terminals, 93 distributed fine
gates, public and one-hot controls, 1.95 V stress, 20 ps adjacent-gap/repeat
limits, positive overlap and absolute fast-quarter headroom remain required.
Future fixtures explicitly probe `XD:unused_tail`; a missing probe is fatal in
this new producer. The dispatcher and two-worker campaign limit are unchanged.

`verify_tg_driver_experiment_v9.py` regenerates all variants, attests translated
decks and successful native record counts, and independently remeasures complete
waveforms. It keeps all existing sparse comparison limits and cannot admit
dense legal codes, borrowed inverter RC, whole-bank RC or the PHY even if sparse
timing passes. The native pilot and full-result watcher remain running.
Available-case receipt
`tg_driver_experiment_verification_v9/402c6ded5d4a727d` independently verifies
the first two complete zero-code cases:

| Profile | Repeated rise / fall delay (ps) | Fast-quarter headroom (ps) | Peak MOS difference (V) |
| --- | ---: | ---: | ---: |
| `hvt_quad` | 583.775 / 663.145 | -53.389 | 1.883687 |
| `regular_double` | 594.743 / 709.394 | -99.638 | 1.887269 |

Both pass all native voltage and static-control checks, including distributed
fine gates and the now-explicit public tail observation. Neither passes the
absolute quarter-period budget. Against the original component-RC zero code,
wider TGs recover 97.587/92.510 ps rising/falling and regular PMOS alone recover
86.618/46.261 ps. The combined variant and all new fine-span/coarse-overlap
measurements remain pending. These partial results prove neither sparse-profile
success nor a new legal-code table.

Logs: `build/tg-driver-v9-prepare.log`,
`build/tg-driver-v9-pilot.log` and `build/tg-driver-v9-verification.log`.

Primitive preparation is also available in
`tg_device_pcells_v10/505929ce7b0bf358`. The separate
`inspect_tg_device_pcells_v10.py` generates the six candidate native MOS PCells,
writes GDS, and extracts each transistor from a fresh Magic GDS import. Each
extract contains exactly the requested native model, matching W/L and positive
AD/AS/PD/PS. All original primitive geometry and logs are retained.

| Model | W/L (um) | AD = AS (um2) | PD = PS (um) |
| --- | ---: | ---: | ---: |
| N regular | 0.84 / 0.15 | 0.2436 | 2.26 |
| N regular | 1.68 / 0.15 | 0.4872 | 3.94 |
| P regular | 1.00 / 0.15 | 0.2900 | 2.58 |
| P regular | 1.68 / 0.15 | 0.4872 | 3.94 |
| P regular | 3.36 / 0.15 | 0.9744 | 7.30 |
| P HVT | 1.00 / 0.15 | 0.2900 | 2.58 |

The four TG candidate junction estimates match these standalone PCells. That
does not establish their eventual routed TG parasitics or allow substitution
of standalone P-cell junctions for the shared diffusions in the inverter.
PCell interfaces include distinct D/G/S/B contacts for subsequent placement.
Neither a routed TG/inverter nor macro DRC/LVS, passive RC or native circuit
qualification is claimed. Log: `build/tg-device-pcells-v10.log`.

Validation: four focused circuit/fixture tests and two focused verifier tests
pass. The first full regression passes 1,957 tests in 373.020 s
(`build/tg-driver-v9-full-tests.log`). After adding the verifier tests, the
complete current suite passes all 1,959 tests without skips in 385.958 s
(`build/tg-driver-v9-verifier-full-tests.log`). The six-cell native PCell/GDS
inspection also completes successfully, with distinct D/G/S/B in every fresh
extract and all recorded file hashes rechecked. Software and primitive checks
do not turn either measured quarter-period failure into an electrical pass.

### Combined driver result and physical inverter witness (2026-11-05)

Available-case receipt
`tg_driver_experiment_verification_v9/0878bd2bb6e6f70e` independently verifies
the first six cases: zero and fine-one for all three variants. The combined
regular-PMOS/quad-TG zero code is 506.645/608.136 ps rising/falling and passes
the absolute fast-quarter check with only 1.620 ps headroom. Its first fine step
is 12.361/6.131 ps, below the unchanged 20 ps limit. All six pass native voltage,
public/distributed fine controls, one-hot decoding and repeatability. These
are not complete sparse-profile, dense-code or routed-clock passes.

The separate experiment in `tg_headroom_experiment_v12.py` doubles selector
width again to N3.36/P6.72 while retaining the same regular-PMOS driver model,
903 MOS devices, 93 actual fine-gate observations, six sparse codes and voltage/
timing requirements. Prepared context
`tg_headroom_experiment_v12/6d996229830f90f6` has one worker and shares the
unchanged six-engine dispatcher. Its complete zero-code receipt
`tg_headroom_experiment_verification_v12/15abc73b62202730` observes
501.308/608.113 ps and 1.643 ps fast-quarter headroom, with voltage/control
checks passing. The remaining fine/range cases in both campaigns continue.

Matched second-pulse stage measurements from the complete native zero-code
traces (ps):

| Stage | Regular quad rise / fall | Regular oct rise / fall |
| --- | ---: | ---: |
| Input inverter | 81.644 / 134.380 | 92.885 / 166.189 |
| Both TG levels | 142.046 / 200.461 | 129.535 / 171.050 |
| Fine driver | 282.955 / 273.295 | 278.889 / 270.874 |
| Total | 506.645 / 608.136 | 501.308 / 608.113 |

Both saved pulses must have exactly one crossing of each node in the expected
inversion direction. The increased input-inverter loading offsets almost all
falling TG-path improvement. Widening again gains only 0.023 ps of falling
headroom and therefore does not resolve the margin needed for common routing.
Log: `build/tg-headroom-v12-stage-comparison.log`.

The next candidate is reducing the native 4x4 output shunt MIM to 3x3 in the
fine driver alone, then in both data inverters, retaining their MOS geometry
and all thirty-one fine units. This seeks lower fixed delay without reducing
fine range by strengthening the N driver. It is a hypothesis: capacitance
reduction can worsen terminal overshoot and alter fine gaps, so every native
terminal, repeated delay, carry and coarse-overlap check must still pass. A
candidate then needs its own real MIM placement/routes and fresh RC. Do not
remove a guard capacitor or select a smaller one merely to report a timing
pass. Current source/model-specific receipts remain immutable.

The regular-PMOS inverter itself now has a separate physical implementation.
`build_regular_clock_inverter_v14.py` changes only HVTP mask (78/44) in the
original guarded INV8 GDS, preserving the native hierarchy and public pin
scope. All other mask regions are compared exactly. Its distinct core/top
names avoid presenting the changed cell as an unchanged standard cell. Source
regeneration changes exactly eight PMOS models to `pfet_01v8`, while all native
finger dimensions, AD/AS/PD/PS, terminal connections, body taps and the 4x4 MIM
remain. MOS D/S reordering is accepted only together with its corresponding
junction parameters; missing fingers or changed gates/bodies/junctions cannot
match the signature.

Physical context `regular_clock_inverter_v14/7212db74b50b71f1` removes
4.692 um2 of HVTP and passes DRC=0, strict native LVS, native-junction comparison,
fresh flat distributed extraction and a new wire-collapsed strict RC topology
LVS. Raw RC is 256 positive resistors/88 nonnegative capacitors; exact reduction
retains 181 resistors/88 capacitors. No negative element is clipped or removed
to admit the circuit. Native extraction still contains sixteen MOS and one
intentional MIM.

Two earlier attempts are preserved. The v11 flattened GDS
(`regular_clock_inverter_v11/2f39d4f38336a553`) promotes VNB/VPB labels to top
ports and changes boundary annotations on Magic export; mask/pin checks reject
it despite DRC=0. The v13 revision
(`regular_clock_inverter_v13/2805ae9572a765b4`) preserves hierarchy but saves
only the root MAG, so a subsequent process cannot reload the custom children
and writes an empty GDS. The v14 revision saves every imported child. Neither
failed artifact or producer is edited or reused as passing evidence.

Independent `verify_regular_clock_inverter_v15.py` reimports the actual v14
GDS in fresh Magic processes, repeats DRC/LVS and native-junction/mask checks,
verifies raw/reduced passivity and regenerates the exact reduced netlist
byte-for-byte. Receipt
`regular_clock_inverter_verification_v15/5d86129b463ae172` also rejects both
an added M3 shape and a retained HVT marker as negative controls.

`verify_regular_inverter_network_v16.py` binds that physical proof to the
immutable regular-quad diagnostic context. Receipt
`regular_inverter_network_verification_v16/34538f13d3761d76` proves an exact
286-element bijection (17 native primitives, 181 R, 88 C): terminal tokens,
native model/parameter tokens, and R/C values are identical. Only element
identifiers, ordering and root model name differ; no numerical tolerance or
approximate reduction is used. Changed resistance and missing-MOS controls
are rejected. The unchanged diagnostic producer still records its original
borrowed-RC scope; the new separate witness resolves that question for this
isolated component. It does not establish new TG/common wiring, whole-bank RC,
native waveform epochs, dense legal codes, periodic-duty/PVT or PHY admission.

All 1,964 regression tests pass without skips in 409.614 s
(`build/regular-inverter-headroom-full-tests.log`). Focused source/junction
tests (three) and wider-selector tests (two) pass. Physical/RC/network proofs
and their negative controls complete successfully. Additional logs:
`build/regular-clock-inverter-v11.log`, `build/regular-clock-inverter-v13.log`,
`build/regular-clock-inverter-v14.log`,
`build/regular-clock-inverter-v15-verification.log`,
`build/regular-inverter-network-v16.log`,
`build/tg-driver-v9-first-fine-verification.log`,
`build/tg-headroom-v12-prepare.log`, `build/tg-headroom-v12-pilot.log` and
`build/tg-headroom-v12-zero-verification.log`.

### Complete sparse driver result and real smaller guard (2026-11-05)

`tg_driver_experiment_v9/bf8c0a4abc4024a1` completes all eighteen numerical
cases without errors. Full independent receipt
`tg_driver_experiment_verification_v9/3098a005c74751d4` verifies every declared
case. Only `regular_quad` passes its full sparse screen. Its complete delays
are (ps):

| Coarse | Fine | Rise | Fall |
| ---: | ---: | ---: | ---: |
| 0 | 0 | 506.645 | 608.136 |
| 0 | 1 | 519.006 | 614.267 |
| 0 | 15 | 740.325 | 712.456 |
| 0 | 16 | 758.237 | 720.031 |
| 0 | 31 | 1040.558 | 824.071 |
| 1 | 0 | 722.119 | 775.406 |

Peak native MOS difference is 1.883721 V. Fine 15->16 is 17.912/7.575 ps and
coarse overlap is 318.439/48.665 ps rising/falling. All static controls and
repeated pulses pass. HVT-quad still fails the quarter check and its rising
carry (24.120 ps); regular-double fails quarter delay. The passing variant's
1.620 ps headroom remains insufficient evidence that unextracted TG/common
routes will fit. Sparse success does not prove dense codes or full PVT.

The guard reduction now uses an actual physical component. In
`build_small_guard_inverter_v17.py`, a retained native 3x3 MIM replaces the
4x4 child of the independently verified regular inverter. Its C1 contact keeps
the same position; C2 moves 0.5 um toward the signal plate. The M3 ground
landing is extended over x=9.18..10.08 um, y=7.8..8.2 um to maintain a real
connection. No active device, body mask or child placement moves. Root masks
must equal their previous regions, with only the specified M3 rectangle added;
all non-capacitor child mask regions remain identical.

Context `small_guard_inverter_v17/535d866a9ab25197` passes DRC=0, strict native
LVS, all sixteen MOS/junction comparisons, fresh passive RC and a separate
strict RC topology LVS. Its native MIM is exactly 3x3. Extraction contains
254 positive resistors and 89 nonnegative parasitic capacitors; exact reduction
retains 181 resistors/89 capacitors. This is a new geometry and new RC model,
not a changed MIM parameter inside the previous network.

Independent `verify_small_guard_inverter_v18.py` reimports the actual GDS in
fresh Magic processes, repeats physical/native checks, verifies raw/reduced
passivity, and regenerates the reduced netlist byte-for-byte. Receipt
`small_guard_inverter_verification_v18/da386f298106c21e` also rejects an extra
root M1 shape and a changed MOS-child mask. Its pinned CAD Python is recorded
separately from the scientific environment used by native simulations.

`small_guard_bank_v19.py` replaces only the two old driver model references
and their definitions, retaining all other components and bank connections:

| Profile | Input driver guard | Fine driver guard |
| --- | ---: | ---: |
| `fine3` | Actual 4x4 RC | Actual 3x3 RC |
| `both3` | Actual 3x3 RC | Actual 3x3 RC |

`small_guard_component_families_v19.py` rechecks both physical evidence chains
using the recorded CAD interpreter, while keeping NumPy/SciPy in their pinned
scientific environment. It requires the exact regular-inverter network witness
to name the same physical parent as the smaller guard. Extracted interfaces
must match the original A/Y/VGND/VPWR order. Prepared context
`small_guard_bank_v19/4403ce2a6170108c` includes twelve SS/40 C cases (six codes
per profile), one worker, all 903 native MOS, all 93 actual fine gates and the
explicit passive tail probe. All voltage, pulse, 20 ps gap/repeat, positive
overlap and absolute-quarter requirements remain unchanged. TG/common/control/
tail-cap routing is still unextracted.

Independent first-case receipt
`small_guard_bank_verification_v19/ec1f4863fd997a14` measures `fine3` zero code
at 490.342/596.306 ps rising/falling, 13.450 ps fast-quarter headroom and peak
MOS difference 1.883716 V. Public/distributed/one-hot controls and repeated
pulses pass. Reducing the fine guard improves falling delay by 11.830 ps; it
does not alone establish a routed-clock margin or fine/coarse coverage. The
subsequent two-case receipt
`small_guard_bank_verification_v19/cb1369375a76367b` independently verifies
both zero codes:

| Profile | Rise / fall delay (ps) | Fast-quarter headroom (ps) | Peak MOS difference (V) |
| --- | ---: | ---: | ---: |
| `fine3` | 490.342 / 596.306 | 13.450 | 1.883716 |
| `both3` | 475.380 / 568.223 | 41.533 | 1.883659 |

Both pass voltage, all static controls and repeatability. The 39.913 ps falling
improvement over the original regular-quad zero code is measured with actual
smaller-guard component RC. The campaign subsequently completes all twelve
cases without numerical/reporting errors. Full independent receipt
`small_guard_bank_verification_v19/165edf7ab05fd312` verifies all declared
cases and passes the six sparse codes in each profile. Fine 15->16 is
17.871/7.609 ps for `fine3` and 17.872/7.569 ps for `both3`; coarse overlap is
315.614/50.331 ps and 318.062/49.116 ps respectively. Voltage, controls and
repeated pulses pass. This supports preserved sparse range after guard
reduction in the model without TG wiring; it does not override the later
actual-TG-RC timing failures below. The pilot and full verifier terminate
successfully, and all original evidence is retained.

The wider-TG campaign also completes all six cases without errors. Independent
receipt `tg_headroom_experiment_verification_v12/8aa510ce77538201` passes its
entire sparse screen, with fine 15->16 of 17.904/7.702 ps and coarse overlap
309.692/33.507 ps rising/falling. Its zero-code headroom remains 1.643 ps.
The original quad-TG version has greater falling overlap (48.665 ps) and nearly
the same zero-code falling delay, so the smaller-guard/physical-TG work retains
quad sizing. Both completed native pilot/verifier pairs terminate with status
zero; no healthy job is restarted or stopped to obtain these results.

### Native compact TG component (2026-11-05)

`build_tg_quad_cell_v21.py` uses the exact inspected N1.68/P3.36 native PCells,
with separate body contacts, complementary controls and six public ports
A/Z/EN/ENB/VPWR/VGND. N and P centers are 4 um apart. Narrow M1 escapes precede
the larger M1/M2 via pads; M2 drops and short M3 tracks connect the signal,
control and body nets. The original v20 placement
(`tg_quad_cell_v20/b16df1b7693057c8`) passes LVS but has four met1.2 spacing
violations at the gate-pad notches. That failed producer/layout is retained.
The separate v21 revision raises gate escapes from 0.3 to 0.5 um.

Context `tg_quad_cell_v21/78e1793488d080ca` passes DRC=0 and strict native LVS.
The two extracted MOS preserve the expected controls, bodies, W/L and all
junction parameters, including D/S symmetry. Fresh passive extraction contains
213 resistors/56 capacitors; exact reduction retains 190 resistors/56 capacitors.
A new collapsed-RC strict LVS passes.

`verify_tg_quad_cell_v22.py` independently compares both child GDS mask regions
to the original inspected primitive GDS, checks the two placements, reimports
the component GDS for fresh DRC/LVS, verifies raw/reduced passivity and
regenerates the exact reduced network. Receipt
`tg_quad_cell_verification_v22/de62852aec6ea75c` passes. Native wrong-control/
junction negative controls are rejected; focused tests also change a MOS gate
or body while leaving the public port list intact.

A read-only wire-connectivity map confirms that both actual R-separated TG
gate nodes map to their intended EN/ENB controls
(`build/tg-quad-cell-v22-control-access.log`). The physical TG RC is not yet
consumed by a bank campaign. The next gate must replace all twenty source TGs
with this verified component, generate observations for all forty actual TG
gates plus the ninety-three fine gates, retain every native terminal, and
measure the absolute zero-code delay first. Only a timing/voltage-passing
complete component-RC bank should proceed to dense/PVT screening and common
physical routing. No whole-bank RC, new calibration ROM, DLL/DCC or PHY gate
is admitted by this component work.

The smaller-guard implementation passes 1,970 regression tests in 417.586 s
(`build/small-guard-v19-full-tests.log`). With the additional native-TG tests,
the full current suite passes all 1,972 tests without skips in 363.239 s
(`build/small-guard-tg-v22-full-tests.log`). Native component proofs and both
zero-code remeasurements also pass. Logs:
`build/small-guard-inverter-v17.log`,
`build/small-guard-inverter-v18-verification.log`,
`build/small-guard-bank-v19-prepare.log`,
`build/small-guard-bank-v19-pilot.log`,
`build/small-guard-bank-v19-verification.log`,
`build/small-guard-bank-v19-zero-verification.log`,
`build/small-guard-bank-v19-two-zero-verification.log`,
`build/tg-quad-cell-v20.log`, `build/tg-quad-cell-v21.log` and
`build/tg-quad-cell-v22-verification.log`.

### Actual TG RC closes the source-headroom question (2026-11-05)

`tg_component_bank_v23.py` installs the complete independently verified native
TG component in all twenty switch positions of the two smaller-guard banks.
It compares original and wire-collapsed native geometry/connectivity only for
binding; simulation retains every actual R/C. All unrelated component
definitions, the 16 uniform taps, 31 fine units, guards, tail termination and
bank connections remain intact. Native device coverage remains 903. Actual
R-separated EN/ENB gates are mapped through the real component wiring: all
forty must match saved native MOS gate terminals and the correct public
one-hot targets. They supplement, rather than replace, the 93 fine-gate checks.

Context `tg_component_bank_v23/dd51484b10ebd382` uses two workers under the
unchanged six-engine dispatcher for two complete SS/40 C zero-code cases,
fixed 1.8 V, 100 ps input slew, 20 fF load and two pulses in 20 ns. Each TG adds
190 positive R/56 nonnegative parasitic C. Total expanded component wiring is
12,601 R and 4,858/4,859 C for `fine3`/`both3`. SC control-cell/common/tail-cap
routes remain unextracted; this is still not whole-bank RC.

Full independent receipt
`tg_component_bank_verification_v23/a3e55bc6d04fac5a` regenerates all libraries,
native census and gate mappings, verifies translated decks/logs/raw record
counts, then remeasures both complete traces:

| Profile | Rise / fall delay (ps) | Fast-quarter headroom (ps) | Peak MOS difference (V) |
| --- | ---: | ---: | ---: |
| `fine3` | 632.810 / 811.766 | -202.011 | 1.880510 |
| `both3` | 618.299 / 785.915 | -176.159 | 1.880506 |

All actual MOS voltage checks, 93 fine gates, 40 TG gates, public/one-hot
controls and repeated pulses pass. Worst TG-control deviations are
41.423/41.839 mV, below the unchanged 180 mV requirement. Repeat differences
are below 0.001 ps. Both fail the unchanged absolute fast-quarter budget.
The 217.692 ps added falling delay in `both3` erases its previous 41.533 ps
headroom. No range, calibration table or PHY admission follows from this
two-case diagnostic; even a zero-code pass would not prove all six sparse codes.
The pilot and its verifier terminate successfully with no numerical/reporting
errors. Failed timing remains a circuit result.

### Measured native-terminal timing diagnosis

Restored component resistance separates the public tap/tree/selected wires
from native MOS terminals. These passive public nodes are not automatically
saved by the fixture. `diagnose_tg_component_path_v24.py` therefore measures
actual saved terminals, with R-connectivity used only to identify each
terminal's role. It does not reconstruct passive waveforms or call those
measurements public-net delays. The selected zero-code path includes sixteen
input-driver output terminals, both terminals at each side of each selected
TG, sixteen fine-driver gates and sixteen fine-driver output terminals, plus
public IN/OUT. Every requested saved vector and exactly one crossing in each
direction per pulse are mandatory. Missing vectors, extra crossings or missing
native fingers cannot silently shrink a timing band.

Receipt `tg_component_path_diagnosis_v24/6e18a08567e9e556` binds the independently
rechecked complete gate and reproduces its public input/output propagation.
For the second `both3` falling pulse, measured intervals between native crossing
bands are (ps):

| Native-terminal interval | Lower / upper bound |
| --- | ---: |
| IN to input-driver output terminals | 122.621 / 128.686 |
| First TG input terminals to its output terminals | 153.285 / 165.166 |
| Root TG input terminals to its output terminals | 154.348 / 164.025 |
| Fine-driver gates to its output terminals | 317.659 / 326.572 |

Other intervals between those active boundaries account for the connecting
segments. A few lower bounds can be slightly negative because different
native-terminal crossing bands overlap; bounds are neither clipped nor
interpreted as inferred public-node timing. This shows the two loaded TGs and
fine driver dominate the restored-RC path.

A separate conservative explicit-wire loading calculation counts every
coupling C in full at both connected public ports. It gives 5.603 fF at A and
4.363 fF at Z per TG, excluding native MOS capacitance, including 1.209 fF A-Z
coupling. This is a diagnostic loading bound, not a replacement for the full
RC transient (`build/tg-component-v21-port-capacitance.log`).

### Legal NMOS-low-Vt isolation

The next experiment retains every reference R/C while changing selected native
device flavors. The pinned local `libs.tech/magic/sky130A.tcl` permits
`nfet_01v8_lvt` at Lmin=0.15 um/Wmin=0.42 um. Its `pfet_01v8_lvt` defaults
require Lmin=0.35 um, so it is not substituted into existing L0.15 PMOS devices.
The broader experiment uses regular `pfet_01v8` in the coarse buffers, as in
the previously physically proven regular-driver change.

`nlvt_data_path_v25.py` defines two variants from the failed actual-RC `both3`
bank, retaining topology, W/L, AD/AS/PD/PS, all R/C and all fine/control devices:

| Profile | Native NMOS model changes | HVT-to-regular PMOS changes |
| --- | ---: | ---: |
| `tg_nlvt` | 20, TGs only | 0 |
| `data_nlvt` | 196, TGs/input/fine drivers/16 coarse-buffer pairs | 160, coarse buffers only |

Changed component model names are diagnostic names. Instance names, terminal
census, 1.95 V domain limits, all 903 MOS observations and all 133 actual
control-gate observations remain intact. The original implant layouts no
longer prove physical equivalence for these components; retained interconnect
RC is explicitly borrowed for flavor isolation. No capacitor or routing
element is removed to obtain a result. A favorable candidate requires new
implant-specific GDS/native/passive-RC proof and complete sparse-range checks,
especially coarse overlap after speeding the coarse buffers.

Prepared context `nlvt_data_path_v25/a937b3dd487bed57` binds the failed complete
gate, regenerated actual component banks and both new model variants. Its two
SS/40 C zero-code cases and independent verifier complete successfully under
the unchanged dispatcher. Full receipt
`nlvt_data_path_verification_v25/4a5573aa2eb7a558` independently verifies both
complete numerical traces. The earlier available-case receipt
`nlvt_data_path_verification_v25/e9bfa8b41b949c64` also binds both cases.

| Profile | Rise / fall delay (ps) | Fast-quarter headroom (ps) | Peak MOS difference (V) |
| --- | ---: | ---: | ---: |
| `tg_nlvt` | 573.311 / 731.952 | -122.196 | 1.880508 |
| `data_nlvt` | 543.525 / 647.174 | -37.418 | 1.869753 |

All native voltage, public/fine/TG control and repeated-pulse checks pass. The
maximum actual TG-control deviations are 43.036/50.824 mV. Both still fail
quarter delay. The broader change recovers 138.741 ps of falling delay from
the original 785.915 ps actual-component-RC path. This is evidence of useful
drive-strength improvement, not a passing clock backend or physical proof for
the changed implants.

Native-terminal band measurements using the existing saved-terminal reader
on the complete broader-flavor trace give about 124--134 ps across the first
TG, 111--117 ps across the root TG, and 252--261 ps from fine-driver gates to
its output terminals on the second falling pulse. This diagnostic retains the
borrowed-RC scope (`build/nlvt-data-path-v25-terminal-bands.log`).

The next physical experiment will shorten and balance A/Z TG routes: align
the N/P signal contacts with a mirrored P device, use short local data tracks,
and keep control/body escapes separate. Fresh native DRC/LVS, preserved
junctions and measured extracted A/Z capacitance must establish that the new
cell reduces loading. The favorable NMOS-LVT/data-buffer changes also require
their own implant-specific component proofs. Restore those actual models and
recheck zero delay/voltage/controls before complete sparse codes, including
coarse overlap after changing buffer drive. No dense/PVT, code-update,
periodic-duty, DLL/DCC or PHY gate is admitted by these zero-code diagnostics.

Validation: the TG-RC restoration passes 1,977 regression tests in 390.917 s
(`build/tg-component-bank-v23-full-tests.log`); native-terminal diagnosis passes
the 1,980-test suite in 369.776 s (`build/tg-component-path-v24-full-tests.log`).
The complete current suite, including the three legal-flavor/RC-preservation
tests, passes all 1,983 tests without skips in 388.006 s
(`build/nlvt-data-path-v25-full-tests.log`). Native complete-waveform gate and
terminal-band remeasurement also pass, while the circuit quarter-period check
fails. Logs: `build/tg-component-bank-v23-prepare.log`,
`build/tg-component-bank-v23-pilot.log`,
`build/tg-component-bank-v23-verification.log`, `build/tg-component-path-v24.log`,
`build/nlvt-data-path-v25-prepare.log`, `build/nlvt-data-path-v25-pilot.log` and
`build/nlvt-data-path-v25-verification.log` and
`build/nlvt-data-path-v25-available.log`.

### Stacked native low-Vt TG: physical routing repair

The stacked TG is now a physical candidate rather than only a model-flavor
substitution. Producer `build_stacked_nlvt_tg_v27.py`, context
`stacked_nlvt_tg_v27/b246982d731cb0f7`, places an NMOS-LVT W1.68/L0.15
below a mirrored regular PMOS W3.36/L0.15, separated by 4.8 um. Short local
M1 data connections replace the previous side-by-side routing. Both native
junction geometries and all six public ports are retained. The first attempt,
`stacked_nlvt_tg_v26/562e0fe96581bb5f`, passes LVS but fails eight M1 spacing
checks at the native D/S metal. It is preserved unchanged. The v27 data rails
move from +/-0.5 to +/-0.6 um, clearing those notches.

Independent fresh-GDS receipt
`stacked_nlvt_tg_verification_v28/d4502a53e9953cf4` passes zero DRC errors,
strict native LVS, exact primitive masks and both placements, raw/reduced RC
passivity, and byte-identical regeneration of the exact RC reduction. It also
rejects wrong-gate and changed-junction negative controls. The component has
215 raw resistors, 192 reduced resistors and 57 explicit capacitors.

| Explicit wiring capacitance upper tally | Previous side-by-side TG (fF) | Stacked TG (fF) |
| --- | ---: | ---: |
| A | 5.60281 | 4.19082 |
| Z | 4.36265 | 3.91223 |
| A-Z coupling | 1.20853 | 0.91526 |

These diagnostic tallies exclude native MOS capacitance and count coupling in
full at both connected ports; they do not replace the distributed RC network
in simulation. Lower wiring loading is established, but recovered bank timing
is not. The existing low-Vt diagnostic still misses the fast-quarter gate by
37.418 ps and uses borrowed RC for changed data-component implants. Actual
low-Vt inverter/buffer layouts and fresh extraction are the next prerequisite.
Input duty remains 40%/60%, nominal 50%, at 390/400/410 MHz, fixed supplies
and the approved 0/25/40 C temperatures. No electrical or PHY gate is waived.
