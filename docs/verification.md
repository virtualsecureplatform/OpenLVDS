# Validation map

## Extended native capture aperture

`scripts/extend_rx_aperture.py` extends the unchanged extracted capture model
from 20/200 ps to a 20/200/250 ps grid on both clock and data. The wider grid
contains 1,080 conditions across all five processes, 0/25/40 C, both clock
edges, both data polarities and setup/hold. It simulates only the 600 new
conditions. The original 480 conditions are reused only after independent
verification of their complete passing table and original endpoint seeds.
The fixed 1.8 V supply, 410 MHz stimulus, 20 fF public loads, published-pair
checks, 5 ps search resolution and 20 ps guard remain unchanged.

This extension addresses the restored coupled trace's 216.889 ps clock
slew. Capture closure hashes match between that trace and the ongoing
original aperture campaign; the extension does not substitute another RX
capture circuit. `prepare` may capture the immutable original model while
its campaign runs. That permits independent new simulations, but grants no
reuse or aperture admission from partial original results.

Each uncached point uses one individual P2 dispatcher lease. Two workers
share the existing six-engine budget, with no outer lease. Existing partial
outputs cannot be restarted. A failed boundary holds remaining work for
diagnosis. `assemble` requires all 600 new boundaries and the independently
verified original 480 before producing a table. It rechecks every failing,
passing and guarded witness, the entire original deck including supply,
load and maximum step, complete finite binary waveforms and exact exported
samples. The combined receipt binds witness paths and hashes from both
artifacts. `verify` regenerates the complete table; a pass flag, changed
model, missing original matrix or edited witness cannot admit the table.

The explicit `extend_rx_aperture.read_table` consumer returns a 20–250 ps
aperture receipt only after that verification. Existing consumers and
running producers retain their original 20–200 ps rules. Integrating the new
receipt with a later selected PHY/link profile remains a separate step;
neither table preparation nor a passing aperture alone qualifies a PHY.

Nine focused checks cover exact coverage/reuse, retained native fixture,
raw/export mismatch, altered supply/load/step, guarded boundaries, complete
parent admission, combined witness locations, foreign/edited receipts and
retry rejection. The full regression passes 1,446 tests without skips
(`build/rx-aperture-extension-full-tests.log`).

## Existing validation flows

Every runner archives decks, tool logs and JSON results under `build/`. Read
the current manifests instead of inferring success from an artifact's existence.
Digital hardening excludes intentional clock-delay cells from general buffering.
The final PFD netlist must connect REF/FB directly to its two clock pins and
UP/DN through matched native buf_8 drivers. Reset coincidence uses the buffered
outputs. Physical and release checks reject bypassed or asymmetric drivers.

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
| Published exact-byte macro library | `build/release/current.json` (`make release-library`) |
| Isolated OTA bundle release decision | `BUNDLE/release/status.json` (`check_release.py --bundle ...`) |

Behavioral models check logic and ordering only. The functional DLL measures a
period and schedules ideal phases; electrical DLL performance comes from the
transistor tests. The RTL matrix exercises all 27 clock/duty/skew combinations,
100 ps pp jitter and more than one million bits.

Driver benches check differential amplitude, common mode, polarity, transition
count and propagation delay after settling. Output eye centers are measured
between output crossings, accounting for propagation delay. Input/output edges
are paired in order from the first driven transition, with the initial DC
polarity and edge cadence checked. This distinguishes a valid delay longer than
one bit interval from inversion or lost transitions. Receiver benches
check ±100 mV decisions from 0.05 to 2.35 V common mode, keeping both input pins
within 0–2.4 V. Separate `--test receiver-rate` benches exercise the minimum
250 mV link swing at 420 MHz (840 Mb/s) with 100 fF output loading. They reject
missing clock edges and require both valid CMOS levels to persist for at least
two 200 ps margin intervals. DLL benches check acquisition, quarter-cycle phase, feedback
error and the error indicator. The standalone `verify_phase_detector.py` response
bench also rejects missed error cycles, multiple fault edges per reference cycle,
and fault highs shorter than 200 ps. A continuously asserted valid fault level
is accepted because it blocks lock directly. All use actual SKY130 process models
at the three requested temperatures. `--settled-start` solves DC bias at the fixed supplies
before reset and clock stimuli, matching the stable lab supply contract. The
Makefile uses this mode. Direct runner invocation without the flag also tests
a 1 ns supply/reference startup ramp; it is not a supply sweep.

RC extraction rereads GDS, restores public port indices from layout coordinates,
flattens it and extracts resistance, capacitance and coupling. Netlists retain
device and terminal parasitics. The exact resistor-only reduction eliminates
unobserved algebraic nodes by a Schur complement; capacitor and device nodes
are protected. The optional TICER pass additionally removes quick internal RC
nodes. Its circuit snapshots and comparison results are hashed separately.
The DLL comparison fixture loads PH0 and PH90 at 40 fF each, matching the
native transmitter launch loads in the electrical qualification bench. It
uses the same 200 ps separation between the 32-cycle precharge and detector
enable. A prior underloaded DLL fixture cannot supply this comparison.
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
The release checker compares each recorded configuration to the required case,
verifies the captured runner, circuit, deck and waveform hashes, and recreates
the current clock replay and DLL phase fingerprint. A nominal result cannot
satisfy another process, duty, skew, or clock-source case by changing its label.
It also checks independent extracted-topology audit reports and current OpenPLL
source and trace bindings.

Remaining release work must stay visible: uncompleted extracted tests, any failed
electrical corner, missing characterization, and unsupported clock evidence must
not be replaced by behavioral results. DRC/LVS are connectivity/manufacturability
checks, not proof of LVDS timing, input tolerance, mismatch or silicon yield.

The DLL electrical bench holds precharge for 32 complete clock periods and
then adds 200 ps before the enable transition. This separates the ideal
control source from a coincident clock breakpoint at non-integer periods.
The original 420 MHz, 55% duty case stopped at the enable source with a
sub-femtosecond timestep; the delayed-enable retry advances beyond that point.
Phase, tracking-error, and acquisition limits remain unchanged.

The phase-response runner now defaults to 120 ns settling followed by a 40 ns
measurement window, allowing the averaged indicator to settle. `--corners`
selects 105 process/temperature/offset cases; `--slew-corners` selects the 70
extreme-PVT cases with 20/200 ps and 200/20 ps reference/feedback edges. Feedback
source timing compensates the slew difference so the requested phase remains
the voltage-midpoint offset. The runner reads macro terminal names from the
captured library and supports the separate sense/filter ports for fault injection.
A startup-only fault or an incomplete settled window cannot qualify detection.

Release requires both complete extracted phase-fault reports: 105 uniform-slew
PVT cases and 70 extreme-PVT unequal-slew cases. The runner publishes hashed
current-report pointers after completion. Release validation checks every case,
current DLL/PFD/bias bindings, simulator and producer fingerprints, captured
files, and actual waveform response. It also verifies reference frequency and
requested input slew. A passed aggregate label cannot replace missing cases or
a valid measured fault response. Schematic reports cannot satisfy this gate.

Driver routing diagnostics must retain the extracted transistor finger geometry.
Replacing the driver with the hierarchical schematic also changes individual
MOS widths and body-model behavior. To isolate routing, the diagnostic shorts
only parasitic resistor elements and removes only parasitic capacitor elements;
all PDK device instances, including intentional resistor and MIM devices, remain.
An independent LVS audit checks this circuit against the physical schematic.
Captured clock/data replay simplification is bounded at 10 µV with both edge
counts and midpoint timing independently checked. Such replays remain diagnostics.

The stressed 32-bit link artifact `093b45fc9a1d` uses TICER approximate RC.
Its baseline replay directory named `full` means the unchanged baseline variant;
it does not mean an exact RC network. A separate exact-driver replay keeps the
original receiver/capture models to isolate the driver. This mixed-model test
cannot replace the six-fixture certificate or the complete qualified link matrix.

Current component receipts can be reconciled independently of historic batch
exit codes:

```sh
scripts/env.sh --ngspice python3 scripts/verify_component_evidence.py
```

This verifies exactly 90 distinct schematic/native driver, static-receiver and
rate-receiver PVT reports. It checks active circuit scope, extraction identities,
requirements, fixed-supply startup, simulator, producer/analyzer snapshots, deck
and waveform hashes, plus the driver's DC result. A shared case lock prevents
reading evidence while a producer rewrites it; active cases are reported as
running, never counted as passes. Shared locks use readable descriptors for NFS.
The output is `build/diagnostics/component_refresh/current_evidence.json`; exit
status is zero only when all 90 current proofs pass. Historical failed traces
and batch return codes are retained. This receipt covers components only and
does not replace the strict DLL, aperture, link or release checks.

The digital macro handoff can be checked before electrical release:

```sh
scripts/env.sh --ngspice python3 scripts/promote_phy_candidate.py build/diagnostics/phy_candidate/8f364c6a8fdabafb --check-netlists
```

This checks the selected TX, PFD and RX routed logical (`.nl.v`) and power-aware
(`.pnl.v`) netlists. Expanded bus pins must match the extracted macro interface;
cell types, logic terminals, wire declarations and continuous assignments must
agree between the two forms. Every cell's supply/body ties must be correct,
including the native two-supply-pin tap cell. Preflight writes only
`netlist_preflight.json` with `qualified_phy=false`; it cannot seal a package or
replace the current release pointer. Successful promotion rechecks these files
and packages both netlist forms alongside each digital GDS/LEF, with hashes of
the same validated bytes. All electrical, timing and release gates still apply.

Link payload decoding now uses the same public RX observation window as native
aperture characterization: +0.80 to +1.05 ns after each received rising clock
crossing, at 5 ps intervals. Both data bits must hold one legal value throughout
that window and VALID must stay high. Sampling at half a clock period could
instead observe the next early-publication update under duty/jitter stress.
The input setup/hold subtraction, extra 200 ps margin, analog sensitivity,
clock eye, pin limits, payload size and full link coverage are unchanged.
Reports include the public window and the first payload publication time; their
runner fingerprint rejects cached evidence from the preceding analyzer.

Downstream orchestration runs inside the pinned `/work/OpenLVDS` environment.
Ordinary child jobs execute the base image's `/usr/bin/python3` directly; jobs
requiring implementation tools enter the existing Nix shell with shell-quoted
arguments. They do not attempt to launch another Apptainer container from the
base image. Host-side command construction retains the pinned `env.sh` wrapper.
