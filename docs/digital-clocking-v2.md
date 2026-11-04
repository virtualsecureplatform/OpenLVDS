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
15 PVT, both input swaps and matched/unequal slews at +/-20 ps. The tagged
one-period trial hardware, repeated votes and physical detector still need
implementation and native qualification.

Dense DCDL reanalysis found real SS40 control-device stress at 1.95726 V,
above the unchanged 1.95 V limit. Strengthening the complementary-control
inverter worsens it to 1.97904 V. A native 2x2 MIM shunt reduces it to 1.93214 V
in the first eight-code source test, preserving delays. The separate
`dcdl_control_margin_v2/4a4181e6cbb757d0` tests 2x2/4x4 shunts, both code
directions and large jumps at 20/100/200 ps control slew. The first large-jump
2x2 result fails at 20 ps (1.96278 V), while 100 ps passes (1.93223 V); the
remaining geometry/slew cases are running. No delay ROM is admitted.

Next gates, in dependency order: finish independent source repair matrices;
select a stress-safe fine bank and characterize a common all-PVT code path;
build tagged period/tournament measurement hardware; qualify fresh physical
clock primitives and startup; connect TX/RX clock islands; then run the native
full-link and release matrix. Supplies remain fixed throughout.
