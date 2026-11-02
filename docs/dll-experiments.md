# Pulse-area DLL experiments

The experiment compares a repaired charge pump and NMOS control follower with
an averaged-PFD current-mirror OTA integrator. Both use independently averaged
UP/DN signals for phase and activity monitoring. Active analog and transmitter
macros remain unchanged until qualification; the readiness controller now includes
a conservative acquisition guard. Supplies remain fixed at 3.3/1.8 V,
with VREF 1.2 V and one external 35 µA reference per standalone DLL fixture.
The clock range is 390/400/410 MHz, and temperatures are 0/25/40 °C.

## Running work

The corrected architecture campaign is
`build/diagnostics/dll_architecture/6d99d42cf3eb5d31`. It contains captured
sources, libraries, producer files, stimulus, hashes and a durable task state.
Inspect live service and queue health on the host with:

```sh
python3 scripts/manage_dll_jobs.py status
```

This detects a dead manager or a stale heartbeat instead of trusting a cached
`running` flag. The legacy manifest/task listing remains available with:

```sh
./scripts/env.sh --ngspice python3 scripts/dll_campaign.py status \
  build/diagnostics/dll_architecture/6d99d42cf3eb5d31
```

The supervisor runs on the host, with Apptainer workers, under the independent
user systemd service `openlvds-resident.service`. All six existing simulations
were moved into its cgroup without restarting them. Detached processes alone
were insufficient because they still belonged to the tool/tmux scope.
Start the watchdog independently of a terminal with:

```sh
python3 scripts/manage_dll_jobs.py start
```

The supervisor, OTA characterization, receiver aperture characterization and
native qualification share `build/diagnostics/dll_architecture/.supervisor.lock`.
Waiting programs do not launch additional transients. An exclusive lease serializes
campaigns. At the user's request on 2026-10-30, the comparison supervisor runs
six cases concurrently; other campaigns retain their four-case limit. The four
original simulations were preserved when the supervisor restarted. Do not change a
queued campaign's captured producer dependencies or the pinned simulator.
Prepare another generation when a circuit, stimulus or measurement changes.

The watchdog restarts crashed coordinators. The comparison manager adopts live
workers using PID/start-time/boot identities. A missing worker's incomplete
outputs are archived and retried at most twice; incomplete traces never count
as circuit passes. Dependent coordinators are launched sequentially, avoiding
a lease handoff that could launch extra jobs while orphan workers remain alive.
Logs, PID records, heartbeat and the controlled recovery-test report are under
`build/diagnostics/resident_jobs/`. Stop all managed jobs explicitly with
`python3 scripts/manage_dll_jobs.py stop`.
User lingering is enabled so logout does not terminate the user service. The
unit is transient; after a host reboot, start it again with the command above.

The recovery test killed only the comparison manager: the watchdog replaced
it and all six native ngspice PIDs survived unchanged. The exact cause of the
earlier simultaneous process loss was not established; the shared-session
lifecycle weakness and stale-state recovery are fixed. A host reboot still
requires restarting interrupted SPICE transients; there is no checkpoint.

The former `2c89de68294cda33` campaign has a rejected loop fixture with a
duplicated bias generator. Its unaffected monitor waveforms were verified and
reanalyzed in the corrected campaign. Interrupted startup traces are retained
for diagnosis and never counted as complete qualification.

## Physical candidates

W8/C4 has now passed zero-error DRC and strict LVS in
`build/diagnostics/dll_layout/c465a14562c2ff4f`. Exact extraction and independent
RC audit run under `openlvds-w8c4-rc.service`. The separate
`openlvds-w8c4-advance.service` waits for a passing audit, prepares a new
qualification generation, and registers it with the resident watchdog.
Its source is the unchanged W8/C4 snapshot from the completed architecture
campaign (51 passing and three failing cases).

The resident configuration defers the old CP qualification. New qualification
workers use six shared slot locks, reserving four slots for the frozen receiver
aperture producer until it completes. This allows two new OTA workers alongside
the existing RX work without modifying that producer or its provenance.
The current artifact path is published in
`build/diagnostics/resident_jobs/config.json` once preparation succeeds.

New native campaigns default to `--stage screen`: SS monitor/acquisition cases
precede TT and FF, with bulk work held for stability assessment. `--stage full`
requires `--stability` pointing to a passing measured report for the same exact
model inputs, with at least 60 degrees estimated phase margin and 6 dB gain
margin. The report is not yet available; native operating-point, delay-gain,
AC transfer and recovery measurements remain necessary.

The AC backend uses the original verified engine without changing transient
producer provenance. Its complex-data parser and measured-G/Y margin estimator
have unit coverage, and the backend passes a native RC reference. These checks
are tool validation and are not W8/C4 stability evidence.

`measure_dll_stability.py` now measures PFD area gain from the native ±50 ps
cases, signed delay sensitivity from ±10 mV CTRL perturbations, and native AC
G/Y at both static clock states. The averaged model uses conservative
one-reference-cycle latency. It validates predicted control-step amplitude and
90% settling time against separate native 400→390/410 MHz steps, applied only
after 1700 ns to avoid mixing startup drift with the step response. Both errors
must remain within 25%. All original qualification timing limits remain intact.

The advancement service waits for the early extracted screen, runs these
measurements, verifies the report and source hashes, and only then requests full
matrix expansion. After a passing full matrix it repeats the model assessment
over all 15 PVT points. Failed model or electrical gates stop advancement for
diagnosis; no CP fallback is selected. A passing all-PVT model only marks the
candidate ready for staged bundle integration, not PHY release. The measurement
and validation tools have been implemented but W8/C4 native measurements have
not yet run. There are 117 passing unit tests at this milestone.

The readiness guard adds `MIN_ACQUIRE_CYCLES=615` to DLL control, preserving
32 precharge cycles, 64 good cycles and public ports. Acquisition and good-cycle
counters run concurrently and reset qualification on faults. The PHY retains
its 256-cycle warmup after lock. Full RTL coverage passes 54 cases and 2,373,588
bits; 112 unit tests pass at this milestone.

| Candidate | Layout and audit directory | Exact analog network hash |
| --- | --- | --- |
| `ota_w4_c8` | `build/diagnostics/dll_layout/087c477aad210a72` | `3502faf1b5c1` |
| `cp_b2_c4` | `build/diagnostics/dll_layout/deb4cf2965966128` | `62713ea94c5a` |

The common eight-terminal PFD is under
`build/diagnostics/pfd_area_physical`, with network hash `11fa96b45bbb`.
`scripts/dll_candidate_library.py` checks physical scope, GDS, independent audit
and extracted-network hashes before binding its ports by name. Neither this
assembly nor its unqualified fast model replaces an active manifest.

Native extraction splits CTRL/VCOPY routing labels into `.tN` terminals. The
measurement observes every storage-capacitor plate, chooses a largest-unit
plate as the primary probe, and checks the worst storage-copy error or ripple.
`scripts/spice_probes.py` verifies all hierarchical probe names before queuing.

The isolated matched serializer is under `build/diagnostics/tx_buffer4_physical`.
Its direct-output build and exact RC audit pass. Earlier retries remain in the
physical directory's `history/` and `runs/` folders. Its source remains under
`rtl/experiments/`; no active serializer has been replaced.

## Qualification queues

Prepared native suites are:

| Candidate | Artifact |
| --- | --- |
| `ota_w4_c8` | `build/diagnostics/dll_qualification/34f44f4cfa4d40d4` |
| `cp_b2_c4` | `build/diagnostics/dll_qualification/a62222a02a048ab0` |

Each manifest has 313 cases. The suite waits for all three architecture-screen
corners to pass, then acquires the simulator lease. A failed or skipped
prerequisite rejects dependent cases. `state.json` records progress and each
task has a hash-bound `summary.json` and waveform. The suite can resume with:

```sh
./scripts/env.sh --ngspice python3 scripts/qualify_dll_candidate.py run \
  build/diagnostics/dll_qualification/34f44f4cfa4d40d4 --jobs 4
```

The fixed-frequency DLL tests retain the 1200–1500 ns settled window and then
omit one clock pulse. Following its absence through PH0/PH90/PH180/PH270/FB
checks causal delay and rejects whole-cycle phase aliases. Frequency-step and
clock-loss/rearm cases also check the restored clock and unwrapped delay.
Full/fast comparisons retain 20 ps crossing and 20 mV plateau tolerances.
Passing this DLL suite does not qualify the complete PHY or its approximation.

The full-RC capture characterization artifact is
`build/characterization/rx_aperture/e9ca7d2f2ae6d61b`. Its 480 boundaries cover
setup/hold, both capture edges, both data polarities, and independent 20/200 ps
10–90% clock/data slews at every PVT point. The search uses a ±800 ps bracket,
5 ps resolution, 20 ps guard and 10 ps upward rounding. It checks the complete
published pair and valid signal rather than private sampler node labels.
Its `table.json` appears only after the matrix finishes.

`simulate_link.py` automatically discovers a complete current aperture table,
or accepts `--aperture-table PATH`. Qualified link evidence checks its circuit,
requirements, simulator, captured producer and failed/passing/guarded boundary
witnesses. The measured per-corner setup/hold bounds are subtracted before
requiring the additional 200 ps margin. `--diagnostic` permits the legacy
200/80 ps estimates when no table exists; those results cannot release.
Qualified link runs also require measured capture input slews within the
characterized 20–200 ps 10–90% domain.

The OTA offset screen, steady loop tests and omitted-pulse checks do not alone
establish phase margin or noise performance. Candidate selection and promotion
also require stability assessment, the complete six-fixture RC comparison,
and the full 45-case extracted link matrix. The work does not make an MTBF,
mismatch/yield, pad/ESD or assembled-PHY-GDS qualification claim.

## Staged PHY validation

`stage_phy_candidate.py QUALIFICATION` writes isolated full/fast libraries under
`build/diagnostics/phy_candidate`. It changes no active extraction pointer.
Both libraries retain the audited candidate DLL, pulse-area PFD and matched
buf_4 serializer. The loader checks captured circuit scopes, physical reports,
qualification producers and requirements before use.

Run the same six nonlinear RC fixtures and then the link matrix on that bundle:

```sh
scripts/env.sh --ngspice python3 scripts/validate_fast.py --bundle BUNDLE --resume --jobs 6
scripts/env.sh --ngspice python3 scripts/simulate_link.py --bundle BUNDLE --fast-rc --diagnostic --settled-start --dll-phase --bits 32 --process ss --temperature 0 --mhz 410 --duty .55 --skew-ps 100
scripts/env.sh --ngspice python3 scripts/regression.py --bundle BUNDLE --fast-rc --jobs 6
```

The certificate is `BUNDLE/rc_certificate.json`; the matrix report is
`BUNDLE/regression/summary.json`. Per-case waveforms remain hash-separated under
`build/link`. Certificate references may reuse completed traces only when their
instantiated circuit, fixture, requirements and simulator evidence match.
New simulations use the shared six-slot pool, preserving the four reserved RX
workers while the frozen capture characterization is active.

Staged link phase comes from the exact native qualification case at the requested
process, temperature, frequency and duty, with fresh waveform reanalysis. The
captured OpenPLL mean duties are additional TT qualification inputs when outside
the nine nominal clock/duty combinations. As in the existing link partition,
the settled DLL phase scales with the captured clock period; this does not prove
the DLL's response to individual captured jitter edges.

The advancement service runs these steps only after W8/C4 native electrical
and all-PVT stability qualification. The non-diagnostic matrix waits for the
complete 480-boundary capture table. A passing matrix still requires the
remaining analog operating-range and release checks before promotion; native
readiness and limiting-corner recovery now precede staged validation as below.

## Native recovery and readiness

`qualify_dll_recovery.py QUALIFICATION --stability ALL_PVT_REPORT` selects the
lowest measured phase margin, lowest gain margin and longest predicted settling
time. The union of those corners and SS/0 °C, TT/25 °C and FF/0 °C must pass
native 400→390/410 MHz steps and clock-loss/rearm. Matching completed cases from
the original native matrix are reanalyzed; missing limiting-corner cases run
with the same full-RC library, loads and measurement limits. The report lives
under `QUALIFICATION/recovery` and binds its source model and native traces.

`qualify_dll_readiness.py QUALIFICATION --stability ALL_PVT_REPORT --recovery RECOVERY_REPORT`
replays every native all-PVT frequency-step clock and BAD waveform through the
actual `openlvds_dll_control` RTL. It retains BAD transitions between reference
edges. At each lock assertion, the preceding 100 ns must pass phase, cadence,
quiet-BAD and every-storage-plate checks. Every locked reference sample also
checks feedback and quarter-phase error, clock activity and the BAD level.

Additional native loss cases at the fixed and limiting corners run to 4700 ns.
Their clock interruption is 2200–2300 ns, after initial lock can occur. The
clock-ready contract deasserts at 2210 ns and returns at 2300.1 ns. The replay
checks lock before loss, clearing during loss, a new acquisition guard, and
lock after recovery. Native detector-enable commands retain the fixture's
200 ps propagation partition after the controller's 32-cycle precharge; the
replayed controller must issue its corresponding edges at 85 and 2380 ns.
This is RTL replay across an explicit analog command partition, not a
metastability or assembled controller-GDS qualification.

The advancement workflow runs both gates before staged PHY validation. Their
production W8/C4 results remain pending. The replay backend passes actual RTL
tests for startup, short/asynchronous BAD events, later BAD faults, late clock
loss/rearm and rejection of unsafe phase even when BAD is optimistic.

## Further exact resistor elimination

The full W8/C4 extraction contains 95,814 resistor-graph nodes after the original
degree-4 reduction. `exact_rc_candidate.py` eliminates additional internal
resistor-only nodes by a positive-conductance Schur complement. It preserves
every capacitor/device statement, their terminal names, and every public port.
It is separate from the TICER capacitance approximation.

The independent numerical witness uses sparse Dirichlet solves on both complete
resistor graphs, with four deterministic clamped-terminal patterns. It compares
currents at every protected resistor terminal and checks solver residuals.
The result supplements analytic and small-network complex-admittance tests;
it does not replace the native transient comparisons or electrical matrix.

The analysis environment resides within OpenLVDS:

```sh
uv venv --python /usr/bin/python3 build/tools/exact-rc-venv
UV_CACHE_DIR=build/cache/uv uv pip install --python build/tools/exact-rc-venv/bin/python --index-url https://pypi.org/simple -r scripts/exact_rc_requirements.txt
build/tools/exact-rc-venv/bin/python scripts/exact_rc_candidate.py build/diagnostics/dll_layout/c465a14562c2ff4f --degree 8
scripts/env.sh --ngspice python3 scripts/benchmark_exact_dll.py NEW_LAYOUT --reference ORIGINAL_QUALIFICATION
```

The candidate retains the original physical GDS and receives a new independent
topology audit and exact-netlist hash. Its manifest captures the reduction
producer, sparse-solver binaries, source evidence and numerical witnesses.
The native benchmark preserves the original SS/0 °C 0/+50 ps fixtures except
for their library include. It checks 20 ps crossings, 20 mV plateaus and every
CTRL storage plate. Timing ratios exclude waiting for a shared simulator slot.
Both comparisons must pass before selecting the profile for a fresh native
qualification campaign; the benchmark cannot qualify a PHY.

`advance_ota_candidate.py --layout NEW_LAYOUT` can run the complete workflow on
an already audited alternate layout. Changing profiles clears the previous
profile's stage and stability pointer. Restarting the same workflow reuses
verified current stability evidence; failed or damaged evidence is retained
for diagnosis rather than overwritten.

The resident watchdog binds each OTA coordinator to its artifact. A profile
change retires the old coordinator by interrupting only its Python main thread,
allowing the executor to finish already submitted native work. A durable request
prevents a second interrupt during cleanup. The new artifact has a distinct
coordinator record; the same six native slots continue to protect the RX workers.


## Monitor loading repair and source-specific screen

The physical W8/C4 monitor misses ±150 ps faults at SS/0 °C and +150 ps at
TT/25 °C; its SS/0 °C +300 ps response is too late. The original qualification
window and voltage thresholds remain unchanged. `repair_dll_monitor.py` compares
unloaded baseline, baseline with captured extracted coupling capacitances, and
repaired devices with the same captured loads. It scales monitor resistors by
1/4, averaging capacitance by four and comparator branch widths by four.
The OTA and CTRL storage remain unchanged. This tests a loading hypothesis;
it omits distributed resistance and extracted device junction geometry.

After a passing proxy, build and independently audit a new layout. Before native
qualification, prepare a separate architecture screen of that exact source:

```sh
scripts/env.sh --ngspice python3 scripts/screen_repaired_dll.py prepare CANDIDATE_SOURCE --reference ORIGINAL_QUALIFICATION --layout EXACT_REFERENCE_PROFILE
scripts/env.sh --ngspice python3 scripts/screen_repaired_dll.py run NEW_SCREEN --jobs 2
scripts/env.sh --ngspice python3 scripts/advance_ota_candidate.py --layout NEW_AUDITED_LAYOUT --screen NEW_SCREEN
```

The three-corner architecture screen uses native-finger schematic analog devices
including the delay line, extracted PFD/bias, the unchanged startup/load fixture
and 1200–1500 ns loop criteria. All workers use the six-slot project lease.
Source bytes, libraries, fixtures, simulator and producer hashes are captured;
qualification independently rechecks each waveform. This evidence is diagnostic:
the new GDS and full native matrix must pass separately. An explicitly held
candidate cannot silently resume through advancement; a new artifact retires
the previous OTA hold and cached stage without enabling CP or changing RX.

## Correlated OTA operating points

After native electrical and all-PVT model qualification, run:

```sh
scripts/env.sh --ngspice python3 scripts/ota_operating_points.py QUALIFICATION --stability ALL_PVT_REPORT --jobs 6
```

The tool takes observed common mode, CTRL and UF−DF from each native loop and
late frequency-step scoring window. It guards each correlated point by ±20 mV
common mode and ±10 mV CTRL, rather than sweeping a cross product of unrelated
corner extremes. Six perturbation slots measure gain at zero and at the actual
input difference. Both gains must exceed 1 µS, input offset must stay below
10 mV, and every thin-device terminal pair must stay within 1.95 V. Thick-oxide
input/tail devices are treated separately. Fixed supplies and the single 35 µA
reference remain unchanged. These native-finger schematic checks complement
the extracted loop; they do not establish mismatch/yield or general tapeout
stress qualification.


## Staged release evidence

The staged checker preserves the active release status and writes to
`BUNDLE/release/status.json`:

```sh
scripts/env.sh --ngspice python3 scripts/check_release.py --bundle BUNDLE --stability ALL_PVT_REPORT --recovery RECOVERY_REPORT --readiness READINESS_REPORT --ota-operating-points OPERATING_REPORT
```

It reconstructs both tested libraries from the audited physical inputs, checks
15-port OTA topology without a control-copy branch, and verifies the complete
native case coverage independently of the saved success flags. Every fixture is
reconstructed to preserve loads, scoring windows, supplies, probes and the one
reference generator. Every native waveform is remeasured; all ten full/fast DLL
comparisons are recomputed. Model, recovery, readiness and OTA reports must share
the same native candidate and selected model/recovery inputs.

The common checks still require scoped schematic/extracted driver and receiver
characterization, DC driver levels, current RTL/OpenPLL evidence, independent
RC audits, the complete six-fixture certificate and every case in the 45-case
link matrix. The candidate PFD-area and buf_4 physical policies use their archived
inputs; inactive CP/copy and raw-clock-qualifier checks do not substitute for
candidate-specific native evidence. A checker pass does not itself promote files.


## Candidate RTL assembly

The staged 15-terminal analog macro and 8-terminal PFD use
`rtl/experiments/openlvds_dll_core_area.v`; the canonical development wrapper
still has the preceding qualifier connections. `verify_candidate_rtl.py` builds
an isolated source snapshot with this wrapper, the captured buf_4 TX sources,
matching functional models and the current controller/top-level ports:

```sh
scripts/env.sh --tools --ngspice /usr/bin/python3 scripts/verify_candidate_rtl.py BUNDLE
```

Named instance connections are checked against the characterized SPICE core.
Interface elaboration uses the actual archived PFD declaration and 15-port
analog blackbox. The full 54-case generic/native regression, DLL controller and
PHY assembly must pass. The staged release checker verifies the source snapshots,
tool hashes, case logs and bit counts separately from the native electrical gates.

Staging retains the same exact shared bias in both electrical views. The fast
baseline is normalized before driver/RX closure protection, avoiding a silent
replacement of a separately approximated bias during the DLL overlay. The
complete six-fixture comparison still qualifies the resulting fast view.


## Exact-byte local release promotion

After all staged release checks pass, `promote_phy_candidate.py BUNDLE` repeats
them from their selected proofs before writing a package. It preserves the exact
tested full/fast libraries, copies eight macro GDS/LEF pairs and matching source
files, and validates each LEF pin set against extraction. Package contents receive
hashes; an existing package cannot be overwritten with changed bytes. The current
pointer is replaced only after packaging and source revalidation complete, with
the preceding pointer retained in the release history.

```sh
scripts/env.sh --ngspice python3 scripts/promote_phy_candidate.py BUNDLE
scripts/env.sh --ngspice python3 scripts/released_phy.py inspect
scripts/env.sh --ngspice python3 scripts/released_phy.py check
scripts/env.sh --ngspice python3 scripts/released_phy.py link --fast-rc --settled-start --dll-phase
```

`make release-library` locates the published libraries, GDS/LEF files and matching
sources; `make release-current` rechecks the published proof selection. The
schematic is `PACKAGE/source/analog/openlvds.spice`. The RTL snapshot contains the
15/8-port assembly and captured buf_4 implementation. Release packages live under
`build/release/packages/`; native waveform evidence remains referenced within
the OpenLVDS workspace. This is a local macro release, not an independently
exported evidence archive or an assembled PHY GDS. The canonical development
flows remain available for subsequent experiments. No package is published while
any required electrical or link gate is missing or failed.


## Early native static monitor probes

After physical audit, an immutable static monitor fixture can diagnose the real
layout while source-specific loop screens are still running:

```sh
scripts/env.sh --ngspice python3 scripts/probe_native_dll.py QUALIFICATION phase_ss_0_150ps
```

The helper accepts full-RC phase/activity cases only, holds the native campaign
lease, and delegates to the unchanged qualified-fixture executor and shared SPICE
slots. It records a diagnostic request without changing campaign state or claiming
architecture, model or PHY qualification. A completed unchanged case can be
rechecked and reused by the later campaign. Loop and approximate fixtures are
rejected by this early-probe entry point. This is particularly useful when actual
new-layout capacitance differs from the older loading used in a schematic proxy.


Independent architecture provenance checks bind the screened source bytes to the
physical candidate before native registration and at final release. They verify
source-specific screen producers and their archived copies alongside the shared
campaign dependencies; a changed helper or candidate source cannot inherit the
previous screen's success.


## Native monitor diagnosis and local routing

For a completed native phase fixture, inspect comparator terminals at the
measured fault operating point without replacing extracted devices or R/C:

```sh
scripts/env.sh --ngspice python3 scripts/diagnose_native_monitor.py QUALIFICATION phase_ss_0_150ps --stage dc
scripts/env.sh --ngspice python3 scripts/diagnose_native_monitor.py QUALIFICATION phase_ss_0_150ps --stage transient
```

The DC diagnostic adds test ports to clamp UF, DF and CTRL to their measured
120–160 ns means and removes the pulsed PFD stimulus. It diagnoses equilibrium;
it cannot establish fault timing. The transient retains the original native
fixture and adds actual extracted terminal probes. Optional `--stop-ns 320` or
`600` creates a separate diagnostic while retaining the original 120–160 ns
phase measurement. Both stages bind the native manifest, trace, report, library
and producer hashes. Their reports explicitly exclude PHY qualification.

A layout-only alternative keeps each comparator's O/OB/L/T wiring inside its
own child island, separate from the passive network and output logic:

```sh
scripts/env.sh --tools --ngspice python3 scripts/layout_dll_candidate.py CANDIDATE_SOURCE --local-comparators
scripts/env.sh --tools --ngspice python3 scripts/dll_candidate_rc.py NEW_LAYOUT
```

The generator creates a new source-hashed layout directory and runs DRC and
strict LVS. Extraction/audit and new immutable native fixtures follow separately.
Source equality allows reuse of a matching schematic screen only; previous
native electrical results never qualify the new physical network. Select the
layout only after its native fault, quiet and loop checks pass.


## Isolated internal-Q-reset PFD physical experiment

The wide-range capture diagnosis compares the existing PFD with a separate
physical implementation whose reset coincidence senses the flip-flop Q outputs
before buf_8 output delay. Existing sources and policies remain unchanged.

```sh
scripts/env.sh --tools --ngspice python3 scripts/harden_qreset_pfd.py --artifact-dir build/diagnostics/pfd_qreset_physical_v1
scripts/env.sh --tools --ngspice python3 scripts/digital_candidate_rc.py build/diagnostics/pfd_qreset_physical_v1
scripts/env.sh --ngspice python3 scripts/probe_pfd_physical_candidate.py build/diagnostics/pfd_qreset_physical_v1 --reference build/diagnostics/pfd_capture/b65a8cceadd819c0
```

Choose a fresh physical artifact directory for a new build. The wrapper retains
the preceding policy's rejection and independently applies the explicit
`pulse-area-q-reset` structural policy. DRC/LVS, unchanged archived inputs,
direct clocks, separate buffered outputs, high-tied data and reset/enable wiring
remain required. The source and producer archive are included in the physical
evidence. The standard RC extraction performs an independent connectivity audit.

The native probe requires those audited physical artifacts and the same analog
loading, bias, simulator and immutable −850/+850/0 ps reference fixtures. Its
adapter follows actual extracted port order. The PFD is native extracted GDS;
the DLL analog/delay remain native-finger schematics for this isolated component
comparison. It checks pulse-area direction over 60–80 ns, not closed-loop lock,
monitor fault timing or full-PHY readiness. Near-zero activity, full static
monitor windows, PVT, acquisition and all release gates must still pass before
this PFD can replace the previous implementation.


The internal-Q-only physical change failed the −850 ps control. The subsequent
single-AOI experiment has its own source, structural policy and physical build:

```sh
scripts/env.sh --tools --ngspice python3 scripts/harden_fast_reset_pfd.py --artifact-dir build/diagnostics/pfd_fast_reset_physical_v2
scripts/env.sh --tools --ngspice python3 scripts/digital_candidate_rc.py build/diagnostics/pfd_fast_reset_physical_v2
scripts/env.sh --ngspice python3 scripts/probe_pfd_fast_reset.py build/diagnostics/pfd_fast_reset_physical_v2 --reference build/diagnostics/pfd_capture/b65a8cceadd819c0
```

Here a22oi_4 with one input tied high implements
`clear_b = !(raw_up & raw_dn | !(RESET_N & PD_ENABLE))`. Only the Q-to-reset
path crosses the single AOI gate; the disable NAND lies outside that critical
path. The wrapper retains the preceding policy rejection and labels the actual
new topology `pulse-area-fast-reset`. Native probes reuse the source-bound port
adapter and preserve the matched analog loading, supplies and stimulus. Physical
checks pass, but native capture and acquisition have not yet been established.


After the physical capture controls complete, prepare and run the matching
three-corner loop screen:

```sh
scripts/env.sh --ngspice python3 scripts/screen_fast_reset_dll.py prepare build/diagnostics/pfd_physical_capture/6562211b6d43fb89
scripts/env.sh --ngspice python3 scripts/screen_fast_reset_dll.py run NEW_SCREEN --jobs 3
```

The source archive updates the PFD's SPICE definition to the single-AOI circuit
and checks that every analog device, bias and wrapper connection is unchanged.
The library retains the actual PFD GDS extraction and captured bias, while
analog/delay devices remain native-finger schematics. The three original
architecture fixtures retain their supplies, 32-cycle preset, loads and
1200–1500 ns scoring. Preparation and cached preparation print the artifact
path. Execution reanalyzes the capture waveforms and waits for complete controls
with correct large-offset polarity. A missing control or changed source, fixture,
producer or archive cannot dispatch the long loop cases. The screen remains
diagnostic; fresh integrated GDS/native DLL and all release gates are required.


## Preserve an unchanged analog macro when updating only the PFD source

The proposed source now contains the single-AOI PFD definition. The existing
analog GDS can be rebound only after proving the update is confined to that
unrelated definition:

```sh
scripts/env.sh --tools --ngspice python3 scripts/rebind_dll_pfd_source.py build/diagnostics/dll_layout/schur_6ce2c5e21bf17f36 build/diagnostics/dll_architecture/0ca8225b328ecaa1/inputs/ota_w8_c4.spice
```

The tool rejects any other source/global change, altered PFD interface, duplicate
definition or changed flattened analog schematic. It verifies the parent's
source, GDS, extracted network, ports and RC audit, then reruns strict RC
connectivity LVS for the unchanged macro under the new source binding. A new
directory retains the prior source, proposed source, flattened scope, producer
archive and binding receipt. GDS and extracted network hashes must remain
identical. Electrical results and qualification are never transferred; the
combined DLL with the new PFD requires fresh native evidence. Changes to analog
devices or wiring require new layout and extraction.


## Combined physical PFD and analog monitor probes

Prepare the combined source-bound native candidate with explicit physical PFD
selection. Assembly validates the declared topology and both physical audits:

```sh
scripts/env.sh --ngspice python3 scripts/qualify_dll_candidate.py prepare --layout build/diagnostics/dll_layout/pfd_bind_1583499260541bb4 --pfd build/diagnostics/pfd_fast_reset_physical_v2 --screen build/diagnostics/dll_architecture/0ca8225b328ecaa1 --variant ota_w8_c4
scripts/env.sh --ngspice python3 scripts/probe_native_dll.py build/diagnostics/dll_qualification/1d201e9ed2f89f56 phase_ss_0_150ps phase_ss_0_0ps phase_ss_0_-150ps --jobs 3
```

Static probes retain the native full-RC fixtures and original scoring windows.
Up to three workers share the global six-slot budget and one exclusive native
campaign lease. Duplicate requests, approximate RC and loop fixtures are rejected
before dispatch. Each case records its producer, manifest and result hashes;
these diagnostic requests cannot mark the complete campaign or PHY qualified.
The three architecture loops run independently. Full campaign expansion still
requires their success and the measured stability gate.


## Isolate RX public-output degradation

```sh
scripts/env.sh --ngspice python3 scripts/probe_rx_publication.py prepare build/characterization/rx_aperture/e9ca7d2f2ae6d61b
scripts/env.sh --ngspice python3 scripts/probe_rx_publication.py run build/diagnostics/rx_publication/dd89f11b1af99f29 --jobs 1
```

The six diagnostic cases reuse the original +800 ps setup endpoint for rising
clock/rising data at SS/0 °C (20 ps clock), TT/0 °C (200 ps clock), and a
passing FF/0 °C control (200 ps clock), all with 20 ps data slew. Each has the
original 20 fF external output load and a separate zero-external-load control;
VALID loading stays unchanged. Actual extracted output-stage drain/source,
gate and local supply terminals are saved for three successive stages of both
data outputs and VALID. Resistive connectivity identifies related terminals;
it never collapses the simulated network or modifies transistor geometry.

Preparation verifies original waveform witnesses, saves unchanged native RC,
and archives its producer dependencies. Each result reports original-window
public output measurements, internal voltage limits and difference from its
source public limits. Cached results are remeasured and changed inputs are
rejected. All execution uses the global six-slot budget and one diagnostic
coordinator lease. The zero-load comparison is diagnostic only; the 20 fF
qualification requirement and 0.36/1.44 V thresholds remain unchanged.


After starting the three SS seed probes, queue static expansion separately:

```sh
scripts/env.sh --ngspice python3 scripts/continue_native_static.py build/diagnostics/dll_qualification/1d201e9ed2f89f56 --jobs 3
```

This coordinator waits on the same native campaign lease. It then requires all
three seed summaries to pass, verifies deck/raw/export hashes, and remeasures
all three waveforms. It also checks the actual architecture PFD/bias binding.
Missing, failed or changed evidence holds expansion. Only the remaining 18
full-RC static fixtures at SS/0 °C, TT/25 °C and FF/0 °C dispatch; original
windows, supplies and ±50/±150/±300/0 ps coverage are unchanged. All workers
use global SPICE slots. The separate follow-up record is diagnostic and never
marks the full campaign, architecture screen or complete PHY qualified.


## Native RX output-drive repair experiment

The SS publication/load controls justify strengthening only the public data
drivers. Candidate `rtl/experiments/openlvds_ddr_rx_buffer4.v` retains the sampling
and publication logic and falling-edge `inv_1`/`dfrtp_1` path. Two explicit
retained `buf_4` drivers replace automatic `buf_1` data drivers; VALID retains
an explicit `buf_1`. The generic RTL branch uses direct assignments. It changes
no pipeline latency, sampling edge, public port, load requirement or score.

```sh
scripts/env.sh --ngspice python3 scripts/verify_rx_buffered_rtl.py
scripts/env.sh --tools --ngspice python3 scripts/harden_rx_buffer4.py build/diagnostics/rx_buffer4_physical_v1
scripts/env.sh --tools --ngspice python3 scripts/rx_candidate_rc.py build/diagnostics/rx_buffer4_physical_v1
```

The isolated hardener uses the captured RX flow configuration with archived
candidate/reset/blackbox/constraint sources and disables automatic output
buffering. It leaves the frozen hardener and active physical evidence untouched.
The strict candidate policy checks actual driver strengths, output wiring,
unique public drivers, sampler/reset/clock connections and absence of inserted
clock-delay cells. Source/producer drift rejects its physical result.
`rx_candidate_rc.py` checks those archives, extracts the actual candidate GDS
and independently LVS-checks the RC topology against the post-route transistor
schematic. No schematic-only or unloaded pass qualifies the required 20 fF
native RX endpoint. Fresh loaded controls must pass before a new full aperture
matrix; staged PHY integration and all release evidence still need that exact
new RX network.


## Buffered RX loaded endpoints and complete aperture matrix

```sh
scripts/env.sh --ngspice python3 scripts/rx_candidate_aperture.py prepare build/diagnostics/rx_buffer4_physical_v1
scripts/env.sh --ngspice python3 scripts/rx_candidate_aperture.py run build/characterization/rx_aperture/7636dbd7a4c55979 --stage all --jobs 3 --wait-slot 1
```

The artifact binds actual audited candidate GDS/RC, source/producer archives,
physical reports, original aperture producer, requirements and simulator. Six
+800 ps loaded setup endpoints cover both data polarities at SS/0 °C (20 ps
clock slew), TT/0 °C (200 ps) and FF/0 °C (200 ps), with 20 ps data slew and
the original 20 fF public loads. The `all` stage first runs those endpoints
with one worker; a failure holds full expansion. All six completed witnesses
are remeasured before starting the complete 480-condition matrix. Public level
limits, original observation windows, ±800 ps search bracket, ≤5 ps boundary
resolution, 20 ps guard and 200 ps additional link margin remain unchanged.

Each endpoint or complete boundary search owns one global SPICE lease. Optional
`--wait-slot` blocks on one of the existing six lease files for the endpoint
stage; it does not create a seventh slot or signal a live coordinator. Slot 1
was selected behind a short native DLL fixture to avoid repeated reacquisition
by the larger DLL queue. Full matrix workers return to the shared pool. Frozen
original aperture code is reused unchanged and never called without a wrapper
lease. Partial endpoints and physical/functional passes cannot qualify the
aperture table, staged PHY or release.


## Stage a selected native RX with matching RTL and physical package

```sh
scripts/env.sh --ngspice python3 scripts/stage_phy_candidate.py build/diagnostics/dll_qualification/1d201e9ed2f89f56 --rx build/diagnostics/rx_buffer4_physical_v1
scripts/env.sh --ngspice python3 scripts/verify_candidate_rtl.py build/diagnostics/phy_candidate/712bb74a908d85f4
```

RX selection overlays the audited exact/approximate RX closures while protecting
the DLL, TX, analog receiver/driver and delay line. PFD model metadata is also
bound to the actual selected native PFD. Staged RTL uses archived RX source and
requires consistent shared reset RTL. The native functional branch exercises
both retained SKY130 TX and RX cells; its source fingerprint includes RX models.
Packaging selects the corresponding RX GDS, LEF and extraction and rejects any
digital macro whose GDS differs from its staged model. These operations stage
and verify artifacts only; they cannot qualify or promote them electrically.

Advancement accepts explicit `--rx` and `--aperture-table` selections. It requires
a complete rechecked table matching the bundle's exact RX before forwarding that
table to the complete link regression. Link evidence checks the selected bundle's
RX rather than an unrelated canonical RX pointer. All original DLL, analog,
readiness/recovery, six-fixture RC certificate and 45-case link gates remain
mandatory. No advancement or promotion has been launched for the failing RX.


The stronger publication/output prototype has an isolated functional check:

```sh
scripts/env.sh --ngspice python3 scripts/verify_rx_buffered_rtl.py --source rtl/experiments/openlvds_ddr_rx_buffer8_publish4.v --rx-model models/experiments/sky130_rx_buffer8_functional.v
```

The verifier captures the explicitly selected source and functional cell models,
checks all 54 clock/duty/skew combinations with jitter/reset, and requires one
million bits per generic/native mode. This does not replace actual GDS extraction,
loaded native endpoint timing, aperture search or staged link qualification.


## Stronger publication candidate and failure-aware aperture dispatch

```sh
scripts/env.sh --tools --ngspice python3 scripts/harden_rx_buffer4.py build/diagnostics/rx_buffer8_publish4_physical_v1 --strength 8 --publication4
scripts/env.sh --tools --ngspice python3 scripts/rx_candidate_rc.py build/diagnostics/rx_buffer8_publish4_physical_v1
scripts/env.sh --ngspice python3 scripts/rx_candidate_aperture.py prepare build/diagnostics/rx_buffer8_publish4_physical_v1
scripts/env.sh --ngspice python3 scripts/rx_candidate_aperture.py run build/characterization/rx_aperture/f99deb414f62ab19 --stage all --jobs 3 --wait-slot 2
```

The existing hardener now selects either the preceding `public-data-buf4`
policy or explicit `public-data-buf8-publish4` policy. The stronger policy checks
both retained publication `dfrtp_4` cells, their direct clock/reset and Q-to-driver
connections, both `buf_8` data drivers, original falling sampler and unit VALID
driver. Unknown labels and incompatible strength/publication combinations fail.
The exact captured source and blackboxes are selected before hardening; policy
and producer changes create new physical/electrical evidence, never inherited
success. Staged RTL selects the matching functional RX cell models.

Admission now requires 12 loaded both-polarity endpoints: SS/40 slow clock,
SS/0 slow clock, SF/40 slow clock, SS/0 fast clock, TT/0 slow clock and FF/0
slow clock, with the original +800 ps separation and 20 fF loads. The selected
single endpoint slot is retained for the batch, preventing a long unrelated
fixture from taking the slot between each short endpoint. Full boundary workers
return to the shared six-slot pool. All 480 original conditions remain required;
slow SS/SF publication cases are dispatched first.

A failed endpoint or boundary holds queued work. Active boundary searches finish
and their traces are retained. Held cases have no simulated coverage claim.
An incomplete matrix writes `incomplete_summary.json` and a failed hold state,
not a complete aperture table. Twelve seed witnesses and all 480 actual boundary
results remain mandatory for qualification. Unit regressions cover failure holds,
exclusive real-slot ownership, complete coverage and selected-slot batch release.


Internal publication diagnosis can target one captured failed endpoint before
a full aperture table exists:

```sh
scripts/env.sh --ngspice python3 scripts/probe_rx_publication.py prepare build/characterization/rx_aperture/f99deb414f62ab19 --case ss_40_rising_rise_200_20_setup
scripts/env.sh --ngspice python3 scripts/probe_rx_publication.py run build/diagnostics/rx_publication/3efd83d2a44327ab --jobs 1
```

The diagnostic binds either the existing complete table or the selected seed
report, verifies the original endpoint waveform and retains fixed scoring.
Additional probes include native external-clock gate terminals and D/S terminals
of clock-controlled MOS devices, alongside the existing output-stage gates,
outputs and local supplies. It does not reinterpret a failed seed as qualified.


The controlled publication-cell comparison is explicit and independently scoped:

```sh
scripts/env.sh --ngspice python3 scripts/verify_rx_buffered_rtl.py --source rtl/experiments/openlvds_ddr_rx_buffer8_publish1.v --rx-model models/experiments/sky130_rx_buffer8_functional.v
scripts/env.sh --tools --ngspice python3 scripts/harden_rx_buffer4.py build/diagnostics/rx_buffer8_publish1_physical_v1 --strength 8 --publication1
scripts/env.sh --tools --ngspice python3 scripts/rx_candidate_rc.py build/diagnostics/rx_buffer8_publish1_physical_v1
scripts/env.sh --ngspice python3 scripts/rx_candidate_aperture.py prepare build/diagnostics/rx_buffer8_publish1_physical_v1
scripts/env.sh --ngspice python3 scripts/rx_candidate_aperture.py run build/characterization/rx_aperture/4032d9b01f924bfd --stage all --jobs 3
```

Only one declared publication option is accepted. The strength-1/strength-4
publication policies remain separate; both retain the same two `buf_8` data
outputs, original sampler/clock edges, pipeline and VALID driver. The shared
slot pool allows this short admission batch alongside native DLL acquisition
and component characterization. Physical/functional passes do not substitute
for its original loaded native timing and full aperture requirements.

## Half-cycle RX publication experiment

Internal native traces show that the positive-edge publication flop plus output
buffer is late in SS/40 °C, even when its input clock arrives on time. The new
experiment holds the rising sample on the falling edge and publishes it beside
the falling sample. VALID uses the same falling-edge holding convention. A
positive-edge consumer receives the same first word and ordered stream, one
cycle earlier than the old pre-edge interface; after each positive edge, valid
pairs agree with the original receiver. This phase/latency change requires
integration verification before promotion.

```sh
scripts/env.sh --ngspice python3 scripts/verify_rx_early_contract.py
scripts/env.sh --ngspice python3 scripts/verify_rx_buffered_rtl.py --source rtl/experiments/openlvds_ddr_rx_early.v --rx-model models/experiments/sky130_rx_early_functional.v
scripts/env.sh --tools --ngspice python3 scripts/harden_rx_buffer4.py build/diagnostics/rx_early_physical_v1 --early-publish
scripts/env.sh --tools --ngspice python3 scripts/rx_candidate_rc.py build/diagnostics/rx_early_physical_v1
scripts/env.sh --ngspice python3 scripts/rx_candidate_aperture.py prepare build/diagnostics/rx_early_physical_v1
scripts/env.sh --ngspice python3 scripts/rx_candidate_aperture.py run build/characterization/rx_aperture/20b04dcf527af283 --stage all --jobs 3
```

The distinct `half-cycle-publish-buf4` policy checks explicit inv_4 falling clock,
three falling-clock FFs, the rising sampler, pair-start FF, shared run gating,
and all three buf_4 public drivers in source and routed netlists. Reusing a
positive-edge publication label is rejected. The original loaded output window,
20 fF loads, 12 admission points, all 480 boundary conditions and timing margin
stay unchanged. Native admission failure holds matrix expansion. Passing native
coverage must additionally be followed by full link testing, including duty and
jitter stress; RTL and nominal STA alone do not prove the half-cycle path at PVT.

The supplementary early-RX burst diagnostic tests a different failure mode from
a single-transition aperture search: continuous words traversing the rising to
falling holding path at SS/40 °C, 410 MHz, 45/55% duty, independent bounded ±50 ps
clock-edge jitter, ±100 ps serial skew, 200 ps clock/data slew and 20 fF loads.
Four deterministic cases each check 32 consecutive pairs after eight warmup
cycles, including all symbols and alternating bits. Every word must meet the
original +0.80–1.05 ns public window and 0.36/1.44 V logic thresholds; VALID is
checked throughout that window. It does not replace the 480 aperture cases,
full link matrix or DLL qualification.

```sh
scripts/env.sh --ngspice python3 scripts/probe_rx_burst.py prepare build/diagnostics/rx_early_physical_v1
scripts/env.sh --ngspice python3 scripts/probe_rx_burst.py run build/diagnostics/rx_burst/0a6a8b72e9d5e53d
```

The diagnostic binds the physical audit, exact network, producer snapshots and
simulator provenance. Cached traces are remeasured; changed evidence is rejected.
It acquires the same shared native slot as other simulations and stops on the
first failed case. Tests independently derive sampled words from serial events
at actual jittered clock edges and reject corrupted, invalid or incomplete
waveforms.

A supplementary exact-RC data-path diagnostic can expose TX/receiver integration
issues while native DLL and approximate-RC qualification run:

```sh
scripts/env.sh --ngspice python3 scripts/simulate_link.py --bundle build/diagnostics/phy_candidate/8f364c6a8fdabafb --diagnostic --settled-start --bits 32 --process ss --temperature 40 --mhz 410 --duty .45 --skew-ps 100 --training-ns 60
```

This uses the actual selected full-RC TX, drivers, analog receivers and early RX,
with ideal quarter-phase clocks and fixed-supply DC startup. Its 60 ns training
is a diagnostic override. The required stressed diagnostic and full qualification
still require measured DLL phase, original training, a current complete aperture
table and the six-fixture certificate. No result from this supplementary run can
release a PHY. The shared six-slot pool also applies to this queued test.

## Resume downstream signoff after standalone native qualification

A campaign owned by a standalone service can continue after complete native and
all-PVT model validation, without registering another resident dispatcher:

```sh
scripts/env.sh --ngspice python3 scripts/advance_ota_candidate.py --qualified-native build/diagnostics/dll_qualification/1d201e9ed2f89f56 --all-pvt-stability ALL_PVT_REPORT --rx build/diagnostics/rx_early_physical_v1 --aperture-table build/characterization/rx_aperture/20b04dcf527af283/table.json
```

Replace `ALL_PVT_REPORT` with the completed report path. Entry reanalyzes the
entire native qualification and verifies all 15 model corners before starting
any downstream work. Incomplete/failed/stale proofs stop advancement; a CP
artifact is rejected. This path leaves resident configuration and native
fixtures unchanged. Both entry paths take one qualification-wide advancement
lock, so a second owner cannot launch duplicate signoff jobs.

Resume writes logs and `workflow.json` under the qualification's `advancement/`
directory. The same existing gates remain: observed/guarded OTA operating points,
limiting-corner recovery, readiness, selected-macro RTL, six-fixture RC comparison,
measured-DLL-phase diagnostic, complete selected-RX aperture table, full link
matrix, strict release recheck and exact-byte local promotion. Selecting an RX
requires its explicit aperture table. The original resident-dispatch entry
continues to use the selected layout's workflow directory.

## Continue the preset and local-delay native experiment

The standalone native handoff ends after screening. Its continuation can wait
for that owner to exit, recheck cached screen waveforms, measure the SS/TT/FF
model, run all 336 native fixtures and verify their proofs, then measure and
verify the model at all 15 process/temperature corners:

```sh
python3 scripts/continue_native_dll.py \
  build/diagnostics/dll_qualification/15cac0ba813a9333 \
  build/diagnostics/dll_layout/schur_513f603fc5e6c3aa/native_handoff.json \
  --producer-unit openlvds-local-delay-exact-native-handoff.service
```

The waiting job runs on the host to inspect user services and enters the pinned
container for simulator provenance, evidence verification and simulations.
The job uses the existing six-slot simulator pool. An exclusive progression
lock prevents duplicate continuation owners. Its receipt under the qualification's
`continuation/` directory binds the original handoff identity, qualification
manifest and producer sources. Failed or changed evidence holds progression;
current model evidence is verified before reuse. The full matrix requires the
measured native model, including independently forced-control delay gain and
390/410 MHz transient validation. The trajectory-inferred AC diagnostic cannot
satisfy this gate. Resident dispatcher configuration is untouched. Successful
completion still requires the downstream signoff described above.

## Receiver decision and restoration experiment

The doubled-input-tail receiver restores every sharper-control clock edge but
still loses nine rising and nine falling edges with captured pins. During its
first lost negative pulse, PP−PN reverses for 367.259 ps while CO reaches only
0.665 V. The next physical experiment retains those input tails, doubles the
decision-stage current/mirror/input widths, and drives three inverters sized
P/N = 4/2, 8/4 and 16/8 µm. This reduces the CO gate load while retaining output
polarity and final drive. It remains a diagnostic candidate.

```sh
scripts/env.sh --tools python3 scripts/layout_receiver_gain_candidate.py
scripts/env.sh --tools python3 scripts/receiver_candidate_rc.py \
  build/diagnostics/receiver_layout/784114a01817b339
scripts/env.sh --ngspice python3 scripts/probe_receiver_gain_candidate.py prepare \
  build/diagnostics/clock_restore/50565a94b3b04171 \
  build/diagnostics/receiver_layout/784114a01817b339
scripts/env.sh --ngspice python3 scripts/probe_receiver_gain_candidate.py run \
  build/diagnostics/receiver_replay/cb6fffffb0809887
```

Run commands only when their existing owner has exited. Physical DRC/LVS and
independent RC audit pass for this candidate. Both original pin stimuli, bias,
native early-RX loading and scoring interval are retained; PP/PN/CO and the two
added restoration nodes are observed. Any selected receiver still needs fresh
component PVT, headroom, sensitivity, continuous-clock and full-link evidence.
The buf_8 TX comparison failed and the baseline remains buf_4.

The matching full-link fixture can be prepared before the pin replays finish:

```sh
scripts/env.sh --ngspice python3 scripts/probe_receiver_candidate_link.py prepare \
  build/link/ss_40_410m_d0.45_s100_e0_ideal_32/6735242e52a2 \
  build/diagnostics/receiver_replay/cb6fffffb0809887
scripts/env.sh --ngspice python3 scripts/probe_receiver_candidate_link.py run \
  build/diagnostics/receiver_candidate_link/467b30dda15cf743
```

The run command first remeasures both completed replay waveforms through their
original verifier and requires zero missing clock edges. Incomplete or failed
replays hold the link experiment. Only the two analog receiver instances change
from the original full-RC fixture: buf_4 TX, driver, shared bias, ideal phase
stimuli, channel, early digital RX, payload and scoring remain identical. This
checks actual driver loading by the new receiver rather than clamping its input
pins to saved voltages. It remains a diagnostic and does not qualify a PHY.

## Receiver placement comparison

The decision-current candidate's early native trace still misses the first
short negative pulse. Its PP−PN reversal shrinks from 367.259 to 310.085 ps,
and CO reaches only about 0.697 V. The complete replay is retained. Independent
wire-capacitance inspection also shows that the new global row increased PP/PN
loads, partly offsetting its intended current and gate-load changes.

The placement comparison preserves the decision-current source byte for byte,
including all device sizes, terminal connections and finger banks. Deterministic
bank swaps minimize a weighted wire-span estimate, with extra emphasis on PP,
PN and CO. This estimate guides placement; extracted RC and native waveforms
remain the evidence for electrical behavior.

```sh
scripts/env.sh --tools python3 scripts/layout_receiver_compact_candidate.py
scripts/env.sh --tools python3 scripts/receiver_candidate_rc.py \
  build/diagnostics/receiver_layout/f2492f47d0df06ca
scripts/env.sh --ngspice python3 scripts/inspect_receiver_loading.py \
  build/diagnostics/receiver_layout/f2492f47d0df06ca
scripts/env.sh --ngspice python3 scripts/probe_receiver_compact_candidate.py prepare \
  build/diagnostics/clock_restore/50565a94b3b04171 \
  build/diagnostics/receiver_layout/f2492f47d0df06ca
scripts/env.sh --ngspice python3 scripts/probe_receiver_compact_candidate.py run \
  build/diagnostics/receiver_replay/17c5587a5df91855
```

Physical DRC/LVS and independent RC audit pass. Incident routing capacitances
change as follows; these sum full coupling values, exclude device/MIM capacitance,
and are not effective AC loads:

| Net | Original decision-current placement (fF) | Reordered placement (fF) |
| --- | ---: | ---: |
| PP | 109.141 | 66.413 |
| PN | 115.726 | 62.576 |
| CO | 45.447 | 42.437 |
| CL | 50.169 | 50.380 |
| CT | 138.108 | 165.735 |

The CT load increase is a tradeoff to measure in the native replay. Actual
receiver-loading receipts are `receiver_loading/28d53f03bd0b5df5` and
`receiver_loading/5401712c60ce2946`. The replay adapter captures every selected
physical producer without changing the live replay implementation. Its original
stimuli, shared bias, native early RX load, observations and scoring interval
remain unchanged. The complete captured case loses nine rising and nine
falling edges, matching the preceding placement. Its sharper control remains
pending; no improved clock recovery is established.

Full-link fixture `receiver_candidate_link/98985df18860704a` is prepared for this
layout and the same original buf_4 link. Its run gate still requires both complete
pin replays to recover every edge before any integration simulation starts.

## Tracked decision-node clamp at schematic level

The current-and-buffer candidate's complete captured replay still loses nine
rising and nine falling edges. The reordered placement's complete captured case
also loses nine of each polarity. At its first lost short negative pulse, PP−PN
reverses for only about 216 ps and CO peaks at about 0.561 V. A smaller sum of
wire capacitors has not improved captured-input cadence; the native sharper
controls continue to completion.

`receiver_clamp_experiment.py` compares the decision-current schematic with and
without a local clamp. A replica inverter with P8/N4 µm devices connects its
input to its output at CO_TRACK. It retains the first restoration inverter's
P/N ratio and channel lengths at twice its size. Two parallel existing 1.25 µm
high-poly resistor units connect CO to this reference (nominally about 1 kΩ
together). The aim is to reduce the CO excursion and restore edges near the
tracked inverter trip point. All preceding transistor sizes and connections,
the public nine-port interface and fixed supplies are retained.

```sh
scripts/env.sh --ngspice python3 scripts/receiver_clamp_experiment.py prepare \
  build/diagnostics/clock_restore/50565a94b3b04171
scripts/env.sh --ngspice python3 scripts/receiver_clamp_experiment.py run \
  build/diagnostics/receiver_clamp/e888b13239fc158e
```

The three fixtures are unclamped/captured, clamped/captured and clamped/sharper
control. Both analog cores use flattened schematic device fingers, while the
exact shared bias and native early digital RX load remain unchanged. The saved
pin waveforms, reset, 80 ns stop time and 15–75 ns observation interval are
identical to the preceding replay. PP/PN/CO and the replica trip point are
observed. Source, fixture, library, waveform, producer and runtime hashes bind
the comparison; cached waveforms are remeasured.

These are schematic architecture diagnostics, with no analog receiver wire RC
or physical/electrical qualification claim. Passing results would require an
actual layout, independent extraction, native replay and fresh component/PVT
and full-link checks before selection. The first preparation containing optional
current probes was retired before any simulation; the frozen exporter supports
voltage probes only. Its no-run receipt remains in `receiver_clamp/877040209e65a9d0`.

The unclamped/captured control completes with zero missing edges. Diagnostic
input-to-output edge latency spans 296.120–412.380 ps, and CO ranges
0.0161–1.7919 V over the original 15–75 ns interval. The corresponding native
receiver loses nine rising and nine falling edges. This implicates extracted
parasitics but does not isolate wire capacitance from the extracted devices'
explicit junction geometry: schematic finger models use schematic geometry
defaults. The clamped cases still need complete results, followed by actual
physical/native proof if selected.

The clamped/captured case now also completes with zero missing edges. Its
diagnostic latency is 308.507–441.512 ps, compared with 296.120–412.380 ps for
the unclamped schematic. CO ranges 0.0773–1.6157 V, while CO_TRACK moves
0.5034–1.1273 V under loading. Thus the reference is not stiff and this test
does not establish a speed improvement. The clamped sharper-input case also completes with zero missing edges. All
three original source comparisons are complete.

The physical path is prepared behind both completed, zero-missing-edge clamped
replays. It remeasures all three schematic traces and verifies that their exact
candidate source matches the source to be laid out. It holds on incomplete,
failed, changed or mismatched evidence before creating a layout. The four added
clamp devices are placed immediately before the first restoration inverter;
every preceding device/finger retains its relative order and terminals.

```sh
scripts/env.sh --tools --ngspice /usr/bin/python3 \
  scripts/layout_receiver_clamp_candidate.py \
  build/diagnostics/receiver_clamp/e888b13239fc158e
```

Use the base `/usr/bin/python3` with NumPy inside the physical tools shell for
the source-waveform recheck. Current layout `receiver_layout/f576c6a98d893590`
passes DRC (zero errors), LVS and independent RC audit. It retains 85 devices
and all nine ports. Its native network SHA256 begins `ad5ac6a6d26b0b33`. The
following steps have prepared and started its native comparison:

```sh
scripts/env.sh --tools python3 scripts/receiver_candidate_rc.py \
  build/diagnostics/receiver_layout/f576c6a98d893590
scripts/env.sh --ngspice python3 scripts/probe_receiver_clamp_candidate.py prepare \
  build/diagnostics/clock_restore/50565a94b3b04171 \
  build/diagnostics/receiver_layout/f576c6a98d893590
scripts/env.sh --ngspice python3 scripts/probe_receiver_clamp_candidate.py run \
  build/diagnostics/receiver_replay/7b46eef599fb6e55
```

Native preparation checks
the exact source, physical/extraction proofs and current schematic witnesses;
the replay observes PP/PN/CO, both restoration nodes and CO_TRACK. It preserves
the original two pin stimuli, shared bias, native early RX load and scoring.
`probe_receiver_candidate_link.py` dispatches to this replay's own verifier
before integration, so a passing gain-only report cannot stand in for a clamp
report. Matching full-link fixture `receiver_candidate_link/a3b07823d72b7aeb`
is prepared and held behind both completed, zero-missing-edge native replays.
Physical checks pass, while native clock recovery, all-PVT component behavior
and full-link qualification remain unproven.

## Selected receiver component qualification

`qualify_receiver_components.py` prepares 60 fresh conditions for the selected
receiver: schematic/native models, static sensitivity and maximum-rate tests,
five process corners and 0/25/40 °C. It clones the currently verified original
fixtures, changes only the receiver model/library binding and native observation
names, and protects the original shared bias, driver and delay-line closures.
Original fixed supplies, 100 fF output load, ±100 mV static decisions across the
six legal common modes, 820 Mb/s rate stimulus, timing windows and logic limits
are retained. The original rate analyzer is reused without changes.

```sh
scripts/env.sh --ngspice python3 scripts/qualify_receiver_components.py prepare \
  build/diagnostics/receiver_layout/f576c6a98d893590 \
  build/diagnostics/receiver_replay/7b46eef599fb6e55
scripts/env.sh --ngspice python3 scripts/qualify_receiver_components.py run \
  build/diagnostics/receiver_components/06ef0f1a751e6c5d --jobs 3
```

Only preparation has completed. A real run preflight reconstructs and checks
all 60 original fixtures, then holds at the incomplete native replay gate,
creating no component simulation. Both loaded native replay cases must complete
with exactly one output transition per input period before this campaign can
allocate simulator slots; zero missing edges alone cannot admit extra pulses.
Missing, duplicate or mislabeled conditions and changed fixture/model bytes are
rejected. Every cached candidate waveform is remeasured. This remains separate
from the 90 passing baseline component proofs, with no canonical model-pointer
change. These cases do not replace native headroom, DLL, aperture, RC or full-link
qualification.


The three completed first-clamp schematic controls each have 47 checked input
periods with exactly one corresponding output edge. The integration/component
gate now explicitly rejects repeated edges as well as missing ones. Previously
prepared component/link manifests are retained; the current paths above bind
this stricter producer generation.

## Stronger tracking-reference comparison

The first native clamp's complete captured replay still loses nine rising and
nine falling edges. Its sharper control continues. At the first lost pulse, CO reaches about 0.789 V and CO_TRACK moves 0.508–0.823 V over that pulse's
24.5–26.5 ns interval; the output clock does not fall. The full native replay
continues. This motivates a separate schematic comparison with P32/N16 µm
reference devices, four times the original replica widths, and four parallel
poly units instead of two (nominal clamp resistance about 500 Ω). Existing
input/decision devices, three restoration stages and all other source blocks
remain unchanged. In particular the stronger replica has its own helper; the
middle restoration inverter retains its original P8/N4 dimensions.

```sh
scripts/env.sh --ngspice python3 scripts/receiver_strong_clamp_experiment.py prepare \
  build/diagnostics/clock_restore/50565a94b3b04171
scripts/env.sh --ngspice python3 scripts/receiver_strong_clamp_experiment.py run \
  build/diagnostics/receiver_clamp/86e622030245e729
```

The frozen schematic-replay implementation is reused with the new source
factory explicitly attested. It retains the same three controls, pins, bias,
native digital load, observations and scoring. The new source is isolated from
all preceding experiments. All three source cases now pass, each with exactly one output edge in every
checked input period (47 per case). The captured case gives CO =
0.1661–1.3931 V, CO_TRACK = 0.6468–0.9618 V and latency
313.148–515.246 ps. The reference moves less, but latency has not improved
relative to the unclamped control. Physical/native behavior and full qualification
remain pending; the first clamp's layout gate cannot accept this different source.

The stronger source now has its own physical/native implementation, preserving
that exact schematic and its preceding source witnesses. Six replica fingers
and four clamp resistors sit beside CO before the first restoration inverter;
all original receiver devices retain their relative order and connections.

```sh
scripts/env.sh --tools --ngspice /usr/bin/python3 \
  scripts/layout_receiver_strong_clamp_candidate.py \
  build/diagnostics/receiver_clamp/86e622030245e729
scripts/env.sh --tools python3 scripts/receiver_candidate_rc.py \
  build/diagnostics/receiver_layout/feb7596968046dd1
scripts/env.sh --ngspice python3 scripts/probe_receiver_strong_clamp_candidate.py prepare \
  build/diagnostics/clock_restore/50565a94b3b04171 \
  build/diagnostics/receiver_layout/feb7596968046dd1
scripts/env.sh --ngspice python3 scripts/probe_receiver_strong_clamp_candidate.py run \
  build/diagnostics/receiver_replay/13ab38f8a7b8e217
```

Current layout `receiver_layout/feb7596968046dd1` passes DRC (zero errors), LVS
and independent RC audit, retaining 91 devices and nine ports. Its native network
SHA256 starts `32579bcd62e88ff5`. Source admission additionally requires exactly
one output edge per checked period in every original control. The stronger-clamp
native producer observes PP/PN/CO, both restoration nodes and CO_TRACK and binds
the exact source, physical, RC and schematic proofs. Its replay is queued under
the unchanged six-slot budget. No native clock-recovery improvement is claimed.

Matching full-link fixture `receiver_candidate_link/37d95b09d5fb0059` and all
60 component conditions at `receiver_components/90fff4b7107aa5ae` are prepared.
A real component preflight reconstructs all fixtures and holds before simulation
at pending native replay evidence. Both use the stronger variant's own waveform
verifier; weak-clamp reports cannot substitute. Native cadence, component/PVT,
headroom, new-network RC comparison and full-link gates remain mandatory.

The host-side continuation is active for these exact artifacts:

```sh
python3 scripts/continue_receiver_candidate.py \
  build/diagnostics/receiver_replay/13ab38f8a7b8e217 \
  build/diagnostics/receiver_components/90fff4b7107aa5ae \
  build/diagnostics/receiver_candidate_link/37d95b09d5fb0059 \
  --producer-unit openlvds-receiver-strong-clamp-native-replay.service
```

It binds all three manifests and their producer context, waits for the actual
native owner to exit, and requires both complete native cases with exactly one
output edge per input period. The component and link children independently
remeasure native evidence before taking shared simulator slots. Both children
are allowed to finish if either fails; passing diagnostics do not promote a
release. Receipts and logs are under the replay's `followup/` directory.

The stronger clamp's live native trace still misses the first short negative
pulse: CO reaches only 0.822 V, CO_TRACK moves 0.656–0.830 V, and RESTORE0 remains
above 1.726 V in the 24.5–26.5 ns interval. The full replay continues to its
original stop time. This is an engineering observation, not a completed verdict.

## Wider input-pair source comparison

The next source comparison doubles only XNP/XNN/XPP/XPN widths from 20 to
40 µm in the stronger-clamp circuit. Tail-device sizes, reference current,
mirrors, resistive loads, decision devices and restoration stages are retained.
It tests whether greater input transconductance and lower current density help
the small frontend differential reversal. Increased input loading still needs
physical/native and full-link verification if this source is selected.

```sh
scripts/env.sh --ngspice python3 scripts/receiver_wide_input_experiment.py prepare \
  build/diagnostics/clock_restore/50565a94b3b04171
scripts/env.sh --ngspice python3 scripts/receiver_wide_input_experiment.py run \
  build/diagnostics/receiver_clamp/4e55a995d239fb38
```

The same three source cases, saved pins, shared native bias and digital load,
observations and scoring are retained. Its unclamped control remains the
original schematic control. The scoped source invariant checks preserve all
other receiver devices and all other circuit definitions. This experiment is
queued; no source or native improvement is claimed.

## Xyce compatibility check

The image already contains Xyce 7.10.0 built from release commit
`a592a42ae7472151d1c8e3bca0ca62d27476f2f3`. A parser-only check of the actual
native receiver replay succeeds:

```sh
scripts/env.sh --xyce python3 scripts/probe_xyce_compatibility.py \
  build/diagnostics/receiver_replay/cb6fffffb0809887/captured/bench.cir
```

Receipt `xyce_compatibility/ba10c72ce84ed18a` binds the fixture, library, binary,
image receipt, version, parser producer and output log. This uses `-syntax`;
no transient or speed comparison is performed and no simulator slot is consumed.
The parser warns that the requested BSIM4 version 4.5 is replaced with its oldest
supported version, 4.6.1. Parsing success alone is insufficient evidence to
substitute this runtime into the captured ngspice qualification campaigns.

The inspected upstream master commit is
`e5b7b9bb5b221630c66654c059fc2d33524f5b21`. Its
[BSIM4 source](https://github.com/Xyce/Xyce/blob/e5b7b9bb5b221630c66654c059fc2d33524f5b21/src/DeviceModelPKG/OpenModels/N_DEV_MOSFET_B4.C#L9266)
still contains the same minimum-version fallback. The downloaded source's URL,
commit and content hash are recorded under `xyce_compatibility/upstream/`.
A newer build therefore has no demonstrated device-model or performance benefit
for these fixtures yet. Current numerical campaigns retain their original runtime.

The preset/local-delay source campaign also completes all three original corners.
FF/0 °C passes at CTRL variation 3.163 mV, feedback error 6.493 ps and quarter
delay 632.701–633.013 ps. The exact-profile handoff starts native screen
`dll_qualification/15cac0ba813a9333`; all 312 non-screen cases remain held for
the measured native model. No native acquisition pass is claimed.

The stronger-clamp native captured case completes with 11 missing rising and
11 missing falling edges, worse than the baseline's nine of each.
The sharp native control completes with nine missing rising and
nine missing falling edges. The native owner is terminal with both diagnostic
reports; its continuation correctly records `held_for_diagnosis` for lost clock
edges. Neither prepared component root `90fff4b7107aa5ae` nor prepared link root
`37d95b09d5fb0059` has an execution receipt or raw simulation file. After those
owners terminated, downstream dispatch gained explicit `strong_wide_input`
factory/verifier selection. Fresh component/link preparation is required for
any future selected receiver; those historical prepared contexts are not reused.

The wider-input candidate has separate physical and native producers. Run these
only after its three source comparisons finish; the layout producer remeasures
the cached waveforms and requires exactly one output edge per input period in
every control. It also checks the exact source, so the earlier strong-clamp
comparison cannot qualify the wider input devices.

```sh
scripts/env.sh --tools --ngspice /usr/bin/python3 \
  scripts/layout_receiver_wide_input_candidate.py \
  build/diagnostics/receiver_clamp/4e55a995d239fb38
# Use the layout root printed above for both commands below.
scripts/env.sh --tools python3 scripts/receiver_candidate_rc.py LAYOUT_ROOT
scripts/env.sh --ngspice python3 scripts/probe_receiver_wide_input_candidate.py prepare \
  build/diagnostics/clock_restore/50565a94b3b04171 LAYOUT_ROOT
scripts/env.sh --ngspice python3 scripts/probe_receiver_wide_input_candidate.py run REPLAY_ROOT
```

`LAYOUT_ROOT` and `REPLAY_ROOT` are the actual returned artifact paths. Extraction
must pass the independent connectivity audit before replay preparation. The new
identity is `strong_wide_input`, with input width 40 µm; it cannot be substituted
for the previous strong-clamp identity. Receiver replay remains diagnostic and
does not select a release. Full component, RC comparison, aperture and link
checks remain required if this native candidate recovers every clock edge.

Host continuation `continue_receiver_wide_input.py` is active as
`openlvds-wide-input-native-continuation-v2`. It waits on the actual source owner,
requires successful terminal service status and all three reports, then invokes
the gated layout producer, independent RC audit and original two native replays.
It binds the source/parent manifests and downstream producer hashes. Observation
errors retry; a failed gate holds the pipeline. Its receipt, captured producer
and stage logs are under `receiver_clamp/4e55a995d239fb38/native_continuation/`.
It does not start component/link qualification or publish a PHY release.

```sh
/usr/bin/python3 scripts/continue_receiver_wide_input.py \
  build/diagnostics/receiver_clamp/4e55a995d239fb38 \
  build/diagnostics/clock_restore/50565a94b3b04171 \
  --source-unit openlvds-receiver-wide-input-source-screen.service
```

Completed captured-waveform inspection compares the same negative pin pulse at
24.777 ns (526.689 ps width). In the interval from that crossing through 500 ps
after the following pin rising crossing, weak→strong clamp changes the sampled
PP−PN negative duration from 291.929 to 284.538 ps and its minimum from −37.791
to −35.982 mV. CO peak rises from 0.789424 to 0.821754 V, but neither restores
the output clock. Durations here integrate a sampled sign mask and are diagnostic,
not refined zero-crossing or setup/hold measurements. Stronger clamping alone
has not solved the short-pulse loss; the wider-input experiment remains unproven.

The wider-input captured source case completes: all 47 checked input periods
have exactly one output edge, with zero missing edges. Diagnostic latency is
324.978–448.846 ps; CO spans 0.153–1.420 V and CO_TRACK spans 0.643–0.968 V
in the original scoring window. The unchanged unclamped control also passes.
The sharp-input source control also completes with exactly one edge in each of
47 checked periods. All three source cases now pass. These source results do
not establish native improvement.

Independent incident-routing-capacitance inspection of the completed first and
stronger clamp layouts produces `receiver_loading/590861f9b5121ad3` and
`receiver_loading/564e28b05497f1bf`, respectively. PP rises from 115.776 to
122.001 fF, PN from 122.274 to 128.498 fF and CO from 58.027 to 73.967 fF.
CL, CT and both restoration-net wire sums are unchanged. Thus the stronger
reference comes with increased routing load on the decision output and frontend
signal nets. This comparison does not isolate those loads from the electrical
effect of the stronger clamp, and does not prove the cause of pulse loss. These
are full incident coupling sums, excluding device/MIM capacitance, rather than
effective AC loads. The wider-input extracted network still needs its own
inspection and loaded native replay before any physical improvement is claimed.

The first wide-input continuation held after systemd unloaded the successfully
completed transient source unit (`LoadState=not-found`, inactive, success, status
0). The corrected predicate permits this terminal state only with all complete
reports; the layout producer still independently remeasures every waveform and
source proof. The failed continuation receipt/producer is preserved in
`native_continuation_history_516799b`. Only the host continuation was restarted.

Wider-input physical root `receiver_layout/4cea0a2ca0f9868e` passes DRC/LVS
and independent extracted connectivity audit (95 devices, nine original ports).
Its native network is `7f2680cc72bcaf633f07e7764bd1c850ee6f1d49fd275a117af4f235505b8e02`.
Receiver-loading receipt `c66f016bc3569690` measures incident PP/PN/CO wire sums
124.217/131.377/73.967 fF. Native replay `receiver_replay/5adb1f717c66c41e`
retains both original 80 ns pin stimuli, shared bias and digital receiver load,
and is queued under the shared six-slot limit. No native improvement is claimed.

Fresh wider-input downstream fixtures are prepared at
`receiver_components/f82998633770e370` (all 60 original schematic/native static
and rate conditions) and `receiver_candidate_link/a1fe429613422650` (the original
full-RC SS/40 °C/410 MHz loaded diagnostic). Host service
`openlvds-wide-input-receiver-followup` waits on the actual native continuation.
Both original native cases must complete with every input period producing
exactly one output edge before it can run either campaign. The scientific
children repeat the native waveform/input/producer checks. No downstream
simulation or release result is claimed at preparation.

The wider-input native trace reaches 28.365 ns while still running. Its first
short negative pin pulse fails to restore the output: over 24.5–26.5 ns, CO
peaks at 0.810757 V, RESTORE0 stays above 1.744051 V and no output falling
crossing occurs in 24–27 ns. Both original 80 ns native cases continue to full
reports; no partial trace is used to qualify or promote the receiver.

The next isolated comparison removes decision-stage doubling while retaining
input-tail doubling, the stronger clamp and three restoration stages. It returns
XCT to 64 µm and XC0/XC1/XCD/XCM to 8 µm, their original widths. All other
devices, including original 20 µm input pairs, are unchanged. This tests whether
the added decision loading outweighs its extra current: previous native first
pulse traces show PP−PN minima −66.1 mV before, versus −43.4 mV after, decision
doubling. Those observations also include the restoration change and do not
isolate a cause. Improvement requires new source and physical/native evidence.

```sh
scripts/env.sh --ngspice python3 scripts/receiver_light_decision_experiment.py prepare \
  build/diagnostics/clock_restore/50565a94b3b04171
scripts/env.sh --ngspice python3 scripts/receiver_light_decision_experiment.py run \
  build/diagnostics/receiver_clamp/af769bd4767fe6c2
```

Service `openlvds-light-decision-source-screen` queues the original three source
controls with the same fixed supplies, pin traces, native bias/digital load,
80 ns duration and 15–75 ns scoring window. The unclamped source control remains
the original gain-doubled source; the clamped architecture and historical strong
source comparison provide separate context. Three tests verify exact coherent
decision sizes, all other devices/ports, unchanged control and rejection of
unexpected topology. This source experiment does not select a physical receiver.

The original-decision candidate has dedicated physical/native producers and
identity `strong_light_decision`, `decision_scale=1`. Its physical gate remeasures
all three source traces, requires exactly one edge per checked input period and
checks the exact source; doubled-decision source evidence cannot supply this
proof. Native preparation retains the original terminal order, bias circuit,
digital load, 80 ns stimuli and scoring window, and requires DRC/LVS plus an
independent RC audit. Seven targeted source/physical tests pass.

Host service `openlvds-light-decision-native-continuation` is waiting on the actual
source owner. It freezes source/parent manifests and downstream producers and
uses the corrected transient-unit observation helper. After source success it
runs the gated layout, RC audit and both native controls. Any failed gate holds
the pipeline; no component/link or release is started by this continuation.

```sh
/usr/bin/python3 scripts/continue_receiver_light_decision.py \
  build/diagnostics/receiver_clamp/af769bd4767fe6c2 \
  build/diagnostics/clock_restore/50565a94b3b04171 \
  --source-unit openlvds-light-decision-source-screen.service
```

Its receipt is under `receiver_clamp/af769bd4767fe6c2/native_continuation/`.
The source owner remains live; no original-decision
physical/native result is claimed.

The wider-input captured native case subsequently completes with nine missing
rising and nine missing falling edges. The count improves on the preceding
strong clamp's 11 each but equals the original baseline loss; clock recovery
still fails. Its sharp native control is queued under the same six-slot budget.
Prepared wider-input components and full-link diagnostics remain held by the
loaded recovery gate. The original-decision source experiment continues.

The original-decision captured source case completes with one missing falling
edge and the following rising edge, at input crossings 58.919554 and 59.434356 ns.
The negative pulse is 514.802 ps wide with 83.068 mV peak magnitude. Over
58.7–60.7 ns, CO reaches 0.948352 V but the restored clock remains above
1.702166 V. CO's 0.9 V crossings are 59.153025 and 59.423702 ns; 0.9 V here is
an observation threshold, not a measured first-inverter switching threshold.
The sharp source control is queued. The failed captured case prevents layout
admission even if that control later passes.

Next comparison `receiver_light_clamp_experiment.py` removes exactly XCLAMP2
and XCLAMP3 from the original-decision strong-clamp source. Two parallel resistor
units remain (about 1 kΩ), with the same P32/N16 replica, original decision
sizes, doubled input tails and three restoration inverters. No other device,
connection, control, bias/load, timing window or recovery criterion changes.
The hypothesis is that lower shunt loading lets this smaller decision stage
produce sufficient pulse amplitude/duration; no improvement is established.

```sh
scripts/env.sh --ngspice python3 scripts/receiver_light_clamp_experiment.py prepare \
  build/diagnostics/clock_restore/50565a94b3b04171
scripts/env.sh --ngspice python3 scripts/receiver_light_clamp_experiment.py run \
  build/diagnostics/receiver_clamp/7002b1f71a4ff337
```

Service `openlvds-light-clamp-source-screen` queues these three original source
controls. Two targeted tests verify that only the two resistor instances are
removed and the unclamped control is byte-identical. No physical candidate is
selected from this source experiment.

Both wider-input native controls now complete: captured and sharp each miss
nine rising and nine falling edges. The native continuation and its downstream
follow-up both record `held_for_diagnosis` for failed clock recovery. Neither
component root `f82998633770e370` nor link root `a1fe429613422650` contains an
execution receipt or raw simulation trace. The wider-input candidate is not
selected. The reduced-clamp source control and previous original-decision sharp
source control are now running within the same six-slot budget.

The original-decision source comparison now completes all three controls.
Unclamped captured and clamped sharp controls have zero missing edges; clamped
captured still misses one rising and one falling edge. Its native continuation
rechecks all source waveforms, then holds when the physical source gate rejects
the lost clock edges. No physical artifact is generated for that source, and
neither extraction nor native replay starts. The reduced-clamp experiment's
unchanged source control also completes with zero missing edges; its modified
captured case is queued. No circuit improvement is claimed from a control alone.

Early RX aperture campaign `20b04dcf527af283` now completes all 96 SS conditions:
32 each at 0, 25 and 40 °C. All pass. Each group's exact coverage is checked
against both clock edges, both data polarities, 20/200 ps clock and data slew
endpoints and setup/hold. Maximum guarded setup/hold bounds are 280/120 ps at
0 °C and 270/110 ps at 25 and 40 °C. Other process corners remain outstanding;
the full 480-condition aperture table is not yet qualified. The reduced-clamp
modified captured source case is now running under the shared six-slot budget.

The reduced-clamp captured source case completes with no missing edges and
exactly one output edge in all 47 checked periods. Diagnostic latency is
301.890–510.435 ps. The unchanged control also passes, but the sharp source
control remains outstanding; the three-case source gate is not yet satisfied.

Dedicated reduced-clamp physical/native producers bind identity
`light_decision_1k_clamp`, `decision_scale=1` and two parallel clamp resistor
units. They check the exact source, three complete one-to-one source controls,
physical DRC/LVS, independent RC connectivity audit and all captured producer
hashes. Only the eight replica/clamp devices are moved beside the first
restoration inverter; all other device order/connections are retained. Original
pin waveforms, bias, native digital RX load and scoring windows remain intact.
The downstream dispatcher uses this variant's source factory and waveform
verifier explicitly; it does not reuse the failed four-unit replay.

Host service `openlvds-light-clamp-native-continuation` is waiting on the actual
source owner before running these stages. Its receipt is under
`receiver_clamp/7002b1f71a4ff337/native_continuation/`. The source-unit observation
helper retains complete-report checks and handles successful unloaded transient
units; the physical gate independently remeasures the actual source waveforms.
No reduced-clamp physical/native result or release selection is claimed.

All three reduced-clamp source controls subsequently complete with exactly one
output edge in every checked input period. Its native replay producer now runs
the two independent fixtures concurrently, each acquiring its own lease from
the unchanged six-slot pool. The previous continuation was confirmed waiting
and stopped before changing that producer; no live SPICE process was interrupted.
Its frozen receipt is archived as `native_continuation_history_d6f80e5`.
Service `openlvds-light-clamp-native-continuation-v2` captures the revised code.
Tests verify concurrent fixture starts, separate leases, stable report order
and completion of the other fixture when one simulator fails. Full unit suite:
359 tests, 358 passed and one skipped.

Physical root `receiver_layout/4e540d457ca789a4` passes DRC/LVS and independent
RC connectivity audit (77 devices, nine ports). Native network SHA256 is
`b8e821dc164ef55a4f58f81e1a740f03e0b2ea75451c7658d32712d5416e8723`.
Loading receipt `receiver_loading/2b2f0d4e931336c9` measures incident PP/PN/CO
wire sums 102.831/109.899/44.786 fF and CL/CT sums 25.001/70.874 fF. These
are routing observations, not effective AC load or timing qualification.
Replay `receiver_replay/5c2e6e425ac65e58` now runs both original 80 ns controls.

Fresh component fixtures `receiver_components/57488d46b26d09ec` cover all 60
original source/native static/rate cases. Loaded full-link diagnostic
`receiver_candidate_link/cb4be133271a71ea` retains original stimulus and scoring.
Service `openlvds-light-clamp-receiver-followup` waits on the actual native owner
and requires complete one-to-one native recovery before running either campaign.
No native improvement, component/link pass or PHY release is claimed yet.

Actual component preflight reconstructs all 60 fixtures, then correctly holds at
the incomplete native recovery gate. No execution receipt or raw component
trace is created. `gate_preflight.json` binds this observation to the component
manifest, verifier code and simulator provenance; it is not component qualification.

Native DLL screen `15cac0ba813a9333` also completes all 21 selected static
offsets: exact SS/0, TT/25 and FF/0 coverage at 0, ±50, ±150 and ±300 ps.
Acquisition loops remain outstanding; static passes do not admit the measured
loop model or the remaining 312 qualification fixtures.

The reduced-clamp captured native trace reaches 27.585 ns while running. The
first short pulse still fails to restore: in 24.5–26.5 ns CO reaches only
0.859699 V, RESTORE0 stays above 1.667761 V, and no RXCLOCK falling crossing
occurs in 24–27 ns. CO_TRACK spans 0.738464–0.836576 V. These are partial
engineering observations; both original native controls continue to full reports.

Next comparison `receiver_vref_clamp_experiment.py` changes exactly the reference
terminal of XCLAMP0/1 from CO_TRACK to the existing VREF port. The source fixture
already supplies VREF at 1.2 V. Two approximately 2 kΩ resistor units remain in
parallel; original decision sizes, doubled input tails and restoration are
unchanged. The replica remains present but unloaded as an observation node.
This tests reference binding independently of device size or clamp conductance;
no threshold, timing or PVT improvement is assumed. Additional VREF loading and
full component/headroom/PVT behavior must be checked if this variant is selected.

```sh
scripts/env.sh --ngspice python3 scripts/receiver_vref_clamp_experiment.py prepare \
  build/diagnostics/clock_restore/50565a94b3b04171
scripts/env.sh --ngspice python3 scripts/receiver_vref_clamp_experiment.py run \
  build/diagnostics/receiver_clamp/0244d3fb608b9d06
```

Service `openlvds-vref-clamp-source-screen` queues the original three controls,
retaining 80 ns stimuli, native bias/digital RX load and 15–75 ns scoring. Two
targeted tests verify that only those resistor terminals change, CO_TRACK is
connected only to the replica, and the unclamped source control is unchanged.
No physical candidate or qualification verdict is selected from this experiment.

Reduced-clamp native replay `5c2e6e425ac65e58` now completes both original
controls. Captured misses 10 rising and 10 falling edges; sharp misses nine
of each. Reanalysis of both cached native waveforms reproduces the saved
reports and verifies their captured context. The native continuation and its
downstream follow-up correctly hold for lost clock edges. Neither component
root `57488d46b26d09ec` nor link root `cb4be133271a71ea` has an execution receipt
or raw simulation trace. The candidate is not selected for qualification.
The VREF-bias experiment's unchanged source control is running under the same
six-slot limit; no result for its modified circuit is available yet.

The VREF-biased captured source case now completes: all 47 checked periods
produce exactly one output edge, with no missing/repeated edges. Diagnostic
latency is 260.642–508.359 ps. CO spans 0.387500–1.533384 V and the unloaded
replica remains near 0.832621 V in the original scoring window. The unchanged
control also passes, but the sharp source control remains outstanding. No
physical/native improvement is established by these source results.

Dedicated physical/native producers bind identity `vref_1k_clamp`,
`clamp_reference=VREF`, original decision sizes, two parallel resistor units and
`replica_monitor_unloaded=true`. The physical source gate remeasures all three
complete source controls and requires exact source agreement. Native preparation
requires DRC/LVS and independent RC audit, preserves all nine ports and original
80 ns pin fixtures, native bias, digital RX load and scoring windows. Both native
controls run concurrently with separate shared simulator leases; failures do
not interrupt the other control. Tests reject tracked-reference source or
metadata, check unchanged devices/placement, exact verifier dispatch and parallel
completion/error behavior. The downstream dispatcher selects this VREF variant
explicitly rather than using an older clamp replay verifier.

Service `openlvds-vref-clamp-native-continuation` waits on the actual source owner
before attempting layout, RC audit and native replay. Its receipt is under
`receiver_clamp/0244d3fb608b9d06/native_continuation/`. No VREF-biased physical
artifact or native simulation is claimed while that source gate is incomplete.

All three VREF-biased source controls now complete with exactly one output edge
in each of 47 checked input periods. The native continuation remeasures these
actual waveforms and passes the full source gate. Physical root
`receiver_layout/c9b54df2758e600a` passes DRC/LVS and independent RC connectivity
audit (77 devices, nine original ports). Native network SHA256 is
`36e80ac2285911490ebebbd8d6a881a7d8c944d6f000c824478dd849cc1e2ad1`.
Loading receipt `receiver_loading/3b41530840a8d2e7` reports incident PP/PN/CO
wire sums 102.831/109.899/42.695 fF. These sums do not establish effective AC load
or native timing. Both original native controls are running concurrently in
`receiver_replay/77252e9aa3abb333`, with separate shared simulator leases.

Fresh VREF-biased component root `receiver_components/a09b869f2ffff52b` prepares
all 60 original source/native static/rate fixtures. Full-link diagnostic
`receiver_candidate_link/3635f229cd4efe04` preserves the original loaded stimulus
and scoring. Actual component preflight reconstructs all fixtures, then holds at
the incomplete native gate; no execution receipt or raw component trace is
created. Its `gate_preflight.json` binds manifest, verifier and runtime hashes.
Service `openlvds-vref-clamp-receiver-followup` waits on the actual native owner,
requires complete one-to-one edge recovery, and lets both scientific children
repeat the native waveform/provenance checks before simulation. No native
improvement, component/link pass or release is claimed at this preparation stage.

Native DLL screen `15cac0ba813a9333` completes SS/0 acquisition successfully in
the original 1200–1500 ns window: CTRL variation 1.849904 mV (20 mV limit),
feedback error 19.010343 ps and quarter delay 668.380426–668.485247 ps
(625 ± 100 ps). Cadence and omitted-pulse marker checks pass. Unwrapped marker
section delays are 668.411765, 642.797953, 633.562612 and 632.784872 ps;
mean power is 8.451226 mW. The 1700 ns fixture is complete. Together with all
21 static offsets this yields 22 passing screen cases. TT/25 acquisition is
running; FF/0 is pending. The measured native model and remaining 312 fixtures
remain gated on the complete three-corner screen.

The VREF-biased native captured prefix reaches 28.772 ns and restores the first
previously lost short pulse. In 24.5–26.5 ns CO peaks at 1.152635 V,
RESTORE0 falls to 0.329422 V, RESTORE1 rises to 1.780347 V, and RXCLOCK spans
−0.014268–1.833817 V. The sampled falling crossing is near 25.837800 ns.
CO_TRACK stays within 0.832336–0.833612 V. Both original 80 ns controls continue
to full reports; this local response is not a complete clock-recovery, aperture,
component or link qualification.

The VREF-biased native captured prefix subsequently reaches 62.890 ns and
fails on the weakest negative pulse at 58.919554 ns (514.802 ps, 83.068 mV).
Over 58.7–60.7 ns CO reaches 1.060980 V and RESTORE0 falls to 0.718403 V,
but RESTORE1 reaches only 0.551259 V and RXCLOCK remains above 1.783342 V.
No falling output crossing occurs before the next same-polarity input crossing
at 61.212597 ns. This identifies a restoration-chain response to investigate;
the complete native reports still remain outstanding.

Next isolated source comparison `receiver_fast_restore_experiment.py` doubles
only the first two restoration stages, retaining the final output driver.
XIB0 changes from `lvds_inv18` to the existing `lvds_rx_restore_mid`, and XIB1
changes from that helper to `lvds_inv18_drive`. The chain becomes P/N widths
8/4 → 16/8 → 16/8 µm; every helper definition, input/decision device, clamp,
unloaded monitor, port and other connection remains unchanged. Stronger drive
of the measured internal wire/gate loads is a hypothesis, not demonstrated
improvement; new source and physical/native evidence remain necessary.

```sh
scripts/env.sh --ngspice python3 scripts/receiver_fast_restore_experiment.py prepare \
  build/diagnostics/clock_restore/50565a94b3b04171
scripts/env.sh --ngspice python3 scripts/receiver_fast_restore_experiment.py run \
  build/diagnostics/receiver_clamp/d2827cbf76f9eb80
```

Service `openlvds-fast-restore-source-screen` queues the same three original
controls under the six-slot budget. Two targeted tests verify only those stage
bindings change, their actual helper widths and unchanged final/control paths.
Original native bias/digital load, 80 ns stimuli and 15–75 ns scoring remain.

VREF-biased native replay `77252e9aa3abb333` now completes both controls.
Captured inputs miss one rising and one falling edge; sharp inputs miss none.
Reanalysis reproduces both cached reports with their captured input/producer
proofs unchanged. The native continuation and downstream follow-up hold for
failed captured recovery. Neither component root `a09b869f2ffff52b` nor link
root `3635f229cd4efe04` has an execution receipt or raw simulation trace. The
candidate is not selected for qualification. The stronger-restoration source
experiment's unchanged control is now running within the same six-slot budget.

The stronger-restoration candidate now has dedicated physical/native producers
with identity `vref_fast_restore` and exact widths [[8,4],[16,8],[16,8]]. Source
and metadata from the earlier 4/2 → 8/4 → 16/8 chain cannot qualify it. The
physical producer retains device connections/order except placing the eight
replica/resistor devices beside the first inverter. Native preparation requires
the exact source, all three complete one-to-one source comparisons, DRC/LVS and
an independent RC audit. It preserves VREF bias, unloaded monitor, nine-port
order, original 80 ns stimuli, native shared bias/digital RX load and score window.
Both native fixtures run concurrently with independent shared leases; simulator
failure in one does not interrupt the other. Downstream dispatch selects this
variant's exact source factory and waveform verifier. Eight targeted source/
physical tests pass, with separate dispatcher and parallel-execution tests.

Service `openlvds-fast-restore-native-continuation` is waiting on the actual
source owner before attempting these stages. Its receipt is under
`receiver_clamp/d2827cbf76f9eb80/native_continuation/`. No stronger-restoration
physical/native result is claimed while source comparisons are incomplete.

The stronger-restoration unchanged control and modified captured source case
now finish with all 47 checked periods containing exactly one output edge;
neither misses an edge. The original sharp control remains in progress.
This source result does not establish extracted restoration performance.

`queue_receiver_followup.py` supplies the next automatic handoff without
changing any captured scientific producer. Service
`openlvds-fast-restore-component-link-queue` waits for the actual native owner
to terminate and its state to report a complete passing replay. Both original
native reports must recover every checked edge before it prepares all 60
schematic/native component fixtures and the original loaded-link diagnostic.
The existing follow-up repeats native waveform/provenance checks and runs
components plus link under the shared six-slot budget. Failed native recovery
holds both. Queue receipts freeze producer code, requirements, upstream
manifest and the saved link inputs; all states explicitly remain unqualified.
Five targeted tests pass, including the wait/prepare/run handoff and failure
path without any downstream launch.

The sharp stronger-restoration source control also completes with exactly one
output edge in every one of 47 periods. All three actual source traces pass
remeasurement before layout. Captured-source latency spans 237.406–494.897 ps,
compared with 260.642–508.359 ps for the earlier VREF chain. The weakest
negative pulse's latency falls from 276.441 to 249.913 ps. Extracted improvement
is not inferred from these source measurements.

Physical root `receiver_layout/64ae7a93d207703b` passes DRC (zero errors), LVS
and independent RC connectivity audit, with 78 devices and nine original
ports. Native network SHA256 is
`b6e0bec697e9ef60f8677d77e1817d9c0e70cd26ab45445ee57ead09a36a4d69`.
Both original controls now run concurrently in
`receiver_replay/93c5ecd2ff603292`, each with a separate shared lease. Original
80 ns stimuli, bias, digital RX load and 15–75 ns scoring are retained.
No native recovery verdict, component/link pass or release is claimed yet.

Loading receipt `receiver_loading/820ed53b4961c8bb` reports incident wire sums
PP/PN/CO 103.856/111.014/44.360 fF and RESTORE0/RESTORE1 47.681/58.947 fF.
The earlier VREF layout's corresponding restoration sums were 33.082/44.245 fF;
stronger stages also increase physical routing load. These sums include full
coupling values but exclude device/MIM capacitance, so they do not establish
effective AC load or dynamic improvement. Native replay remains decisive.

Before any follow-up preparation, host review caught a container-path handoff
bug in the new queue: scientific tools print `/work/OpenLVDS/...`, while the
host must validate the corresponding workspace path. The queue now translates
that exact mount prefix and still rejects wrong artifact kinds, escapes and
lookalike prefixes. Its handoff test uses actual container-style output paths.
Six queue tests pass. The waiting original queue was verified to have no
scientific child, then retired; its receipt is preserved under
`component_link_continuation_history_6438c51`. Service
`openlvds-fast-restore-component-link-queue-v2` uses the corrected producer.
No active SPICE process or captured scientific producer changed.

Further boundary review changes container preparation arguments to repository-
relative paths, matching `env.sh --containall` and its sole repository mount.
The queue's end-to-end handoff test now checks incoming arguments as well as
outgoing container-style paths. All six targeted tests pass. The second waiting
queue was verified childless, retired and preserved under
`component_link_continuation_history_bafce31`. Replacement service
`openlvds-fast-restore-component-link-queue-v3` retains the original native gate.

Both stronger-restoration native controls in `receiver_replay/93c5ecd2ff603292`
now complete: all 47 checked periods in each contain exactly one output edge,
with no missing rising or falling edges. The weakest captured pulse produces
output falling/rising crossings at 59.977506/60.493634 ns. Over 58.7–60.7 ns,
CO peaks at 1.052827 V, RESTORE0 falls to 0.456733 V, RESTORE1 rises to
1.770205 V and RXCLOCK spans −0.016088–1.837766 V. The earlier VREF chain
reached RESTORE1 only 0.551259 V at this pulse and missed the output crossing.
The first short pulse also improves: RXCLOCK falls at 25.682580 ns versus
25.837800 ns previously. Captured latency spans 804.040–1244.370 ps; sharp
latency spans 779.589–1300.195 ps. This is complete replay evidence only.

Actual contained preparation creates all 60 component fixtures in
`receiver_components/58bb3aa28d907d28` and the unchanged loaded-link diagnostic
in `receiver_candidate_link/0dee72b71f4525df`. Before native completion, the
component runner reconstructs all fixtures then holds at the native gate with
no execution receipt or raw trace; `gate_preflight.json` records this check.
Once both native controls pass, the queue starts the existing scientific
follow-up automatically. It independently remeasures native traces before
running component/link diagnostics under the original shared budget.

The first three source static cases (TT at 0/25/40°C) fail. TT/25 fails the
expected-high samples at common modes 0.05/0.2/0.6 V; higher common modes
1.2/1.8/2.35 V pass. At those failed samples the PP−PN differentials are
+56.176/+59.170/+65.250 mV, preserving input polarity, while CO stays at
1.140763/1.137516/1.127988 V and Q stays low. The original baseline source
passes the same samples with CO 0.492830/0.480999/0.451381 V. This localizes
the DC failure downstream of a nonzero differential input, but baseline and
candidate also differ in tail sizing and restoration, so this comparison
does not isolate the clamp as the sole cause. A controlled DC comparison is
needed before selecting a repair. No component gates are relaxed; remaining
component cases and the loaded-link diagnostic continue.

Matched static diagnosis `receiver_static_diagnosis/a6dc85becd2ad09c` confirms
the clamp's causal contribution at TT/25. It clones the completed failing
source fixture and removes only XCLAMP0/XCLAMP1, retaining all transistor
sizes/connections, unused replica monitor, 100 fF load, supplies, common modes,
144 ns transient and original sample times. Parent code/input/runtime proofs
are verified and its actual waveform reproduces the saved failing analysis
before preparation. Both structural tests pass; the actual diagnostic uses a
shared simulator lease and reconstructs the exact intervention before running.

All 12 clamp-removed static samples pass. At common modes 0.05/0.2/0.6 V,
expected-high CO values fall from 1.140763/1.137516/1.127988 V to
0.560407/0.538582/0.490294 V, with Q at 1.8 V. Higher common modes also pass.
This proves the DC repair at this one source corner; it does not establish
clock recovery or other corners. The original qualification reports remain
unchanged and its full component/link campaign continues.

`receiver_unclamped_restore_experiment.py` now selects exactly this unclamped
core for the original clock source screen. Only the two clamp rows are removed
from the preceding stronger-restoration circuit. All helpers, port bindings,
input and decision sizes, unloaded monitor and 8/4 → 16/8 → 16/8 restoration
remain. One structural test proves full source identity with the passing
matched DC intervention, including the unchanged control path. Source root
`receiver_clamp/2c86c40885f97e87`, service
`openlvds-unclamped-restore-source-screen`, queues the same three original
80 ns controls under the six-slot limit. The shared runner's legacy
`clamped_captured`/`clamped_sharp_control` labels refer to modified cases only;
the selected source has no CO clamps. New source-clock and physical/native
evidence are required before this candidate can replace the VREF-clamped one.

The unclamped candidate now has dedicated physical/native producers and a
source-to-native host continuation. Identity `unclamped_fast_restore` requires
`decision_clamped=false`, zero parallel clamp units, no clamp reference, the
unloaded monitor and exact restoration widths [[8,4],[16,8],[16,8]]. The source
gate remeasures all three actual cached traces and checks exact source identity;
each checked period must contain one output edge. Layout moves only the six
unloaded monitor devices beside the first inverter, preserving every device
and the relative order of all others. Native preparation then requires passing
DRC/LVS and independent RC connectivity audit, with exact original nine-port
order, shared bias/digital RX load, both original 80 ns stimuli and scoring.

Six targeted source/physical tests pass, including rejection of VREF-clamped
evidence, repeated edges, wrong restoration widths and nonzero clamp metadata.
Parallel replay tests cover both independent fixtures completing and one
simulator failure without interrupting the other, and require explicit
unclamped result metadata. Service
`openlvds-unclamped-restore-native-continuation` waits on the actual source
owner, with receipts in `receiver_clamp/2c86c40885f97e87/native_continuation/`.
It may attempt physical/native stages only after the complete source screen.
No new physical/native result is claimed while that gate remains incomplete.

The unclamped source screen's unchanged control completes all 47 checked
periods with zero missing or repeated edges. The two modified unclamped cases
remain pending; this control result does not qualify the modified circuit.

Read-only inspection finds timestep collapse in the current VREF-clamped
component case `schematic_receiver_rate_ss_40`. Its active ngspice process
continues using CPU, but saved transient time advances only about 7 ps over
several minutes near 25.84 ns. At the inspected prefix, the last 10,000 saved
samples span 1.244135 ps; timestep range is 1.290824e−17–4.130638e−16 s.
Pins are fixed at P=1.075 V/N=1.325 V, while Q remains within
1.799942466–1.799946481 V. This demonstrates numerical slowdown with no large
output oscillation in that local interval. Internal nodes are not saved in
this rate fixture, so it does not identify the internal cause. The process
remains live, its fixture and tolerances unchanged, and no complete rate
verdict is inferred from the prefix.

The same matched resistor-removal DC experiment is now prepared across all
five required process corners and 0/25/40°C, without a supply sweep. Matrix
`receiver_static_matrix/dc93e971d02bb60c` selects all 15 completed original
source static fixtures. Each child revalidates and remeasures its original
case before cloning the exact two-resistor intervention. The matrix binds
child manifests and their original PVT case selection, requirements and its
own producer. Two targeted coverage tests reject missing, duplicate or
mislabeled cases and substitution by rate/native tests.

Service `openlvds-receiver-unclamped-static-matrix` runs these children
sequentially, each acquiring a normal shared lease only for its simulation.
Cached children remeasure actual original/modified waveforms. Its eventual
`dc_all_passed` verdict applies solely to the original source static thresholds
and common-mode samples; it cannot qualify timing, rate, extracted operation,
aperture or the complete PHY. No aggregate DC pass is claimed before all
15 reports complete.

The modified unclamped captured-clock source case in
`receiver_clamp/2c86c40885f97e87/clamped_captured` now completes the original
80 ns run. Every one of 47 checked periods contains exactly one output edge;
no rising or falling edge is missing. Latency spans 291.167580–403.632674 ps.
The weakest negative input pulse (58.919554 ns, 514.802 ps, 83.068 mV) is
recovered with 403.632674 ps latency; the following rise has 291.167580 ps
latency. Waveform SHA256 is
`1d5f1223b80dace5d56dbd690d3fdb87fb47e2e604ec69221484f5728e86e507`.
Together with the unchanged control this completes two of three source cases.
The modified sharp control is still pending, so the physical/native gate
remains closed. No extracted timing or PVT qualification is inferred.

The VREF-clamped stronger-restoration loaded-link diagnostic
`receiver_candidate_link/0dee72b71f4525df` continues toward its original
188.049 ns endpoint. Read-only prefix analysis at 137.627686 ns uses the
unchanged canonical decoder, original 32-bit sequence, actual launch edges,
0.8–1.05 ns publication window and original sampling-margin requirements.
It reports no correctly ordered preamble. This is a prefix diagnostic, not
the completed official report, and the live run continues unchanged.

A subsequent prefix beyond 140 ns covers all checked 60–120 ns transport
periods: 47 clock and 16 data periods have exactly one corresponding output
edge, without missing/extra edges. Clock latency spans 804.842596–1247.375975 ps;
data latency spans 761.984312–1432.601578 ps. A simple interval count gives
25 pin rises and 24 clock rises; this boundary-sensitive count alone would
misidentify a lost edge, while the same-polarity period matching finds none.
Captures at 73.893010 ns and 83.627458 ns lie 13.933615 ps before the next
data edge and 63.826587 ps after the preceding data edge. Other nearby
captures have preceding-edge separations 171.981–252.398 ps. These are local
timing separations in the observed interval, not official aligned margins:
the decoder has not identified the payload preamble. They support investigating
clock/data relative latency after recovery, without moving the publication
window, changing payload alignment or weakening the 200 ps margin requirement.

The loaded-link diagnostic now completes its original 188.049 ns run and
confirms the prefix result: no correctly ordered payload preamble, with
`sampling_margin_passed=false`. Full waveform SHA256 is
`71970afeaaaed89b0a4e86b0efe9e46c2741b5bfb06fd943da6d7dfe577cbea6`.
The original publication window and strict margin gates remain unchanged.
Component qualification continues independently; this failed link cannot
qualify the receiver or PHY.

The first DC matrix `dc93e971d02bb60c` completes TT/0 successfully, then holds
at cached TT/25. Read-only reconstruction shows that only `manifest_sha256`
differs from the saved report: re-preparation serialized code dictionaries in
a different insertion order and rewrote the same semantic manifest. The
original TT/25 report declares manifest hash `9475432a6118fe95...`, while the
rewritten file is `0ce2ab9d57c9fe89...`. The failed matrix's `retirement.json`
and producer snapshots preserve this history; no scientific child is live.

Preparation now sorts code identities and preserves existing manifest bytes
when canonical JSON is identical, rejecting changed values or JSON types.
Matrix exceptions also write a terminal `held_for_diagnosis` state before
raising. Seven targeted tests pass. Fresh matrix
`receiver_static_matrix/1ac68453f143818d` uses the corrected producer and reruns
the cases; the old cache is not promoted or rewritten to make it pass.
Re-preparation in an independent pinned interpreter preserves all 16 fresh
manifest hashes, recorded in `preparation_recheck.json`. Service
`openlvds-receiver-unclamped-static-matrix-v2` is live. No aggregate DC result
is claimed before all 15 new child reports complete. Full regression:
397 tests, 396 passing and one skipped in the pinned ngspice environment.

All three unclamped source controls now complete with exactly one output edge
in every one of 47 checked periods. The continuation remeasures all source
waveforms and passes the exact-source gate. Physical root
`receiver_layout/cc8468627923265c` then passes zero-error DRC, LVS and independent
RC connectivity audit, with 76 devices and nine original ports. Native network
SHA256 is `5479cc708d5f7c06815b5286b5a632e386d981bfda62057c8bdd4cd08b28352d`.
Both original native controls are prepared in `receiver_replay/7be8ec522902db81`
and queued under separate shared leases, with original 80 ns stimuli, bias,
native digital RX load and scoring window. No extracted recovery verdict is
claimed before both complete.

Loading root `receiver_loading/11bbf00548f00ecc` reports incident wire sums
PP/PN/CO 100.381/107.542/35.917 fF and RESTORE0/RESTORE1 47.758/58.947 fF.
CO was 44.360 fF in the preceding clamped layout. These include full coupling
values but exclude device/MIM capacitance, and cannot establish effective
AC load or dynamic improvement. The fresh corrected DC matrix completes
TT/0 successfully and continues with TT/25; its aggregate remains incomplete.

The VREF-clamped `schematic_receiver_rate_ss_40` case eventually recovers from
its tiny-timestep interval and completes successfully after 2678.057 s. Its
original valid-high/low dwell minima are 825.637/1504.218 ps; waveform SHA256
is `be46e3173926d247e27bc3e6e15eb4903974d7d5a29f7b43f655308158c331e4`.
No process was interrupted and no solver setting or gate changed. All 15
source rate cases pass, while all 15 source static cases fail. Native component
cases continue; this clamped candidate is still disqualified by DC and link.

Both unclamped native controls in `receiver_replay/7be8ec522902db81` now run
under separate shared simulator leases. The corrected matched DC matrix
completes TT/0, TT/25, TT/40 and FF/0 with all static samples passing. Remaining
DC corners and both complete native recovery reports are still required.

The unclamped candidate now has a separate scientific entry point,
`qualify_unclamped_receiver.py`, selecting its exact source factory and native
waveform verifier in the existing component/link checks. This leaves every
captured producer file unchanged. It requires identity
`unclamped_fast_restore`, zero clamps/reference, unloaded monitor, unchanged
input/decision sizes and exact restoration widths. Component and link code
identities capture the selector and native producer files. Two targeted tests
verify exact selection, rejection of clamped/wrong-stage metadata and restoration
of process-local selections after an exception.

Actual contained preparation creates all 60 original component fixtures in
`receiver_components/599036f3ae6f5004` and the original loaded-link diagnostic
in `receiver_candidate_link/83066baeca7824fe`. Component preflight reconstructs
every fixture, then holds at incomplete native recovery with no execution
receipt or raw trace; `gate_preflight.json` binds its manifest, selector and
runtime. Host service `openlvds-unclamped-restore-receiver-followup` waits for
the actual native owner and both complete one-to-one recovery reports. Each
scientific child independently remeasures native waveforms/provenance before
simulation. The original supplies, source/native PVT coverage, loaded payload,
publication window and 200 ps margin remain unchanged. These are prepared
diagnostics, not component/link passes or PHY qualification. Full regression:
399 tests, 398 passing and one skipped in the pinned ngspice environment.

The unclamped native captured prefix reaches 27.380 ns and fails at the first
short pulse. Over 24.5–26.5 ns, CO spans 0.033684–0.676372 V, RESTORE0 stays
within 1.783624–1.811894 V, RESTORE1 within −0.000111–0.000316 V, and Q
within 1.799909–1.799960 V. No falling output crossing occurs. The preceding
clamped fast-restoration circuit recovered this pulse, but had failed DC and
link gates. This localizes the unclamped failure to insufficient CO swing for
the first restoration inverter; both original complete native runs continue.

Next controlled factory `receiver_lvt_restore_experiment.py` retains the
unclamped frontend and restoration widths, changing only the first restoration
NFET model to `sky130_fd_pr__nfet_01v8_lvt`. It clones P8/N4
`lvds_rx_restore_mid` into a new private helper, leaving every existing helper
definition, transistor size, node, later-stage binding and control unchanged.
The pinned PDK at revision `1689ac3f2dc763876eaf967227c7dfe831b031ae` contains
the LVT corner models and Magic defaults/draw/check PCell procedures. This
confirms tool/model availability, not dynamic behavior or manufacturability
of a future candidate layout.

Three targeted tests prove exactly one flattened device model changes, all
sizes/connections remain and the static intervention equals the proposed
clock source. Static root `receiver_lvt_static/6dd7065538873479`, service
`openlvds-receiver-lvt-static-screen`, queues the original TT/25 fixture with
all common-mode samples, supplies, 144 ns run, 100 fF load and thresholds
retained. Its control is the completed clamped fixture; unclamped standard
NFET results remain separately available from the matched DC matrix. The
intervention removes the two clamps and substitutes the first-stage NFET;
it is not labeled a single-factor comparison against the clamped control.
No source clock run is launched before this first DC screen. No static,
clock or native improvement is claimed yet. Full regression: 402 tests,
401 passing and one skipped in the pinned ngspice environment.

The LVT TT/25 static screen completes successfully: all 12 original static
samples pass. Source root `receiver_clamp/4ea0f56c1098842a`, service
`openlvds-lvt-restore-source-screen`, now queues the same three original 80 ns
clock controls. No LVT physical/native or clock improvement is inferred from
this one static corner. The standard-NFET clamp-removal matrix separately
passes all six TT/FF temperature cases; other corners remain outstanding.

Read-only analysis of the completed clamped link also demonstrates a driver
clock-eye issue independent of receiver threshold recovery. Among 49 clock
centers in 60–120 ns, three are below the original RX threshold of 100 mV;
minimum RX magnitude is 85.215528 mV at 104.178171 ns. On the TX side,
four of 50 centers in 58.8–118.8 ns are below 100 mV, with minimum 76.416519 mV.
The original buf_4 reference has corresponding minima 82.592226/73.696449 mV.
These interval diagnostics show the weak clock already exists before the
channel. The TX counts use the RX threshold descriptively; they are not a new
driver qualification limit. Receiver recovery alone cannot close the retained
RX eye gate, so driver timing must also be investigated.

`probe_driver_internal.py` creates `driver_internal/c9c5ccd60b8fbe69` from the
completed clamped link. Its native library, devices, interconnect, waveform
sources, supplies, load, payload and full 188.049 ns transient remain exact.
Only the library path and unloaded voltage observations change. Twelve
additional probes observe the clock/data drivers' AD/AB, L/R and DP/DN named
buses. Hierarchical scope validation passes before simulation. The runner
reconstructs the exact instrumentation, checks parent/code/runtime proofs,
uses a shared lease and requires a complete finite monotonic trace. Results
will retain measured node ranges/crossings, center amplitudes and comparison
against the original external traces; no qualification verdict is supplied.
Two targeted tests pass. Service
`openlvds-native-driver-internal-observation` is queued; no stage timing cause
is claimed yet. Full regression: 404 tests, 403 passing and one skipped in
the pinned ngspice environment.

Both standard-NFET unclamped native controls in `receiver_replay/7be8ec522902db81`
now complete. Captured input misses nine rising and nine falling edges; sharp
input misses none. Reanalysis of both cached complete waveforms reproduces the
reports with unchanged provenance. Captured waveform SHA256 is
`076e6b1981ac34673ae54e8373cfc9c560ad0200e4e795e023ae57ee25729e54`;
sharp SHA256 is `bcd59f60982da67cd23ad4c4f219e6a0dc608892a346aa27f56e33f439359292`.
Native continuation and follow-up hold for failed captured recovery. Neither
component root `599036f3ae6f5004` nor link root `83066baeca7824fe` has execution
receipts or raw traces; neither is admitted to scientific follow-up.

The LVT variant now has dedicated physical/native producers. Its gate requires
all three complete passing original clock source controls plus the completed
passing TT/25 LVT static screen. The static waveform is remeasured, all 12
original DC samples must pass and the exact receiver closure must equal the
declared LVT source. Static source/deck/waveform/manifest/report proofs are
bound alongside the clock source proofs. Identity `unclamped_lvt_restore`
records `first_restoration_nfet_model=sky130_fd_pr__nfet_01v8_lvt`, zero CO
clamps, unloaded monitor and original restoration/input/decision sizes.
Native preparation independently repeats these gates and requires DRC/LVS,
independent RC audit, nine-port order and unchanged native bias/digital load.
Both original 80 ns native controls use independent shared leases.

Nine targeted source/static/physical tests pass, including rejection of
standard-NFET evidence, missing/failed static reports, repeated source edges,
wrong stage sizes and nonzero clamp metadata. Parallel tests cover both
controls and one simulator failure without interrupting the other, with exact
LVT result metadata. The actual completed TT/25 screen also passes the new
closure/provenance gate. Service `openlvds-lvt-restore-native-continuation`
waits on the actual source owner before attempting layout, extraction/audit
and native replay. No LVT GDS or native result is claimed while the source
screen remains incomplete.

Full regression after these gates: 413 tests, 412 passing and one skipped in
the pinned ngspice environment.

Read-only driver-prefix analysis now covers the complete 20–35 ns training
interval. TXCLOCK low widths span 860.706–1065.734 ps. AD/AB are both below
0.9 V for 172.825–173.229 ps and both above 0.9 V for 150.429–152.213 ps.
At a 1.65 V observation level, L low widths span 1612.738–1771.218 ps and R
low widths 781.084–1080.717 ps. DP high widths span 1310.171–1488.294 ps;
DN high widths only 123.759–734.732 ps. DP/DN observed maxima are
3.323564/2.837657 V. These are fixed-level diagnostic crossing widths, not
actual inverter trip voltages or transistor conduction intervals. They point
to complementary converter/output restoration timing as a repair target,
without assigning exclusive causality to the extra input inverter. The five
external traces TXCLOCK, CP, CN, RCP and RCN match the original completed run
exactly on a 5001-point grid over this interval. The full driver observation
continues unchanged to 188.049 ns.

`driver_restore_variant.py` now proposes P64/N24 output restoration in place
of P48/N40, preserving total gate width 88 µm and channel length 0.5 µm.
It adds private restoration/level-converter helpers and changes only the
driver core's selected level converter. Existing helper definitions, input
complement generation, current-mode pair/tail, bridge, CMFB and unrelated
circuits remain unchanged. The hypothesis is stronger pull-up drive and a
shifted switching point can recover the short DN high pulse; it is not a
demonstrated improvement.

Comparison `driver_restore/cff36fa92d24e01b` places both original and modified
schematic driver closures into the same saved native link. The schematic
control is necessary to distinguish ratio changes from removing driver wire
parasitics. All other circuits are native and closure-protected. Supplies,
input waveforms, load, 32-bit payload, original publication window, strict
200 ps sampling margin and full 188.049 ns transient are retained. Only
library bindings, corresponding source-driver nodeset names and unloaded
DP/DN observations are rebound. Actual preparation validates the protected
closures and hierarchical nodes. Three targeted structural/fixture tests pass.
Service `openlvds-driver-restore-source-comparison` starts both independent
cases with separate shared leases, allowing the other to finish after one
simulator error. Reports explicitly remain source-driver diagnostics and
cannot establish native driver or PHY qualification. No performance gain is
claimed before both reports complete.

The LVT source screen's unchanged control and modified captured-clock case
also complete all 47 checked periods with one output edge each. Modified
latency spans 292.324739–377.719831 ps; the weakest negative input pulse is
recovered with 377.719831 ps latency. The sharp control remains pending, so
the LVT physical/native gates stay closed. Full regression: 416 tests,
415 passing and one skipped in the pinned ngspice environment.

The separate unclamped follow-up entry point now registers both standard and
LVT profiles. Each selects its exact source factory and native waveform
verifier; the declared first NFET model must match that profile. Mixed
standard/LVT metadata is rejected, and each scientific code identity captures
the selected producer set and selector. Three selector tests pass, including
LVT dispatch and model mismatch rejection. The earlier failed standard-device
follow-up is terminal, and live manifests were checked not to capture this
selector before editing it. Existing scientific producer files remain unchanged.
This prepares the dispatch path only: no LVT component/link fixtures are
created before audited physical/native evidence exists. Full regression:
417 tests, 416 passing and one skipped in the pinned ngspice environment.

Native DLL TT/25 acquisition in `dll_qualification/15cac0ba813a9333/loop_tt_25`
now completes the original 1700 ns transient and passes the original
1200–1500 ns measurement-window gates: control ripple 1.671669 mV,
feedback error 10.840051 ps and quarter delay 659.955500–660.204682 ps
(625 ± 100 ps requirement). Cadence and omitted-pulse recovery also pass.
Unwrapped marker sections are 660.036865, 649.233106, 639.479979 and
640.925721 ps; marker total is 2589.675671 ps. Mean power is 6.897270 mW,
recorded here without claiming complete power/headroom qualification.

Deck, waveform and raw SHA256 values reproduce the actual files. Waveform
SHA256 is `74bcbe8432081448308cb2b7dff6cada2d8c20a9bdefc407215707672c8b0ee8`;
raw SHA256 is `f21c06586f3720a21d2bdd1954b4a8d3e082b1057504a793b4e26459bf2961ae`.
Together with SS/0 and all 21 selected static offsets this yields 23 passing
native screen cases. FF/0 acquisition is queued under the shared six-slot
budget. The measured three-corner native model, remaining 312 fixtures and
all required native stability/PHY gates stay held until the full screen passes.


## 2026-11-02: 16 pF source acquisition complete

The three full 1500 ns SS/0, TT/25 and FF/0 source cases in
`dll_architecture/368259f7b02c5fdc` now all pass. Independent FF/0 receipt
`completed_source_ff0_observation/summary.json` remeasures both matched C4/C16
waveforms and reproduces the original metrics. C16 gives 6.375279 ps maximum
feedback error, 10.267562 ps quarter-phase error and 0.907130 mV control ripple;
the corresponding C4 values are 6.492792 ps, 8.012954 ps and 3.162580 mV.

The completed source admission unlocks fresh native context
`dll_qualification/1a29b2389cee3d01`. The original 24-case native screen is
running with three actual shared-slot leases at most. Remaining fixtures stay
held for fresh native stability evidence. No full native DLL or PHY admission
is implied by this source result.
