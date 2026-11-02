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

Both coupled runs are still pending in this snapshot. The observer reads
only terminal cases and records pending cases as unknown. Re-run it after
completion to obtain a new immutable observation:

```sh
scripts/env.sh --ngspice /usr/bin/python3 scripts/observe_tx_isolation.py \
  build/diagnostics/tx_convergence_isolation/6d6efde953a550ab
```

The raw/reduced coupled outcomes decide the next isolation experiment.
Do not remove rail RC or decap devices from a qualifying model. A decap-free
physical experiment requires positive cell/device mapping, legal tap endcaps,
resolved configuration checks, power connectivity, DRC/LVS/STA and fresh
extraction. After numerical isolation, extend through the full 188.049 ns
diagnostic, then the required long-training corrected loopback.

## Remaining closure

Release still requires at least 256 training cycles, all forty-five link
conditions, 4096 nominal/512 corner payload bits, at least 200 ps margin after
measured aperture subtraction, the sixty RX and thirty driver component
cases, compliant TX levels/waveforms, current OpenPLL evidence, all DLL gates
and six RC certificates. The C16 DLL has passed its 24-case native screen;
stability and full qualification continue independently.

The full pinned regression suite passes **1041 tests, no skips**. Six actual
SPICE processes were verified running at this snapshot: three DLL stability
steps, two coupled isolation cases and one RX native rate screen. Other
workers wait through the shared dispatcher.
