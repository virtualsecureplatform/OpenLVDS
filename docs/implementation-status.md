# Implementation status

The SKY130 macro implementation and reproducible build flows are present.
**The link is still in electrical bring-up and is not released.**

The latest completed checks on 2026-10-28 include:

- RTL: 2,373,576 bits across 54 cases: 1,186,788 each for generic RTL and native
  SKY130 serializer cells, plus DLL control and generic/native PHY assembly.
- Schematic characterization previously passed all 60 cases. The revised receiver
  passes 15 static and 15 rate canonical cases at tt/ff/ss/fs/sf and 0, 25, and
  40 °C.
- Extracted driver: all 15 corners pass, including edge identity, polarity,
  amplitude, common mode, and propagation measurements.
- The compact receiver passes all 15 full-RC static and 15 full-RC rate corners. The rate test uses 840 Mb/s,
  250 mV differential input, and 100 fF output load.
- Physical checks: five analog macros and three digital macros pass DRC/LVS;
  all five current analog extracted networks also pass an independent
  connectivity audit. The compact receiver passes DRC/LVS and extraction.
- Unit tests: 52 pass, including stale-evidence rejection, parallel input timing,
  link measurement boundaries, driver latency/polarity, physical port policy, and RC trace provenance.

Extracted DLL qualification and the complete full/approximate RC
comparison remain outstanding. Completed driver cases are recorded individually
under `build/analog_extracted/`. No approximate network is qualified until the
complete comparison certificate passes. Each reusable reference now carries hashes
of its simulator provenance, requirements, circuit, fixture, waveform, and producer
snapshot. Unattested legacy traces cannot qualify or resume a reference. Fresh
receiver, delay-line, TX, and RX comparison pairs pass; driver and DLL pairs are
still required for a complete certificate.

An archived partial extracted DLL trace showed approximately 508 ps quarter-cycle
delay and 310 ps detector-input error. Automatically inserted clock-delay buffers
were found on the phase detector's inputs and outputs. All three digital macros
have been rebuilt without those cells and pass physical checks; the phase
detector additionally preserves direct clock and UP/DN connections. With equal
45 fF loads, its isolated extracted output pulses now reach approximately 1.82 V,
versus 1.29–1.35 V before the correction. The completed extracted DLL run with the rebuilt PFD fails: quarter-cycle delay
  spans 814–845 ps and detector-input error reaches 405 ps. The isolated pulse
  test is diagnostic evidence. The new schematic response bench also shows the
  existing indicator staying low at ±150 and ±300 ps error; a low indicator
  alone cannot establish lock.

A short extracted link diagnostic with late parallel input changes shows payload
ordering errors. The earlier receiver clock-load problem was corrected and
checked independently.
The bench now launches parallel data according to the existing physical input
constraints. An isolated transistor-level TX diagnostic using the unqualified
approximate RC view and 80 fF output loads decodes all 64 payload bits correctly;
a subsequent 32-bit end-to-end diagnostic decodes every payload bit with valid
voltage levels, but measures approximately 35 ps setup margin against the
unchanged 200 ps requirement. That diagnostic uses a
0.9 V logic threshold: three sampled highs remain below 1.44 V at its selected
sample time, so it does not establish valid CMOS levels or output timing margin.
Short diagnostic runs use less training than
the 256-cycle PHY startup and cannot establish release performance.

The 4096-bit nominal electrical link and complete 45-case extracted regression
have not passed. The current release checker therefore reports failure. Read
`build/release/status.json` and the source-checked tables in
`build/characterization/` for machine-readable evidence. Missing results are
failures, and behavioral or diagnostic results cannot replace them.

The deliverable is a reusable macro library with RTL integration. It does not
include pads, ESD, a complete assembled PHY GDS, mismatch/yield qualification,
or a monolithic PLL/DLL/link noise simulation. Supply voltages remain fixed;
no voltage sweep is included.

The standalone phase-error response bench is available as:

```sh
./scripts/env.sh --ngspice python3 scripts/verify_phase_detector.py --extracted
```

Add `--corners` for all five process corners at 0, 25, and 40 °C. The bench
applies 0, ±50, ±150, and ±300 ps detector-input offsets at fixed supplies,
with the real DLL analog loading and a 20 fF indicator load. It checks that
the indicator stays low at small offsets and reaches a valid high for large
errors; a stuck-low flag cannot pass. It is a standalone diagnostic and does
not replace DLL acquisition or complete link qualification.

The revised receiver uses 10 µm input-mirror devices and a 64 µm decision tail.
Each decision input now has 2 kΩ in parallel with 4 kΩ to VREF, and 4 kΩ to
ground. Its Thevenin equivalent remains 1 kΩ, with a 0.9 V bias derived from the
external 1.2 V reference. This restores decision-stage headroom across the static
corner matrix. A 32-bit replay using this schematic receiver and extracted
capture logic gives zero errors, approximately 174 ps setup margin and 268 ps
hold margin. The setup result still fails the 200 ps target; it is an intermediate
improvement over the preceding approximately 35 ps result. End-to-end timing checks remain required.

Receiver routing now uses 5 µm total inter-cell clearance, local internal buses,
and local signal-pin escapes. Its width drops from 985 to 607 µm. Extracted
coupling-capacitance sums incident on Q decrease from 130 to 23 fF, PP from
121 to 68 fF, PN from 128 to 72 fF, and CO from 43 to 24 fF. These are network
capacitance sums, not independent grounded loads. Compact-layout PVT passes all 30 cases. Its full/approximate RC comparison passes
with at most 1.23 ps edge error and 0.15 mV plateau error. Whole-link diagnostics
remain in progress.

Analog LVS now compares fixed-width poly resistors individually. The PDK's
mixed series/parallel reduction gave an extraction-order-dependent property
error for an unchanged ladder. Disabling those reductions preserves each
connection and resistor length check: the compact layout passes, and a
controlled doubled-length resistor is rejected. Property errors remain fatal.

The preceding native XOR transmitter passed DRC/LVS and timing (7 ps setup
slack, 88 ps hold slack), but its 32-bit extracted-channel payload has only
140 ps setup and 126 ps hold margin, despite zero bit errors. Data common mode
also dips to 1.12265 V, below 1.125 V. These measurements are from the completed
payload window of a still-running diagnostic transient, not release evidence.
Internal traces show alternating clock launch delays of 786–999 ps and data
launch delays of 750–987 ps. Pattern-dependent encoded-state delay is too large.

The revised transmitter uses three plain sampling registers and a PH90-selected
mux for data, with an identical PH0-selected constant-input clock replica.
Both input bits still belong to the same rising-edge capture. Generic and
native RTL pass the full 54-case regression and functional PHY assembly.
The mux revision passes physical DRC/LVS and timing, with 58 ps worst setup
slack and 87 ps hold slack. Native cell connections pass the independent
physical policy. Fresh extracted electrical checks remain required.

The compact receiver with the preceding transmitter revision completes a
32-bit extracted-channel diagnostic with zero errors, 202 ps setup margin,
and 257 ps hold margin. That run uses shortened training and no injected
jitter; it does not qualify the revised native transmitter or the link matrix.
The preceding XOR transmitter's full/approximate RC comparison passes, with
maximum edge error 3.31 ps and plateau error 2.29 mV. That comparison does not qualify the new mux transmitter; the complete certificate remains outstanding.

DLL experiments with stronger charge-pump branches reduce settled nominal
feedback error to 67 ps (8 times the original current) and 48 ps (16 times).
However, the respective control-copy errors reach 80 and 154 mV, exceeding the
50 mV limit. Neither candidate is promoted. A stronger control buffer is under
test. The original phase-error flag also remains inadequate: raw-clock window
prototypes improve sensitivity, but broader process, temperature, and slew
checks expose missed faults or invalid pulse cadence. These prototypes remain
separate from the canonical analog and PFD implementations.

The mux transmitter's fresh full/approximate RC pair passes with a maximum
edge difference of 1.72 ps and plateau difference of 9.18 mV. Receiver,
delay-line, and capture-core comparisons also pass; driver and DLL fixtures
are still needed for the complete six-fixture certificate.
