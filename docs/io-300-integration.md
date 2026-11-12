# OpenLVDS I/O macros: integration guide

`openlvds_io_tx` and `openlvds_io_rx` are asynchronous LVDS driver and receiver
hard macros for SKY130A. The contract they are qualified against is
[`io_300.json`](../io_300.json); the release policy is
[`qualification_io_300.json`](../qualification_io_300.json). They carry no
clocking, serialization or training: that is the 300 MHz DDR PHY, which is a
separate release built on these macros.

Check `make qualify-io-300` before using a build. A gate that is not `pass`
means the macro is not released, whatever this guide says.

## What the macros are, and are not

| | `openlvds_io_tx` | `openlvds_io_rx` |
|---|---|---|
| Function | 1.8 V logic input to LVDS output pair | LVDS input pair to 1.8 V logic output |
| Rate | 580 to 620 Mb/s NRZ (290 to 310 MHz clock pattern) | same |
| Supplies | VDDIO 3.3 V, VDDD 1.8 V, VSS | same |
| Bias | one 35 uA sink on IREF, 1.2 V on VREF | same |

Qualified envelope: process tt/ff/ss/fs/sf, 0 to 40 C, fixed 3.3 V and 1.8 V
supplies. There is no supply sweep and no data above 40 C or below 0 C.

Not in the macros, so you must provide them:

- **Pads and ESD.** The pins are bare metal 4. Nothing protects them.
- **Termination.** 100 ohm differential across the receiver pair, placed at
  the receiver. The transmitter has no on-die termination.
- **VREF.** A buffered 1.2 V reference. Each receiver draws about 0.4 mA from
  it (see the electrical tables); the transmitter draws almost nothing.
- **IREF.** One 35 uA current sink per macro instance.
- **Power-down and failsafe.** There is no enable pin. An open, shorted or
  undriven receiver input gives an undefined output.

## Pins

All pins are metal 4 on the bottom edge, in this order from the left.
Signal pins are 2 um stubs; the three supplies are full-height vertical
straps that a metal 5 power grid can drop onto anywhere along the macro.

| Pin | TX | RX | Use | Notes |
|---|---|---|---|---|
| D | input | | 1.8 V logic | No setup or hold: the macro is asynchronous |
| OUTP, OUTN | output | | LVDS pair | 3 um wide. Route as a matched pair to the pads |
| INP, INN | | input | LVDS pair | Route as a matched pair from the pads |
| Q | | output | 1.8 V logic | Liberty arc is INP to Q |
| VREF | input | input | 1.2 V reference | |
| IREF | bias | bias | 35 uA sink to VSS | One sink per instance |
| VDDIO | supply | supply | 3.3 V | 5 um strap |
| VDDD | supply | supply | 1.8 V | 5 um strap |
| VSS | supply | supply | ground | 5 um strap, shared by both domains |

**Never connect two IREF pins together.** Each macro has its own
diode-connected bias mirror on IREF. Two in parallel share one sink and each
runs at half current.

OUTP is in phase with D. Q is high when INP is above INN.

## Electrical behaviour

The numbers that follow are measured on the layout-extracted macros. The
complete per-corner tables are published with the views as
`openlvds_io_tx_electrical.csv` and `openlvds_io_rx_electrical.csv`; use those
for design, not a summary.

Transmitter, into 100 ohm with 2 pF per pin:

- Differential output 250 to 450 mV, common mode 1.125 to 1.375 V
  (TIA/EIA-644-A 4.1.1 and 4.1.2), with both binary states within 50 mV of
  each other.
- 20 to 80 percent transitions between 260 ps and 0.3 unit intervals
  (484 ps at 620 Mb/s), monotonic, ringing within 20 percent.
- Common-mode variation under PRBS7 below 150 mVpp.

Receiver:

- Decides a +/-100 mV differential input correctly for input common mode from
  0.05 to 2.35 V (pins between 0 and 2.4 V).
- With a 250 mV input at 290 to 310 MHz into 100 fF, the output is valid for
  at least 400 ps in each half cycle.
- Input-referred offset from device mismatch: the mean plus three standard
  deviations stays inside +/-100 mV at every common mode. Offset is largest at
  low common mode, where only the PMOS input pair is active.

### Edge rate depends on your pad capacitance

The transmitter is a current-mode driver. Its output edge is set by the
100 ohm termination and the total capacitance on each pin: the on-die
capacitors and wiring (about 3.2 pF) plus whatever your pad, ESD and package
add. Each extra picofarad per pin slows the 20 to 80 percent edge by about
70 ps. The macro is qualified with 2 pF per pin. Much less than 1 pF risks
edges faster than 260 ps; much more than 3 pF risks edges slower than
0.3 unit intervals. If your pad differs, simulate the extracted netlist with
your load before committing.

## Physical integration

- **Halo.** Keep standard cells and other wells at least 10 um from the macro
  boundary. The macro's 3.3 V wells come within about 6 um of its edge, and
  the LEF does not list wells as obstructions.
- **Routing.** Metal 1 to metal 4 are blocked over the macro. Metal 5 is free.
- **Power.** Connect VDDIO, VDDD and VSS from a metal 5 grid onto the metal 4
  straps. In LibreLane, which pairs every power net with a ground, list the
  shared ground once per supply: `VDD_NETS = [VDDD, VDDIO]`,
  `GND_NETS = [VSS, VSS]`, and give `PDN_MACRO_CONNECTIONS` one entry per
  supply for each instance.
- **Placement.** Place macros against a core edge or leave at least one power
  strap pitch beside them. A narrow strip of standard-cell rows between a
  macro and the core edge gets no power strap and no well taps.
- **Fill.** The macros ship unfilled. Chip-level fill must stay out of the
  macro boundary on local interconnect through metal 4. Their own metal
  density is in the signoff record; minimum density is a whole-die check.
- **Top-level DRC with Magic.** Magic derives the high-resistance poly implant
  (RPM) from the poly shape instead of reading it from GDS, and so reports
  `rpm.1` inside the macro. The GDS is correct: the macro's own full Magic DRC
  (with mask hints) and KLayout DRC are clean. Load the macro as a LEF
  abstract for top-level Magic DRC (`MAGIC_DRC_MAGLEFS` in LibreLane).
- **LVS.** Use the published CDL. It is the flattened device netlist the
  layout was checked against.

[`examples/openlvds_io_ref_top.v`](../examples/openlvds_io_ref_top.v), hardened by
`make io-ref-top`, is a worked example of all of the above. It proves the
views integrate; it is not a link-rate demonstration.

## Timing

- **TX.** The Liberty view gives D its input capacitance and a maximum
  transition. OUTP and OUTN have no arcs. D-to-output delay is in the
  electrical tables; add it to your launch path by hand.
- **RX.** The Liberty view has an INP-to-Q arc, measured from the differential
  zero crossing at the macro pins to Q at 50 percent, against input transition
  and Q load. Board, package and pad delay are yours to add.
- There are 15 Liberty files per macro, one per process and temperature
  point. All are at the fixed nominal supplies.
- SDC templates: `openlvds_io_tx.sdc` and `openlvds_io_rx.sdc`.

## Simulation notes

- The functional Verilog models carry logic values and a typical delay only.
- For SPICE, use the extracted netlist with the pinned SKY130A models. Start
  from a supply ramp rather than a solved DC operating point: the PDK poly
  resistor model has a non-physical high-voltage branch that a DC solve of
  the extracted transmitter can land on.
- After the supplies ramp, the transmitter outputs sit near VDDIO for about a
  microsecond until its common-mode loop settles. A receiver connected to it
  sees up to 3.3 V on its pins during that time. The macro's own receiver
  inputs are thick-oxide and tolerate it; check any other receiver you use.
- In Xyce, cap the time step explicitly and let it follow the Newton
  iteration count (`.options timeint erroption=1`). With truncation-error
  step control, transients of these macros abort with "time step too small"
  at unpredictable points.
- Model a transmission line as an LC ladder, not the simulator's ideal delay
  element. With the ideal element this driver's transient does not converge
  in Xyce or ngspice.

## Known limits

- Fixed supplies and 0 to 40 C only.
- No ESD, short-circuit, power-off leakage or failsafe behaviour has been
  designed or tested.
- Electromigration has not been checked. Each device finger is contacted
  through single vias; wide supply and output crossings use via arrays.
- The receiver is characterized at full rate at 1.2 V common mode only. Across
  0.05 to 2.35 V it is characterized statically.
- Simulated only. There is no silicon measurement.
