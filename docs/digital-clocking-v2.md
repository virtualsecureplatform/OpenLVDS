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
The forwarded clock has the steady polarity `~PH0`; it no longer traverses a
constant-data DDR mux. Changed clock latency is included in RX training.

During calibration a section sees the common reference, then the sections are
cascaded. Increment the fastest section, validate an unwrapped tagged-burst
one-period measurement, and require 64 valid confirmations. An edge-sampled
PD uses symmetric paths, input swapping and repeated votes; both extreme
unequal slews must still bracket zero within +/-20 ps. Clock codes update only
while outputs are invalid and become immutable during payload.

Each DCC ORs the outputs of identical self-reset pulse FFs driven by opposite
rising phases and toggles a final FF. The 780--820 MHz event stream, including
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
