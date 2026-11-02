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
training is not qualified. All fifteen schematic wide-static cases pass;
the fifteen native wide-static cases remain in progress.
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

## Receiver component and RC continuation

The specification campaign has completed all fifteen schematic wide-DC
cases and the three native 390/400/410 MHz rate cases: **18/33 pass**, with
the fifteen native wide-DC cases pending. The verified component handoff
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

Release still requires at least 256 training cycles, all forty-five link
conditions, 4096 nominal/512 corner payload bits, at least 200 ps margin after
measured aperture subtraction, the sixty RX and thirty driver component
cases, compliant TX levels/waveforms, current OpenPLL evidence, all DLL gates
and six RC certificates. The C16 DLL has passed its 24-case native screen;
stability and full qualification continue independently.

The full pinned regression suite passes **1093 tests, no skips**. Actual
SPICE workers use the existing six-slot dispatcher, alongside the DLL
stability campaign. No outer handoff lease is held while another worker waits.
