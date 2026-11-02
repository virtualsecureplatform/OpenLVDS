# Chain restoration and TX convergence isolation

Implementation snapshot, 2026-11-02. OpenLVDS remains in bring-up; no PHY is
released. All artifacts below are relative to `build/diagnostics/`.

## Receiver acceptance

`receiver_acceptance.json` records the agreed laboratory policy separately
from frozen producers. Static sensitivity remains ±100 mV at the original
six common modes. The added ±600 mV tests use common modes 0.3, 1.2 and
2.1 V, keeping pins within 0–2.4 V. Dynamic acceptance ultimately requires
the compliant corrected TX/channel/native RX loopback. There is no new
requirement to transport artificial 100 mV signals at full rate at every
common mode. Old captured replay results remain unchanged stress diagnostics.

The baseline is the original two-resistor feedback inverter receiver,
`receiver_layout/0f9f54a7549bccf1`, with its original frontend and later
inverters. Its old replay `receiver_replay/54143ddc298c5037` loses fourteen
captured crossings and zero sharp-control crossings. The doubled frontend
resistor experiments both lose eighteen captured crossings and zero sharp
crossings; they are held rather than extended.

Fresh campaign `receiver_spec_screen/b7cdfb62ea5040ac` contains:

- Three native SS/40 rate screens at 390/400/410 MHz, 250 mV differential,
  1.2 V common mode and 260 ps 20–80% pin slew. Each is 80 ns, with a 1 ps
  maximum step, both native receivers, shared native bias and the actual
  extracted DDR capture core. Data uses the existing word generator and
  quarter-cycle relationship. Both restoration paths and extracted clock/
  serial capture terminals are saved.
- Thirty additional wide-input static tests: schematic/native × fifteen
  process/temperature conditions, both polarities at all three common modes.

The rate analysis requires correct ordered public payload words, one output
crossing per input clock event, and high/low pulses valid beyond 1.44/below
0.36 V for at least 400 ps. It also reports raw setup/hold distances, without
claiming aperture-subtracted margin. A 0.9 V crossing alone cannot pass.
These short synthetic screens do not establish long-training or PHY release.

All three completed 390/400/410 MHz native rate cases now pass, including
the unique ordered sixteen-word payload.

| Clock, MHz | Minimum valid high/low pulse, ps | Raw setup/hold minima, ps |
| --- | --- | --- |
| 390 | 1155.625 / 1172.511 | 634.688 / 632.799 |
| 400 | 1123.452 / 1140.564 | 617.845 / 616.747 |
| 410 | 1092.841 / 1110.182 | 601.762 / 601.468 |

These raw distances do not subtract measured aperture, and the short
training is not qualified. All fifteen schematic and fifteen native
wide-static cases now pass; the complete screen passes all 33 cases.
The baseline remains preferred; there is no evidence yet requiring either
later-buffer alternative on these representative inputs.

`openlvds-receiver-spec-baseline.service` owns this campaign. Verified host
continuation `receiver_spec_verified_followup/7491414dd4892210`, owned by
`openlvds-receiver-spec-verified-components.service`, binds that exact owner
invocation. Only all 33 passing cases allow the new `qualify_receiver_spec.py`
adapter to remeasure every saved result and run the original sixty component
tests. It captures a separate specification-admission receipt. Original
component/native producers and their old gates are unchanged. A failed or
missing prerequisite holds the handoff; partial output is never retried.

This replaces resource waiter `receiver_spec_followup/ab6d392c598ac24d`:
its invocation-ID check could reject a completed producer after systemd
unloads the transient unit. The replacement accepts an inactive/unloaded
owner only with bound terminal scientific evidence, which is then fully
remeasured by the unchanged admission adapter. A changed live owner is still
rejected. The old waiter was explicitly checked to be waiting, childless and
without a terminal source report before stopping it. No SPICE worker or
scientific producer was restarted; `supersedes.json` preserves the resource
handoff reason and old owner identity.

`receiver_later_buffers.py` implements the two bounded alternatives for use
if representative baseline tests fail: parallel-unit symmetric taper
(P32/N16 then P64/N32), or skewed buffers (P32/N8 then P16/N16). Original
device bins, first inverter, feedback and frontend remain intact. These are
circuit factories only; neither alternative has source, physical or native
admission. Source checks must cover every added MOS device before layout.

## TX numerical isolation

The two corrected-driver coupled diagnostics and the one iteration-budget
experiment all stop at approximately 4.5465 ns at `xtx.vgnd.t436`. The failing
cluster includes extracted rail/decap terminals. The physical flow's empty
`DECAP_CELLS` list did not prevent decap boundary cells: the resolved endcap
was `sky130_fd_sc_hd__decap_3`. This is a lead, not an established cause.

`tx_convergence_isolation/6d6efde953a550ab`, owned by
`openlvds-tx-convergence-isolation.service`, compares four 12 ns cases:
TX-only/coupled × reduced/raw TX RC. Fixed sources, solver accuracy and
1 ps maximum step are preserved; TX-only outputs each see 100 fF. Device and
capacitor statements must match between raw and reduced TX. Additional
probes observe the failing ground/gate cluster. At most two workers acquire
individual P2 leases in the existing six-slot dispatcher.

The coupled isolation/channel controls retain the original four-resistor TIA
receiver from `receiver_feedback_link_diagnostic/ffaef202466488a5` so that
the failed fixture stays fixed while one cause is varied. They do not select
that receiver over the preferred two-resistor baseline. Once the channel/
numerical cause is resolved, restore the two-resistor receiver and recheck its
short native coupled fixture before the full 188.049 ns diagnostic and long
training. A passing isolation control cannot replace baseline-specific evidence.

Both TX-only native engine runs reach 12 ns with finite, increasing raw data.
Their exporter returns an error because the new fixture requested `V(0)`.
The original adapter consequently records `numerically_completed=false`.
Neither record is rewritten. Read-only observer
`raw_completion_observation/dbcee5ba3807090c/summary.json` independently binds
the logs/raw data and distinguishes successful numerical completion from the
export error. The ground-cluster excursions are below 11 femtovolts in these
two traces. This establishes only bounded startup completion: the forwarded
clock has not begun toggling by the end of this short fixture. No functional
TX or electrical pass follows from it.

The reduced coupled run now fails at 4.4465 ns, attempted step 1.25e-24 s,
at `xtx.vgnd.t393`. This is another extracted decap-shaped NFET terminal
(raw X15, W0.55/L0.59), rather than the original X7 terminal. The raw coupled
run also fails, at 4.5465 ns and `xtx.vgnd.t436`, attempted step 1.25e-24 s.
Final observation `raw_completion_observation/89aaa118374b97c3` records all
four terminal cases: both TX-only cases complete, both coupled cases fail.
TX RC reduction is therefore not necessary to reproduce the collapse.
The RX digital block retains its original reduced RC in both cases, so this
comparison does not rule out RX reduction or a whole-network conditioning
problem.
Changing the output interval for the short fixture can change the numerical
trajectory; neither the time nor the terminal is identical to the long parent.
The observer reads only terminal cases and records pending cases as unknown.
It can be invoked without dispatching another simulation:

```sh
scripts/env.sh --ngspice /usr/bin/python3 scripts/observe_tx_isolation.py \
  build/diagnostics/tx_convergence_isolation/6d6efde953a550ab
```

These outcomes direct the next experiment toward coupling/initialization
and the decap rail network. Do not remove rail RC or decap devices from a
qualifying model. A decap-free
physical experiment requires positive cell/device mapping, legal tap endcaps,
resolved configuration checks, power connectivity, DRC/LVS/STA and fresh
extraction. After numerical isolation, extend through the full 188.049 ns
diagnostic, then the required long-training corrected loopback.

For future fresh experiments, `prepare_tx_isolation.py` removes only the
constant-ground print vector and derives a new immutable identity. Prepared
context `tx_convergence_isolation/dd0062114779a180` validates all four new
fixtures. It is not launched: the first campaign's valid raw data and failed
coupled traces are retained, avoiding duplicate simulations.

`isolate_tx_decap.py` positively maps every extracted decap transistor to its
placed boundary cell. It registers extraction coordinates against the DEF
pin geometry, checks the PDK LEF boundary and MOS model/dimensions, requires
the expected rail topology, and requires exactly one N/P pair in each of the
56 cells. All 112 devices map uniquely. In particular:

| Flat MOS | Failed terminal | Placed cell | Extracted position, µm |
| --- | --- | --- | --- |
| X7 | VGND.t436 | PHY_EDGE_ROW_4_Left_32 | 5.915, 21.995 |
| X15 | VGND.t393 | PHY_EDGE_ROW_13_Right_13 | 93.315, 48.175 |

Fresh `tx_decap_isolation/26137b054eba3c5f` removes only those 112 mapped MOS
statements from the raw TX in the otherwise unchanged coupled 12 ns fixture.
Every extracted resistor/capacitor statement and every unrelated device is
retained. This diagnostic has now failed at 4.5465 ns, attempted step
1.25e-24 s, with the reported node shifted to `xrx.vgnd.t215`. Removing the
TX boundary MOS alone therefore does not clear the coupled collapse. It has
no electrical or physical verdict and cannot qualify a decap-free TX.

The RX terminal maps to X4 in the original native DDR receiver,
`rx_early_physical_v1`, specifically `PHY_EDGE_ROW_4_Left_32` at
(5.915, 21.995) µm. The same checked coordinate/PDK/rail mapping uniquely
identifies all 112 RX boundary MOS devices. Fresh two-case context
`endpoint_decap_isolation/335f03b43d9dd052` tests RX-only removal and removal
at both digital endpoints. It preserves every wire R/C and every unrelated
device. `openlvds-endpoint-mapped-decap-isolation.service` owns the two-worker,
individual-P2-lease campaign. RX-only removal now fails at 4.5465 ns,
attempted step 1.25e-24 s, at `xtx.vgnd.t557` (the gate of the original
TX boundary-decap PFET X12). The both-endpoints case remains live.

| Native coupled control | Numerical result |
| --- | --- |
| All original endpoint MOS, raw TX RC | Abort at TX VGND.t436, 4.5465 ns |
| Remove mapped TX boundary MOS only | Abort at RX VGND.t215, 4.5465 ns |
| Remove mapped RX boundary MOS only | Abort at TX VGND.t557, 4.5465 ns |
| Remove mapped boundary MOS at both endpoints | Retired incomplete after original-device channel controls completed; no verdict |

The two single-endpoint removals move the reported trouble node to the
other endpoint. That supports testing the remaining endpoint MOS/numerical
conditioning, but does not yet establish that a physical decap change fixes
convergence. The saved RX-only failure-prefix observation is
`endpoint_decap_isolation/335f03b43d9dd052/rx_only/failure_prefix_observation/ba7f3c55f74422d1`.

The both-endpoints run advanced beyond 4.5465 ns but continued with extremely
small timesteps. After both channel controls completed twelve ns with every
original device intact, this now-superseded MOS-deletion investigation was
explicitly stopped. `endpoint_decap_isolation/335f03b43d9dd052/retirement.json`
binds the verified replacement controls, original device-library equality,
reconstructed channel fixtures, retained partial files and the stopped owner.
The wrapper records exit 143 after the requested stop; that is not a circuit
failure verdict. The incomplete raw file does not pass the normal prefix
validity check and is retained as-is, unqualified. No numerical or electrical
pass/fail is assigned to that partial trace. No qualification worker was
stopped or restarted.
`rebuild_endpoint_tap_cells.py` is ready for a passing complete result: it
rebuilds TX and RX sequentially with original source/constraints and explicit
tap endcaps/well taps, using at most two flow jobs. It requires resolved
configuration, all boundary placements, powered-cell connections, well taps,
DRC/LVS, disconnected-pin/power-grid checks, setup/hold signoff and retained
endpoint-specific functional paths, then fresh extraction and independent RC
audit. TX and RX retain their respective archive/identity validation formats.
No such physical flow is started: the original devices can be retained with
the calibrated original-delay channel representation.

`rebuild_tx_tap_endcaps.py` implements a conditional isolated physical flow
using the original RTL/constraints and explicit tap endcaps/well taps. It
checks resolved config, all 56 legal boundary placements, well taps, powered
cell connections, DRC/LVS, disconnected pins, power-grid errors, setup/hold
timing, retained functional paths, and fresh extraction/independent RC audit.
The flow is held: TX-only MOS removal did not establish the causal completion
required by its gate. No new physical build or model promotion is launched.

## Numerical control with original devices

`observe_failure_prefix.py` inspects complete binary frames from terminal
abort files without making them acceptable to the normal waveform reader.
The failed ngspice files declare zero finalized points; the observer records
that fact, available frame count and trailing bytes, and always marks them
unqualified. Immutable observations are:

- Original raw coupled case:
  `tx_convergence_isolation/6d6efde953a550ab/coupled_raw/failure_prefix_observation/2368d6b24c4f7e89`.
- TX-MOS-removal case:
  `tx_decap_isolation/26137b054eba3c5f/failure_prefix_observation/b82e940dfbb4e730`.

Both prefixes reach 4.5465 ns with finite increasing time. Both source clocks
remain low; the recovered RX clock peaks at only 0.805 mV. The supplied first
clock edge starts at 5 ns, so these aborts precede functional clock activity.
These are observations of incomplete numerical traces, not electrical passes.

The independent original-model control is complete and fails:
`tx_sparse_isolation/b05c673bfe98d862`, owned by
`openlvds-original-coupled-sparse-isolation.service`. It changes only linear
solver selection to Sparse 1.3, retaining every original device and all raw
TX RC, stimuli, tolerances, iteration budget, and 1 ps maximum step. The
actual solver is verified in the ngspice log: `Using SPARSE 1.3 as Direct
Linear Solver`. It aborts at 4.4465 ns, attempted step 1.25e-24 s, reporting
`xtx.vgnd.t557`. Thus changing the linear solver does not clear the original
coupled collapse. The terminal raw prefix is separately preserved at
`tx_sparse_isolation/b05c673bfe98d862/failure_prefix_observation/00f8c7a4620e368a`.
Both solvers are documented in the
[ngspice manual](https://ngspice.sourceforge.io/docs/ngspice-manual.pdf).
This bounded numerical control does not admit a circuit or replace RC checks.

## Channel-model isolation

The both-endpoints MOS-removal diagnostic took very small timesteps around
7.0465 ns: one inspected interval was approximately 1.58e-20 s. It was later
retired as described above. This behavior does not establish decap removal
as a usable fix. The independent Sparse control failed as recorded above.

`channel_model_isolation/1eaa65d55aa8616a`, owned by
`openlvds-channel-model-isolation.service`, now isolates the delayed channel
with all original MOS and wire RC retained. It first requires three passive
calibration fixtures at 25/50/100 ohm termination. Reflective cases use a
10 ohm source; the matched case uses 50 ohms. Both the original T element and
the zero-loss LTRA element must agree with each other and the independent
analytic reflection series within 1 mV over the full twelve ns. The analytic
calculation includes the exact initial DC state and every causal reflection
arrival in the observation interval. This tests delay, DC gain and echoes;
agreement between two equally wrong simulated waveforms cannot pass it.

Only successful calibration starts the two bounded coupled controls:

- `zero_delay` replaces only the four line elements with zero-volt shorts.
  It retains package L/C, source resistance, termination, all devices and all
  internal extracted R/C. It localizes the effect of delay and cannot qualify
  the required cable.
- `ltra_lossless` preserves every original line terminal and its original
  delay/impedance. For each 50 ohm leg, LEN=1, L=Z0*TD and C=TD/Z0, with
  R=G=0: clock legs use 60 nH/24 pF for 1.2 ns and data legs use 65 nH/26 pF
  for 1.3 ns, including the original 100 ps data skew. It changes the numerical
  transmission-line implementation while retaining the analytic two-port
  transfer function. Coupled models, fixed supplies, stimuli, tolerances,
  iteration budget and 1 ps maximum step remain unchanged.

The ngspice manual explicitly notes that a zero-loss LTRA element may be
more accurate than the T element because of implementation details
([sections 6.1–6.2](https://ngspice.sourceforge.io/docs/ngspice-46-manual.pdf)).
This is a documented representation control, not a claim that the T element
caused the observed collapse. The 25 ohm reflective calibration now completes
and passes: maximum T/LTRA disagreement is 2.041e-13 V; maximum LTRA/analytic
disagreement is 1.076e-13 V. The matched 50 ohm control also passes: maximum
T/LTRA disagreement is 5.002e-14 V and maximum LTRA/analytic disagreement is
2.776e-16 V. The 100 ohm reflective control also completes and passes:
maximum T/LTRA disagreement is 8.274e-14 V and maximum LTRA/analytic
disagreement is 0.185185 mV, below the 1 mV limit. All three calibrations pass.
The coupled zero-delay and original-delay LTRA controls both now complete
the full twelve ns with finite increasing raw data and return code zero.
Independent cached remeasurement rechecks all calibration waveforms and both
full traces. Each coupled library is byte-identical to the original-device
parent; reconstructing each channel fixture exactly reproduces its saved deck.
No transistor, extracted wire R/C, supply, package element, termination or
solver tolerance was changed. The original T-line case aborted around 4.5 ns;
the calibrated LTRA representation therefore clears that observed short-run
numerical failure while preserving the intended delay and impedance.

This is startup numerical evidence only. In both complete twelve-ns controls,
the forwarded digital TX clock and recovered RX clock have zero 0.9 V
crossings. The TX data output has one crossing; RX data has none in this
window. No functional transport, payload or timing admission follows from
this result, and numerical behavior after the clock starts remains to be
verified in the extended preferred-receiver diagnostic.
Every actual simulation uses its own P2 lease in the same six-slot
dispatcher; no healthy simulation was stopped or outer lease added.

## Preferred-receiver coupled handoff

`restore_baseline_coupled.py` implements the next gated handoff without
changing the frozen failed producers. Host resource context
`baseline_coupled_followup/097e558936b80c28`, owned by
`openlvds-preferred-baseline-coupled-followup.service`, has admitted the complete
calibrated twelve-ns LTRA control and prepared
`baseline_coupled_restoration/02c868108c5b1da1`. It does not dispatch a
zero-delay substitute. The fresh preferred-receiver short test completed
twelve ns, but its wrapper then raised `NameError: read_raw is not defined`
before recording the result or dispatching the payload. This is a producer
error, not a numerical failure. The frozen producer and all original outputs
remain unchanged.

After that prerequisite, the scientific preparer independently rechecks all
three calibration waveforms, the complete LTRA trace, and all three passing
native rate screens. It restores the audited original TIA r2 model, preserving
the native bias, corrected driver, raw TX and native digital RX closures, and
rebinds the fourteen receiver observations to actual extracted nodes. Public
terminal order is checked before assembly. It then runs a fresh twelve-ns
baseline check. Only numerical completion of that check dispatches the full
original 188.049 ns/32-bit/60 ns training diagnostic. That trace is decoded
and its recovered clock transport measured with the original analyzers.

The handoff holds no outer SPICE lease; each actual run acquires one P2 slot.
It accepts a bound terminal LTRA receipt even if the transient owner unloads;
the preparer revalidates the scientific evidence. Prior partial outputs are
retained rather than retried. These remain diagnostic results: sixty receiver
components, 256-cycle training, long payloads, measured aperture, real DLL
phase/startup, all corners and release checks remain required.

The current payload retains raw TX RC as a numerical reference. Read-only
observation `tx_exact_current_witness/d0a2d429776b333c` independently checks
the existing canonical TX reduction: 22,909 resistors become 5,757 through
exact resistor-only elimination. The non-resistor statement signature and
protected-node set are identical. Four deterministic terminal-voltage
witnesses across 3,103 resistor boundary nodes pass the existing 1 nA plus
1e-8 relative current limits. Maximum absolute current difference is
3.3591e-10 A; reference/reduced sparse solve residuals are 5.14e-16/1.28e-16.
The pinned NumPy/SciPy runtime and both netlist hashes are captured.

This is supporting algebraic evidence for using the smaller canonical
network in future runs. It is not a coupled waveform comparison or a measured
speed improvement, and does not change the live raw-TX payload model. The
existing passing digital RC observation compares canonical exact RC against
TICER RC; it does not itself compare raw RC against canonical exact RC in
this coupled fixture. A matched calibrated-LTRA comparison must precede any
claim that the smaller network accelerates this chain without changing its
measured waveforms. No capacitor or MOS removal is involved.

`recover_baseline_payload.py` independently verifies the complete original
raw trace and exact agreement of every exported voltage, time and sample
index. The saved short trace has 12,089 finite, increasing samples ending at
12 ns. Recovery context `baseline_payload_recovery/678e1b24d0305732` binds
that evidence and all original fixture/model hashes. Its fresh payload deck
changes only the library include path, retains the full 188.049 ns fixture,
and runs through one fair P2 lease. Unit
`openlvds-preferred-baseline-payload-recovery.service` queues that payload;
it does not rerun the completed short test. The original failed service and
its stale `running_short` state are preserved for provenance. A recovered
short observation carries no electrical verdict or PHY admission.

Read-only startup snapshot
`startup_training_observation/12c60c696ecef7b2` now shows functional activity
through the restored chain. The unchanged parallel sources issue training
`01` throughout the fixed 25–40 ns publication interval. The existing public
pair/VALID decoder reads six words as `[1, 1, 1, 1, 1, 1]`, using its full
0.8–1.05 ns publication windows. RX clock and RXVALID are active. The raw
prefix, source deck/library/manifest hashes, publication times and decoder
hash are captured independently of the live simulation.

This is a short startup observation from an unfinished trace. It does not
test the later payload, sustained clock transport, 256 training cycles,
sampling aperture/margin, PVT or release. The full 188.049 ns diagnostic
continues without restart; its original complete-trace analysis remains
required before proceeding to longer training and payloads.

Fixed-window snapshot `startup_clock_observation/aef05be3c3a9a6c4` also
remeasures the complete 20–60 ns clock-transport interval. Its 31 inspected
input events each have one same-polarity recovered output crossing within
the next input period, with zero missing rising or falling output edges.
The saved raw prefix independently reproduces the existing diagnostic
matching result. This uses 0.9 V crossings; it does not establish full valid
pulse widths, payload correctness, aperture-subtracted margin or release.

## Receiver component and RC continuation

The specification campaign has completed all fifteen schematic wide-DC
cases, the three native 390/400/410 MHz rate cases and all twelve native
TT/FF/SS/FS/SF wide-DC cases: **33/33 pass**, including native SF40.
The verified component handoff
still requires all 33 screen cases before dispatching the original sixty
component conditions. A read-only preflight confirms that all sixty original
reference fixtures remain current and passing; this does not replace testing
the selected receiver in those conditions.

`validate_receiver_spec_rc.py` admits the receiver RC comparison through the
new specification evidence and all sixty completed component proofs. It
remeasures cached results, rejects missing or changed outputs before any
dispatch, and retains the original physical audit, exact shared bias,
60 ns TT25 comparison fixture, and 20 ps/20 mV comparison limits. The legacy
failed replay is neither rewritten nor used as the new admission gate.

`continue_receiver_spec_rc.py`, resource context
`receiver_spec_rc_followup/2b7a21efb78ad376`, follows the verified component
owner and queues RC work only after a bound sixty-case pass. Unit
`openlvds-receiver-spec-rc-followup.service` holds no outer SPICE lease.
This comparison covers one RC case; the joint six-case certificate and all
PHY release gates remain required.

## Capture-input slew domain

The original 480-condition aperture campaign remains unchanged at 20/200 ps
clock and data input slews. Its final table cannot admit out-of-domain link
slews. Fixed startup snapshot `capture_slew_observation/662f6a651c2cd6d3`
captures the current preferred-receiver coupled raw prefix and measures only
20–25 ns. RX clock 10–90% slews span 145.313–219.231 ps; RXDATA slews span
128.033–197.647 ps. The clock observation already exceeds the old 200 ps
upper endpoint. The raw snapshot, source manifest hash, measurement code
hashes and unfinalized-prefix description are retained for remeasurement.

This is startup-domain planning evidence only, not an aperture or payload
verdict. Earlier fast-edge observations alone must not determine the added
aperture points for the current receiver. Choose added slow/fast endpoints
from the completed current payload's full scoring window and retain the
original PVT, edge/polarity, setup/hold, guarded-witness and capture-core
requirements. Do not extrapolate the old table or widen its declared range
without new measurements. No additional aperture campaign is launched from
this short startup snapshot.

## Remaining closure

Read-only driver waveform observation
`driver_waveform_observation/eb6972c489141165` now remeasures all thirty
completed corrected-driver component traces. `observe_driver_waveform.py`
checks complete campaign coverage and binds every original fixture, result
and waveform before measuring the full state-to-state 20–80% transition and
the complete common-mode excursion during the alternating 800 Mb/s segment.
The existing component pass flags remain unchanged: their loaded eye checks
sample near interval centers, whereas this observation includes transitions.

Across the fifteen schematic cases, observed transition times span
155.844–199.790 ps and common-mode ripple spans 326.427–499.602 mVpp.
Across the fifteen native cases, these ranges are 274.735–638.370 ps and
770.214–1047.442 mVpp. Each case has 392 measured transitions. All measured
20–80% intervals are monotonic. No case stays within the 260–375 ps
reference range over all measured transitions, and none meets the
150 mVpp common-mode reference.
At native TT25, common mode ranges from 0.451550 to 1.441748 V; a valid
center eye does not establish dynamic output balance.

The reference comparisons come from TIA-644-A sections 4.1.4–4.1.5
([source](https://e2e.ti.com/cfs-file/__key/communityserver-discussions-components-files/138/7380.eia_5F00_tia_5F00_644_2D00_a_5F00_lvds.pdf)).
These saved 100 ohm/2 pF-per-pin component fixtures have not been separately
qualified as the standard generator tests. This is a diagnostic finding,
not a new compliance verdict or a rewrite of existing component results.
Generator waveform qualification remains open. Before selecting a TX
architecture change, correlate the loaded common-mode excursions with the
coupled payload trace and separate complementary-gate timing, steering-current
continuity and common-mode feedback response in bounded source experiments.
Changing the feedback bandwidth or adding output capacitance alone cannot
be assumed to fix the observed transition and common-mode behavior together.

`isolate_driver_balance.py` implements that first bounded source experiment
in `driver_balance_isolation/dddcd0dc2e9d5d96`, owned by
`openlvds-driver-balance-isolation.service`. Three sequential TT25 controls
retain the same corrected 110:1 bridge, common-mode feedback, fixed supplies,
35 uA reference and 100 ohm/2 pF-per-pin load. An 80 ns fixture with a 1 ps
maximum step compares the original converter against ideal complementary
3.3 V gate drives with 100 ps and 400 ps full-ramp transitions. Only the
converter instance is replaced in the two ideal-drive controls; all other
source statements remain identical. These ideal voltage sources cannot be
selected as hardware or qualify gate loading, extracted timing or the PHY.

The controls save both gate voltages, TOP, BOT and SINK. Measurements include
common-mode range, gate-sum error, output edge count and internal voltages at
common-mode extrema over 20–75 ns. If ideal complementary gates suppress
the ripple, level-converter timing is a supported lead; if ripple persists,
bridge current continuity and CMFB behavior remain necessary investigations.
Slower complementary gates distinguish overlap-time sensitivity. All cases
use individual P2 leases within the existing six slots, with no outer lease
and no retry of partial outputs. The coupled payload diagnostic continues
independently; no architecture is selected from these diagnostic controls.

The baseline control now completes all 80 ns with return code zero and
22 rising output edges in the 20–75 ns observation window. It reproduces
478.881 mVpp common-mode movement. The maximum error in `DP + DN = 3.3 V`
is 2.24537 V during switching, establishing substantial non-complementary
gate activity in this source fixture. The ideal 100 ps control also now
completes all 80 ns with return code zero and 22 rising output edges.
Common-mode movement falls to 95.5864 mVpp (1.184353–1.279940 V), with
gate-sum error below 9e-16 V. This supports the gate-drive path as a major
contributor while the bridge, CMFB and output load remain fixed. Ideal drive
changes both complementarity and transition shape. The 400 ps control now
also completes with return code zero and 22 rising output edges, but shows
374.539 mVpp common-mode movement (0.985566–1.360105 V) despite gate-sum
error below 9e-16 V. Complementarity alone is insufficient in this source
fixture; transition speed matters as well. These controls do not establish
a real converter implementation or generator compliance. Prioritize balanced,
fast gate drive and its extracted loading before assuming that a CMFB-only
redesign is necessary.
The original coupled payload continues independently, with no restart.

Historical matched native-driver observation
`driver_restore_balance_observation/597ab334ac14bf77` remeasures the older
loaded link over 60–120 ns and independently rechecks both physical models.
Its `source_control` is P48/N40 with ten mirror fingers (100:1), while the
legacy task name `restore_64_24` actually identifies P64/N24 with eleven
fingers (110:1). The comparison changes both sizing and current ratio; it
cannot isolate either change. In that fixture, clock common-mode ripple is
639.923 versus 320.038 mVpp, and maximum gate-sum error is 2.16602 versus
0.964358 V. Both still show dynamic movement. These numbers use the old
loaded link and 20 ps maximum step, and cannot substitute for the current
source controls or generator test. The initial observational receipt
`26b3b7f8d2cdb765`, whose scope incorrectly described both cases as 100:1,
is explicitly superseded; its waveform measurements are unchanged.

`driver_gate_taper.py` now provides two bounded real-MOS candidates supported
by the ideal-gate result. Each replaces the two final restoration inverters
with three-stage parallel-unit tapers, preserving each branch's inversion:
P16/N8 → P32/N16 → P64/N32, or P16/N8 → P64/N32 → P128/N64. All added devices
use the existing thick-oxide 3.3 V model families with 0.5 um channel length.
The current-mode converter frontend, eleven mirror fingers, bridge, CMFB,
output capacitors and public terminals remain unchanged. The smaller first
stage is intended to reduce converter loading; stronger later stages are
intended to restore the loaded bridge gates. These are hypotheses requiring
measurement, not claimed improvements or selected hardware.

`probe_driver_gate_taper.py` prepares source context
`driver_gate_taper/64ffaad7ac4e4e20`, owned by
`openlvds-driver-gate-taper.service`. It independently remeasures the complete
baseline and ideal 100 ps evidence before preparing the two cases. The
baseline itself is not rerun. Both use the original fixed-supply TT25
80 ns/1 ps fixture. Additional observations record converter/restoration
nodes, all added MOS terminal-voltage differences, and actual IO/digital
supply branch currents for average power over 20–75 ns. Missing or nonfinite
current traces fail the observation rather than silently reporting power.

The two cases acquire separate P2 leases within the unchanged six-slot
budget. The slower ideal control and raw coupled payload remain independent
and unmodified. No source PVT, physical or native candidate is selected by
these pilots. Any promising taper still needs all fifteen source conditions,
DC and waveform checks, power/stress review, local balanced placement,
fresh physical/extraction audits, the full component matrix and corrected
coupled loopback before it can replace the current driver.

The first real-MOS pilot, `taper_16_32_64`, now completes all 80 ns with
return code zero. It retains 22 rising output edges and reduces common-mode
movement to 170.213 mVpp (1.143361–1.313574 V), versus the baseline's
478.881 mVpp. This is an improvement, but remains above the 150 mVpp
reference. Mean measured IO/digital supply powers are 25.998/1.210 mW.
The maximum absolute terminal-voltage difference among the added devices
is 4.04222 V. These are source TT25 measurements only, not PVT stress/power
qualification or a hardware selection. The stronger `taper_16_64_128` now
also completes all 80 ns with 22 rising output edges and 81.0217 mVpp
common-mode movement. Its measured IO/digital powers are 29.248/1.210 mW,
and its largest added-device terminal difference is 4.04209 V. It clears
the common-mode reference in this source pilot, but no complete waveform,
PVT or hardware admission follows. All three causal controls and both real
pilots have independent cached waveform remeasurement; no unfinished producer
was invoked to obtain these observations.

The completed first taper also has estimated differential 20–80% transition
times of 151.740–158.267 ps over 44 edges. This estimate infers the positive
steady-state level by symmetry from its initial negative operating point;
it is not a compliance measurement. It nevertheless motivates separating
fast gate restoration from output edge shaping: slowing the gates alone
already worsens common-mode movement in the 400 ps control.

`probe_driver_output_shape.py` implements one calculated symmetric MIM
candidate, source context `driver_output_shape/8a7fdbf9ec16dd27`, owned by
`openlvds-driver-output-shape.service`. It changes only the two existing
output capacitors from 10×10 to 30×30 um on the first taper. The pinned TT
MIM model's area/perimeter terms estimate 0.20658 versus 1.81978 pF per
capacitor. Including the unchanged external 2 pF per pin gives a nominal
capacitance ratio near 1.73. Simple capacitive scaling predicts roughly
263–274 ps transitions; actual nonlinear waveforms must determine the result.
The estimated minimum is close to 260 ps, so full PVT margin cannot be
assumed even if this TT25 trial passes.

Two otherwise matched 80 ns/1 ps TT25 cases start from opposite initial
logic states and retain the same subsequent alternating cadence. They
measure fresh negative and positive DC levels over 0–8 ns before evaluating
the 20–75 ns transitions. No symmetry assumption is used in the final
calibrated edge analysis. The experiment retains supply-current and added-MOS
voltage observations, checks monotonic 20–80% transitions against the
260–375 ps reference for this 800 Mb/s fixture, and reports the common-mode
and DC reference comparisons. These are source pilot checks, not generator
compliance or hardware selection. Both cases use individual fair P2 leases;
no supply sweep, original-model replacement or healthy-job restart occurs.

The shaping candidate's `negative_op` case has completed with return code
zero, 22 rising output edges and 139.842 mVpp common-mode movement. Its
solved initial DC point is -339.728 mV differential at 1.248092 V common mode,
with less than 5e-12 V variation over 0–8 ns. With a *temporarily assumed*
symmetric positive DC level, 44 monotonic edges estimate 265.371–269.952 ps.
The `positive_op` case has now completed with return code zero. Its solved
initial point is +339.728 mV differential at 1.248092 V common mode, and
dynamic common-mode movement is 139.047 mVpp. Fresh two-polarity calibration
measures 265.371–269.952 ps for `negative_op` and 265.383–269.923 ps for
`positive_op`, with 44 monotonic edges each. Both retain 22 rising output
edges, and the complete nominal source reference checks pass. The initial
symmetry estimate is no longer used for this nominal verdict. This is only
TT25 source evidence: the narrow nominal timing/common-mode margins cannot
select a physical candidate or establish PVT margin.

`qualify_driver_output_shape_source.py` implements the next required source
matrix: all five process corners × 0/25/40 C × both initial logic polarities,
for thirty distinct cases and fifteen PVT points. Each keeps the exact
shaped circuit, fixed rails/reference, 100 ohm/2 pF-per-pin load and original
80 ns/1 ps stimulus. Each PVT point receives its own fresh two-polarity DC
calibration before transition, monotonicity and common-mode reference checks.
Actual supply currents and added-MOS voltages remain observations; this
matrix does not itself admit power/stress, physical layout or the PHY.

Host continuation `driver_shape_source_followup/a5e76aa1dd959a0e`, owned by
`openlvds-driver-shape-source-followup-v2.service`, waits for the original
shaping producer's complete terminal receipt. Only a bound nominal pass can
call the scientific preparer, which remeasures both saved waveforms, DC
points and calibrated transition results before preparing any new case.
Missing, failed or changed evidence holds the handoff. The source matrix
uses at most two workers, each with one P1 lease in the existing six-slot
dispatcher; the host waiter holds no SPICE lease. No physical dispatch is
automatic, even after a source waveform pass.

The nominal handoff has now independently remeasured both completed cases
and prepared `driver_shape_source/40b882e177324c81`, containing all thirty
source fixtures. Its two workers use P1 leases. Four source cases have now
completed, covering TT0 and TT25 in both polarities. Independent pair
remeasurement passes TT0 with 264.869–270.810 ps transitions and
142.640–143.431 mVpp common-mode movement. The entire fifteen-point matrix
is still required; no source circuit or physical selection is promoted from
these first results.

`verify_driver_shape_source.py` implements the read-only full-matrix handoff
check. It requires all thirty terminal case receipts and a bound aggregate,
checks fixture/output hashes and identical source circuits, then remeasures
every waveform and both DC calibration polarities at all fifteen points.
It compares the complete remeasurement with the original aggregate and
captures all evidence hashes. Missing, changed, failed or incomplete evidence
rejects the handoff without running SPICE or changing the original results.
Its receipt reports supply-power ranges and the maximum added-device
terminal difference, with physical admission and PHY qualification explicitly
false. Four tests cover complete remeasurement, partial output, tampering,
changed analysis and a failed case hidden by an aggregate pass claim.

After the complete source matrix passes, run:

```sh
scripts/env.sh --ngspice /usr/bin/python3 scripts/verify_driver_shape_source.py \
  /work/OpenLVDS/build/diagnostics/driver_shape_source/40b882e177324c81
```

The current incomplete campaign correctly rejects this command. This check
does not dispatch physical work or replace the required device-stress,
power, layout or native-waveform review.

The initial childless resource waiter `d7c392bc3bd8201a` was stopped before
any source matrix was prepared to correct handling of an empty successful
scientific run log. Its producer/owner and replacement receipt are retained.
No science worker, source waveform or parent pilot was stopped or rewritten.

Release still requires at least 256 training cycles, all forty-five link
conditions, 4096 nominal/512 corner payload bits, at least 200 ps margin after
measured aperture subtraction, the sixty RX and thirty driver component
cases, compliant TX levels/waveforms, current OpenPLL evidence, all DLL gates
and six RC certificates. The C16 DLL has passed its 24-case native screen;
stability and full qualification continue independently.

The full pinned regression suite passes **1148 tests, no skips**. Actual
SPICE workers use the existing six-slot dispatcher, alongside the DLL
stability campaign. No outer handoff lease is held while another worker waits.

## Payload clock loss after restored startup

`observe_payload_clock.py` freezes a copy of the available raw bytes, binds
the original recovery inputs and producer hashes, and measures only a fully
available fixed interval. Observation `payload_clock_observation/fee62e0eec5b4b89`
covers 60–95 ns of the still-running 188.049 ns diagnostic. An independent
read of its saved snapshot reproduces the complete report. This chain uses
the original native 110:1 driver and preferred two-resistor receiver; the
new shaped source driver is **not** present.

Startup transport was intact over 20–60 ns, but the payload interval loses
four falling responses and the four following rising responses under the
same diagnostic period-matching rule (eight missing events of twenty-six
complete input periods). TX digital and differential clocks continue, and
the pulses reach the receiver pins. The four lost negative pulses start
at 69.804, 72.213, 74.643 and 89.282 ns. Their peaks are 180, 152, 139 and
144 mV; their longest support beyond -100 mV is 313, 306, 336 and 339 ps.
The receiver's first restoration node never falls below 1.107–1.189 V in
these respective pulse windows. Thus there is no low decision for the last
two buffers to restore. A separate recovered low pulse lasts only 50.6 ps
at the diagnostic 0.9 V crossing, reinforcing why crossings alone do not
establish capture validity. Available public payload words also disagree
with the expected sequence; the full-run terminal verdict is still pending.

Negative differential pulse widths are already distorted at the TX output:
511–1029 ps there and 533–1025 ps at the RX input, compared with 863–1067 ps
digital low pulses. These observations locate the loss before the final
receiver buffers but do not separate driver distortion, shared-bias effects
and early receiver response. Static sensitivity is not a guaranteed dynamic
response to every short pulse that briefly exceeds 100 mV. No new minimum
pin-pulse acceptance limit is introduced by this report.

Continue the unchanged reference run and shaped-driver source PVT matrix.
Do not select a later-buffer change from this failure. If the source matrix
passes, review power/device stress and use compact physical placement for
the fast gate stages and local output capacitors before native checks. The
existing generic driver is a 4.09 mm horizontal strip, so its RC cannot be
assumed to preserve the source improvement. Then compare the compliant native
driver/channel against this same preferred receiver. An early receiver
architecture change requires failures on that representative input, with
stage and shared-bias observations sufficient to isolate the cause.

## Fast-corner failure and stronger gate pilot

The first shaped driver's source matrix now has actual fast-corner failures.
FF0 measures 183.177/181.697 mVpp common-mode movement in the negative/positive
initial-polarity cases; FF25 measures 185.864/185.297 mVpp. The FF40 negative
case measures 187.422 mVpp. These exceed the unchanged 150 mVpp reference,
so this candidate cannot receive the full source waveform handoff even
though TT0/25/40 pairs pass. The original matrix continues all thirty cases;
no failed result or healthy worker is reset.

`probe_stronger_driver_shape.py` prepares bounded pilot
`stronger_driver_shape/1b35b6d74efed383`, owned by
`openlvds-stronger-driver-shape.service`. It first remeasures and binds the
actual FF0 failure and the completed stronger real-MOS taper. The candidate
uses that existing 1/4/8 taper (P16/N8, P64/N32, P128/N64) with the **same
30×30 um output capacitors**. Relative to the failed shaped driver, only
the gate taper changes. Bridge, 110:1 mirror, CMFB, supplies, reference,
load, stimulus and time step remain fixed. TT25 and FF0 each have fresh
negative/positive DC calibration and full 80 ns traces. Two P2 workers
queue individually through the existing dispatcher. Its three tests check
the bounded coverage, unchanged circuit outside the two capacitor sizes
and rejection without a measured prerequisite failure. Passing this pilot
would still require a fresh complete fifteen-point source matrix before
physical work.

A signed-voltage spot check of the completed weaker-taper TT0 traces finds
the first-stage input reaching 4.041 V on the fixed 3.3 V rail; the following
stage drain extrema span -0.157 to 3.451 V. The first PMOS therefore reaches
positive VGS of approximately 0.741 V, while a later NMOS reaches negative
VGS of approximately -0.157 V. The existing maximum-absolute terminal report
alone does not describe these excursions. The published [SKY130 device
details](https://skywater-pdk.readthedocs.io/en/main/rules/device-details.html)
give signed model operating ranges for these thick-oxide devices. Those
ranges are model-characterization information, not a transient reliability
certificate. Keep signed excursions and actual device/body currents in the
physical review; this observation neither introduces a zero-overshoot
acceptance rule nor declares the devices safe from an absolute maximum alone.

## Matched LTRA benchmark for exact TX reduction

`benchmark_ltra_exact_tx.py` prepares
`ltra_exact_tx_benchmark/df68f33bb3275375`, owned by
`openlvds-ltra-exact-tx-benchmark.service`. It binds the existing independent
TX current witnesses and replaces only the raw TX resistor network with the
canonical exact degree-four elimination (22,909 to 5,757 resistors). All
capacitors, MOS devices, public terminals, printed probes and directives
are retained. The full preferred-r2/110:1-driver LTRA fixture keeps its
188.049 ns duration, 1 ps step, stimuli, shared native bias and solver
settings. One P2 worker runs the reduced case; the healthy raw reference
`baseline_payload_recovery/678e1b24d0305732` is reused without another raw run.

Comparison waits for both full terminal traces, verifies their raw/export
agreement and original diagnostic metrics, and compares all saved voltages
on a 1 ps grid over the full interval. It requires matching public digital
edge counts, at most 20 ps edge error, at most 20 mV voltage error and the
same payload diagnostic outcome. Four tests cover unchanged non-resistor
statements, complete matching waveforms, incorrect voltages/clock edges and
rejection of incomplete or nonfinite evidence. This is a numerical and
performance experiment: reproducing a failing payload cannot qualify it.

The TT25 C16 DLL corner stability run has now completed and passed its full
3300 ns screen. SS0 and FF0 continue; all three passing corner screens are
still required before the queued full campaign advances.

## Stronger pilot pass and complete PVT handoff

The stronger-cap30 pilot `stronger_driver_shape/1b35b6d74efed383` has now
completed all four cases and passes both freshly calibrated PVT points:

| PVT | Negative / positive common mode, mVpp | Combined 20–80% transition range, ps |
| --- | --- | --- |
| TT25 | 63.356 / 61.647 | 263.940–266.576 |
| FF0 | 136.480 / 135.659 | 263.689–273.087 |

Each trace has 44 monotonic calibrated transitions and 22 rising output
edges. Compared with the failed weaker taper at FF0, the stronger taper
reduces common-mode movement from 181.697–183.177 to 135.659–136.480 mVpp
with the same capacitors. IO/digital supply-power observations across these
four cases are 29.203–29.259 / 1.124–1.210 mW; the maximum observed
added-device terminal difference is 4.067 V. These observations do not close
the required power/stress or native physical review. Minimum edge time still
has only about 3.7 ps headroom to the 260 ps reference in these pilots.

`qualify_stronger_driver_shape.py` independently remeasures all four pilot
cases, both DC polarities and both complete corner reports before preparing
any full matrix. The accepted handoff prepared
`driver_shape_source/b016a1113b51cd82`, owned by
`openlvds-stronger-driver-source-pvt.service`. It contains all thirty source
cases, five processes × 0/25/40 C × both initial logic polarities, with the
same 80 ns/1 ps fixtures and fixed circuit/rails/load. Its two P1 workers
use the existing dispatcher without an outer lease.

The adapter reuses the frozen source runner and verification checks. A
process-local analysis adapter supplies the actual stronger taper's 1/4/8
parallel-unit counts; the adapter code is bound in the new campaign identity,
and the original helper is restored afterward. Frozen files, waveform
limits and other campaigns are unchanged. Five tests cover incomplete
pilot rejection, wrong-variant rejection, correct measurement routing and
restoration after exceptions, and two-worker full-matrix dispatch.

Only after all thirty source cases pass, remeasure the full matrix with
its matching analysis adapter:

```sh
scripts/env.sh --ngspice /usr/bin/python3 scripts/qualify_stronger_driver_shape.py verify \
  /work/OpenLVDS/build/diagnostics/driver_shape_source/b016a1113b51cd82
```

No physical candidate is dispatched from this pilot pass. The source matrix,
power/stress review, compact routing, native PVT and coupled timing remain
required. The original weaker-taper PVT matrix continues independently and
retains its failed fast-corner results.

Receiver screen `receiver_spec_screen/b7cdfb62ea5040ac` has also completed
all 33 cases with a bound passing aggregate. Its verified continuation
remeasured the complete screen and started the original sixty components in
`receiver_components/24ea17b76d61a8e3`; the new specification-admission
receipt is retained there. The RC continuation still waits for all sixty.
The C16 DLL SS0 stability screen has now completed and passed its full
3300 ns run as well. TT25 and SS0 pass; FF0 is still running and remains
required before the full DLL handoff advances.

## Complete weaker matrix and the stronger taper's SS failure

The weaker 1/2/4-cap30 matrix `driver_shape_source/40b882e177324c81` is
complete, with **6/15 PVT points passing**. TT and SF pass at all three
temperatures. FF fails common mode at 183.177–187.422 mVpp; FS fails at
155.261–166.676 mVpp. SS has acceptable common mode but minimum calibrated
edges of 256.585–256.734 ps, below 260 ps. The complete failed result is
retained; the producer has exited normally with a held source-matrix receipt.

The stronger 1/4/8-cap30 matrix `b016a1113b51cd82` passes all six completed
TT/FF points, but its SS results invalidate source selection. SS0 measures
176.374/175.403 mVpp common-mode movement in negative/positive cases, and
the SS25 negative case reaches 187.753 mVpp. Fresh two-polarity SS0
calibration measures 250.628–261.127 ps for the negative case and
250.688–259.971 ps for the positive case, with 44 monotonic transitions each.
Both common-mode movement and minimum transition time need correction.
Neither taper has full source admission, and no new physical build starts.

The pinned `sky130.lib.spice` includes the same
`r+c/res_typical__cap_typical.spice` and
`r+c/res_typical__cap_typical__lin.spice` files in TT/FF/SS/FS/SF. The
transistor-corner tests therefore do not select different MIM parameter
corners. The observed SS speed difference cannot be attributed to such
a capacitor-corner selection.

A read-only branch-zero timing comparison uses the median delay from each
1.65 V input crossing to the following opposite output crossing during
20–74 ns of the complete negative-initial-state traces:

| Taper / corner | L → G0 rise/fall, ps | G0 → G1 rise/fall, ps | G1 → DP rise/fall, ps |
| --- | --- | --- | --- |
| 1/2/4 SS0 | 103.45 / 135.62 | 97.30 / 119.70 | 71.38 / 85.98 |
| 1/4/8 SS0 | 156.47 / 217.96 | 114.03 / 146.71 | 53.40 / 74.78 |
| 1/2/4 FF0 | 72.61 / 79.11 | 64.77 / 78.28 | 50.29 / 51.98 |
| 1/4/8 FF0 | 112.91 / 132.64 | 73.95 / 95.65 | 35.73 / 43.54 |

These are diagnostic threshold delays, not aperture measurements. The
stronger taper doubles the first unit's gate load while leaving its drive
unchanged. Its larger and less balanced SS first-stage delays support
isolating that fanout before assuming that stronger final gates solve PVT.

`driver_stage0_balance.py` changes only the first stage's unit count from
one to two in both branches: **2/4/8**, retaining the 30 um capacitors.
`probe_driver_stage0_balance.py` binds and remeasures the actual failing
SS25 and passing FF40 source references, then prepares the same two
negative-initial-state 80 ns/1 ps controls. Artifact
`driver_stage0_balance/6458be492f296656`, owned by
`openlvds-driver-stage0-balance.service`, uses at most two P2 workers in
the existing dispatcher. It measures common mode, actual rail power,
negative initial DC stability and added-device voltages with the correct
2/4/8 counts. Three tests verify the two-unit-only change, retained caps,
and rejection without the required source failure/control evidence.

These two controls cannot supply fresh positive DC calibration or complete
transition/PVT admission. If they fix common mode without breaking FF,
fresh both-polarity calibration must determine whether an additional fixed
output-capacitor increase is still needed for the SS minimum edge time.
There is no capacitor sweep or voltage sweep. The running 1/4/8 source
matrix and all receiver, DLL and coupled jobs continue unchanged.

## First-buffer tradeoff and calculated next candidate

The two 2/4/8-cap30 controls are complete. SS25 common-mode movement improves
from 187.753 to **50.471 mVpp**, but FF40 worsens from 132.480 to
**217.693 mVpp**. Both retain 22 rising output edges, solved stable negative
DC levels within the original ranges, and their actual power/stress
observations. The combined control fails and does not admit this taper.
Simply increasing the first buffer is therefore not a uniform PVT fix.

The completed 1/4/8-cap30 matrix passes **9/15** points: TT, FF and FS at
all three temperatures. SS fails common mode and minimum edge time; its
largest common-mode movement is 191.770 mVpp, with the fastest calibrated
edge approximately 250.151 ps. SF also fails minimum edge time
(255.106–256.355 ps), despite passing common mode. These failed results
remain unchanged.

`driver_geometric_shape.py` defines one calculated candidate: **1/3/8**
parallel gate units and **36×36 um** output MIMs. The first buffer's load
on the CML converter stays at one unit. The two interstage load factors
become 3 and 8/3, near the equal-fanout value sqrt(8), rather than 4 and 2.
This tests a timing compromise while retaining the final strong gates.
Increasing the fixed capacitors separately addresses the measured fast-edge
failure. All remaining circuit statements, original device bins, mirror,
bridge, CMFB, supplies/reference and loads are retained.

The pinned nominal MIM formula gives 1.819782 pF at 30 um and 2.615742 pF
at 36 um per capacitor. With the unchanged external 2 pF per pin, the total
capacitance ratio is approximately 1.2084. Pure capacitive scaling of the
completed 250.151–273.087 ps source range predicts approximately 302–330 ps.
That is an estimate, not admission: the gate-taper change and nonlinear
current waveforms must be measured. Only this one calculated capacitor
choice is introduced; there is no sweep or source-PVT limit relaxation.

`probe_geometric_driver.py` remeasures and binds both completed first-buffer
controls and the completed stronger-matrix reference cases before preparing
`driver_source_pilot/2dc8b9a5062d0dc9`. Unit
`openlvds-geometric-driver-pilot.service` owns six fresh 80 ns/1 ps cases:
TT25, SS25 and FF40, each with negative and positive initial logic states.
Every pair receives its own fresh DC calibration before the unchanged
20–80%, monotonicity, common-mode and DC checks. Two P2 workers use the
existing dispatcher. The factory's two tests check exact circuit scope and
reject changed or repeated source transformations.

Reusable `driver_source_campaign.py` binds the recipe/runner hashes,
identical case circuits and declared coverage. It rejects partial/nonfinite
or shortened traces, retains every failed output, and never retries a
partially run case. Its four tests cover full 80 ns completion, undeletable
full-PVT coverage, incomplete-admission rejection and no partial retry.
Verification remeasures all saved cases and recomputes the complete report.
The next full thirty-case matrix can be prepared only after all six pilot
cases pass this remeasurement:

```sh
scripts/env.sh --ngspice /usr/bin/python3 scripts/probe_geometric_driver.py prepare-full \
  /work/OpenLVDS/build/diagnostics/driver_source_pilot/2dc8b9a5062d0dc9
```

The full stage requires all fifteen process/temperature points with both
polarities, uses two P1 workers, and still cannot admit physical work without
complete passing evidence and power/stress review. No new physical model,
selected PHY or release claim follows from preparing this pilot.

The preferred receiver has now passed all **sixty components** in
`receiver_components/24ea17b76d61a8e3`. Its specification-admitted RC
comparison `receiver_spec_rc/b2ba11aa2ef77c6f` also completes and passes;
the RC resource handoff has finished. This is one receiver comparison, not
the final joint six-case RC certificate or aperture/coupled qualification.

All three C16 measured stability screens (TT25, SS0, FF0) complete and pass.
The live full-DLL continuation has advanced to `running_full_336_native_cases`.
Its scientific child runs the original full qualification, followed by all
fifteen stability corners only on a full native pass. Recovery, readiness,
OTA, RC and actual coupled DLL timing remain required afterward.

## Geometric-cap36 pilot passes all three points

Pilot `driver_source_pilot/2dc8b9a5062d0dc9` completes all six cases and
passes the unchanged reference checks at all three declared PVT points:

| PVT | Negative / positive common mode, mVpp | Combined calibrated transition range, ps |
| --- | --- | --- |
| TT25 | 89.971 / 88.822 | 320.146–324.585 |
| SS25 | 117.549 / 116.130 | 307.017–317.547 |
| FF40 | 141.813 / 142.180 | 319.706–329.673 |

Every trace has 44 monotonic 20–80% transitions and 22 rising output edges.
Each point uses its own solved negative and positive DC levels; the final
edge results do not assume symmetry. This resolves the observed SS
common-mode/fast-edge failures in the bounded pilot while preserving FF40.
FF40 still has only about 7.8 mV common-mode headroom to the 150 mVpp
reference, so physical margin and the remaining process/temperature cases
cannot be inferred from these results.

Observed IO/digital powers across these six cases are
28.496–28.693 / 1.136–1.292 mW per driver, and the largest added-MOS terminal
difference is approximately 4.067 V. These remain source observations,
without native power/device-stress or PHY admission.

The complete read-only pilot verifier remeasured all six raw/export results,
both DC calibrations and all three pair reports before preparing
`driver_shape_source/b1325bf847630063`. Unit
`openlvds-geometric-driver-source-pvt.service` now owns its thirty source
cases: all five processes × 0/25/40 C × both initial logic polarities.
The fixed 1/3/8-cap36 circuit, rails, reference, load, stimulus and time
step remain unchanged. Two P1 workers use the existing six-slot dispatcher;
there is no outer lease or retry of partial output.

Only complete passing source evidence can produce the next readiness
receipt:

```sh
scripts/env.sh --ngspice /usr/bin/python3 scripts/probe_geometric_driver.py verify \
  /work/OpenLVDS/build/diagnostics/driver_shape_source/b1325bf847630063
```

That receipt still sets physical admission and PHY qualification false.
Power/stress review, a compact physical driver, native PVT, coupled timing,
the final current apertures and all release gates remain required.

## Full source pass, completed raw reference and physical interface preparation

The geometric-cap36 matrix `driver_shape_source/b1325bf847630063` completes
all thirty cases and passes **15/15** process/temperature points. Complete
read-only remeasurement produced readiness receipt
`driver_shape_source_verification/49d28e2c45badad9/summary.json`. Across the
full source matrix:

- Common-mode movement is 37.444–142.327 mVpp.
- Calibrated transitions are 306.637–330.278 ps.
- Solved differential DC magnitude is 323.866–345.938 mV.
- IO/digital power observations are 28.201–29.081 / 1.124–1.295 mW per driver.
- Maximum observed added-MOS terminal difference is 4.161 V.

All thirty saved traces and DC/pair reports were checked again against their
bound inputs, code and output hashes. These source results enable physical
experiments; they do not admit a native driver or the PHY. Signed voltages,
real native loading and power/device behavior still require physical checks.

The original-device raw-TX/r2/LTRA reference
`baseline_payload_recovery/678e1b24d0305732` also completes **188.049 ns**
with return code zero and no numerical failure. An independent reread
verifies all 190,038 raw/export samples and reproduces both terminal metrics.
Payload fails with no correctly ordered preamble, and the complete 60–120 ns
transport observation loses five falling and five rising responses. This
closes the numerical restoration milestone while retaining the old driver's
electrical failure. No original MOS device, capacitor or rail was removed.
The matched exact-TX benchmark remains running; its transient-equivalence
result is still pending.

`driver_finger_banks.py` prepares compact physical groups from the exact
flattened source fingers. The candidate contains **320 devices, including
302 MOS fingers**. Equal model, terminal order, width and length allow those
fingers to form **32 MOS banks**; the eighteen passive devices stay separate,
giving fifty placements. Every original finger identity is tracked, all
widths remain at most 8 um on the 5 nm grid, and unsupported MOS parameters,
duplicate identities and repeat grouping are rejected. This is placement
preparation, not a claim of identical extracted parasitics or reduced device
physics.

The pinned Magic PCells support `nf` and separate gate contacts. The physical
recipe uses one guarded row, independent diffusions/poly and individually
accessible G/D/S contacts. Multi-finger cells enable both top and bottom
access because the short-channel arrays interleave their gate contacts.
Single fingers retain top-only gate access.

The first real interface probe `driver_finger_pcells/c879157e8fce9932`
rejected missing alternating gate labels on thin 1.8 V arrays when bottom
access was disabled. Its geometry, logs, failure receipt and original helper
snapshot are retained. The corrected source-gated probe
`driver_finger_pcells/6f91f0001837f0af` generates **nineteen unique MOS
PCell recipes**, passes all terminal-interface checks and verifies all saved
file hashes. Every finger exposes G/D/S explicitly; no incomplete interface
is silently accepted. Actual gate contacts on the 1.8 V four-finger cell
alternate between y=-4.275 and +4.275 um. Routing must accommodate both sides,
including outward gate-contact escape, rather than reuse the old top-only
fanout assumption.

The probe uses the full source readiness receipt before any PCell generation,
and binds the pinned technology scripts and helper code. It records the
source current/voltage observations alongside its physical-interface scope.
Its two tests reject partial source admission and cache-key reuse across
different finger counts; five bank tests cover connectivity, terminal access,
parameter/grid restrictions and unchanged passives.

These are unconnected primitive interfaces: a complete driver still needs
connected banks/inverter tiles, compact fast-node routing and power delivery,
DRC/LVS, fresh RC extraction/audit and native electrical qualification. No
GDS or interface-only result is promoted as a usable driver.


## Connected finger banks pass physical checks

The full source gate remains `driver_shape_source_verification/49d28e2c45badad9`:
30/30 cases and 15/15 PVT points. The connected-bank build
`driver_connected_banks/628b8eaa6b8adda3` now passes **nineteen of nineteen
recipes with zero DRC errors and strict LVS matches** against every original
independent MOS finger. Gate routing accommodates both alternating contact
sides, and bulk routing leaves the guard vertically before crossing gate
access. Drain/source landings are staggered to fit the dense thin-oxide
contacts; no transistor or terminal was removed.

Two failed physical contexts remain available. `c3715658165e4f35` passed
LVS throughout but used undersized Magic via drawing layers and produced
spacing notches around repeated landing pads. `83754c6a3c794e6e` corrected
those issues and passed eighteen recipes; the single-finger 1.8 V cell
retained four metal1 spacing violations. The final 0.37 um metal landing
with a legal 0.26 um via1 drawing clears that cell as well. These corrections
change physical access only, with the source circuit held fixed.

`build_driver_inverter_tiles.py` selects the nine original CMOS inverters
by common drain/gate and supply-tied source/body connectivity. There are
five distinct P/N recipes. The new tiles stack the checked P/N banks with
local input/output spines and separate supply rails. Their own DRC/LVS
checks precede complete-driver placement; bank admission does not admit a
tile or a native electrical model. Source readiness, parent evidence,
technology and producer hashes bind each build, and partial contexts are
retained rather than overwritten.

The complete regression passes **1,152 tests without skips**. Complete-driver
compact routing, GDS RC extraction/audit, native waveform qualification and
the restored coupled link remain required. The existing six-slot simulation
campaigns continue without restart or changed accuracy settings.


## Compact complete driver passes DRC, LVS and native RC audit

The five distinct source-matched CMOS inverter tiles in
`driver_inverter_tiles/68dc41fb1597cada` all pass **zero-error DRC and strict
LVS**. They cover all nine original inverter instances. The complete
physical trial `driver_compact_layout/65385b4549fed34b` also passes
**DRC=0 and LVS**, retaining all **320 original devices, including 302
independent MOS fingers**. The layout uses forty-one child placements.

Each mirrored branch places its CML stage, three inverter tiles, bridge
transistors and output capacitor locally. The four inter-stage connections
use direct metal3 routes of **54 um** each. Quiet bias/CMFB/current-mirror
circuits occupy two separate rows. Metal4 buses and metal5 drops join the
remaining nets, with shared columns only for the same electrical net.
The actual routed bounding box is x=-17.4..772.4 um and
y=-324.7..252.5 um: **789.8 x 577.2 um**. This replaces the earlier
4.088 mm-wide strip with a compact routed driver; it does not itself
establish an electrical advantage.

The first complete trial `c39572bba628c0f3` retained ten MiM/via3 spacing
errors and failed LVS because greedy access tracks crossed neighboring
capacitor plates. Earlier assembly contexts `78db8453bfc4b41b` and
`64e36979c6c52179` stopped on ambiguous bridge selection and overlapping
resistor bounds. `b8d7cc326779abbe` stopped at the new unsafe-access guard.
All remain retained. The successful implementation includes transformed
child boxes when calculating bounds, rejects overlapping children, checks
horizontal access corridors and matches safe tracks globally before
routing. It shares mirrored supply columns without joining different nets.

`driver_compact_extraction/d72cbc423b52f949` extracts distributed RC from
the qualified GDS and passes independent wire-collapsed LVS. The network
contains **40,160 resistors and 4,045 capacitors** before the existing exact
positive-conductance degree-four elimination, and **30,110 resistors**
afterward. No MOS device or capacitor is removed. All nine public terminals
retain their source order. This is an RC connectivity milestone, not native
electrical admission.

Six fresh native-output pilots are prepared in
`driver_compact_native_pilot/7542c9e673372ad7`, owned by
`openlvds-compact-driver-native-pilot.service`. They cover TT25, SS25 and
FF40 with both initial polarities, using the original full **80 ns / 1 ps**
stimulus, fixed supplies/reference, 100 ohm differential load and 2 pF per
pin. The two workers acquire individual P2 leases under the existing
six-engine global limit; there is no outer lease or existing-run restart.
They measure fresh DC, calibrated 20–80 transitions, common-mode movement,
output edge count and actual supply power, with exact raw/export voltage
agreement. Internal MOS stress, complete fifteen-point native qualification,
restored coupled tests and PHY admission remain separate work. The pilot
verifier remeasures complete cached traces and never retries partial runs.

The full regression passes **1,155 tests without skips** after the complete
physical/extraction flow and native pilot adapter were added.
