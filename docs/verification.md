# Validation map

Every runner archives decks, tool logs and JSON results under `build/`. Read
the current manifests instead of inferring success from an artifact's existence.

| Evidence | Location |
| --- | --- |
| Behavioral DDR, reset/restart, all 16 pair transitions | `build/rtl/summary.json` |
| DLL lock qualification and functional PHY assembly | `build/rtl/dll_control.log`, `phy.log` |
| Transistor-level fixed-supply electrical tests | `build/analog/<test>_<process>_<temperature>/` |
| Analog GDS, LEF, Magic layouts, DRC/LVS | paths in `build/layout/current.json` |
| TX, RX and PFD digital physical checks | `build/physical/{tx,rx,pfd}/summary.json` |
| GDS-based full distributed R/C networks | `build/extracted/{current,digital}.json` |
| Fast network candidate, explicitly approximate | `build/extracted/fast.json` |
| Nonlinear full/fast comparisons | `build/rc_validation/summary.json` |
| Extracted electrical tests | `build/analog_extracted/`; approximate tests in `build/analog_fast/` |
| Actual OpenPLL RTL/controller trace | `build/openpll/summary.json`, `clock.csv` |
| Optional imported physical DCO trace | `build/openpll/physical_summary.json` |
| Extracted complete-link waveforms and bit checks | `build/link/<case>/<fingerprint>/` |
| Aggregate extracted regression | `build/regression/summary.json` |
| Release decision with every missing/failed gate | `build/release/status.json` |

Behavioral models check logic and ordering only. The functional DLL measures a
period and schedules ideal phases; electrical DLL performance comes from the
transistor tests. The RTL matrix exercises all 27 clock/duty/skew combinations,
100 ps pp jitter and more than one million bits.

Driver benches check differential amplitude, common mode, polarity, transition
count and propagation delay after settling. Output eye centers are measured
between output crossings, accounting for propagation delay. Receiver benches
check ±100 mV decisions from 0.05 to 2.35 V common mode, keeping both input pins
within 0–2.4 V. Separate `--test receiver-rate` benches exercise the minimum
250 mV link swing at 420 MHz (840 Mb/s) with 100 fF output loading. They reject
missing clock edges and require both valid CMOS levels to persist for at least
two 200 ps margin intervals. DLL benches check acquisition, quarter-cycle phase, feedback
error and the error indicator. All use actual SKY130 process models at the three
requested temperatures. `--settled-start` solves DC bias at the fixed supplies
before reset and clock stimuli, matching the stable lab supply contract. The
Makefile uses this mode. Direct runner invocation without the flag also tests
a 1 ns supply/reference startup ramp; it is not a supply sweep.

RC extraction rereads GDS, restores public port indices from layout coordinates,
flattens it and extracts resistance, capacitance and coupling. Netlists retain
device and terminal parasitics. The exact resistor-only reduction eliminates
unobserved algebraic nodes by a Schur complement; capacitor and device nodes
are protected. The optional TICER pass additionally removes quick internal RC
nodes. Its circuit snapshots and comparison results are hashed separately.
The method is described in the [KLayout-PEX TICER documentation](https://iic-jku.github.io/klayout-pex-website/doc/doc.html#quick-nodes).

The link bench uses the physical TX/RX DDR macros and analog cores, two terminated
differential transmission-line pairs, pad capacitance, package inductance and
series loss. Parallel inputs arrive 250 ps after the preceding actual clock edge,
matching the upstream register timing in TX SDC. It decodes actual sampled two-bit outputs against the transmitted
sequence. A fixed preamble search allows startup latency without allowing dropped
words or arbitrary realignment during the payload. Qualified link runs include
the same 256 training cycles as the PHY RTL; explicitly shorter diagnostic
runs cannot establish startup performance.

The clock-generation boundary is partitioned: the link replays source clock
edges, with DLL phase characterized separately. `--dll-phase` can replay the
measured extracted DLL delay at the matching frequency and clock duty.
`make dll-clocks` generates those cases, including available OpenPLL trace
duties. A replay rejects phase evidence at another duty. It does not simulate PLL, DLL and link acquisition
as one monolithic transient. Imported physical DCO traces are fixed-code evidence;
repeating them does not establish closed-loop stochastic jitter performance.

`scripts/regression.py --list` prints the exact release matrix: 4096 nominal
extracted bits; 512 bits at each other process/temperature; timing stress cases;
±200 ps aperture shifts; and OpenPLL trace replay. `--case` supports diagnosis,
but a partial matrix cannot pass release. No run with `--diagnostic` qualifies.

Remaining release work must stay visible: uncompleted extracted tests, any failed
electrical corner, missing characterization, and unsupported clock evidence must
not be replaced by behavioral results. DRC/LVS are connectivity/manufacturability
checks, not proof of LVDS timing, input tolerance, mismatch or silicon yield.
