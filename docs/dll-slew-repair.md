# DLL slew repair

Approved direction: prefer standard cells, then use an analog input receiver
only if the bounded standard-cell search fails. Verify both unequal-slew
directions across all fifteen PVT points. Supplies remain fixed at 3.3/1.8 V;
temperatures remain 0/25/40 C and frequencies 390/400/410 MHz. No CDR.

## Current evidence and first implementation checkpoint

The native SS40 +50 ps / 20-200 ps and -50 ps / 200-20 ps cases falsely
assert BAD. The completed three-case `buf_4` diagnostic independently verifies
as failed: +50 ps becomes 97.414 ps after conditioning. Both +/-150 ps fault
checks still pass. Preserve these controls and their original producer files.

`calibrate_dll_slew_bench.py` now prepares thirteen calibration cases in
`build/diagnostics/dll_slew_bench/85c249e5e4f7d185`: ten native controls
(zero, +/-50, +/-150 ps in both unequal-slew directions) and the three
completed buffered controls. It retains the native PFD/shared bias, uses the
schematic monitor/local bias, and omits VCDL/OTA circuitry. Classification
must match, UF/DF and their difference must agree within 5 mV, conditioned
phase within 5 ps, and engine elapsed time must improve by at least 2x.
Every comparison requires complete finite raw/export agreement. Independent
verification remeasures all outputs and checks their hashes. A failing
calibration holds screening; it does not admit the surrogate.

All four proposed source frontends are generated from pinned PDK cells:
`clkbuf_4`, `clkbuf_8`, tied-input `nor3_1` followed by `inv_4`, and tied-input
`nor4_1` followed by `inv_4`. Their generation is implemented; candidate
simulation, ranking and physical admission remain pending calibration.
The reverse-slew draft is retained with a forward-success dispatch gate;
no further `buf_4` experiments are admitted after the failed forward result.

## Remaining execution gates

1. Screen the four candidates at SS40 first, then expand survivors across
   all PVT points. Retain valid 0/+/-50 ps and fault +/-150/300 ps tests;
   require the mean UF-DF zero crossing to lie between -20 and +20 ps.
   Check clock integrity, reset/disable behavior and power. Rank by worst
   timing offset, then power/area. Use the full native bench if calibration
   fails. Do not widen the health window to hide offset.
2. Implement the selected frontend physically with preserved named cells
   and matched routing. Require DRC, strict LVS and fresh RC. Seed native
   SS40 failures and fault controls before full expansion. Retain the old
   suite and add both unequal-slew directions at every PVT point at 400 MHz,
   including +/-20 ps balance tests; test frequency extremes at SS40 and
   the worst screened corner. Deduplicate cases through a versioned coverage
   profile rather than a literal 336-case count.
3. If all standard-cell candidates fail, prototype matched differential
   input receivers against shared VDDD/2, with shared-reference current
   bias and restoring CMOS outputs. Start the approved four-variant grid
   (approximately 140/280 uA tails and 20/40 um input widths). Qualify the
   same timing, headroom and terminal-voltage limits. Version any private
   PB/VDDIO interface additions; keep the public DLL interface unchanged.
4. Repeat acquisition, all-PVT stability, recovery, readiness and operating
   point/stress checks for the selected physical circuit. Preserve 60-degree
   phase margin and 6 dB gain margin. Then update staging/phase replay and
   complete the existing link and RC release gates. No old electrical
   qualification transfers automatically.

All real simulations use individual six-slot dispatcher leases, with at most
two diagnostic workers. Partial runs are retained without retries. Commit
and push meaningful checkpoints; a source experiment is never PHY release.

## Bounded screening implementation

`screen_dll_slew_frontends.py` implements the first 56-case SS40 screen:
four candidates, both unequal-slew directions, and seven phase offsets
(-150, -50, -20, 0, +20, +50, +150 ps). It requires the terminal calibration
receipt and independently remeasures numerically completed calibration.
Passing calibration selects the isolation bench; a failed accuracy/speed
gate selects the full native DLL/PFD/bias bench. Original native controls
are reused rather than rerun. Partial calibration cannot create a screen.

Candidate checks retain the original phase/BAD limits, require one-to-one
rising/falling clock transport and valid delivered levels, and require
monotonic mean UF-DF with opposite signs at -20 and +20 ps. Survivors are
ranked by estimated worst zero offset, using power then actual PDK LEF cell
area to resolve timing ties within 2 ps. Footprints for the two input paths
are 15.0144, 27.5264, 22.5216 and 25.024 um2 for clkbuf_4, clkbuf_8,
nor3/inv4 and nor4/inv4 respectively. Independent verification binds every
output hash and remeasures all results. No source result selects hardware.

`continue_dll_slew_screen.py` binds the exact live calibration invocation
and immutable manifest before waiting without an outer SPICE lease. The
prepared handoff is `dll_slew_screen_followup/706a5b0e1efa5458`. A restarted,
missing or failed owner cannot dispatch; successful owner completion still
requires the scientific terminal report. It prepares the selected bench,
runs under individual P2 leases with two workers, and independently verifies
the completed screen. Partial work is retained without retries. No-survivor
results hold subsequent promotion rather than claiming successful repair.

The first two calibration controls reproduce both zero-phase health and the
native +50 ps false-BAD failure with approximately 2.28x engine speedup.
The other eleven controls remain required. Candidate screening, expanded
PVT coverage, physical implementation and analog fallback remain unfinished.

The full regression at this checkpoint passes 1,285 tests without skips.

## Versioned repaired-DLL coverage

`dll_slew_coverage.py` defines `dll-slew-repair-v1`. Native coverage is the
union of the complete original signature set (including captured clocks and
fast/native comparisons) with both unequal-slew directions at every PVT point
at 400 MHz and offsets -150, -50, -20, 0, +20, +50, +150 ps. It also adds
390/410 MHz at SS40 and the measured worst screened PVT, deduplicating when
those corners coincide. Its descriptor binds the version, worst PVT and
canonical signature-set hash. Verification rejects missing, duplicate or
unexpected cases and preserves the OTA and stuck-fault requirements.

The profile does not use a fixed task count as an admission criterion. It
does not modify or requalify the running original DLL campaign. The selected
physical frontend's future qualification and staging adapters must consume
this profile and remeasure their own evidence before promotion.

## Survivor expansion and automatic handoff

`expand_dll_slew_frontends.py` admits only independently remeasured SS40
survivors. Each survivor receives 1,215 source-frontend experiments: all
fifteen PVT points, 390/400/410 MHz, 100/100, 20/200 and 200/20 ps slews,
and offsets 0, +/-20, +/-50, +/-150 and +/-300 ps. The expansion always
uses the full native PFD, bias and analog DLL loading; SS40 isolation
calibration does not establish surrogate accuracy at other PVT points.
Shared immutable libraries avoid copying the native model into every case.

Each complete curve must pass the original health/fault limits and clock
integrity checks, remain monotonic and bracket zero between -20/+20 ps.
Ranking uses the worst estimated zero offset across PVT/frequency/slew,
then measured power and cell area for timing ties within 2 ps. The report
identifies the actual worst PVT for subsequent physical coverage. Independent
verification rehashes and remeasures every output. Reset/disable checks,
physical implementation and all loop/release gates remain separate work.

`continue_dll_slew_expansion.py` binds the original bounded-screen owner's
invocation and terminal receipts. The original prepared handoff was
`dll_slew_expansion_followup/c7d283a388cd40e0`, owned by
`openlvds-dll-slew-expansion-followup.service`; it is now held after the
upstream transient-owner failure described below. Its design waits without an outer
lease, then prepares/runs/verifies admitted expansion with two individual
P2 workers. No-survivor evidence holds for the approved analog fallback;
partial output and failed/restarted owners cannot dispatch or retry.

At this checkpoint four of thirteen calibration cases pass, with measured
speedups of 2.16-2.29x. Calibration and bounded screening remain required
before expansion dispatch. Preflight checked all 4,860 possible expansion
decks against the actual native library and PDK, including probe existence,
corner/temperature directives and absence of duplicate subcircuits; this
performed no new electrical simulations. The complete regression passes
1,299 tests without skips (`build/dll-slew-expansion-tests.log`).

## Preserved PFD frontend source and connectivity policy

`pfd_slew_policy.py` generates each of the four bounded frontend topologies
around the unchanged fast-reset core. REF and FB use identical named cells,
with keep/dont_touch attributes and kept intermediate wires. Public ports,
flip-flops, output drivers and the single-AOI reset equation are retained.
The new checker verifies both source and final flat netlists: exact cell
types and tied NOR inputs, exactly the intended loads on every clock net,
and no bypass, cross-coupling, added logic, declaration initializer or
behavioral primitive. It accepts physical fill/tap cells and split tie
cells, and rejects incorrect power-pin connections. The original policy
files remain unchanged.

`prepare_slew_pfd.py` independently verifies the completed native expansion
before generating the ranked winner's physical source. It captures the
source, required extra blackbox, existing PFD blackboxes and constraints,
along with the measured worst-PVT coverage recipe and complete source
evidence hashes. It refuses no-survivor/partial evidence and changed
generated files. No winner artifact has been prepared while screening is
pending. This helper prepares source only; matched placement/routing, zero
DRC, strict LVS, fresh extraction and the expanded native qualification
remain required.

All four source variants successfully elaborate against actual SKY130 TT
Liberty in Yosys and retain the required topology after elaboration:
`slew_pfd_elaboration/07cbd666da7f246c`. The policy producer is archived
there and the generated sources/netlists/logs are hash-bound. An earlier
preflight using only the legacy explicit blackbox files lacked `dfrtp_4`;
that failed output is retained under `8875e81b675e3eba`. The successful
preflight reads the complete PDK Liberty, as the physical synthesis flow
does. These checks do not perform placement or electrical simulation.
The complete regression now passes 1,307 tests without skips
(`build/dll-slew-pfd-policy-tests.log`).

## Paired placement and final geometry checks

`slew_pfd_floorplan.py` derives paired input-chain placement targets from
the existing PFD's actual DEF row grid. The REF and FB conditioners,
restoring inverters where present, flip-flops and output buffers use the
same orientation and translated locations. The present grid yields a
21.76 um vertical translation. REF/FB external pin shapes, routing layer,
orientation and relative row-center locations are also matched in a DEF
pin template. The reset gates occupy the middle row. The helper refuses
irregular/narrow grids, differing row orientation and malformed clock pins.

Its configuration uses the installed flow's `MANUAL_GLOBAL_PLACEMENTS`,
strict `FP_DEF_TEMPLATE` pin matching and `RSZ_DONT_TOUCH_LIST`. Clock tree
insertion, input/output buffering and post-placement/routing resizer
repairs are disabled. The final-DEF checker verifies the actual cell
masters, pair translations/orientations and external pin coordinates and
shapes. A legalizer move that breaks matching is a failed check, even if
the requested initial placement was matched. Matching placement does not
prove matching routed RC; the checker explicitly leaves route matching
and physical/PHY admission false.

Configuration preflight against the actual baseline DEF and the installed
LibreLane Classic constructor accepts all four generated configurations:
`slew_pfd_floorplan_preflight/432b6fbd46d2f329`. The producer is archived,
and configuration/source/pin-template hashes are captured. This only
loads configurations; it performs no physical flow. The prior configuration
loader API failures remain in their original preflight directories.
The complete regression passes 1,311 tests without skips
(`build/dll-slew-floorplan-tests.log`). Calibration remains live with seven
of thirteen cases passing at this checkpoint. Winner selection, the actual
physical-flow adapter, routed matching/DRC/LVS/RC evidence and all electrical
qualification gates remain unfinished.

## Gated physical-run adapter

`harden_slew_pfd.py` prepares and runs an isolated LibreLane placement/route
diagnostic from an admitted `slew_pfd_source` artifact and the retained
baseline row-grid/configuration evidence. It captures generated source,
combined frontend/PFD blackboxes, shared models, constraints, the DEF pin
template, placement targets and tool/Liberty hashes. Producers are archived;
re-preparation preserves exact bytes. It uses the paired floorplan settings
above and rechecks the actual final netlist and DEF after the flow.

Passing requires successful flow completion, all final artifacts, exact
frontend/reset connectivity, paired placement/pin geometry and explicit
zero final routing/Magic/KLayout DRC counts. Missing DRC metrics cannot pass.
Independent verification rechecks the input context, output hashes,
connectivity, geometry and metrics. The input archive also retains the
existing `digital_candidate_rc.captured_inputs` contract, with the new
frontend blackbox definitions inside the captured PFD blackbox file.

This is a physical diagnostic, not final physical admission: strict
extracted LVS, matching of routed RC and the expanded native electrical
qualification remain required. Existing/partial flow output is never
restarted. No physical winner artifact is prepared or run while the source
screen and expansion gates are pending.

Use the pinned `--tools --ngspice python3` environment for this adapter.
The installed LibreLane Python lacks NumPy, so the adapter uses only the
standard library and connectivity helpers. Its source-admission validator
runs with the container's existing `/usr/bin/python3`, with incompatible
Nix Python paths removed. Runtime preflight confirms both interpreter paths
load successfully and that missing source evidence is rejected without a
physical run (`build/dll-slew-physical-tool-context.json` and
`build/dll-slew-physical-validator-preflight.json`). No frozen scientific
producer or active simulation was changed to resolve this environment issue.

The complete regression passes 1,318 tests without skips
(`build/dll-slew-physical-adapter-final-tests.log`). All ten native
calibration comparisons now pass; the three buffered comparisons remain
pending at this checkpoint. This reproduces the original failures for
calibration and does not claim those phase-detector failures are repaired.

## Fresh RC and strict LVS adapter

`extract_slew_pfd.py` creates a separate `slew_pfd_rc` context after the
physical-run verifier passes. It preserves the routed artifact and copies
its exact physical receipt/configuration for the existing extractor;
`strict_summary.json` is the new extraction-stage result. Inputs, producers,
PDK cells/setup/technology files and extraction tool binaries are bound.
Existing or partial local/global extraction output is held without retries.

The verifier requires the actual GDS/source binding, all eight named public
PFD terminals, complete native RC metadata and strict LVS without property
errors. It regenerates the PDK transistor reference, collapsed-wire model
and strict setup for comparison. It also independently repeats exact
degree-four resistor elimination in temporary files and compares the
complete resulting model and reduction metadata. Every transistor,
capacitor and public terminal must remain unchanged. Output hashes cover
the raw/reduced model, extraction records, setup, reference and tool logs.
Routed matching and native/loop/stability/PHY admission remain false.

Baseline-only preflight `slew_pfd_rc_preflight/cf008b871dc4c96a` rechecks the
retained fast-reset PFD's actual extracted model and strict LVS evidence,
with archived producers and bound input/output/tool hashes. It confirms
the new checker can reproduce the exact reduction in the installed tools
environment; it does not qualify any repaired frontend. No new physical
winner or extraction artifact has been prepared yet.

The full regression passes 1,325 tests without skips
(`build/dll-slew-strict-rc-tests.log`). All thirteen isolation calibration
comparisons now pass and independently reverify, with 2.16-2.32x engine
speedup. The original transient-owner handoff held when systemd unloaded
the successfully completed calibration service; its evidence is preserved.
The independently admitted 56-case isolation screen is now
`dll_slew_screen/10795eedc551acd1`, running under the fresh retained service
`openlvds-dll-slew-screen-calibrated.service`.

## Retained direct-screen handoff recovery

The completed calibration independently verifies all thirteen comparisons
and its scientific summary passes. The original systemd calibration unit
had `RemainAfterExit=no`; systemd collected it after successful completion,
so its original waiter correctly held on `LoadState=not-found`. The chained
expansion waiter then held on that waiter's failed exit. Both failed handoff
artifacts and all completed simulations remain unchanged. Recovery used
the completed scientific calibration gate to prepare the fresh bounded
screen above; it did not repeat calibration or retry partial SPICE output.

`continue_dll_slew_verified_expansion.py` follows the direct screen under
`openlvds-dll-slew-screen-calibrated.service`. Preparation explicitly requires
`RemainAfterExit=yes` and captures the live PID/invocation and manifest.
Only the same retained invocation, successfully exited with a terminal
scientific report, can proceed. It independently verifies the entire screen
before preparing expansion. No survivors hold for the approved analog
fallback; survivors run under the existing two-worker native expansion and
are independently verified afterward. No outer SPICE lease is held.

The active recovery handoff is
`dll_slew_verified_expansion_followup/b7020ea7934013b6`, owned by
`openlvds-dll-slew-verified-expansion-followup.service`, also retained after
exit. A real two-second service lifecycle test confirms the invocation ID
remains available and successful exit is recognized
(`build/dll-slew-retained-owner-probe.json`); that test service was then
stopped. The full regression passes 1,329 tests without skips
(`build/dll-slew-retained-handoff-tests.log`).

The 30/30 long compensated-driver component cases also completed and the
original followup independently verified the passing report. The native
driver matrix and its joined payload restoration remain pending; this
does not admit a complete PHY.

## Receiving-gate observations for native PFD checks

`pfd_native_clock_observations.py` maps delivered clocks to the actual
receiving flip-flops' MOS gate nodes. The physical conditioner will reside
inside the PFD macro, so its public REF/FB pads cannot stand in for the
delivered FF clock after routed RC. The resolver checks the actual DEF
cell master/bounds against PDK LEF, derives the extraction coordinate scale
from both public input-pin rectangles, and follows the GDS clock-pin
equivalences. Matching MOS model/geometry before and after `extresist`
identifies every separate native gate node, including both CMOS branches.

Each selected gate must remain inside its receiving flip-flop and exist
as a MOS gate in the exact native model. Missing branches, wrong cells or
geometry, pad substitutions and cross-clock shorts fail. No ideal alias,
resistor short or guessed `.tN` terminal is introduced. The probe helper
requires an explicit instantiated hierarchy prefix; subsequent native
fixtures must validate these nodes against their actual assembled library.
This supplies observation provenance, not routed-matching or electrical
admission.

Baseline-only preflight `pfd_clock_observation_preflight/c9a3fc3fd33af908`
resolves the retained PFD's actual FF inputs to `REF.t0`/`REF.t1` and
`FB.t0`/`FB.t1`, with archived producers and bound DEF/LEF/extraction/model
hashes. These particular nodes are not reusable in a different physical
frontend. The resolver must run again on the winner's fresh extraction.
The full regression passes 1,335 tests without skips
(`build/dll-native-clock-observation-tests.log`).

The bounded source screen currently has four complete `clkbuf_4` cases
without numerical errors. Their individual health/fault checks pass, but
UF-DF is +24.042 mV at -20 ps and nearly zero at -50 ps (-0.062 mV), so
this candidate already violates the required -20/+20 ps zero bracket.
The complete planned screen remains running; other candidate results and
physical selection are still required. No BAD threshold was widened.

## Native repaired-DLL model assembly

`assemble_slew_dll.py` consumes the winner's completed strict PFD RC/LVS
receipt and validates the retained 16 pF native DLL model context. It
replaces only `lvds_pfd_physical` and its eight-terminal public wrapper,
using the actual extracted pin order. An exact comparison of all other
definitions protects the analog DLL, delay line and shared bias. Native
model/probe evidence, PDK collateral and producers are captured in a fresh
`dll_slew_native_model` context; the retained qualification remains untouched.
Its old electrical results do not transfer to the changed circuit.

The assembler resolves receiving MOS gate observations again from the new
PFD's own DEF/LEF and pre/post-resistance GDS extraction. Both phase-test
(`XP:XPHYS`) and full-DLL (`XL:XCORE:XPFD:XPHYS`) hierarchy paths must resolve
against the actual composed model. The existing scientific interpreter
validates the retained context and confirms exactly one endpoint reference;
the assembler itself runs in the installed tools environment without NumPy.
No aliases or active bias generators are added.

Baseline-only preflight (`build/dll-slew-native-assembly-preflight.json`)
confirms the native reference admission, four phase and four loop receiving
gate probes, and one shared reference. It performs no transient simulation
and does not prepare a winner artifact while the source screen is pending.

## Native seed pilot

`pilot_native_slew_dll.py` prepares eighteen fresh SS40/400 MHz cases only
after native model assembly verifies. It dispatches the historical +50 ps
20/200 ps and -50 ps 200/20 ps false-BAD cases first. Both directions then
cover 0, +/-20, +/-50, +/-150 and +/-300 ps. The original native analog
loading, single 35 uA endpoint reference, 160 ns stop, 5 ps print, 20 ps
maximum step and 120-160 ns scoring window are retained. No old transient
success is reused as electrical evidence for the new PFD.

Every actual receiving MOS gate must transport exactly one rising and one
falling event per cycle, with valid levels in every scored cycle. Rising
and falling delivery delay is measured separately at every native gate.
The original phase/BAD limits remain mandatory. Both complete UF-DF curves
must be monotonic and bracket zero between -20/+20 ps; individual point
success cannot conceal servo bias. Independent verification rechecks full
raw/export agreement, output hashes, source/probe/fixture regeneration and
the aggregate. The selected assembled model must match byte for byte.

The pilot uses two individual P1 dispatcher leases and never retries partial
output. A passing pilot only admits the next native qualification step;
expanded all-PVT phase coverage, reset/disable controls, acquisition,
stability/recovery/readiness, stress and PHY gates remain required. No
pilot has been prepared or dispatched while frontend selection is pending.

Baseline-only fixture preflight
`native_slew_pilot_preflight/47f12630507ac2bd` validates all eighteen decks,
including the actual four receiving-gate probes and one shared reference,
without any transient run. The full regression passes 1,346 tests without
skips (`build/dll-native-pilot-tests.log`). The bounded source screen has
now reproduced both false-BAD failures in `clkbuf_4`, in addition to its
failed zero bracket; other frontend results remain required.

## Reset/disable protocol baseline

`pfd_control_protocol.py` adds a versioned `pfd-reset-enable-v1` protocol
to the complete loaded 160 ns phase fixture. Both clocks continue while
PD_ENABLE is initially low, is asserted and disabled again, and while
RESET_N is asserted and released dynamically. Digital control transitions
do not change the fixed 3.3/1.8 V supplies. Observed control-pin edges must
match within 5 ps. After a half-period clearance allowance, both actual
UP/DN outputs must stay below 0.36 V in the disabled/reset windows, while
each observed clock still has rising/falling events and valid levels.
Both controls must be released in the unchanged 120-160 ns phase window.
Ordinary phase-health recovery and receiving-gate transport are checked
separately; a passing clearance check cannot replace them.

`probe_native_pfd_controls.py` prepares one new matched-slew SS40/400 MHz
baseline using the retained, unchanged native DLL/PFD/bias model. It binds
the actual GDS/LEF gate observations, donor fixture, normalized protocol
stimulus, aliases and producer archive. The phase fixture retains its 5 ps
print and 20 ps maximum step. This is a new control protocol experiment,
not a repeated original phase case or an admission of a repaired frontend.
The prepared artifact is `pfd_controls_baseline/b851f13d37380489`, running
under `openlvds-pfd-reset-enable-baseline.service` with one individual P2
lease and retained service ownership. Partial output cannot retry.

The protocol and baseline adapter pass the complete 1,353-test regression
without skips (`build/pfd-controls-baseline-tests.log`). The real baseline
simulation remains required. Source-survivor all-PVT control coverage and
its physical-source admission gate still need to consume this protocol;
reset/disable behavior is not yet qualified for any new frontend.

The bounded source screen has 24/56 complete cases without numerical
errors at this checkpoint. Both `clkbuf_4` and `clkbuf_8` fail the zero
bracket and false-BAD requirements, so drive strength alone is not an
adequate repair. The NOR/inverter candidates remain queued. Separately,
the compensated coupled restoration
`compensated_coupled_restoration/40f1b82bf02b80fb` completed its strict
12 ns/1 ps numerical screen with return code zero and verified complete
raw/export data. Its original 188.049 ns payload run is now running; no
payload-restoration or final PHY success is inferred from the short run.

The reset/disable baseline subsequently completed and independently
remeasured as passed (`build/pfd-controls-baseline-verified.json`). The
worst observed UP/DN maxima are 0.425 mV during initial disable, 5.026 mV
during dynamic disable and 6.715 mV during dynamic reset, all below the
unchanged 360 mV low limit. All six observed clocks (two pads and four
actual receiving MOS gates) continue with valid levels/events in every
hold window. Control-edge timing and final receiving-gate transport pass;
phase health recovers with BAD below 1.22e-8 V in the scoring window.
This verifies the protocol and retained matched-slew circuit at SS40 only.
It does not admit any new frontend or replace its required PVT/control
qualification.

## Source-survivor reset/disable qualification

`qualify_slew_frontend_controls.py` consumes the independently verified
native source expansion and passing reset/disable baseline. Every source
survivor receives all fifteen process/temperature points at 400 MHz and
390/410 MHz at TT25, SS40 and its measured worst source corner. Each point
includes matched 100/100 ps and both 20/200, 200/20 ps clock slews. After
deduplication this is 57 or 63 new control cases per candidate. Supplies
remain fixed; the temperature set remains 0, 25 and 40 degrees Celsius.

The protocol retains the native PFD, bias and complete analog loading.
During each disable/reset hold, clocks must continue at both pads, both
conditioner outputs and all four actual receiving MOS gates. Released
controls must recover original phase health and receiving-gate transport.
The recovered UF-DF value must remain inside that same source candidate's
measured -20/+20 ps bracket. A control failure filters the candidate from
the original measured source ranking; it cannot reorder survivors or
widen timing/BAD limits.

Preparation and independent verification regenerate every fixture and
observation from bound donors. Producer/model/deck hashes are checked at
dispatch and completion. Two workers use individual P2 leases; partial
output cannot retry. No new control campaign is prepared while source
selection remains pending.

Fixture-only preflight `slew_controls_fixture_preflight/81d2f14a014a09b5`
compiled all twelve combinations of four source frontends and three slew
pairs against the retained complete native library. The four receiving
gate observations resolve in every fixture, with explicit observed
RST/ENABLE and the original timing. This preflight ran no transient and
provides no candidate electrical admission.

## Control-qualified physical source

Use `prepare_controlled_slew_pfd.py source CONTROL_ARTIFACT` for the new
physical source path. It independently verifies the complete controls,
selects the first surviving candidate in the measured source ranking and
retains its actual worst-PVT coverage recipe. It generates the same
preserved named-cell source, blackboxes and constraints as the existing
source policy, with an additional `source-slew-with-controls-v1` admission
profile. A phase-only source artifact cannot satisfy this profile.

Use the same adapter's `physical SOURCE_ARTIFACT --baseline BASELINE`,
`run PHYSICAL_ARTIFACT` and `verify PHYSICAL_ARTIFACT` actions for subsequent
placement/routing. Each action validates the controlled source before
delegating to the retained physical implementation. In the physical tools
environment, scientific validation runs through the container system
Python with Nix Python paths removed. The physical adapter itself imports
without NumPy; that behavior passed the actual installed tools preflight.
Old evidence-bound producers remain unchanged.

Source control success still requires fresh physical matching, zero DRC,
strict extracted LVS, RC, native electrical and complete PHY qualification.
There is no prepared winner or physical run while source screening and
expansion remain pending. The source/control adapters pass all 1,361 tests
without skips (`build/slew-frontend-controls-tests.log`).

## Retained control/source handoff

`continue_slew_frontend_controls.py` joins the retained verified expansion
controller to the new controls and source admission. It binds the upstream
service invocation, requires retained ownership, checks its independently
verified expansion receipt and rechecks the passing native protocol
baseline. It then prepares, runs and independently verifies the complete
source-control campaign. Only a control-qualified survivor can generate
physical source; the generated source is independently validated again.
The controller never holds an outer SPICE lease or starts placement/routing.
Missing survivors, owner/context changes and partial scientific output
hold for diagnosis without retry.

Handoff `slew_frontend_controls_followup/42e0cae167bfdd1c` is waiting under
`openlvds-slew-frontend-controls-followup.service`, with
`RemainAfterExit=yes`. It follows the healthy
`dll_slew_verified_expansion_followup/b7020ea7934013b6` invocation; existing
campaigns and producers remain unchanged. Its coverage and failure-path
checks pass the complete 1,365-test regression without skips
(`build/slew-controls-handoff-tests.log`).

At this checkpoint the bounded screen has 36/56 complete cases and no
numerical errors. NOR3/inverter now also reproduces false BAD at +50 ps
and fails the +/-20 ps zero bracket. At zero external phase with 20/200 ps
input slews, the measured median differential rising delivery delays are
45.09 ps (`clkbuf_4`), 46.13 ps (`clkbuf_8`) and 41.21 ps (`nor3_inv4`).
Faster output transitions alone have not removed the input-slew timing
bias. Remaining NOR4 results are still required before the conditional
analog fallback begins. The coupled payload continues running separately.

## Fresh extracted-native reset/disable campaign

`qualify_native_slew_controls.py` closes the control-check gap between the
source prototype and the changed routed/extracted circuit. Preparation
requires the complete eighteen-case native pilot and restoration of both
historical false-BAD cases. Independent control verification rechecks that
pilot admission. Old source controls and the retained native baseline do
not count as electrical results for the repaired physical PFD.

Each selected model receives reset/disable tests at all fifteen PVT points
at 400 MHz and at 390/410 MHz at TT25, SS40 and the measured source worst
corner, using matched and both unequal clock slews. Deduplication gives 57
or 63 cases. Fixtures retain the complete native model, one endpoint bias
reference, fixed supplies, original 160 ns/5 ps/20 ps timing and recovered
120-160 ns scoring window. The actual four receiving MOS gate probes are
bound to the selected assembly's extraction; they must keep switching with
valid levels while both UP/DN outputs clear under reset/disable. Original
phase health and native clock transport must recover after release.

Preparation/regeneration binds every deck, alias, producer archive, parent
pilot result and full native model. Two workers use individual P1 leases;
existing partial output cannot retry. `prepare NATIVE_PILOT`, `run ARTIFACT`
and `verify ARTIFACT` are scientific-environment actions, for example via
`scripts/env.sh --ngspice /usr/bin/python3 scripts/qualify_native_slew_controls.py`.
No campaign is prepared or dispatched before a physical repair and passing
native pilot exist.

Baseline-only preflight `native_slew_controls_preflight/26753998275a83d5`
compiles all 63 fixtures against the retained complete extracted model,
checking all PVT/frequency directives, actual receiving-gate observations,
explicit observed controls and single shared bias. It runs no transient
and selects no repaired candidate. This control campaign does not replace
expanded native phase/zero-balance coverage, acquisition, measured
stability, recovery/readiness, operating-point stress or PHY qualification.

The complete regression passes 1,370 tests without skips
(`build/native-slew-controls-tests.log`), including rejection of failed
pilot admission, independent clearance/recovery failures, incomplete or
duplicated case results and partial-output retries.

## Complete native phase and stuck-fault partition

`qualify_native_slew_phases.py` implements the entire native phase/logic
partition of `dll-slew-repair-v1`. It retains every original native phase
signature (217 cases) and all 60 original stuck-UP/DN monitor cases, then
adds the required native unequal-slew coverage at all fifteen PVT points
at 400 MHz and frequency extremes at SS40/measured worst PVT. The catalog
deduplicates by canonical signature, binds a versioned partition hash and
derives its count from requirements. It contains 465 cases when the worst
corner is SS40 and 493 otherwise; these numbers are descriptive, not
admission constants.

Preparation requires the complete passing native pilot and restoration of
both historical false-BAD cases. All eighteen pilot signatures occur in
the required partition. Their raw evidence is reused only after proving
identical circuit bytes, phase signatures, stimulus, scoring windows and
actual receiving-gate observations. The only allowed deck normalization
is its model include path. Reused evidence obtains no SPICE lease and no
new simulation. Every other case requires a fresh transient on the same
selected extracted native model, shared bias and unchanged analog loading.

Phase cases require the original health/fault limits and receiving-gate
clock transport. Stuck-fault fixtures retain their original static UP/DN
stimulus and monitor probes; they do not observe an uninstantiated PFD.
Each required unequal-slew UF-DF curve must remain monotonic and bracket
zero between -20/+20 ps. Every case must pass; passing point tests cannot
hide a biased detector. Preparation and verification regenerate the whole
catalog, fixtures, probe aliases and pilot equivalence. Complete finite
raw/export agreement and all output hashes are rechecked independently.

`prepare NATIVE_PILOT`, `run ARTIFACT` and `verify ARTIFACT` run in the
scientific environment. At most two P1 workers dispatch individual leases;
partial output cannot retry. No new phase matrix is prepared while the
physical repair/native pilot remain pending. This partition provides no
loop, full/fast RC-comparison, reset/disable, stability/recovery/readiness,
stress or PHY admission; all those requirements remain mandatory.

Baseline-only preflight `native_slew_phases_preflight/776c3b934d7a523c`
successfully compiled all 493 fixtures (433 phase and 60 logic) against
the retained complete extracted library. It checks PVT directives,
original timing, single shared bias and actual receiving-gate probes, and
proves fixture equivalence for all eighteen reusable pilot signatures.
Its donor manifest is explicitly a fixture catalog, with no passing-pilot
receipt or transient data. It provides no repaired-candidate admission.
The complete regression passes 1,376 tests without skips
(`build/native-slew-phases-tests.log`), including full partition coverage,
zero-balance/monotonicity failures, invalid reuse, missing/duplicate cases,
partial-output retention and dispatch of only fresh cases.

## Conditional analog fallback and DC readiness

`dll_analog_frontend.py` implements the approved four-variant source grid:
approximately 140/280 uA tail current and 20/40 um input width. Each clock
uses a continuous NMOS differential pair against shared VDDD/2, PMOS
mirror loads and two CMOS restoring stages. Clock drives the diode-load
branch; the fixed reference drives the output branch, giving a
non-inverting restored output. Input length is 0.15 um, PMOS loads are
8/0.3 um and local NFET reference/tails are 100/0.3 um. Restoring P/N widths
are 4/2 um then 16/8 um at 0.15 um length.

A 3.3 V PMOS mirror with 4x/8x the endpoint reference geometry derives the
local tail current from the existing 35 uA bias. The wide 1.8 V tail devices
use a local 1.8 V diode-connected reference; they are not connected directly
to the endpoint's high-voltage NB. Identical passive divider resistors
generate shared VDDD/2 with an approximately 1 pF MIM bypass (22 by 22 um).
The private eight-port `lvds_slew_analog_pair_v1` explicitly carries PB and
VDDIO. No public DLL port or retained core has changed.

`probe_dll_analog_frontend_dc.py` cannot create any analog artifact until
independent verification proves all four standard-cell candidates complete
and failed, with no numerical errors. A surviving standard-cell candidate,
partial screen or failed owner cannot authorize the fallback. The first
experiment is twenty SS40 DC points: each of the four variants at static
clock pairs 0/0, 0.9/0.9, 1.8/1.8, 0/1.8 and 1.8/0 V. These are signal
states; supplies remain fixed at 3.3/1.8 V. There is no supply sweep.

The DC fixture uses the retained native endpoint bias and exactly one
35 uA reference. It measures actual BSIM tail current, gm, gds and vdsat,
all frontend MOS terminal voltages, shared reference, restored outputs and
rail power. Tail headroom must exceed vdsat by 20 mV, reference/tail current
must stay within 25% of its declared target and tails within 20% of their
local reference. Rail-state outputs retain 0.36/1.44 V limits; the 0.9 V
input state has no digital-output requirement. Every terminal pair of all
twenty frontend MOS devices is checked against 1.95 V for native 1.8 V
devices or 5.5 V for the HV bias mirror. The PDK source confirms the declared
device ports and internal MOS names used by the operating-point probes.

Two workers obtain individual P0 leases, with no outer lease or partial-run
retry. Complete single-point finite raw data, every requested model vector,
canonical fixture/model regeneration and all hashes are required. DC
readiness does not select a timing winner or admit a source repair: complete
phase/BAD, zero balance, clock transport, controls, PVT, physical and DLL/PHY
qualification still follow. No analog artifact or transient has been
prepared while the standard-cell screen remains incomplete.
