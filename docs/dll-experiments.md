# Pulse-area DLL experiments

The experiment compares a repaired charge pump and NMOS control follower with
an averaged-PFD current-mirror OTA integrator. Both use independently averaged
UP/DN signals for phase and activity monitoring. The active PHY is unchanged
until a candidate passes qualification. Supplies remain fixed at 3.3/1.8 V,
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
