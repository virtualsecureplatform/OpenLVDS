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
