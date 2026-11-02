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

The completed 390 and 400 MHz native cases both pass, including the unique
ordered sixteen-word payload. At 390 MHz, minimum valid clock high/low widths
are 1155.625/1172.511 ps and raw setup/hold minima are 634.688/632.799 ps.
At 400 MHz they are 1123.452/1140.564 ps and 617.845/616.747 ps. These raw
distances do not subtract measured aperture, and the short training is not
qualified. The 410 MHz case and the thirty wide-static cases remain required.
The baseline remains preferred; there is no evidence yet requiring either
later-buffer alternative on these representative inputs.

`openlvds-receiver-spec-baseline.service` owns this campaign. Host continuation
`receiver_spec_followup/ab6d392c598ac24d`, owned by
`openlvds-receiver-spec-components-followup.service`, binds that exact owner
invocation. Only all 33 passing cases allow the new `qualify_receiver_spec.py`
adapter to remeasure every saved result and run the original sixty component
tests. It captures a separate specification-admission receipt. Original
component/native producers and their old gates are unchanged. A failed or
missing prerequisite holds the handoff; partial output is never retried.

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
individual-P2-lease campaign. Its results remain pending.

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

One independent original-model control is queued:
`tx_sparse_isolation/b05c673bfe98d862`, owned by
`openlvds-original-coupled-sparse-isolation.service`. It changes only linear
solver selection to Sparse 1.3, retaining every original device and all raw
TX RC, stimuli, tolerances, iteration budget, and 1 ps maximum step. The
actual solver must be verified in the ngspice log before numerical completion
can be recorded. Both solvers are documented in the
[ngspice manual](https://ngspice.sourceforge.io/docs/ngspice-manual.pdf).
This bounded numerical control does not admit a circuit or replace RC checks.

## Remaining closure

Release still requires at least 256 training cycles, all forty-five link
conditions, 4096 nominal/512 corner payload bits, at least 200 ps margin after
measured aperture subtraction, the sixty RX and thirty driver component
cases, compliant TX levels/waveforms, current OpenPLL evidence, all DLL gates
and six RC certificates. The C16 DLL has passed its 24-case native screen;
stability and full qualification continue independently.

The full pinned regression suite passes **1057 tests, no skips**. Actual
SPICE workers use the existing six-slot dispatcher, alongside the DLL
stability campaign. No outer handoff lease is held while another worker waits.
