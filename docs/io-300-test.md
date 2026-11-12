# OpenLVDS I/O macros: test guide

How the evidence behind `qualification_io_300.json` is produced, and how to
check the macros on silicon. Every command runs from the repository root;
tools come from the project container through `scripts/env.sh`.

## Reproducing the evidence

Run these in order. Each step refuses stale inputs, so a change to the
schematic, the layout generator or the contract means starting again from the
top.

| Step | Command | Produces |
|---|---|---|
| Layout, DRC, LVS, antenna | `make io-layout` | `build/layout/current.json` |
| KLayout DRC, density, electrical rules | `make io-signoff` | `build/io_300/signoff/current.json` |
| Parasitic extraction | `make io-extract` | `build/extracted/current.json` |
| Post-layout 15-corner benches | `make io-analog-extracted` | `build/io_300/analog_extracted/` |
| Cross-simulator, numerical and raw-RC comparisons | `make io-compare` | `build/io_300/analog*/` |
| Mismatch Monte Carlo | `make io-mismatch` | `build/io_300/analog_ngspice/` |
| Views and frozen candidate | `make io-publish` | `build/release_io_300/` |
| Reference integration top | `make io-ref-top` | `build/physical/io_ref/summary.json` |
| Fresh extraction of the published GDS | `make io-fresh-rc` | `build/release_io_300/fresh_rc.json` |
| Gate receipts | `make io-receipts` | `build/release_io_300/receipts/` |
| Release check | `make release-io-300` | exit status 0 only if every gate passes |

`make qualify-io-300` prints the state of every gate without failing.

Do not run `make io-layout` or `make io-extract` once the benches have
started. Magic numbers the extracted sub-nodes differently on every run, so a
new extraction is a new netlist and makes existing bench results stale.

## What each bench measures

All benches are in `scripts/verify_analog.py --contract io_300.json`.

| Bench (`--test`) | Stimulus | Pass criteria |
|---|---|---|
| `driver` | Both DC polarities, then two PRBS7 periods at 620 Mb/s into 100 ohm and 2 pF per pin | Levels, state-to-state imbalance, 20-80% edges, monotonic, ring, common-mode variation, thin-oxide stress |
| `receiver` | +/-100 mV at six common modes from 0.05 to 2.35 V | Correct decision at each, thin-oxide stress |
| `receiver-rate` | 250 mV at 290, 300 and 310 MHz, 100 fF load | Valid high and low pulse of at least 400 ps |
| `link` | PRBS7 through TX, the contract channel and RX; 4096 bits at tt/25 C, 512 elsewhere | Receiver-pin eye, Q valid window, zero bit errors, pin range, stress |
| `timing` | Receiver edges against input transition and load; RC charge of D and INP | Liberty tables and pin capacitances |
| `power` | Static, then toggling at 310 MHz | Supply and reference currents (reported, no limit) |
| `driver-mc`, `receiver-mc` | Local mismatch, 200 samples at tt/25 C and 50 at every other point | Mean plus three sigma inside the contract bounds |

The contract channel is 100 ohm differential, 0.1 and 1.2 ns delay, 1 ohm
series resistance, 2 pF and 1 nH at each pin, terminated in 100 ohm at the
receiver. The line is modelled as an LC ladder with 50 ps per section.

Xyce runs start from a 1 ns supply ramp. Benches that need the transmitter's
common-mode loop settled wait 1.5 us before stimulus. Mismatch runs use the
pinned ngspice and a solved DC start, with initial guesses for the
transmitter's common-mode loop.

ngspice runs differ from Xyce in two numerical details, both applied by
`scripts/run_ngspice.py`. A supply ramp is held at zero for its first 0.1 ns,
because ngspice 42 cannot take its first step when every source moves at time
zero. A run that aborts with "timestep too small" under Gear integration is
rerun once with trapezoidal integration, with the same mismatch seed, and
leaves a `numerics_retry.txt` beside its result. About one receiver mismatch
sample in 300 needs this.

Xyce step size follows the Newton iteration count under a fixed ceiling:
500 ps while only supplies and bias settle, then 10 ps under stimulus (5 ps in
the `refined` profile). Truncation-error step control is not used: on the
5 V devices' near-floating body nodes it shrinks the step until Newton fails,
at an unpredictable point in roughly one run in ten. Against
truncation-error-controlled runs that did complete, the 10 ps ceiling matches
edges within 1 ps, levels within 0.2 mV and common-mode variation within
2 mV. Overshoot spikes about 50 ps wide on 1.8 V nodes read about 15 mV low,
so the thin-oxide stress check subtracts a 20 mV guard from the 1.95 V limit.

## Gates

| Gate | Evidence |
|---|---|
| `model_compatibility` | Xyce against ngspice, schematic, tt/25 C |
| `numerical_refinement` | Baseline against refined Xyce tolerances, schematic, tt/25 C |
| `exact_rc_equivalence` | Reduced against unreduced extraction, tt/25 C |
| `native_drc_lvs_rc` | Magic full-rule DRC, Netgen LVS, extraction with resistance |
| `antenna_density_erc` | Antenna, KLayout DRC, density report, electrical rules |
| `analog_tx_rx_15pvt` | `driver`, `receiver`, `receiver-rate`, extracted, 15 points |
| `device_stress` | Thin-oxide terminal span in every extracted bench |
| `async_link_eye` | `link`, extracted, 15 points |
| `offset_and_mismatch` | `driver-mc`, `receiver-mc` |
| `timing_library_15pvt` | `timing`, extracted, 15 points; Liberty read by STA |
| `published_views_integration` | All views present and hashed; reference top signoff clean |
| `fresh_joint_rc_and_release` | Published GDS re-extracted to an equivalent netlist |

A receipt is `pass` only if every check in it is true and every file it read
still has the recorded hash. Editing a source listed in the candidate after
`make io-publish` invalidates the candidate.

## Bench measurements on silicon

Bias both macros with VDDIO 3.3 V, VDDD 1.8 V, VREF 1.2 V and one 35 uA sink
per IREF pin. Ramp supplies before applying data and allow a few microseconds.

Transmitter, 100 ohm across the pair at the probe:

1. Hold D low, then high. Record the differential and common-mode voltage in
   each state and their differences.
2. Drive PRBS7 at 600 Mb/s. With a differential probe measure 20 to 80
   percent rise and fall times and overshoot. With the two outputs summed
   measure the common-mode peak-to-peak variation.
3. Note the fixture capacitance per pin. Compare edge rate against the
   contract only at 2 pF, or correct by about 70 ps per picofarad.

Receiver, 100 ohm across the pair at the pins:

1. Apply +/-100 mV DC at common modes of 0.05, 0.2, 0.6, 1.2, 1.8 and 2.35 V
   and check Q. Sweep the differential slowly in both directions to find the
   trip point; the mean of the two is the input offset.
2. Apply a 250 mV, 300 MHz differential clock at 1.2 V common mode and measure
   the Q pulse widths with the intended load.

Loopback: drive the transmitter with PRBS7, connect it to the receiver through
the intended channel and termination, and count errors on Q with a
self-synchronizing checker such as the one in `examples/openlvds_io_ref_top.v`. The
macros have no clock recovery, so sample Q with a clock whose phase you
control.

Supply currents to expect are in the published electrical tables.
