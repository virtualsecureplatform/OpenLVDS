# Implementation status

The SKY130 macro implementation and reproducible build flows are present.
**The link is still in electrical bring-up and is not released.**

New bank evidence (2026-11-07): the two-stage architecture v322 completes
its SS40/410 MHz, zero-code, 50% duty case and passes every original
point gate. Its quarter-period headroom is **+38.637 ps**, improving
95.671 ps over the original regular bank's -57.034 ps. Full 25 ns replay
at `two_stage_bank_native_replay/20261107T030617Z` reproduces every native
metric for 1365 MOS and 173 programming-gate observations. Rising delay
is 563.902--571.119 ps, falling delay 457.010--457.265 ps, maximum slew
109.605 ps, maximum period error 7.218 ps, and peak terminal difference
1.873843 V. All eight startup cycles remain included. This supports the
depth reduction at this one point; both fine31 duty endpoints, coarse
overlap, shared-wire RC, dense codes and all-PVT qualification remain open.

New counter evidence (2026-11-07):

The stronger-storage shared-RC pilot v232 now completes all 12 SS0/SS40,
40/50/60% duty, both-stopped-level cases without numerical errors. Only
four functional cases pass: stopped-low at 40/50%, at both temperatures.
Every stopped-high case fails clear/reassert, and all 60% cases fail startup
ordering; all twelve producer terminal-stress screens pass. Independent
full SS40/60% replay confirms low0 misses its original guaranteed-low
window by 81.334 ps in both traces, while stopped-high PREPARE clears
24.864 ps after REQUEST reasserts. Receipts
`strong_counter_clear_diagnosis_v266/7898a3df49531f9f` and
`counter_low_windows_v305/2e1f49e3e7801289` retain the separate causes.

The fast-clear shared-RC counter v269 also completes its SS40/410 MHz,
60% stopped-low case. Independent full replay reproduces every native
metric for all 644 observed MOS: clearing and terminal stress pass, but
startup ordering fails. Fixed original epochs put low0, low1 and armed
98.143, 1.239 and 3.401 ps beyond their guaranteed-low windows,
respectively. Their actual clock voltages are 0.504254, 0.183899 and
0.190722 V against the unchanged 0.18 V low limit. PREPARE and RESET_N
clear 672.669 and 714.718 ps before REQUEST reassertion; peak terminal
difference is 1.932172 V. Receipts
`fast_clear_counter_clear_diagnosis_v299/05cf6dbc905a78f5` and
`counter_low_windows_v305/125ae40984574c3a` separate successful clearing
from the remaining startup timing failure. The stronger CLK-drive repair
remains under test; this older case supplies no electrical admission.
The final stopped-high case also reproduces independently at
`fast_clear_counter_clear_diagnosis_v299/a04289ad2ebfa9cb` and
`counter_low_windows_v305/571c6b882071675e`: identical startup misses,
but PREPARE/RESET_N clear 163.695/199.736 ps before REQUEST reassertion
and peak terminal difference is 1.897615 V. The original v269 campaign is
complete, 12 cases with zero numerical errors. Its eight 40/50% cases
pass function; all four 60% cases fail startup ordering. All twelve pass
clearing and terminal stress. The family remains rejected at the required
60% boundary; no cases or thresholds are removed.

Independent full v306 SS0/50% stopped-low replay at
`matched_counter_native_replay/20261107T014034Z` also confirms the unrepaired
matched buffer's voltage failure at nominal duty: minimum clock-low window
improves from 249.412 to 460.242 ps, but peak stress is 1.962008 V against
the unchanged 1.95 V limit. The REQUEST-stage repair remains required
across the allowed clock duty range; a larger storage guard alone does
not resolve the completed startup/clear failures.

The complete SS/0 C, 410 MHz, 60% duty, stopped-high comparison confirms
the same startup/stress tradeoff as the stopped-low comparison. Independent
full native replay at
`matched_counter_native_replay/20261107T005528Z/summary.json` reproduces
every original measurement for v306 cases 2 and 3. The baseline has
17.580 ps minimum remaining clock-low window and 1.893681 V peak terminal
difference; matched buffers increase that window to 234.258 ps but reach
1.961919 V, exceeding the unchanged 1.95 V limit. Phase ordering and
stopped-clock clearing pass in both cases. This is component RC with ideal
shared wiring, not whole-counter electrical qualification.

The REQUEST-only P10/N8 first-stage repair (v317) now passes both complete
SS/0 C, 410 MHz, 60% duty stopped-level cases. Its first stopped-low replay
`request_taper_native_replay/20261107T010347Z/summary.json` reproduces every
original metric and the exact limiting native samples. Startup margin is
232.798 ps. REQUEST final-stage peak stress falls to 1.909018 V; the whole
counter's limiting low0 setter reaches 1.949317 V, leaving only 0.683 mV
below 1.95 V. The stopped-high full replay
`request_taper_native_replay/20261107T014342Z` also reproduces every metric
and limiting sample: startup margin is 232.798 ps and peak stress is
1.917961 V. Its SS40 stopped-low case now also passes every original
point gate. Full replay `request_taper_native_replay/20261107T031301Z`
reproduces all 808-MOS metrics and limiting samples: minimum startup
window is 233.577 ps, REQUEST final-stage peak is 1.910917 V, and the
low0 setter's drain/body peak is 1.949083 V at 23206.5 ps. Only 0.917 mV
remains below the unchanged 1.95 V limit. The final SS40 stopped-high
case and whole-counter shared RC remain required; three point passes
do not establish full PVT or electrical qualification.
The repair retains the final REQUEST drivers, both clock-buffer
stages, counter logic, 20 ps REQUEST edges and all original voltage/timing
limits. A real 54-MOS/2-MIM REQUEST-buffer component now passes zero DRC,
strict native LVS, unchanged stage masks/junctions and fresh complete local
RC qualification at `request_taper_buffer_physical_v323/8cfc7cf7b15b78c9`
and `request_taper_buffer_rc_v324/39c432524ec4f06d`. This supplies actual
interstage-wire RC for later counter integration; SS40, whole-counter
shared RC and electrical qualification remain pending.
The matching CLK component now also passes native physical/local-RC proof
at `regular_clock_buffer_v325/9d3380b4eca0696f`: two unchanged P20/N16
stages, 72 MOS/two MIM, zero DRC, strict LVS and independent Schur proof.
Both buffer component types are available for future physical counter
integration; the active source pilot and its qualification gates are unchanged.
A native integration preflight now passes at
`counter_buffer_material_preflight_v326/7654d308b75a4197`: all 22 phase
macros and seven public pins are preserved, shared native masters are
compatible, and the proposed netlist matches the actual v317 circuitry
uniquely in strict LVS. Its counter core has 744 MOS/50 MIM; the existing
downstream loads add 64 MOS/six MIM to reach the 808-MOS/56-MIM testbench.
This is a netlist/material check; new counter geometry, shared RC and
SS40/native timing qualification remain pending.
A subsequent actual-dimension floorplan check found both parallel buffer
pairs overlap in the old 24 um corridor. The additive v327 plan widens
that corridor to 40 um while retaining the existing rows, buses and
direct-feedback construction. Receipt
`request_taper_counter_plan_v327/d8e29c7f91c15d0d` has no overlapping
macro footprints and passes the existing spine-clearance check; REQUEST
and CLK pair footprint gaps are 8.96 and 4.16 um. Four targeted tests
also pass. This is a deterministic plan only; final v317 timing remains
required before routing, and no new geometry/RC/electrical gate is admitted.
Further escape analysis finds eight same-row different-net M4 overlaps
if the old straight-escape renderer is used with these new ports. Receipt
`counter_m4_escape_conflicts/20261107T032434Z` retains their exact planned
coordinates. The v327 plan fixes footprint fit only and is not directly
routable by the old renderer. A new v328 escape plan raises A on M4 and
takes X across M5; receipt `counter_buffer_escape_plan_v328/34a91d9cf9e8e4ae`
removes the planned positive-area overlaps. The stricter v329 receipt
`counter_escape_contact_check_v329/e2d9db89c15c5d2d` also excludes shared-edge
and corner contacts: 704 native-layer checks across all 22 instances,
with seven targeted tests passing. This supplies a concrete escape plan,
not a counter GDS; minimum spacing/vias, actual routing, DRC/LVS and fresh
shared RC remain required after the final v317 timing gate.
The reordered fine bank (v315) now completes its zero-code case:
voltage, controls, eight pulses, slew and period/history pass, but quarter
headroom is still -46.311 ps. Full native/stage replay reproduces every
metric at `preconditioned_bank_stage_replay/20261107T011544Z`.
Its fine31/60% case also completes and fails period/history at 47.460 ps,
despite passing all eight pulses, voltage, controls and 135.179 ps slew.
Full replay `preconditioned_bank_stage_replay/20261107T020053Z` reproduces
every metric and locates 43.530 ps of the 47.455 ps first-to-last rising-event
change across the loaded fine inverter. Remaining cases continue; both
completed failures prevent admission.
Clock coverage remains 390/400/410 MHz with
40/50/60% input duty, fixed supplies, and five process corners at 0/25/40 C.

The original regular-pair bank (v263) completes all four native cases with
no numerical errors, but fails the component hypothesis: zero-code quarter
headroom is -57.034 ps and conservative fine/coarse overlap is
-44.976/-121.970 ps rising/falling. Independent full coarse-case replay
`regular_regenerated_stages_v300/3f782ffe5c4d326b` reproduces all original
metrics. Its guarded physical, transport, dense, PVT and full-range followers
reject the failed source. They are retained without reruns or admission.
The retained 2x2/2x3 MIM fine cells now both pass current native/Schur RC
proofs at `retained_mim_fine_rc_v320/ddf3c29ce3fc44da`; substitution behind
the isolated driver is implemented in v321, with six targeted tests passing.
The eight-case MIM pilot is prepared at
`mim_isolated_fine_bank_v321/d7b9c9202d5285da`, with seven targeted tests
passing. Its first zero-code native simulation has started and is advancing
under the unchanged dispatcher;
no MIM-bank native verdict exists. Fresh bank physical/RC and complete timing qualification
remain required.

An independent latency candidate is prepared at
`two_stage_fine_bank_v322/4092d10edbdce08c`. It connects the two existing TG
levels directly and removes the group inversion and one post-fine inversion
together, preserving noninverting public behavior. Original fine cells,
coarse units and all 173 programming gates remain; the native census becomes
1365 MOS/34 MIM. Seven prepared-artifact tests pass. Its runner is active,
checking inputs before its first lease; no new native timing verdict exists.
Both alternatives still require complete point screens and fresh bank qualification.

Current architecture work (2026-11-06):

The current measured balanced b2 bank passes the component-model three-point
screen: zero has 110.126 ps fastest-quarter headroom, with positive rising/
falling coarse overlap of 58.070/167.461 ps. Actual whole-bank routing now
passes with zero violations (`measured_balanced_bank_route_v152/d7f930268a4bd034`).
The streamed native bank passes zero Magic DRC, unique LVS, exact native masks/
hierarchy/placements and its 1,453-MOS/42-MIM inventory
(`measured_balanced_native_gds_v150/6766444ea6d551f4`).

Actual whole-bank joint RC is now qualified at
`measured_balanced_joint_rc_v155/7065685b553b1050`: original extraction preserved,
selective measured fine-capacitor junction correction, all 155 fine MOS junctions,
strict native parameter/topology checks, elementwise passivity, exact reduction
and independent Schur current witness. The complete native SS/40 C zero screen now passes at
486.497/532.941 ps repeated rise/fall delay and 174.364 ps maximum slew,
with 76.815 ps fastest-quarter headroom. The actual first-coarse point passes with 174.838 ps slew and both-edge
overlap remains positive. Fine31 passes voltage/control/repetition checks but
fails the 250 ps slew limit at 265.033 ps; the actual sparse gate is false.
Both output-guard prototypes pass their three-point hypothesis screen. The
unguarded variant reaches 222.248 ps fine31 slew. Its new native component
passes DRC/LVS, exact 32-MOS parameters and fresh RC at
`unguarded_output_cell_v162/54829739e9b70627`. The new whole-bank native GDS passes zero DRC, unique LVS and exact
1,453-MOS/40-MIM output-only geometry at
`unguarded_bank_gds_v164/53b0a015a681410b`. Fresh whole-bank RC passes at
`unguarded_bank_joint_rc_v171/82a3dfbf3d1494ac`, followed by a passing actual
native zero at 486.850/522.734 ps rise/fall delay, 153.913 ps maximum slew and
87.021 ps fastest-quarter headroom. Fine31/first-coarse and six sampled boundary points pass. The completed 27-case periodic
screen passes only 10 cases and exposes a fine31 history-dependent timing failure despite acceptable
output swing, voltage and slew. Actual internal-node observations show the
loaded mux node failing to restore its rail between edges. The first native INV1 isolation cases restore mux swing but lose output
pulses. A stronger native INV8/NAND2_8 pilot is running; complete INV8 endpoint
traces still fail slew or period/history limits. Its completed zero-code case
also misses the fastest-quarter budget by 267.777 ps despite passing native
safety, pulse, slew and repetition checks. Read-only stage-crossing analysis
identifies 368–389 ps between the loaded fine node and output in that zero
case; this is a measured crossing difference, not an intrinsic cell delay.
Two new balanced regular-P/N
drivers now pass physical closure and fresh local RC. Their measured-bank
P20/N10 fine31 endpoints now complete: 40% passes, while 60% still fails
period/history despite passing native safety and slew. Its first-coarse
reference now also completes and passes individual interface checks, but
the complete histories give rising overlap of −3.063 ps at 40% and
−69.849 ps at 60%; conservative falling overlap is +63.006 ps. This older
configuration therefore fails the required overlap gate. Its zero case now
also completes and misses the quarter budget by 265.838 ps, despite passing
all 1473-MOS native safety/control and output slew checks. Two stronger-discharge
N16 variants also pass zero DRC, unique LVS and fresh local RC. P20/N16 now
passes both complete fine31 40/60% duty endpoints (2.08/12.76 ps period
error, about 232.8 ps maximum slew). Its first-coarse reference now completes
and passes individual native checks, but complete endpoint histories give
conservative rising/falling gaps of 14.365/22.121 ps. Its complete zero trace also confirms the quarter-period
budget failure by 205.629 ps (815.385 ps worst delay), despite passing all
1479-MOS native safety, control, period, repetition and 225.178 ps slew checks.
Complete stage analysis measures 296/345 ps rise/fall crossing differences
from fine node through the BUF8 to OUT. Both complete zero results confirm
the earlier prefix diagnoses. Neither branch is admitted. A separate v263 candidate replaces only the native BUF8
regenerator with two instances of the qualified regular P20/N16 inverter,
preserving overall polarity and the existing isolation stage. Its four native
checks prioritize zero delay, both duty endpoints and coarse overlap. New
shared wiring and timing are unqualified; existing campaigns continue.
The prepared artifact is `regular_regenerated_bank_v263/7fa8c46ce9db679e`;
its persistent runner is live under the unchanged dispatcher.
Both complete fine31 points (40% and 60% duty, SS40/410 MHz) pass all
1529-MOS native, pulse, period, repetition and interface checks. Maximum
slew is 87.992/87.894 ps and maximum period error is 1.966/16.003 ps
respectively. Independent full-metric replay reproduces both traces.
Zero and coarse overlap remain required; no complete v263 component or
physical admission follows.
Its physical backend is now implemented separately: 181 functional/353
physical instances, exact native graph and 1529-MOS/43-MIM inventory,
corrected native supply-port reference, 52-site fine-array/control-row
shift and actual metal-4 output access. Placement feasibility passes zero
DRC and verifies all 353 connections/placements plus all three fixed buses at
`regular_regenerated_placement_v272/82dc7493ef40f70d`; routing, whole-bank
LVS/RC and timing admission remain open for this revised architecture.
The revised router-interface preflight also passes exact native restoration
at `regular_regenerated_routing_interface_v274/b41db4edac628761`: 93 fixed
terminals, all eight root outputs and all three M4 stages retained. Stored
verification at `regular_regenerated_routing_verification_v275/13aea70be0ae4a65`
also passes: all three databases reproduce six native record sets and ten
injected native/geometry/type faults are rejected. No routing has been performed.
Fresh ordinary extraction and geometry diagnostics now complete for this
placement at `regular_regenerated_junctions_v276/ca85f4dd7ca7a27a`: all 353
native instances and 31 separate fine active regions are verified, with the
expected 1529 MOS/43 MIM census. All 62 capacitor MOS retain the known
per-device junction allocation mismatch in the preserved raw extraction;
this diagnostic does not qualify shared RC or whole-bank LVS.
The separate measured reference now completes at
`regular_regenerated_junction_reference_v279/56daa1af193011cf`: only 62
capacitor MOS/124 fields change, all 155 fine MOS match measured junctions,
all other native/passive bytes remain, and correction is byte-idempotent.
The original extraction remains intact; this is not a routed LVS/RC receipt.
The revised routing producer (v278) is implemented behind the complete
four-point v263 native gate. It retains all 93 fixed-bus terminals and
requires the new `restored_b` route; no route has been prepared or launched.
The revised native GDS and fresh shared-RC qualifiers (v282/v283) are also
implemented, with nine passing targeted tests. Their RC tests use a native
device fixture and artificial passive network; they do not qualify a routed
bank. The v284 continuation is live, waiting for the exact v263 invocation
before routing, native DRC/LVS/mask checks and fresh RC qualification. It
preserves the complete four-point timing gate and captured source closure.
The revised native observation and electrical transport scripts (v285–v289)
are implemented and pass 15 targeted tests. All 1529 MOS, 173 programming
gates, 86 logical controls and actual selected/fine/restored-node terminals
are covered. A separate continuation waits for v284 before testing the actual
routed bank at zero code, fine/coarse overlap and all 27 sparse-code clock
conditions. No revised routed-bank electrical result exists yet.
The next PVT producer (v291) is implemented for 405 sparse-code clock
conditions across all five process corners and 0/25/40 C, retaining
390/400/410 MHz and 40/50/60% duty at fixed supplies. It remeasures/reuses
the 27 passing SS/40 cases and prepares only the remaining 378. Nine matrix
and continuation tests pass. Its v292 continuation waits on the exact v289
job; no PVT campaign or electrical result exists yet. Dense/common legal
tables, update behavior, DCC and full-clock qualification remain pending.
The first revised dense curve producer (v294) is also implemented: all 32
fine settings at coarse 0/1, SS40, 410 MHz/50% duty, preserving eight cycles
and all native observations. It reuses three matched periodic cases and
prepares 61 new cases only after the complete v288 clock screen passes.
All 11 dense producer/handoff tests pass; v295 is live waiting for v289.
Raw fine-step reversals or excessive gaps remain explicit characterization
results. No dense result, common legal table or full-range admission exists.
The full current TX range producer (v301) is now implemented: 512 raw codes
at all 15 PVT, 7680 reference-clock cases at 410 MHz/50% duty. It consumes
106 matching remeasured sparse/dense conditions and requires 7574 new cases
only after both prerequisite screens pass. Its v302 handoff requires both
exact parent jobs and a common routed-bank lineage. Fourteen targeted tests
pass. No full-range native campaign or timing result exists yet; selected
clock checks, other bank dimensions, RX range, updates and physical ROM
remain required before any table or PHY admission.
The separate v303 eligibility evaluator retains all 7680 measured results,
including failed raw codes, and searches only codes passing every original
check at every PVT. This corrects v301's blanket all-raw-pass prerequisite
without dropping coverage or relaxing any selected-code limit. Its v304
follow-up handles only a complete original campaign or its specific
all-raw-pass rejection; source/model/waveform/measurement failures remain
fatal. Twelve targeted tests pass, including the actual timing function's
out-of-epoch rejection and common ROM proposal compatibility. No native
eligibility receipt exists yet; selected-clock and update safety remain open.
The common sequence selector (v296) is now implemented and passes 12
algorithm tests. It requires complete raw-code intervals across all 15 PVT
and both edges, finds one shared ordering, prefers 10 ps gaps, enforces the
20 ps maximum, and checks TX quarter-range or RX longest-period-plus-500 ps
coverage. It emits proposals only: native provenance, complete dense curves,
safe updates and physical/full-link admission remain unverified. No actual
bank table has been generated or admitted.
Legal-index/native-code mapping is now implemented in a constant RTL ROM
and a v3 DLL-control wrapper, preserving the v2 calibration and exact
configuration/settling protocol. Proposal export keeps table admission zero.
Ten export/mapping/synthesis tests and five original DLL-control tests pass;
these use synthetic tables/observers and do not qualify a physical ROM or
native timing. Mapped TX/RX v3 control compositions now connect these tables,
including a separate RX deskew map and invalid-map settling gate. All 24
functional scenarios pass, along with two synthesis checks, ten ROM/core
regressions and six export-integration checks. Physical ROM/decoder timing,
calibrated delay bounds and full native clock/link integration remain pending.
The bank pilot runs under the same dispatcher, with a gated continuation for
the complete 27-case frequency/duty/sparse-code screen of any passing family; bank timing and full
frequency/duty/physical validation remain required. The calibrated clock chain, dense/common legal tables, all-PVT
clock transport and LVDS PHY remain unqualified. The broad regression and separate CAD checks pass.
The latest broad run passes **2540 tests with 51 tool-dependent skips**; all
**51 CAD/synthesis checks pass separately with no skips**. A fresh discovery
audit confirms the skipped names exactly match those executed separately.
This includes the new counter/stage, full-range and universal-eligibility
tests. These tests verify the build, RTL and qualification machinery;
they do not admit pending native timing.

Counter startup has distinct clear and low-phase timing constraints. The
fast-clear branch passes its four completed SS0/410 MHz cases: 40% and 50%
duty, both stopped levels. A completed predecessor 60% case clears correctly but misses the
original low0 voltage window by 90.188 ps; the repaired 50% cases retain
17.560 ps low0 headroom at 50% and 29.738 ps at 40%. The matched CLK/REQUEST buffer experiment (v306)
now compares 24 paired SS0/40, 40/50/60% cases with qualified component RC
and ideal shared wiring: 644 baseline MOS and 844 replacement-buffer MOS,
all other logic and downstream loads preserved. Its seven tests pass and
the persistent runner has started from
`counter_matched_buffers_v306/f9b748a6ac5c2ee2`. No prototype result or new
physical counter, all-PVT, DCC/full-clock or PHY admission exists yet.

The isolated fine-stage drivers and BUF8 have canonical physical integration
views (v236): all three pass zero DRC, native LVS, unchanged manufacturing
masks/junction parameters and OpenDB interface checks. Their new bank placement
(v238) also passes zero DRC and exact OpenDB placement/connectivity checks.
The physical graph matches all 180 native component calls (1479 MOS, 43 MIM),
including the isolated fine node and unchanged programming gates. The reversible
router-interface preflight also passes, retaining all native connections and
actual M4 driver access. Rereading all three saved databases reproduces their
native records; six injected connection/geometry/type faults are rejected.
Five native standard-master reference extractions now pass strict LVS. The
fresh whole-bank junction diagnostic also completes with all 1522 native
primitives checked, a corrected supply-port reference order, and 155 fine MOS
bound to the separate geometry-allocation proof. The measured ordinary
reference is now prepared: 62 capacitor devices/124 fields are selectively
corrected, all 155 fine MOS match the measurements, and correction is byte
idempotent. This does not qualify shared-wire RC. The regular-route producer
requires that corrected reference evidence and waits for the complete native
pilot's zero/overlap/duty gates. The streamed native GDS and fresh shared-wire RC qualifiers are implemented.
Exact-owner coordinators are live to advance through routing, native GDS,
RC qualification, and the newly implemented zero/overlap/27-case clock
transport screens after those gates pass. The observation mapper covers all
1479 MOS, 173 programming gates and both isolated data nets. Actual isolated-bank
shared RC remains pending; eight RC/handoff tests pass using a native-device
fixture rather than a routed-bank qualification receipt. The broad regression
passes 2540 tests with all 51 tool-dependent skips executed separately; 15 targeted
observation/transport tests also pass. Actual routed transport remains pending. Both finite-input fine31 endpoint comparisons now preserve
the original P20/N10 pass/failure results; full four-case parity is still open. Whole-bank routing, LVS and shared-wire
RC for this architecture remain open.

Clock checks use 390/400/410 MHz and 40/50/60% input duty (40% and 60%
endpoints plus the 50% nominal check), fixed supplies and
0/25/40 C across all five process corners. The periodic campaign runs under the unchanged global six-engine dispatcher;
its failures are retained and do not admit the bank.
See [digital clocking v2](digital-clocking-v2.md) for the implementation contract
and exact receipts.

The independent 90-condition counter PVT screen completed with six SS/50%
terminal-stress failures. Enlarging setter guards leaves a stopped-low reset
body excursion at SS0. A new physical substrate-contact row for storage
passes zero DRC, unique LVS, exact native parameters and fresh component RC.
Its integrated pilot passes both stopped levels at all three temperatures.
The actual 3 um setter master/pair also passes DRC/LVS and fresh component RC.
Both actual repairs pass the six-case SS pilot; the 90-case PVT screen is
running. The repaired counter and both clock drivers are now being integrated
as a 21-macro routed block. It has zero Magic DRC and unique LVS, but the
strict native-master witness initially finds directory-qualified GDS names.
A separate name-only repair now passes exact mask/label/placement and native
master checks. Fresh shared-wire RC now passes exact native parameters,
passivity, topology, reduction and independent current witnesses. Actual
shared-wire transient replay observes all 510 MOS. Its first two SS0/50%
cases complete but fail the original phase-event count: low0 emits an extra
startup pulse. Independent complete terminal screens pass on these two
traces (1.940872/1.898217 V peaks); this does not waive the timing failure.
All six completed SS0 cases fail function; at 40% duty PREPARE and
RESET_N never assert. Their independent terminal screens still pass. A
compact same-logic 21-macro route now passes zero DRC, unique LVS and exact
native masters/placements; fresh RC qualification passes and the original native timing replay is
queued by an active source-bound continuation. A further direct first-loop
feedback route also passes zero DRC, unique LVS and fresh RC, reducing
feedback parasitics from 63.4 to 37.2 fF; its full native replay runs
separately under the same six-engine dispatcher. The first two cold/50%
traces of both new routes fail the unchanged sticky-arm event count while
passing native terminal safety. Native path diagnosis confirms late
setter/storage propagation remains; feedback routing alone does not fix it.
A new 22-macro variant now uses six guarded body-contact NAND8 storage
cells, two REQUEST buffers and three direct low-phase feedbacks. It passes
zero DRC, unique LVS and fresh 598-primitive shared RC. Its original timing
replay now has a first passing case at SS/0 C, 410 MHz, 50% duty, stopped
low, with all 612 counter/load MOS observed. Independent saved-trace
remeasurement reproduces every original metric: prepare/release margins
are 326.399/524.558 ps to the next half phase, minimum clock-low margin is
84.715 mV, and maximum terminal difference is 1.941780 V against 1.95 V.
The stopped-high companion now completes with a clear/reassert failure:
PREPARE falls 38.597 ps after external request reassertion, while RESET_N
clears with 195.177 ps headroom. Startup ordering and all native safety
checks still pass. Complete read-only diagnosis reproduces both original
traces and their gates at `strong_counter_clear_diagnosis_v266/06bdfd120dd71fed`.
The remaining pilot cases continue; full PVT and whole-clock validation remain open. No repaired whole clock
assembly or PHY is qualified.

A new fast-clear physical candidate changes only the two high-phase setter
NAND4 cells to the qualified native NAND8 model already used by the release
setter. All pin maps, phase logic, six stronger storage cells, both REQUEST
buffers, clock drivers and three direct low-phase feedback routes are retained.
It has 580 block MOS/50 MIM (630 primitives), plus the original 64 load MOS
in replay. `fast_clear_counter_physical_v267/5f2c400d640d10fb` now passes
zero DRC, unique LVS, exact native masters and all 22 macro placements.
Fresh RC now passes at `fast_clear_counter_rc_v268/d058dcd53f23d60f`:
all 630 native primitives, exact parameters/topology, passive reduction and
four independent terminal-current witnesses (maximum error 0.209 nA).
The exact-invocation v270 coordinator prepared and runs the unchanged twelve-case
native pilot. An actual RC-consumption test verifies all retained output
hashes and maps all 644 block/load MOS terminals into that original fixture.
Counter timing remains unqualified; the original failed traces remain.
The twelve-case replay is now prepared as
`fast_clear_counter_shared_rc_v269/12b91a2b04a05d8c` and its runner is live.
Its first two SS0/410 MHz/50% cases now pass at both stopped levels, with all
644 native MOS observed. Independent complete-trace remeasurement reproduces
every original metric. The formerly late stopped-high PREPARE now clears
159.827 ps before external reassertion, a 198.425 ps improvement; RESET_N has
194.833 ps margin. The other ten pilot cases and full clock/PVT matrix remain
required. This is a repaired nominal stopped-high case, not full clock/PHY admission.
The full routed-counter matrix producer (v264) and exact-owner continuation
(v265) are implemented and live behind that twelve-case gate: 270 conditions
cover all 15 PVT points, three frequencies, three duties and both stopped
levels, with twelve pilot cases consumed and remeasured rather than rerun.
No full-matrix SPICE case starts before the native pilot passes.
The actual RC-observation test and two complete internal-slew tests added
after the latest broad discovery also pass separately. These checks do not
qualify the pending native timing or full clock chain.

Earlier clocking experiments remain useful diagnostic evidence:

An earlier regenerated delay bank passes the actual routed SS/40 C zero-code screen
with 64.8 ps quarter-cycle headroom. Its falling coarse/fine overlap still
fails by 18.544 ps, and periodic 410 MHz clocks at 40/60% duty fail output
slew or full-swing checks. The calibrated clock chain and LVDS PHY remain
unqualified. See [digital clocking v2](digital-clocking-v2.md) for the exact
physical, native timing and independent verification receipts.

Three smaller complementary gate-capacitor fine cells (0.42/0.84/1.26 um)
now pass compact native GDS DRC/LVS and standalone distributed component RC.
The RC extractor's zero source-junction fields on tied D/S/body capacitor
MOS devices are reconstructed from independently measured separate-terminal
primitive geometry. Placed masks and separate active regions, all native
parameters, wire-collapsed topology and passive reduction are checked. Original
extractions remain intact. These component results do not qualify bank wiring
or timing.

The measured fine-cell RC is now integrated into a fresh bank model with
all native programming-gate observations rebuilt. The original-route bank
has repeated zero delay 593.519200/661.131259 ps; falling delay exceeds the
609.756098 ps quarter budget. Fine31 slew is 395.098036 ps and its rising
repeat difference is 101.623783 ps. Native voltage and control checks pass.
Stage diagnostics identify the root mux as the largest delay interval.

Moving the private capacitor bus between the device rows passes new native
geometry and RC checks, reducing its external wire capacitance from
14.01067 to 6.48771 fF while increasing data-port capacitance from 3.61526
to 4.63909 fF. That route improves fine31 slew to 351.881531 ps but worsens
zero falling delay to 726.678695 ps; both timing gates still fail.

Two qualified TG cells in parallel at each root branch improve zero to
554.000517/644.940498 ps and fine31 slew to 286.136079 ps. A second parallel
final inverter subsequently passes fine31 slew at 248.661930 ps, but zero
is 556.915374/658.680965 ps and rising coarse overlap is -12.968506 ps.
Native voltage/control/repetition checks pass. Quarter timing and overlap
still fail; these prototypes are not qualified delay banks.

Stage diagnostics after root strengthening show comparable group-inverter
and root-mux delay. Two completed candidates test different repairs. Balanced drive
parallels the first muxes and group inverters along with root/final cells,
using a newly qualified 1.26 um middle-bus fine cell: 1,133 MOS, 42 MIMs,
173 programming gates. Post-mux regeneration moves branch inversion after
the mux, places the fine load on the active inverter output and retains
two serial inversions per path: 981 MOS, 35 MIMs, 133 programming gates.
Both retain 86 root controls, complete qualified component models and the
original timing/safety gates. New topology/gang/common wiring remains
unextracted. The balanced-drive three-point pilot is complete with zero errors:
zero code passes at repeated 453.806932/498.587763 ps, with 111.167584 ps
fastest-quarter headroom. All three points pass native/slew checks, but rising
coarse overlap fails by 10.716291 ps (falling overlap is +129.826301 ps).
It is not admitted. The post-mux pilot is also complete: all native/slew
checks pass and zero quarter headroom is 35.421664 ps, but rising overlap
fails by 17.271380 ps (falling overlap +196.913000 ps).
The post-mux fine31 point now passes native checks with 202.856371 ps maximum
output slew and 0.171048 ps rising repeat difference. The standalone physical
parallel INV8 output master now passes zero DRC, strict native LVS, all 34
native parameter checks and complete component RC/reduction witnesses at
`parallel_output_cell_v111/719aa3336298176d`. Its connecting wires are measured;
a fresh bank experiment now includes that measured component wiring at
`post_mux_output_rc_v113/13796ed50f568b43`. Its three native timing cases
are complete: v113 passes native/slew checks but
still fails rising overlap by 17.157387 ps, with 34.921845 ps quarter headroom.
Complete bank interconnect remains unextracted. Canonical zero-origin GDS/LEF
views for the measured fine/output cells now pass fresh DRC/LVS, mask and
junction preservation and actual OpenDB checks at
`clock_cell_views_v114/5c1222c9bf8bb27b`. Post-mux stage traces isolate the
edge-dependent fine range mostly to the common inverter. A root-only drive
experiment is testing input-edge shaping without increasing coarse-tap
loading or adding serial inversion. Its v117 zero case now passes native/slew
checks but has rising delay 627.550649 ps, missing the quarter budget by
17.794551 ps. The complete three-case comparison also fails rising overlap by 31.570167 ps;
falling overlap is +177.182354 ps. This root-only trial is not admitted.

The exploratory post-mux placement at
`post_mux_placement_v119/5092f682fb99bf91` now passes zero placement DRC,
exact 160-component/989-MOS graph mapping, actual 332-instance OpenDB checks,
14-master mask preservation and all fixed bus connectivity checks. It preserves
the taller fine cell's global public rails and proves the 33-terminal
`fine_slow` bus. Whole-bank routing/native LVS/joint RC and timing admission
remain outstanding; this placement does not select a failed/pending candidate.

A matched coarse-drive experiment is running for the balanced bank at
`strong_coarse_bank_v123/8d9e2e94f139b1a3`:
its first muxes were doubled while coarse buffers retained their original
strength. Double/triple native coarse-buffer gangs now pass standalone
DRC/LVS, junction and complete RC checks at
`parallel_coarse_cells_v121/be7fd56d4ea74868`. Actual bank preflight preserves
all fine/output/control circuitry and verifies 1,453/1,773 MOS, 42 MIMs and
173 programming gates. Six native timing cases test the two strengths
under unchanged gates and dispatcher limits. The double-coarse profile now has all three completed native points, with
positive rising/falling overlap of 58.053478/167.446004 ps and zero-code
quarter headroom of 111.213640 ps. All native/slew screens pass; triple-coarse
cases remain running; its fine31 point now passes at 690.584011/854.005211 ps
and 243.178202 ps maximum slew. These component-model results do not admit common bank
wiring, periodic clocks, PVT or the PHY.
Canonical middle-fine and stronger-coarse GDS/LEF views now pass fresh native,
mask/junction and OpenDB checks at
`clock_cell_views_v124/3557a1acd9b9ad4c`. The v125 integration model includes
measured group/final inverter-pair wiring; both native inventories and all
173 programming gates are preserved. Its v126 canonical physical graph has
179 functional macros and matches every named component connection and full
native model/W/L inventory. These are structural preparations; their native
timing and routing/native-bank-LVS/RC admission remain open. Both exploratory
balanced placements now pass zero DRC, all native masks/hierarchy/labels,
actual 351-instance OpenDB checks and fixed-bus connectivity at
`balanced_placement_v129/a158104d2fd54d99` (b2) and
`balanced_placement_v129/f53b50318fc8e365` (b3). Each has 179 functional macros
and 43 tapped control rows; root outputs remain unrouted. Read-only native
mask previews are available through `render_balanced_placement_v130.py`.
Both placements also pass native router-interface roundtrip checks at
`balanced_routing_interface_v134/3cdfa2a88b9de6ad` (b2) and
`balanced_routing_interface_v134/b892336c2e21e16f` (b3). Exact existing metal
is represented by three temporary router ports while 94 already connected
fine-bus terminals are detached. All eight root outputs remain available;
all 351 placements, native connections, pin geometries/types and fixed buses
are restored exactly. The initial v132 API failure is retained. Independent
stored-database verification passes at
`balanced_routing_interface_verification_v136/c4810dca76a4b101` (b2) and
`balanced_routing_interface_verification_v136/adadda7948c4b82b` (b3): all six
native database readbacks match and all eight injected faults are rejected.
The first v133 movement-fault fixture is retained; OpenDB refused to move a
FIRM instance, so the corrected fixture unlocks only its disposable copy.
No routing or timing candidate admission is performed by these preparations.
The v135 routing producer now refuses incomplete native evidence and unrouted
coverage. Its active service waits for the exact v131 coordinator, then
independently remeasures all three traces and checks the identical model hash
before preparing any route. Actual route coverage, native GDS DRC/LVS, joint
RC and electrical timing remain pending; the service does not stop or restart
existing solvers.
The v137 native GDS stage is prepared behind that route: original native masks,
hierarchy/labels/351 placements, fresh full-bank DRC/LVS and the exact native
MOS/MIM census/dimensions/junction parameters are all mandatory. Both placement
hierarchy preflights pass with 27 used native cells each, and all three new
inventory guard tests pass. Its service waits for the exact routing process;
no routed-bank GDS or joint-RC result is claimed. Fresh ordinary Magic
extraction of both unrouted placements preserves the exact 1,453/1,773 MOS
and 42 MIM census, port order, model/W/L and reference-supplied junction fields.
Both also reject duplicate-instance and altered-port-label GDS faults even
when their flattened mask regions are unchanged. These diagnostics do not
establish routed connectivity or repair raw-RC junction fields.
A new mask-bound fine-section diagnostic completes for both banks at
`measured_bank_fine_junctions_v140/a6b60e88a441469d` (b2) and
`measured_bank_fine_junctions_v140/97fe2de6760931ca` (b3). All 31 sections,
62 capacitor MOS, 93 programming MOS and 31 guard MIMs are identified by
native topology and tied to independently measured primitive geometry.
All 62 capacitor devices have per-device junction mismatches in ordinary
whole-bank extraction: 120 zero fields and four nonzero fields per profile.
Those fields were absent from the width/length-only fine schematic, so the
earlier reference-supplied-parameter check did not admit them. No model is
changed. A future bank RC repair needs this geometry/identity proof and full
native LVS; directly reusing ordinary capacitor-junction fields or applying
the single-cell zero-only fix would be invalid.
Both writer comparisons complete at
`measured_bank_junction_writer_v141/72df769d07c6686b` (b2) and
`measured_bank_junction_writer_v141/d817d4c0605b061d` (b3). Flat/hierarchical
policies retain the 62 capacitor mismatches; distributing area makes 31 P
capacitors match but leaves 31 N capacitors wrong and changes other native
junction fields. All three policies preserve topology/W/L, but none is a
valid physical repair. A separate check confirms every junction field of
all 93 pass/clear switches matches its measured primitive in both profiles.
The selective correction is now implemented in v142. Both measured-reference
preparations pass at `measured_bank_junction_reference_v143/1595e26c774ff542`
(b2) and `measured_bank_junction_reference_v143/a01184cabad95322` (b3), each
correcting 124 fields on only 62 capacitor devices. All non-capacitor devices,
topology and dimensions remain unchanged; the correction regenerates and is
byte-idempotent. These are unrouted measured references, with no joint RC or
PHY admission. Extraction defaults and admitted timing models are unchanged.
The v144 actual routed joint-RC producer is now prepared and queued behind the
existing native GDS service. It refuses unrouted inputs and binds actual
routed GDS/LVS to the exact fine-geometry proof, preserves the original
extraction, corrects only capacitor fields in separate raw/reference copies,
and requires all native parameters, all 155 fine-MOS measured junctions,
passivity, regenerated reductions, native collapsed LVS and the independent
Schur witness. Both fine-junction preflights pass and reject an injected clear
junction error. This service waits for the exact existing GDS process; no
routed joint-RC result or transient/PHY qualification is claimed yet.
The v145 observation mapper is prepared for the actual joint-RC bank. It binds
all 351 physical instances and 150 logical nets to actual extraction aliases,
retains all separate MOS terminals, and checks 173 programming gates by native
type/width/control polarity plus all 86 logical controls. Both reference-graph
logic preflights pass, and all four injected gate/polarity faults are rejected.
Those preflights use synthetic aliases and do not qualify actual routed mapping.
The v146 complete observed post-layout zero screen is prepared and queued
behind actual joint-RC qualification. It regenerates mapping from the actual
native/RC files and refuses an unrouted corrected reference. The case retains
the full two-pulse 20 ns, 2 ps maximum-step SS/40 fixture, all MOS terminals,
173 programming gates and 86 controls. Native safety/control/repetition,
250 ps full-swing slew and both pulses' fastest-quarter timing must all pass.
No post-layout timing artifact or PHY admission is claimed yet.
The matched measured-inverter fine31 diagnostic is complete at
`measured_gang_fine_v127/36cf5a7471a52929`: repeated delays are
692.500788/856.038786 ps and maximum slew is 244.222924 ps, with all native
and slew checks passing. New zero/first-coarse runs use the identical model
at `measured_gang_sparse_v131/58a9364cba76fa27`, consuming the completed fine31
trace as the third point. The first-coarse case now completes and independently
remeasures exactly: repeated 634.430366/688.577488 ps, maximum slew 156.083759 ps,
all native/slew gates passing. Its overlap with fine31 is +58.070422/+167.461298 ps.
The zero-code case remains active and must pass the complete fastest-quarter
and native/slew gates. Both cases retain the full 20 ns fixture and original
observations. This measured-gang model still needs its own three-point verdict;
no whole-bank or PHY admission follows.

The 0.76 um original width prototype separately passes its three initial
endpoint cases with overlap 20.649958/10.736333 ps and max slew
247.110212 ps. Its new local geometry/RC remains unqualified; it cannot
supersede the measured-RC bank failures. The 0.80 um campaign also retains
its original scope in `moscap_fine_component_v89/2be386aad63fa8a0`.

The full regression passes **2,146 tests without skips** in 389.665 s
(`build/measured-balanced-joint-zero-v146-full-tests.log`), including physical
graph, native reconstruction, typed observation and complete zero-screen guards. Both CAD campaigns also reject injected metal,
label and duplicated-instance faults; these native layout checks supplement
the software suite. Native architecture experiments
use the unchanged six-engine dispatcher and at most two workers per campaign;
healthy older solvers and failed results are retained. Remaining timing gates
must pass before bank/common-RC, dense/update/periodic, all-PVT legal-code
and full clock/link qualification. No voltage sweep is introduced; temperatures
remain 0/25/40 C, and input-duty endpoints remain 40/60%.

Earlier implementation checkpoints:

The both2 actual-component-RC bank now passes the complete six-point sparse
SS/40 C screen in independent receipt
`nlvt_guard2_sparse_verification_v41/834d4ff6707b3812`. Fine carry is
17.422/7.449 ps rising/falling, coarse overlap is 376.347/96.290 ps, and
maximum native span is 1.893185 V against 1.95 V. All voltage, internal/public
control and repeated-pulse checks pass. Zero-code headroom is only **4.286 ps**;
common/control/tail wiring remains unextracted, and dense codes, periodic
clocks, all-PVT timing and the PHY remain unqualified.

The corrected named-pin physical netlist for all 156 components and 39 public
pins passes independent Yosys reimport and native connectivity/parameter
equivalence (`tg_bank_netlist_verification_v46/71ab47a14855ae22`, exporter v45).
The fine-cell physical ports are explicitly adapted from legacy
`NODE/EN/ENB/VDD/VSS` to `A/CTRL/CTRL_B/VPWR/VGND`; the capacitive data port and
supplies are inouts. Registry preflight exposed incorrect direction/use roles
for these legacy names in the earlier v42/v43 physical interface. Those frozen
artifacts are retained, and v45/v46 supersedes them for physical integration.
The native SPICE connectivity and measured timing were unaffected: the expanded
signature remains `d78fc44432de65fe35486216c43f8d1a215f09024c43327b3892819c416cf5fc`
for all 903 MOS and 65 MIMs with exact parameters and body ties. Thirteen
imported-JSON and two native-SPICE corruption controls are rejected, including
rewiring the actual canonical fine data pin. This is structural input for
macro registration, placement, routing, whole-bank DRC/LVS and joint RC
extraction; it transfers no electrical admission. The full software regression
passes **2,025 tests without skips**, including the canonical fine-cell and
physical adapter checks.

The normalized physical cell library
(`bank_cell_registry_v44/61876a666017a856`) also passes: all ten functional
masters plus tap/filler import into OpenDB with exact pin rectangles; all five
custom masters pass fresh GDS import, zero DRC, strict native LVS and native
dimension/junction checks. Manufacturing masks are preserved under translation,
fine-cell GDS labels are canonical, and LEF includes native MIM routing
keepouts. The library alone does not establish bank supply/body connectivity. Independent library geometry receipt
`bank_cell_registry_verification_v48/b1813242cd69dc23` passes all twelve
masters, merged-hierarchy mask comparison, fresh OpenDB import and six actual
corruption controls. Whole-bank routing and joint RC remain required
before the next timing gate.

The first complete both2 placement now passes in
`tg_bank_floorplan_v49/0a60afeff47f241b`: 156 functional instances plus 86 taps
and 86 fillers in 43 control groups, within 454.02 by 106.08 micrometres.
Actual OpenDB coordinates, every logical terminal and all 39 public ports
match the intended graph. The assembled GDS with fixed fine data/supply buses
passes zero DRC. Physical M3 component checks connect all 31 fine data rails
to the output driver and join both fine supply rows without touching other
named nets. This is partial routing; coarse/control/remaining supply routing,
whole-bank native LVS and joint RC timing still remain. Routing bring-up also passes in
`tg_bank_route_v50/9c3f35cf80e72b04`: all 145 non-preconnected nets have actual
regular wires, the final router violation count is zero, and every instance,
placement, public port, body connection and master pin geometry/type is
preserved. The two fixed fine power buses are restored exactly after routing.
Router checks are separate from full GDS DRC/LVS; physical streamout and fresh
native qualification now pass in v51 below. The full regression passes 2,030
tests without skips.


The fully routed native GDS checkpoint now passes in
`tg_bank_native_gds_v51/05d794b67900d80f`: zero flattened Magic DRC and a unique
strict native LVS match. All manufacturing masks and native routing from the
placed source are retained, and all 903 MOS/65 MIM model dimensions and every
previously supplied junction parameter agree. Actual junctions are newly
measured for 418 standard-cell control MOS whose earlier reference supplied
W/L only. This is no timing transfer: joint RC extraction and a fresh zero-code
native waveform remain the next gate. Antenna and independent foundry signoff
also remain separate. The final frozen-producer regression passes all **2,035 tests without skips**
in 364.640 seconds, including five new native-inventory tests.


The complete bank joint-RC proof also passes in
`tg_bank_joint_rc_verification_v52/fa94fb57149b7ec4`: all 39 ports, 30,288 raw
resistors and 10,556 capacitors are verified passive. Exact reduction yields
22,517 resistors while retaining every capacitor and native-device statement.
Independent sparse terminal-current witnesses pass at 8,789 boundary nodes;
collapsed native LVS and all 903 actual MOS junctions/65 MIM geometries match
the routed native reference. The extraction retains the existing 0.01 fF
capacitance reporting threshold. This supplies the actual joint model for the
next complete SS/40 C zero-code transient; no routed timing or PHY admission
exists yet. The earlier component-model headroom remains only 4.286 ps.


The complete first routed SS/40 C zero screen is now measured and independently
rechecked (`joint_bank_zero_v53/6c3374a3e635505d`, receipt
`joint_bank_zero_verification_v54/a41613b9a7864021`). It **fails timing**:
603.996/725.646 ps rising/falling, with **-115.890 ps** conservative quarter
headroom. All 903-MOS voltage checks, all 93 fine/40 TG programming gates,
639 control-terminal observations and repeatability pass. Peak native span is
1.867242 V. All 2,041 regression tests pass without skips.

Complete-trace diagnosis `joint_bank_zero_diagnosis_v55/36ad887c243c85e0`
finds roughly 81 ps of added falling-edge latency before the final inverter
and 39 ps afterward. Explicit wire capacitance rises 19.840 to 31.658 fF on
the first mux node, 21.375 to 32.894 fF on the selected node and 102.766 to
119.425 fF on OUT. The repair experiment relocates input inversion to four
first-level mux-output regenerators, reusing the qualified INV2 component.
The separate component-RC feasibility campaign
`regenerated_bank_v56/454ef5c8722f8a61` is running with 951 MOS and 68 MIMs;
its new common/control/power routing remains unqualified and cannot replace
the complete routed failure or supply timing admission. Its complete 20 ns
waveform remains pending. The updated regression passes all **2,044 tests
without skips** in 362.785 seconds.


The selected next architecture is [calibrated digital clocking v2](digital-clocking-v2.md):
four-section TX and RX DLLs with symmetric rising-event DCCs, one RX deskew
DCDL, explicit startup training and an independent 25 MHz management clock.
The existing LVDS analog I/O is retained. There is no background CDR, dual RX
bank, FFE or PODL driver. Legacy wrappers remain the development baseline until
the new physical clock islands and training integration qualify.

The repaired weighted delay bank now passes whole-bank GDS physical checks,
fresh passive RC extraction and independent strict flat native-device LVS.
The matched four-case physical fine-control campaign is complete. Independent
remeasurement passes both guarded DATA biases and retains the ideal-source
comparisons as failures. The unchanged gate has admitted the complete routed
model to its sparse timing pilot. A bounded live prefix already exposes 40
terminal-limit violations in the return-mux region (observed peak 1.97362 V
against 1.95 V), with very little conservative zero-code quarter-period
headroom. A reproducible bounded-prefix diagnosis confirms 32 downstream gate
stresses and eight return-device drain/source stresses. Both completed native
extra-drive/optional-MIM diagnostics fail voltage stress (peaks 2.01877/2.01047 V),
so neither is selected. A new separated-output child/pair passes DRC/LVS,
independent native-mask/source/placement checks and fresh passive-RC verification.
Pair B-Y coupling falls from 10.5944 to 0.67189 fF (93.7%) without resizing
transistors or MIMs. Native transient voltage/delay and a newly routed whole
bank are still required before this candidate can qualify as a repair. Both
original 60 ns traces are now recovered in a separate receipt after the old
producer failed JSON serialization of a NumPy Boolean. Pulses and control
settling pass, but the rising fine carry decreases by 6.6--6.9 ps and the first
coarse/fine ranges leave a 655/568 ps rising/falling gap. A smaller coarse step
and monotonic fine architecture are required in addition to voltage repair.
The original failed producer and raw evidence remain untouched. These results do not yet qualify
delay range, legal-code ROMs, all-PVT clock timing
or the complete link. See the [routed-bank timing checkpoint](digital-clocking-v2.md#staged-native-timing-using-complete-routed-bank-rc).

The replacement uniform-tap prototype is now implemented in
`scripts/dcdl_uniform_tree_v3.py`. Its complete 16-tap/32-setting native pilot
`dcdl_uniform_tree_v3/486381e17636fb87` uses 875 MOS devices, verified component
buffer/fine RC and a two-level mux4 selection tree. Ten SS/40 C static-code
cases screen coarse 0/1 and fine 0/1/15/16/31, with two complete pulses per
case. The pilot and independent waveform verifier have been launched with the
unchanged dispatcher and at most two solver workers. Native source mux/control
cells and ideal common wiring still require physical implementation and fresh
joint extraction. This sparse experiment cannot qualify dense legal codes,
updates, periodic 40%/60% clocks, all-PVT timing or the PHY.

Fresh native mux GDS/private-node inspection now passes exact-source LVS for
both mux4_4 (13 distinct private nodes) and mux2_4 (six). Independent reimport,
extraction and repeated LVS receipt
`mux_tree_access_verification_v4/bd92d6d6bb512d60` confirms unchanged native
masks and identical access observations. The existing LI candidate search finds
usable-size rectangles for only five mux4 nodes and four mux2 nodes; complete
private-node routing access is not proven. The failed first n-diffusion-only
label probe remains retained. This is a physical-access result, without mux
voltage, RC, timing or PHY qualification.

The uniform bank now has a checked structural physical netlist, including
explicit supply/body ties and the final tap's balancing load. Export
`uniform_tree_netlist_v3/11cd16824e8785a8` and independent fresh-import receipt
`uniform_tree_netlist_verification_v3/46218d038aded0a4` preserve all 120 native
components and reject eight actual imported-graph corruption controls. Checked-in
Verilog/blackboxes compile for all declared dimensions. This is a placement and
routing input, without routed geometry, parasitic or electrical admission.

The first complete uniform-bank RC case now fails at coarse/fine zero:
1.66/2.50 ns rising/falling delay versus a 610 ps fast-quarter budget, and
2.311 V worst MOS terminal difference versus 1.95 V. Both complete pulses and
control settling pass. A matched diagnostic preserves all 875 MOS devices,
their extracted junction parameters and all native MIMs while deliberately
removing component routing R/C. Its zero-code case still fails at 1.12/2.03 ns
and 2.342 V. Complete-waveform receipt
`uniform_zero_diagnosis_v4/2961120aa3611ff5` verifies both traces and locates
about 1.54 ns of idealized falling delay in the two mux4 levels. This candidate
is not selected for full-bank routing. The next circuit experiment must replace
the mux4 data path with a native transmission-gate tree and a separately sized
fine-bank driver; all existing timing and voltage limits remain unchanged.

That replacement is now implemented as `dcdl_tg_tree_v5/88d4f72c48c8e1b5`:
balanced transmission gates, real static one-hot decoding and a separate
fine-bank inverter driver, with restored/direct output comparisons. Independent
receipt `dcdl_tg_tree_verification_v5/2d21722f18cb5037` verifies the first eight
complete 20 ns cases. The wider-TG direct-output zero code reaches
428.019/520.509 ps rising/falling delay and 89.247 ps fast-quarter headroom;
its first fine step is 10.191/5.249 ps. Voltage still fails in eight MOS devices
at the balancing buffer's unloaded output (peak 1.95585 V). A fresh revision
must add and test a real tail-output capacitive termination; the active bank
and all its evidence remain unchanged. New TG junctions are prelayout estimates
and component wire parasitics are idealized, so no physical or PHY admission
follows from these sparse results. The 24-case campaign continues.

The native termination revision is now complete:
`dcdl_tg_terminated_v6/36524d260790b5b9` adds one 2x2 MIM to `unused_tail`
while retaining every MOS and active connection. All six SS/40 C sparse cases
pass native voltage, control settling, repeatability, zero-code quarter budget,
sampled fine ordering/gaps and first coarse overlap. Independent complete
receipt `dcdl_tg_terminated_verification_v6/f9ec6c58d7b7315d` observes worst
MOS stress 1.931542 V, zero-code 428.019/520.509 ps and coarse overlap
226.585/49.099 ps rising/falling. This is a source architecture checkpoint:
component parasitics remain idealized and new TG junctions are estimates.
Dense codes, actual component and whole-bank RC, code updates, periodic clocks,
all 15 PVT points and full PHY qualification remain open. The next electrical
gate must restore the verified component RC before selecting physical bank
routing or claiming those 89 ps of source headroom survive extraction.

That component-RC gate is now measured. All six native simulations complete,
and independent recovery
`dcdl_tg_component_rc_recovery_v8/c051828d34e445bb` passes voltage (worst
1.891679 V), all 93 distributed fine-gate observations, one-hot controls,
repeatability and coarse overlap. Timing fails: zero-code 681.361/755.655 ps
rising/falling leaves -145.899 ps fast-quarter headroom, and rising fine
15->16 is 24.162 ps against the 20 ps maximum. Added delay is concentrated at
the loaded fine driver. The original reporter omitted a passive public tail
probe; its failures remain retained, while recovery checks every actual MOS
terminal and reports the unsaved public-node range as unavailable. No solver
was rerun or restarted. This bank still needs faster data-path drive and a new
native screen before physical bank routing, dense/PVT or PHY admission.

The next controlled experiment is now launched as
`tg_driver_experiment_v9/bf8c0a4abc4024a1`. Three complete 16-tap/32-fine
variants compare doubled selector width with the original HVT drivers,
regular-threshold PMOS in the input/fine drivers with the previous selectors,
and both changes together. Eighteen SS/40 C static cases retain all 903 native
MOS observations, all 93 distributed fine gates and the same six sparse codes.
The new fixtures explicitly save the passive public tail node. Regular-PMOS
variants borrow the original inverter wiring RC for device-flavor diagnosis;
that RC is not a physical witness for the changed implant. Buffer/fine-unit RC
is unchanged. Two workers use the existing six-engine dispatcher, and the
full-result verifier waits for completion. Independent available-case receipt
`tg_driver_experiment_verification_v9/402c6ded5d4a727d` verifies the first two
zero codes: wider TGs give 583.775/663.145 ps and regular PMOS alone give
594.743/709.394 ps rising/falling, with safe voltage and controls. Both improve
delay but still fail the fast-quarter budget. The combined variant and all new
range/gap measurements remain pending. Primitive preparation also verifies
six requested MOS models/W/L and positive junctions by fresh-GDS extraction
(`tg_device_pcells_v10/505929ce7b0bf358`); those standalone TG junctions match
the estimates but do not prove routed bank parasitics. No new physical
equivalence or PHY admission has been established.

The combined regular-PMOS/quad-TG zero code now passes the sparse SS/40 C
quarter check at 506.645/608.136 ps rising/falling, but with only 1.620 ps
headroom. Its first fine step is 12.361/6.131 ps and voltage/control checks
pass. Independent receipt
`tg_driver_experiment_verification_v9/0878bd2bb6e6f70e` verifies all first six
cases. The further-widened N3.36/P6.72 TG experiment
`tg_headroom_experiment_v12/6d996229830f90f6` uses one additional worker under
the unchanged six-engine limit. Its independently verified zero code
(`tg_headroom_experiment_verification_v12/15abc73b62202730`) gives
501.308/608.113 ps: falling headroom improves by only 0.023 ps because added
input-inverter loading consumes the TG-path gain. Fine range/carry/overlap
measurements remain running. Further widening alone is not a sufficient margin
repair; the next candidate is a smaller native driver shunt MIM, with unchanged
transistor/fine-unit geometry and the same mandatory voltage/timing screens.

The faster inverter now has its own physical component witness:
`regular_clock_inverter_v14/7212db74b50b71f1` removes only HVTP (78/44), preserves
all other mask regions, all sixteen native MOS geometries and the 4x4 guard MIM,
and passes DRC, strict LVS and fresh passive distributed RC. Independent
fresh-GDS proof `regular_clock_inverter_verification_v15/5d86129b463ae172`
passes with negative mask controls. Exact network witness
`regular_inverter_network_verification_v16/34538f13d3761d76` matches all 286
electrical elements to the prior regular-PMOS diagnostic, allowing only element
identifiers/order and the root model name to differ. This resolves the isolated
inverter's borrowed-RC question; new TG/common/control wiring, whole-bank RC,
dense/PVT timing and the PHY remain unqualified. The full suite passes all
1,964 tests; original failed physical attempts and all running solvers are
retained.

The eighteen-case driver/selector campaign is now complete with no numerical
or reporting errors. Full independent receipt
`tg_driver_experiment_verification_v9/3098a005c74751d4` passes all six sparse
codes for `regular_quad`: voltage (peak 1.883721 V), controls, repeatability,
quarter delay, sampled fine gaps and coarse overlap (318.439/48.665 ps
rising/falling). The HVT-quad and regular-double variants remain failures.
The passing variant still has only 1.620 ps zero-code headroom and no routed
TG/common-wire qualification.

The smaller guard is now real hardware, not a changed capacitor parameter in
borrowed RC. `small_guard_inverter_v17/535d866a9ab25197` replaces the native
4x4 MIM with 3x3 and extends its M3 ground landing, preserving all MOS/body
masks, transistor junctions and child placements. DRC, strict native/RC LVS,
passivity and fresh extraction pass. Independent fresh-GDS proof
`small_guard_inverter_verification_v18/da386f298106c21e` also rejects changed
root routing and changed MOS masks. Actual driver RC is used in the twelve-case
`small_guard_bank_v19/4403ce2a6170108c` campaign (`fine3` and `both3`, one worker).
Independent first-case receipt
`small_guard_bank_verification_v19/ec1f4863fd997a14` measures `fine3` zero code
at 490.342/596.306 ps, with 13.450 ps headroom, safe voltage and settled controls.
The later two-case receipt
`small_guard_bank_verification_v19/cb1369375a76367b` also verifies `both3`
zero code at 475.380/568.223 ps, with 41.533 ps headroom and safe voltage/
controls. Full receipt
`small_guard_bank_verification_v19/165edf7ab05fd312` subsequently verifies all
twelve cases and passes the six sparse codes in both profiles. Falling
coarse overlap is 50.331/49.116 ps for `fine3`/`both3`; neither profile includes
TG wiring RC. The wider-TG campaign is now complete too: independent
`tg_headroom_experiment_verification_v12/8aa510ce77538201` passes all six
sparse codes but retains only 1.643 ps headroom and 33.507 ps falling overlap.

The selected quad TG now also has a real component layout:
`tg_quad_cell_v21/78e1793488d080ca` passes DRC/LVS and fresh passive RC with two
native MOS, while retaining the inspected PCell junctions. Independent proof
`tg_quad_cell_verification_v22/de62852aec6ea75c` verifies native child masks,
placements, fresh-GDS DRC/LVS and exact reduction. The rejected v20 layout is
retained (four M1 gate-pad spacing violations, LVS passed). This TG RC has not
yet been substituted into the bank; whole-bank/PHY qualification remains open.
The next gate must restore it, observe all forty actual TG gates in addition
to the existing ninety-three fine gates, and recheck absolute zero-code delay
before spending on dense/PVT bank timing or whole-bank routing.
All 1,972 regression tests pass. The original driver and wider-TG pilot/
verifier services terminate successfully; the smaller-guard campaign and its
full verifier have also terminated successfully.

The actual-TG-RC gate is now measured, and it fails timing. In
`tg_component_bank_v23/dd51484b10ebd382`, all twenty TGs use independently
verified component RC. Every one of the 903 MOS, 93 fine gates and 40 actual
R-separated TG gates remains observed. Independent full receipt
`tg_component_bank_verification_v23/a3e55bc6d04fac5a` verifies both complete
zero-code traces: `fine3` is 632.810/811.766 ps and `both3` is
618.299/785.915 ps rising/falling. Their headroom is -202.011/-176.159 ps.
Voltage, static controls and repeatability pass. Thus the earlier 41.533 ps
headroom does not survive restored TG wiring. These are complete numerical
results, not convergence failures or a relaxed quarter-period requirement.

Native-terminal diagnosis
`tg_component_path_diagnosis_v24/6e18a08567e9e556` measures saved transistor
terminals rather than inferring unsaved passive tap/tree voltages. The `both3`
falling intervals are roughly 153--165 ps and 154--164 ps across the two TGs,
then 318--327 ps through the fine driver. New source-flavor diagnostic
`nlvt_data_path_v25/a937b3dd487bed57` compares legal L0.15 NMOS-LVT only in the
TGs versus TGs/data drivers/coarse buffers; the broader variant also changes
coarse-buffer PMOS from HVT to regular at unchanged L0.15. Fine-unit and
control devices, W/L/junctions and all explicit R/C are retained. This is
borrowed-RC isolation for changed implants, not a new physical witness. Both
two-worker zero-code cases and their verifier have completed successfully.
Full independent receipt `nlvt_data_path_verification_v25/4a5573aa2eb7a558`
measures TG-only NMOS-LVT at 573.311/731.952 ps and the broader data-path
variant at 543.525/647.174 ps. Both pass native voltage, controls and repeatability,
but quarter headroom remains -122.196/-37.418 ps. Thus the broader change
recovers 138.741 ps of falling delay without yet satisfying timing. The next
physical candidate shortens and balances the TG data routes; changed implants
also need fresh GDS/native/RC proof before physical admission. Local PDK NMOS-LVT
limits permit L0.15/W>=0.42; PMOS-LVT has Lmin0.35 and is not substituted at
L0.15. All 1,983 regression tests pass. Whole-bank, dense/PVT and PHY gates
remain open.

The matched two-buffer component experiment fixes the observed 60% duty
clock-low margin regression in all four SS/40 C cases. Independent remeasurement
passes phase ordering, low-level arming, stopped-clock clearing and terminal
stress. Shared inter-driver wiring is ideal in this pilot. A physical parallel-buffer
macro passes DRC/LVS and independent fresh passive-RC verification, but its
routed timing and joint DCC first-event behavior remain unqualified; see the
[clock-drive experiment](digital-clocking-v2.md#matched-native-clock-drive-experiment-for-the-60-low-phase-regression).

Implemented v2 foundations include the machine-readable contract, conservative
physical-delay reference algorithms, atomic code CDC, clock-loss watchdog,
bounded DLL management FSM and training transmitter/receiver RTL. The RTL tests
exercise 64 confirmations, epoch/range rejection, code freezing, timeout, clock
loss, asynchronous mailbox backpressure, all 256 frame rotations, both payload
pair alignments and an independently generated TX frame reference. DLL
physical measurement paths and offset qualification, qualified delay-code ROMs,
full PHY wrappers, new
physical extraction and release integration remain to be built.
These control tests do not qualify clock timing.
Low-level measurement hardware now includes isolated tag launch with a
next-epoch comparison reference and a phase-trial controller with route/swap
holding, event-count guards, result tags, timeout and cancellation. Its default
refuses unadmitted models. Tests use synthetic paths to check the protocol,
including a full extra period that must remain long. Physical routing,
conditioners, event observers and settling still require native qualification.
The all-pairs/vote sequencer and its connection to actual isolated phase trials
are now implemented. It checks six pairs, both signed offsets and both input
swaps, rejects stale tags and reversed/disagreeing brackets, and bounds retries.
The real calibration FSM converges in a synthetic transaction test and still
requires all 64 confirmations before code freeze. Composed pulse/event tests
and Yosys process/check pass; physical offsets and native convergence remain open.
`openlvds_dll_control_v2` now connects actual calibration, measurement, clock
watch and raw-reference configuration CDC. All four codes and separated/cascaded
mode commit as one tagged bundle. Measurement waits for a separate matching
physical-settle acknowledgement; digital mailbox capture alone cannot qualify
the bank. Stale and pre-retrain acknowledgements are rejected, locked codes
freeze, and missing settling times out. A composed test reaches all 64
confirmations using actual launch/event/controller RTL with explicitly synthetic
external paths. Default physical/model admission remains closed.

That integration exposed the shared clock watch counting eight stale samples
after its CDC pipeline. Four stale samples now leave room for CDC and a
registered status consumer within the unchanged eight-management-cycle budget.
Tests stop clocks at 80 phases each for 390/400/410 MHz and verify the full bound.
This is digital protocol evidence; native DCC/warmup timing and physical PHY integration
remain open.

The DCC/startup/training control path is now connected in
`openlvds_clock_startup_v2` and `openlvds_tx_training_control_v2`. Each DCC gets
own-phase reset release and a fresh clock-watch generation; each actual
delivered phase must complete 256 warmup cycles. Both phases are required before
training starts at a full-frame boundary. A stopped delivered clock invalidates
its own data-domain readiness asynchronously. Missing clocks time out, and
independent DCC-model admission defaults false. The composed test uses actual
clock-hold DCC topology with test-only cell delays, checking framing/payload,
fresh reacquisition, per-phase clock loss, default admission and warmup rejection.
These are protocol proofs; native DCC timing, total startup budgeting and
whole-PHY integration remain open. Yosys reports zero problems with DCC admission
enabled and disabled (`build/clock-startup-v2-synthesis-1.log` and `-0.log`).

`openlvds_tx_control_v2` now connects actual DLL calibration/configuration/
measurement control, DCC startup and transmitter framing under one coordinator.
A request edge starts one calibration; the held level continues training until
the lab ends it. The final grant is synchronized into the actual pair-clock
domain. The coordinator's single 100 ms deadline spans calibration and warmup,
and failures stay latched after stages disable. Both model admissions default
false. A composed protocol test uses all actual control blocks and clock-hold
DCC topology with explicit synthetic external paths/phases and test-only cell
delays; it checks 64 confirmations, both warmups and an independently generated
432-pair training/end-marker/payload stream. Stage-error, deadline and missing
admission cases pass. This does not qualify physical delay or clock timing.

`openlvds_rx_deskew_transaction_v2` now holds the real startup path for each
code update, requires safe source-clock publication plus fresh matching physical
settling, and waits for both actual delivered-clock warmups before completion.
Cancellation retains the physical code and flushes pending transport. Twelve
composed protocol scenarios pass using actual startup/DCC control with test-only
cell delays. Model admission defaults false; full RX wrapper integration and
native backend settling qualification remain open.

`openlvds_rx_training_v3` now composes the real scanner, physical deskew
transaction and DCC startup under one overall deadline, including DLL lock wait
and final-code revalidation. Intentional update holds are distinguished from
unexpected clock loss, pending capture state is canceled, and payload code
freezes. Fifteen composed scenarios and 480 delivered-phase loss cases at
390/400/410 MHz pass; the latter preserve the eight-management-cycle bound.
`openlvds_clock_startup_v3` exposes the existing loss decode to avoid an extra
status-register delay. The eye/settling backend and cell delays are synthetic;
full DLL-controller/RX-wrapper wiring and native qualification remain open.

`openlvds_rx_control_v2` connects the actual DLL calibration/configuration/
measurement controller to the RX training/scanning path. The pre-deskew source
and post-deskew DLL reference remain separate physical inputs, with explicit
backend routes, code-settling grants and captured pairs. One overall deadline
covers actual DLL calibration, every deskew update/warmup, scanning and final
revalidation. Model admissions default false. Native backend qualification and
physical PHY integration remain open.

The passive native clock-component checkpoint passes all 1,706 tests
without skips using the `make test-full` environment; log:
`build/passive-native-clock-components-v3-full-tests.log`. Yosys process/check with both admissions
enabled and with defaults closed reports zero problems
(`build/tx-control-v2-admitted-synthesis-check.log` and
`build/tx-control-v2-default-synthesis-check.log`).

The original 270-case pulse/toggle DCC source matrix completed without numerical
errors but failed all 54 SF cases: self-reset release while CLK remained high
retriggered pulse FFs. The clock-aware reset repair passes its 24-case SF40/SS40
pilot and all 270 fresh cases in `dcc_clock_hold_pvt_v2/8b83d935bd2d01f3`.
Independent receipt `dcc_clock_hold_pvt_verification_v2/f1d1e1e39c014c23`
confirms all 15 PVT and 29.70 ps worst balanced mean half-cycle error.
Phase-specific reset release passes logic startup/quadrature regression but
still needs native CQ/recovery/removal qualification. See [repair evidence and
remaining gates](digital-clocking-v2.md#native-repairs-and-next-admission-gates).
The actual LibreLane configuration preflight now passes. Its Python environment
has no NumPy, so source receipt/witness validation runs in the separate scientific
interpreter; physical inputs bind both interpreters and package hashes. No
physical artifact or qualification was created by that preflight.
The later completed flow `dcc_physical_v2/75fb1becc16e8a41` has clean routing,
Magic/KLayout DRC, LVS and antenna counts. Its strict summary writer failed on
two infinite unconstrained timing slacks. Separate recovery
`dcc_physical_recovery_v2/5b37b88a57c9d32d` preserves that failure, binds the same
GDS used by signoff and validates true constant tie clones and power-only row
endcaps without changing signal topology. Fresh extraction contains 6,890 R and
734 parasitic C; the independent transistor-topology audit passes. Nonfinite
slacks remain explicit diagnostics, not zero slack or timing closure. Native RC
clock behavior, actual loads/slews/duty and whole-PHY qualification remain open.

RX scan control and capture-domain integration are now implemented in
`rtl/v2/openlvds_rx_scan_v2.v` and `openlvds_rx_training_v2.v`. The scan tests every
legal code, times out missing markers individually, selects maximum conservative
physical clearance, reapplies the best code and requires a new four-frame pass.
The default refuses unadmitted timing tables. Tagged command/result mailboxes
reject stale measurements, code updates use atomic raw-clock-domain commits,
and separate raw/capture clock monitors invalidate status even when the capture
clock stops. Reference comparisons cover unequal code spacing, split/narrow
eyes, malformed ROMs, timeout and final revalidation failure. An integration test
uses a clearly synthetic eye mask to exercise actual frame recognition, the
end marker, payload publication and stopped-capture-clock invalidation. This is
control/CDC evidence; it does not qualify the mask as a timing model.

The original NAND-mirror DCDL source pilot completed 12 cases in
`digital_dcdl_v2/52741a634623ac02`, retaining one numerical timestep collapse at
the PWL falling corner. The separate smooth-source diagnostic
`digital_dcdl_smooth_v2/669f29af98c95bd2` completed all four cases without
numerical errors; both campaigns were independently remeasured. Matching TT25
smooth-source endpoints expose a real range gap: coarse 0/full fine rises at
446.0 ps, while coarse 1/zero fine rises at 559.8 ps, leaving 113.7 ps uncovered.
The corresponding falling gap is 97.3 ps. Thus the enabled-inverter fine bank
cannot meet the unchanged 20 ps common-code gap limit.

A new custom MOS-switched native MIM fine bank is being evaluated in
`digital_dcdl_cap_v2/7261f0f8fd8f0771`. All 12 source cases completed without
numerical errors. The 2x2 geometry at TT25 expands the coarse-0 rising delay
from 306.3 ps to 842.9 ps and overlaps coarse 1 (501.4 ps minimum); all custom
MOS stress checks pass. That establishes range feasibility only. Dense code
steps still need measurement. A second candidate strengthens just the return
merge from NAND4 to NAND8, keeping the 2x2 MIM geometry, to reduce fine step size.
`digital_dcdl_batch_v2/de70a6fd17e9ca96` measures every fine code at coarse 0/1
and TT25/SS40/FF0, eight isolated tagged pulses per run. Codes change only while
the input is low. The first eight TT25 codes rise at 305.0--360.1 ps, with
adjacent steps about 6.0--8.7 ps and all 93 custom MOS checks passing. The full
192-code/24-run source matrix is complete, retaining ten producer measurement
failures from the internal logic check. Reanalysis also finds real SS40 stress
at 1.95726 V, beyond the unchanged 1.95 V limit. It is not all-fifteen-PVT or
physical admission.

The initial batch analyzer incorrectly applied a 10 mV reference tolerance to
internal complementary control outputs. Native traces show up to 26 mV of
feedthrough, comfortably within digital logic margins. The producer failures
and immutable traces remain retained. `analyze_dcdl_batch_v2.py` independently
compares binary/exports and remeasures them with strict 10 mV stimulus checks,
10/90% internal logic margins and unchanged 1.95 V terminal-stress limits.
Its first eight-code receipt is
`dcdl_batch_reanalysis_v2/44e9b9522ad4d449`. Sparse or reanalyzed source samples
cannot authorize a delay ROM. `digital_delay_path_v2.py` finds a single monotonic
raw-code order across supplied corner intervals, preferring 10 ps and rejecting
all gaps over 20 ps; it rejects corners that only pass after different code
reordering. Characterization coverage, uncertainty bounds, actual clock pulse
transport and physical proofs remain separate prerequisites.

The 60-case exchanged-input FF sampler completed and fails the near-zero
bracket. A retained-event regenerative arbiter removes its FF setup dead zone,
but both placements of standard-cell conditioning retain unequal-slew bias.
The retained analog conditioner plus a 30x30 um native reference MIM passes all
six new-load +/-20 ps sign, stress and reference checks; independent receipt
`clock_repairs_v2_verification/3d4ed08666f410c4`. Its 180-case all-PVT/input-swap
expansion in `analog_arbiter_pvt_v2/e6ec7847a89bd52b` is archived incomplete:
the new threshold load supersedes that circuit. It retains 54 original summaries
and 55 cases, including a final export, in retirement receipt
`superseded_clocking_drain_v2/1598271_440984732`. Healthy solvers and exports
finished before the exact Python coordinator was retired.
The original 18-case native signed-threshold pilot completed without solver errors in
`phase_threshold_v2/b5b100243bdaa8b1`: matched switched-MIM branches after
conditioning, both threshold selections and raw -20/0/+20 ps under matched
and unequal slews at SS40. It checks the changed load, native custom-device
stress and unchanged reference-ripple limit. All-PVT, control-update and
physical threshold qualification remain open.
The first two threshold cases fail PMOS stress despite correct signs: the
off-branch driver node undershoots to -0.156 V. A separate six-case 4x4-base-MIM
repair completed in `phase_threshold_load_v2/f8c2416efc6cd197`; all six cases
pass sign, stress and reference checks. Independent receipt:
`phase_threshold_load_verification_v2/aaa5f22c61533cda`. Unequal slews, PVT and
physical threshold qualification remain open. The original producer is retained.
The six repaired native cases also pass independent 200 ns/20 ns quiescent-prefix
equivalence (`phase_prefix_verification_v2/15be3c82462f9f28`), with a 3.31 times
aggregate runtime improvement. Hardware warmup is unchanged. A new 30-case SS40
cohort in `phase_threshold_slew_v2/1a45576caa4bab48` completes and independently
passes all remaining input orders and unequal 20/250 ps slews in
`phase_threshold_slew_verification_v2/7061a3cc4f520556`. The new 540-case
`phase_threshold_pvt_v2/7f2eeea8cd9e0678` is running all 15 PVT, both swaps,
three offsets, three slew pairs and both threshold selections. Verification is
queued. This remains static source evidence; physical matching, route updates
and native convergence are unqualified.

A native 2x2 MIM shunt reduces complementary DCDL control stress to 1.93214 V
in the first eight SS40 codes; stronger inverter drive instead worsens stress.
The separate six-case shunt margin campaign tests both code directions, large
jumps and 20/100/200 ps control slew. All six cases completed and were
independently remeasured in
`dcdl_control_margin_verification_v2/7f57360f2f2b99f7`. Both shunts fail 20 ps
bulk updates, but pass 100/200 ps. The worst fast-update stress is now caused by
shared-node r0 undershoot below -0.16 V. The four-case
`dcdl_charge_kick_v2/a802a32a83c0b5ee` compares shared-node MIM capacitance
against one-bit updates at both bank endpoints. No delay ROM or detector is
admitted. All four source repair cases pass; independent receipt:
`dcdl_charge_kick_verification_v2/702b10e5862a3a2e`. The 4x4 node shunt peaks at
1.91815 V, compared with 1.94795 V for 2x2 and 1.93223/1.87948 V for single-bit
updates near the low/high endpoints. Its 150-run all-PVT dense-code/bulk-update
expansion in `dcdl_node_bank_pvt_v2/e307e4f382060f33` is archived incomplete
after the same source core failed the actual unit-RC minimum. Retirement receipt
`superseded_clocking_drain_v2/1603762_441209628` retains 43 original summaries
and 45 cases, including the final healthy exports. No running solver was killed.
It does not qualify RX range or select a minimum-area implementation.
The complete original
24-run dense reanalysis is retained separately
in `dcdl_batch_reanalysis_v2/163552785b25d024`, including all eight SS40 stress
failures and all original producer measurement errors.

A physical five-device fine-switch unit is now built from actual PDK PCells.
`mim_switch_unit_physical_v2/9ee573b2d67b6ab9` passes zero-error Magic DRC and
unique independent LVS after three retained failed routing placements. Its
fresh distributed extraction contains 199 resistors and 55 parasitic capacitors;
independent topology/model receipt:
`mim_switch_unit_verification_v2/e0f493e7d69328f9`. This qualifies component
geometry/connectivity only. It supplies no whole-bank or electrical admission.
The integration LEF (`mim_switch_unit_abstract_v2/e1049520c33a5145`) exposes only
the five designated M3 rails and moves other routing shapes to obstructions,
preserving every routing rectangle and the GDS. Actual OpenROAD/OpenDB port
validation passes. This does not qualify an array or its timing.
The NODE interconnect bound is about 3 fF/unit. The exact 31-unit RC/source-core
SS40 experiment `dcdl_unit_rc_v2/fd1d622597ea4be3` completed and was independently
remeasured in `dcdl_unit_rc_verification_v2/d44e7b19d8358afc`. Stress passes, but
minimum rising delay is 711.88 ps, above the required 609.8--641.0 ps quarter
range. The present driver configuration cannot advance to whole-bank routing.
A separate three-case native compound-driver search completed in
`dcdl_rc_drive_v2/7d81b2af858f05f5`, preserving the exact unit RC and timing/stress
limits. Independent receipt `dcdl_rc_drive_verification_v2/cc13670b539c43b5`
confirms all three stress passes. The only range survivor has first/repeated
fine-0 delays of 609.24/607.32 ps, leaving just 0.52 ps first-edge headroom.
It is not selected for routing. A fresh four-case SS40 balanced-drive pilot
(`dcdl_balanced_drive_v2/ebaad5ef41119fe1`) doubles the whole coarse core,
compares two output drives and tests coarse codes 0/1 with identical hardware.
Independent checks use worst first/repeated minimum-code delay and both-edge
coarse/fine overlap. Dense steps, all-PVT, compound-cell physical proof and
full-bank RC remain open.

The terminal `core2` coarse pair recovers minimum-delay headroom (556.41 ps first,
554.65 ps repeated at coarse 0/fine 0), but coarse 0/fine 31 reaches only
832.95 ps versus coarse 1/fine 0 at 858.19/857.68 ps. Even the best repeat leaves
a 24.73 ps rising range gap. Independent binary/export remeasurement and
before/after hashes retain these two case witnesses while other parent cases
continue. This is a measured range failure, not a numerical error.
The complete four-case campaign now has independent receipt
`dcdl_balanced_drive_verification_v2/ca2ad9a4ffc2cf92`. All cases pass device
stress, but conservative rising overlap is -25.24/-27.11 ps for the two output
drives. Extra output drive improves minimum-delay headroom but does not close
the range gap; neither candidate qualifies an overlapping code table.

A separate larger fine-switch unit changes only its switched MIM from 2x2 to
2x3 um; MOS geometry and the 2x2 control shunt remain unchanged. Actual PCell
inspection, fresh layout and unique LVS pass with zero Magic DRC errors in
`mim_switch_2x3_physical_v2/7635bb0cb7abe0c4`. Fresh GDS extraction and independent
topology receipt `mim_switch_2x3_verification_v2/26f440d15e6e9da1` pass; its
198 R/55 parasitic C model has about 2.97 fF NODE interconnect load, excluding
intentional MIM and MOS capacitance. The M3-only LEF passes OpenDB validation.
Original 2x2 layouts/models are unchanged. Six native tasks in
`dcdl_larger_unit_v2/b22eb8e365e6d65a` test 31 actual extracted larger units
at SS40/FS40/FF0, coarse 0/1, fine 0/1/16/31/0. All six pass independent overlap,
first-edge headroom and stress checks in
`dcdl_larger_unit_verification_v2/8c6234e034c425d5`. No dense ROM, full-PVT, full-bank or PHY
admission follows from the component proofs; whole-bank routing remains held.
The first SS40 pair passes source-core/extracted-unit stress and restores
conservative rising overlap to 34.51 ps: coarse 0/fine 31 is 892.10 ps versus
coarse 1/fine 0 at 857.59/857.08 ps. First/repeated coarse 0/fine 0 is
555.80/554.05 ps, leaving about 54 ps first-edge headroom. This is early component
evidence. Across all three pilot PVT, minimum rising overlap is 32.48 ps and
minimum first-edge headroom is 53.95 ps.

The native shared 4x4 shunt has zero Magic DRC errors and unique LVS in
`mim_base_4x4_physical_v2/d32143aff2efa2c7`; raw/restricted LEFs are retained.
The first access-parser failure is preserved separately. The complete bank
generator matches the measured 128-cell core at every coarse setting, adds real
control drivers and 31 fine macros plus the shared shunt. Its original direct
parallel-gate netlist fails Yosys's multiple-driver check. A separate 174-instance
physical view uses 64 single-output compound macros, expands to the same 238
native instances, and passes Yosys with zero problems. All four compound types
now pass native geometry/connectivity checks in
`compound_driver_physical_v2/e526d97182ddb6c5`, and extracted topology audits in
`compound_driver_rc_v2/ff754f3ebf571140`. OpenDB checks all six macro interfaces,
174 instance connections and 96 nonoverlapping macro placements in
`dcdl_bank_assembly_v2/cbcead194f7cc775`. Whole-bank routing, native timing and ROM
admission remain open.

The first routed DCC timing tests fail: long pulses overlap or prevent the
OR output from falling through its switching threshold. Independent receipt
`dcc_native_failure_v2/a8e252ff2a35af3d` retains the first two raw-waveform
diagnoses. Terminal excursions also exceed the screening limit. The native
pilot continues without restarting healthy solvers. The source-only DCC pass
therefore does not admit the routed backend.

New DCC experiments replace the one-shot/800 MHz toggle stage with independent
400 MHz toggles and an XNOR. Reset-qualified feedback fixes the observed extra
startup toggle, but a single XNOR still has duty bias. A swapped-input paired
XNOR source pilot and real compound layout now test a symmetric alternative.
The five-cell reset-qualified candidate separately passes complete physical
checks and fresh RC topology in
`dcc_toggle_pair_physical_v2/59c37db357dc5b9b`; four native timing/stress tests
are queued. These are diagnostic candidates; all clock admission defaults stay
false. See [the native DCC experiments](digital-clocking-v2.md#native-dcc-failure-and-replacement-experiments).

The four native tests of the five-cell candidate now complete and fail timing
or terminal screens. Static NAND storage and real MIM shunts lead to a new
buffered transmission-gate combiner. Independent receipt
`dcc_static_verification_v2/23edcfb662ca029c` confirms startup, output events and
terminal screening in all 24 SS40/SF40 source cases (peak 1.933721 V). Mean
half-cycle error still fails in eight cases; there is no production admission.
The agreed 50 ps criterion remains the descriptor's **mean** error. Individual
cycle excursions are retained as full-link diagnostics.

A completed eight-device TG width experiment passes N=1/P=3 µm matched cases
at SS40/SF40, with worst mean error below 37.5 ps. All twelve cases of the
continuous 410 MHz conditioner pilot pass at SS40/SF40 and limit phase-spacing
perturbation to 4.21 ps under the tested fanout and both unequal slew directions. That pilot
holds the actual DCC in reset. Independent receipt
`conditioned_clock_verification_v2/94097d668b5de414` confirms exact regenerated
sources/decks/MOS coverage and raw remeasurement. The running joint source
pilot connects the DCC and real two-edge reset release; all twelve SS40/SF40
N1/P3 cases pass all checks. N1/P4 remains running. The first controller's tied-REQUEST terminal-stress
failure is retained separately and fixed by direct first-stage data. Its
cohort was safely drained after active children finished.

Native NAND2 drive-2/8 with actual stack/output MIM shunts now pass DRC, unique
LVS, fresh RC and independent topology checks. Their isolated extracted-gate
pilot exposes terminal excursions and heavy-load settling limits: the first
two fast-slew drive-2 cases reach 1.980/1.956 V and are not admitted. A separate
larger-output-MIM variant separately passes DRC/LVS and fresh RC/topology.
Its first finite transients reduced peaks to 1.931/1.924 V, but subsequent
passivity audits invalidate both isolated-gate RC cohorts: negative capacitor
matrix diagonals make their timing/stress results unsuitable for qualification.
They are archived incomplete, preserving all diagnostics. Six additional shunted
NAND3/qualifier/inverter/buffer variants and both guarded TG XOR macros now
pass DRC and unique LVS. New flat single-pass extraction removes negative
parasitics; all ten component variants pass positive-element gates and fresh
comment-aware independent topology LVS. The original joint RC pilot failed near
17 ps and is archived. Replacement `native_clock_components_v2/fab3576c6ca5b3c8`
is live with 880 tracked MOS per case; its first two simulations have advanced
past 4.5 ns. Native timing is unproven; independent raw verification is queued.
It still uses ideal inter-component wires; routed
whole-backend RC, integrated native timing and full-PVT qualification remain open.
See [the joint-clock evidence](digital-clocking-v2.md#joint-conditioned-dcc-and-native-reset-release).
The [passivity repair record](digital-clocking-v2.md#passivity-repair-before-native-timing-qualification)
binds failed RC, corrected extraction, strict sign/topology gates, partial
waveforms and exact process-retirement receipts. The source/threshold campaigns
and retained passive bias/DCDL compound models are unaffected by this failure.

All diagnostics use the existing shared six-engine dispatcher, with at most
two workers per campaign. Independent verification is queued after the active
campaigns; no healthy solver has been restarted.

The legacy analog timing screen completed 54/54 and reports tail140_w20 as its
survivor, with worst estimated zero offset 3.803 ps. All four RX skew buffers
decode 32/32 bits and pass stress, but fail the unchanged 200 ps hold-margin
requirement (about 166--168 ps). These results motivated real RX phase/duty
restoration. The old 1215-case analog expansion and extended aperture campaign
have been drained: exact coordinator dispatch stopped, active solver/export
children finished, and separate receipts inventoried the evidence before the
coordinators retired. The analog expansion retains 16 original case summaries
and two terminal exports awaiting separate remeasurement. The aperture drain
retains 1043 point summaries and two terminal exports; point counts are not
completed aperture-boundary counts. Neither incomplete campaign is admitted.
Original producer files, artifacts, and the qualified original 480-condition
capture aperture remain unchanged. Drain receipts are under
`build/diagnostics/legacy_clocking_drain/`.

Previous analog bring-up checkpoint (2026-11-03):


The compensated driver has independently passed all thirty native output
cases and all thirty long component cases. Coupled restoration
`compensated_coupled_restoration/40f1b82bf02b80fb` is complete and independently
verified: all 32 diagnostic bits decode, with zero word errors and no missing
clock responses. Its actual capture clock slew reaches 216.889 ps, beyond the
current 200 ps aperture domain. The decoder's diagnostic setup/hold margins
are 66.326/328.496 ps. Actual DLL phase, sufficient training, characterized
aperture-subtracted margins and full-length link qualification remain open.
Verified per-edge analysis also finds that a common phase shift cannot
satisfy both 200 ps margins with the diagnostic aperture estimates; separate
rising/falling shifts have nonempty intervals. Clock duty-cycle restoration
therefore needs a real circuit experiment after extending aperture coverage.

The native capture aperture has now completed all 480 original conditions,
with independent remeasurement. SS40 bounds are 270 ps setup and 110 ps
hold; the domain remains 20–200 ps. The receive-clock buffer handoff also
verifies the original binary/export witnesses and starts the first two of
four declared skew-buffer variants in `rx_clock_skew_source/1db2d1392fbf30a2`.
These new source circuits still need complete timing results; they are not
physical, PVT, actual-DLL-phase or PHY admission. Native internal TX gate
observations continue separately.

All four standard-cell DLL frontend candidates failed the complete bounded
screen without numerical errors. The analog architecture now uses an
always-biased resistor-loaded NMOS preamp and a PMOS decision stage. Legal
parallel MOS fingers and a measured preamp-mirror correction produce three
complete SS40 DC survivors; the fourth is rejected for headroom. The native
54-case analog timing screen is running. Its narrow 140 uA frontend passes
both original false-BAD cases: +50 ps / 20-200 ps and -50 ps / 200-20 ps,
including receiving-gate, reference and stress checks. The wide 140 uA and
280 uA frontends clear BAD in the forward case but fail reference-voltage
tolerance. These individual cases are not a full timing screen result;
both complete offset curves and zero-balance brackets remain required.

`expand_dll_analog_frontend.py` implements a separately gated 1,215-case
source expansion for a fully verified survivor across all fifteen PVT and
390/400/410 MHz. No source survivor has yet been admitted. Source controls,
fresh analog physical implementation and RC extraction, native qualification,
closed-loop/stability checks and joint PHY release remain required. Healthy
experiments continue under the shared six-engine dispatcher.

See [DLL source expansion](dll-slew-repair.md#analog-source-expansion-implementation)
and [restored coupled payload](chain-restoration.md#compensated-native-coupled-payload-restored).

Earlier bring-up checkpoints follow; their running/queued descriptions are
historical and are superseded by the state above.

DLL qualification has a completed electrical failure at SS40, +50 ps phase
and 20/200 ps input slew. The solver completes all 160 ns, but BAD stays high
for a phase error required to be valid. Saved native controls show overlapping
absolute filtered errors for valid +50 ps and invalid -150 ps, so widening
a symmetric threshold would risk hiding a fault. Three matched input-buffer
diagnostics are queued in `dll_input_conditioning/b93665ce5ff8f7c9` to test
slew conditioning while retaining the +/-150 ps fault checks. Native DLL
signoff remains held; original failures and running models are preserved.
See [the failure and controlled experiment](chain-restoration.md#routing-and-feedback-isolation).

The new `stage_compensated_phy.py` provides explicit, gated staging of the
compensated driver/preferred receiver/corrected DLL and exact physical
TX/capture. It requires complete driver and DLL qualification plus restored
coupled payload, retains fresh physical driver-node guesses, and binds all
eight model views. Its loader rejects changed evidence, missing blocks and
approximate or release claims. The actual incomplete DLL correctly rejects
staging, so no bundle is prepared. Connecting the later full-link runner to
this selection and completing all electrical/timing/release gates remain open.

The read-only `preflight_compensated_dll.py` checks compatibility of the new
driver/preferred receiver with the storage-corrected DLL using its matching
validation profile. The actual-model in-memory overlay preserves the
sixteen-port DLL wrapper, 38 probes and unrelated circuit closures. This
does not instantiate the DLL or qualify a combined DLL/TX bias network,
phase replay, full link or selected PHY. Existing running models and the
coupled restoration handoff remain unchanged.

The compensated driver passes all six native TT25/SS25/FF40 pilots,
independently verified: 88.5–129.4 mVpp common-mode movement and
310.7–341.7 ps monotonic calibrated transitions. The full thirty-case
native output matrix `driver_compact_native/7e50cdcac4ffb5e1` and matched
thirty-case long components `driver_compact_components/605c95726124145d`
are now running together under the six-engine limit. Coupled restoration
is implemented but requires both complete campaigns to pass first.
The full-native TT0 pair passes at 92.4–97.6 mVpp with monotonic
326.9–337.3 ps transitions. TT25 also passes both polarities at
91.5–96.8 mVpp with monotonic 327.0–338.1 ps transitions.
TT40 independently passes both polarities at 90.9–96.2 mVpp and monotonic
327.2–338.5 ps transitions. All three TT temperatures now pass; twelve
other process/temperature points remain required.
FF0 also independently passes both polarities at 113.6–120.6 mVpp and
monotonic 329.2–341.5 ps transitions, bringing native coverage to four of
fifteen required PVT points.
The joined coupled handoff is live and waiting on both complete,
independently verified qualification results before dispatching a link test.

All three TT long native components independently pass the original 2.54 us
fixtures: **91.1–92.0 mVpp** common-mode movement and **326.5–337.7 ps**
monotonic edges. Mean native supply power spans **31.92–32.10 mW IO** plus
**2.09–2.11 mW digital**, with all 305 actual MOS devices observed. Schematic
TT0, TT25, TT40 and FF0 also pass; FF0 independently remeasures at 52.2 mVpp
and monotonic 318.3–329.7 ps transitions. Seven of thirty long cases pass;
the other process/temperature conditions remain pending.

A separate exact resistor-reduction benchmark preserves all capacitors,
PDK devices, native bias and saved internal conductors. Mathematical
current witnesses pass below 1 pA while reducing resistors from 29,915 to
20,888. One matched 80 ns/1 ps transient comparison is prepared against
completed native TT25 data in `compensated_driver_exact/8afdf90644b01ae1`,
owned by `openlvds-compensated-driver-exact-benchmark.service`.
It now completes and independently verifies waveform agreement across all
1,221 saved voltages within 30.9 nV, with unchanged output crossing counts.
Observed ngspice elapsed time is 884.9 s versus the original 1,143.2 s,
about 23% lower on the shared machine. This is one matched condition;
no all-PVT or joint RC certification or model promotion is inferred. Running
qualification models and the joined coupled handoff remain unchanged.

The preceding routing-only revision remains held:

The local CMFB routing revision passes zero-error DRC, strict LVS and fresh
GDS RC connectivity checks. With native bias, its completed TT25 cases
measure **153.2–162.2 mVpp**, compared with 178.3–186.3 mVpp for the old
layout. Both still exceed the 150 mVpp reference. All six cases now
complete: SS25 passes at 138.1–142.5 mVpp, while FF40 fails at
222.2–228.8 mVpp. Only one of three PVT points passes; the full native
handoff is held. The routing improvement has not admitted a native driver.

Matched extracted-device controls with ideal core wires measure
120.6–120.9 mVpp at TT25, 60.6–64.5 mVpp at SS25 and
158.05–158.06 mVpp at FF40. The remaining ideal-wire FF failure motivates
one circuit experiment: retain one compensation MIM directly at the CMFB
output and put the other five behind one PDK poly resistor. Total MIM
geometry and all MOS devices remain unchanged. Six matched-device tests
are dispatched in `driver_source_pilot/347eaadfdb85f913`; their ideal wires
and source bias make them diagnostics, not native hardware qualification.
See [the routing and feedback findings](chain-restoration.md#routing-and-feedback-isolation).

All six compensation diagnostics now pass at TT25/SS25/FF40, with
38.7–77.7 mVpp common-mode movement and 307.4–326.8 ps monotonic calibrated
transitions. The actual schematic preparer independently verifies this
complete evidence and the original full source matrix, then dispatches
`driver_source_pilot/12b18f8552d5652e`. All six actual schematic pilot cases
now pass: 46.9–63.5 mVpp movement and 308.5–327.3 ps monotonic calibrated
transitions. Independent verification succeeds and the full thirty-case
actual source matrix `driver_shape_source/ec61f8a97b10dab9` now passes
**30/30 cases and 15/15 PVT points**, independently verified in
`driver_cmfb_lead_source_verification/1d753bc32a560831`. Common-mode
movement is 23.0–71.1 mVpp and calibrated monotonic transitions are
308.2–328.0 ps. The physical builder has started from this complete source
receipt. The new compensated macro passes zero-error DRC, strict LVS and
the independent native RC audit; six native core-plus-bias pilots are now
complete in `driver_compact_native_pilot/9a7d8f21db2f1acc`. Full native PVT
and full link qualification remain open.
Its completed TT25 pair now passes the existing native output checks:
91.5–96.8 mVpp common-mode movement, 327.0–338.1 ps monotonic calibrated
transitions and fresh DC levels of +/-322.6 mV at 1.2485 V common mode.
SS25 passes both polarities at 88.5–93.1 mVpp with monotonic
310.7–320.2 ps calibrated transitions. FF40 also passes, at
122.8–129.4 mVpp. The full native matrix remains required.
Failed stages stop without retries. Physical/native and full link gates
remain open. The routing-only native revision also passes its SS25 pair
at 138.1–142.5 mVpp, but remains held by the TT25 failures above.

The compensated physical builder is implemented behind full actual-source
verification. Read-only checks confirm 321 devices (302 unchanged MOS,
19 passives) and compatibility with the nineteen existing bank and five
inverter recipes. The completed compensated macro contains 321 devices in
42 placements. Its reported geometry extent is 937.2 x 697.9 um. Native
extraction has 40,369 resistors and 3,982 capacitors; exact degree-four
resistor elimination retains 29,915 resistors with an independent LVS pass.
The native pilot preparer is also implemented with explicit compensated
source selection, audited native bias, all 305 MOS terminal observations
and a fresh GDS-resolved compensation-node observation. Its model matches
the audited native assembly exactly, with one reference per endpoint.
The owned physical/native handoff has advanced to the thirty-case native
output matrix after independent verification of every pilot point.
Failed stages stop later dispatch.

The matched long-component handoff also passes its prerequisite checks and
is running the original thirty 2.54 us fixtures alongside the full native
output matrix under the same six-slot dispatcher.

The complete pinned `make test-full` regression passes **1268 tests**.
The complete 188.049 ns raw-versus-exact TX comparison also passes:
saved voltages agree within 13.3 nV and edge counts agree. Both retain
the original failed payload, so this admits a numerical optimization
for further experiments rather than an electrical link.

The following entries retain the earlier bring-up history.

The compact native driver completes both TT25 pilots, but fails the
common-mode movement reference at **168–176 mVpp**. DC output is about
+/-319 mV, all expected edges remain present, and calibrated edges pass at
322–339 ps. A slower common-mode excursion grows after the early prefix;
internal feedback/bias observations are queued before selecting the fix.
SS25/FF40 continue, while full native qualification remains gated. The
native shared-bias library and original long-component runner are prepared.
See [the completed native findings](chain-restoration.md#completed-native-tt25-exposes-a-slow-common-mode-excursion).

The geometric-cap36 driver now passes the complete source matrix:
**30/30 cases, 15/15 PVT points**, independently remeasured. Common-mode
movement is 37.4–142.3 mVpp and calibrated transitions are 306.6–330.3 ps.
All nineteen connected MOS-bank recipes, all five distinct inverter tiles
and the complete compact driver now pass zero-error DRC and strict LVS.
The 790 x 577 um routed driver retains all original 320 devices. Fresh
GDS RC extraction and independent connectivity audit pass; six native
TT25/SS25/FF40 output pilots are dispatched with both initial polarities.
The pilot-gated thirty-case native-output runner and automatic handoff are
implemented; full native PVT/stress and coupled qualification remain open.
These output campaigns retain the source bias circuit. Original long
component fixtures and integration with audited native shared bias remain
separate gates. The original raw-TX/r2/LTRA run also
completes all 188.049 ns numerically, while retaining its failed payload and
ten lost clock responses. See [the full source and physical preparation
results](chain-restoration.md#full-source-pass-completed-raw-reference-and-physical-interface-preparation).

The calculated **1/3/8-cap36** driver now passes all six fresh TT25/SS25/FF40
pilot cases. Calibrated transitions span 307.0–329.7 ps, and common-mode
movement spans 88.8–142.2 mVpp. The complete pilot was independently
remeasured before preparing the full thirty-case source matrix
`driver_shape_source/b1325bf847630063`, now queued. The remaining PVT points,
physical/native driver and coupled acceptance remain unproven. See the
[complete pilot results](chain-restoration.md#geometric-cap36-pilot-passes-all-three-points).

Receiver bring-up has passed **33/33 screens, 60/60 components and the new
specification-admitted RC comparison**. All three C16 DLL stability screens
pass, and full 336-case native qualification is active. The 2/4/8 driver
control fixes SS common mode but breaks FF, so it is held. A calculated
1/3/8 taper with fixed 36 um caps now has six fresh source pilots queued
at TT25/SS25/FF40. Neither a physical driver nor the PHY is admitted. See
[the latest driver experiment and completed RX gates](chain-restoration.md#first-buffer-tradeoff-and-calculated-next-candidate).

The stronger 1/4/8 gate taper fixes the measured FF common-mode failure but
now fails SS: 175–188 mVpp common-mode movement and SS0 edges as fast as
250.6 ps. A two-case 2/4/8 first-buffer control is queued at SS25 and FF40
with the capacitors and remaining circuit held fixed. The weaker 1/2/4
matrix is complete: TT/SF pass, FF/FS fail common mode, and SS fails minimum
edge time. Neither taper is selected for physical implementation. See
[the SS analysis and control](chain-restoration.md#complete-weaker-matrix-and-the-stronger-tapers-ss-failure).

The preferred receiver now passes the complete **33/33** specification
screen. Its verified handoff has started the sixty original components in
`receiver_components/24ea17b76d61a8e3`. The stronger gate taper with unchanged
30 um output capacitors passes both TT25 and FF0 pilot pairs: 61.6–63.4 and
135.7–136.5 mVpp common-mode movement, respectively, with calibrated
263.7–273.1 ps transitions across the two points. The full thirty-case source
matrix `driver_shape_source/b016a1113b51cd82` is now queued. TT25 and SS0 DLL
stability pass; FF0 continues. These are bring-up results, not PHY release.

The shaped-driver source matrix now exposes fast-corner common-mode failures:
FF0/FF25 measure 182–186 mVpp versus the 150 mVpp reference, while TT pairs
pass. A bounded stronger-taper/same-capacitor pilot is queued at TT25 and
FF0. A matched exact-TX/LTRA benchmark is also queued to compare the existing
resistor-only reduction against the unchanged running raw reference. The
TT25 C16 DLL stability screen has completed and passed; SS0/FF0 continue.
See [current experiments](chain-restoration.md#fast-corner-failure-and-stronger-gate-pilot).

The current [chain-restoration implementation](chain-restoration.md) runs a
fresh specification-based RX campaign and raw/reduced TX convergence
isolation. `receiver_acceptance.json` records the revised admission policy:
the earlier captured replay remains a stress diagnostic. Its failures below
are preserved and do not serve as the new specification admission gate.
No new RX or PHY admission has passed yet.

The new loaded native RX screens at 390/400/410 MHz all pass ordered DDR
payload and valid pulse checks; wide-static PVT cases remain in progress.
TX-only boundary MOS removal fails at the same 4.5465 ns with
the reported node moved into the native digital RX. The RX-only MOS-removal
and original-device Sparse-solver controls have also finished. Both
single-endpoint removals fail with the reported node in the
other endpoint. The both-endpoints removal was retired incomplete after the
original-device channel controls completed; its partial data remains
unqualified. The original-device Sparse control has failed at
4.4465 ns on a TX ground terminal; switching linear solvers did not clear the
collapse. The causal gate holds the tap-endcap physical rebuild.
An additional channel-model control retains all original devices and tests
the delayed-line representation, with passive analytic/reflection calibration
before coupled zero-delay and equivalent zero-loss LTRA diagnostics. Its
25/50/100 ohm calibrations all pass; both original-device zero-delay/LTRA
controls numerically complete twelve ns. The equivalent-delay LTRA model
clears the observed short-run abort while retaining every original device.
Forwarded/recovered clock activity has not started in this short window, so
these results cannot admit the PHY. The resource handoff has restored the
preferred two-resistor receiver in fresh context `02c868108c5b1da1`; its short
check completed twelve ns, followed by a wrapper missing-import error.
Recovery context `678e1b24d0305732` verifies its complete raw/export evidence
and queues only the full 188.049 ns diagnostic, preserving the original
producer and outputs. The specification screen has passed all 33 cases;
the sixty components are running, with the receiver RC comparison queued
behind their complete admission. This cannot
substitute the isolation receiver or short training for final qualification.
An immutable 25–40 ns snapshot of the running coupled test now decodes all
six observed public words as the expected training `01`, with RX clock and
RXVALID active. This supports startup chain restoration; the full payload,
long training and timing qualification remain unproven. A separate saved
20–60 ns clock-transport observation finds 31 matched events and zero missing
edges, under the diagnostic 0.9 V matching rule.

The subsequent immutable 60–95 ns payload observation finds four lost
negative clock pulses and their four following rising responses. The pulses
reach the receiver but are distorted; the first restoration node stays above
1.10 V on the lost negative pulses. Available payload words disagree, and
one recovered low pulse is only 50.6 ps at the diagnostic crossing. This
does not support changing the later buffers. The full reference run remains
active; the shaped source driver is not part of this native chain. See the
[payload analysis](chain-restoration.md#payload-clock-loss-after-restored-startup)
for measured input support and the next causal checks.

A new read-only observation of all thirty completed corrected-driver traces
finds substantial common-mode movement during transitions: 326–500 mVpp
schematic and 770–1047 mVpp native. Existing DC and center-eye results remain
valid within their scope; they do not establish dynamic generator waveform
compliance. The [waveform observation](chain-restoration.md#remaining-closure)
records the measurement and the next isolation questions. The recovered
coupled payload diagnostic is running; no TX architecture change is selected.
Three TT25 source controls are queued to isolate this finding: original
converter and ideal complementary gates with 100 ps/400 ps transitions.
Their bridge, CMFB, supplies and output load are held fixed; they are
diagnostic controls and cannot be selected as hardware.
The original-converter control reproduces 479 mVpp common-mode movement,
with up to 2.25 V error in the complementary gate sum. Ideal 100 ps
complementary gates reduce movement to 96 mVpp while retaining all 22 expected
rising output edges. This supports the gate-drive path as a major contributor;
the slower ideal-gate control has now completed at 375 mVpp despite perfect
complementarity. Fast transitions matter as well. No real converter or TX
architecture change has been selected.
Two real-MOS three-stage gate-restoration tapers are now implemented and
queued as TT25 source pilots, with supply-current and added-device voltage
observations. They retain the current bridge, mirror and CMFB. Their purpose
is to test a practical gate-drive fix. The first completes at 170 mVpp,
improving on the baseline but remaining above the 150 mVpp reference. Its
measured IO/digital powers are 26.0/1.21 mW and its largest added-device
terminal difference is 4.04 V. The stronger taper now completes at 81 mVpp
and 29.25/1.21 mW, with all 22 expected rising output edges. No PVT admission
or physical selection is claimed.
An additional fixed MIM-size pilot is queued on the first taper to separate
fast gate drive from output edge shaping. It changes only the two existing
MIMs from 10×10 to 30×30 um and measures both initial DC polarities for fresh
transition calibration. Its calculated nominal edge times are near the
lower reference limit; neither TT25 success nor PVT margin is assumed.
Both initial-state cases have now completed, with 140/139 mVpp common-mode
movement and freshly calibrated 265–270 ps monotonic edges. The complete
nominal source reference checks pass; no symmetry estimate is used for that
verdict. PVT margin and physical selection remain unproven.
The gated continuation has remeasured that nominal proof and prepared all
thirty shaped-driver source cases across the fifteen PVT points. Its two
workers are queued within the fixed-supply scope. Source waveform success
cannot automatically select a physical macro.

| Receiver candidate | Source DC | Source clocks | Physical/extraction audit | Native clock transport |
| --- | --- | --- | --- | --- |
| Original larger amplifier | 15/15 | 3/3 | Pass, 90 devices | Fail: 18 captured edges missing, 0 sharp |
| Matched smaller amplifier | 15/15 | 3/3 | Pass, 87 devices | Fail: 16 captured edges missing, 0 sharp |
| Matched larger amplifier | 15/15 | 3/3 | Pass, 90 devices | Fail: 18 captured edges missing, 0 sharp |
| Feedback inverter, two resistor units | 15/15 | 3/3 | Pass, 77 devices | Fail: 14 captured edges missing, 0 sharp |
| Feedback inverter, four resistor units | 15/15 | 3/3 | Pass, 79 devices | Fail: 16 captured edges missing, 0 sharp |

DC covers all fifteen fixed-supply PVT cases. Source clocks are the three
original full 80 ns controls; this table does not establish component or PHY
qualification. Detailed evidence follows.

- **Both weaker receiver corrections pass all fifteen source DC cases.**
  `receiver_soft_common_mode_matrix/d3271555fcb702b9` retains every original
  144 ns/twelve-point fixture, fixed supply, measured current and observed
  twelve-device stress gate. Two/three series resistor units to VDDD target
  unloaded common modes of 1.08/1.028571 V. At SS/40, minimum sampled tail
  VDS is 139/101 mV versus 34 mV control, while SF high-common-mode
  sensitivity remains passing. This is source admission, not native or PHY
  qualification. The stronger 1.2 V alternatives are rejected at SF corners.
- The new source-clock contexts are `receiver_clamp/efcc143161073193`
  (two-unit pull-up) and `receiver_clamp/1ea95c4cfc1e34f4` (three-unit).
  Their unchanged reference controls independently complete all 47 periods
  with zero missing edges. Actual waveforms are byte-identical to the
  previously completed reference; active libraries agree apart from comments
  and blank lines, and decks agree apart from include paths. Both modified
  captured-clock cases now complete the full 80 ns with 47 edge-matching
  checks and no missing/repeated edges. Both sharp controls also pass all
  47 checks, and both exact source-clock admissions are now true.
- Workflows for new geometry/extraction/native tests, all sixty receiver
  component conditions and a corrected 110:1-driver/native-receiver coupled
  diagnostic are implemented behind exact source/native gates. The two-unit
  and three-unit layouts/extractions/RC audits now pass. The complete two-unit
  and three-unit native replays each fail with eighteen captured-clock edges
  missing and zero sharp-control edges missing.
  Continuations independently lease from the
  six existing SPICE slots. They do not select a PHY or publish a release.
- **Both first-restorer threshold candidates pass all fifteen source cases.**
  Fresh matrix `receiver_restore_threshold_matrix/0f010f4a46bd1d37` compares the exact
  two-unit control with LVT first-stage NFETs at W4 and W8, preserving its
  P8 PMOS, decision/frontend/bias and later restorers. Six pilot corners
  gate bulk work; each intervention needs its own fifteen-case pass. A
  resource-only continuation waits for complete DC evidence before preparing
  original full-duration source-clock controls. Both candidates now fail their full native captured-clock tests: N4
  misses eighteen edges and N8 sixteen; both sharp controls lose none.
  Neither has native transport or PHY admission. Control and both LVT widths
  pass all fifteen cases with independent admissions. Fresh source-clock and
  physical/component/coupled continuations bind this recovery matrix. New
  source-clock contexts each pass all three original 80 ns controls, with
  47 checks each and zero missing/repeated edges. Both new layouts pass
  DRC/LVS, extraction and independent RC audit. The
  physical context `receiver_physical_followup/5896ecbb92009d53` lets both
  variants advance independently after their own complete source-clock gates;
  actual simulators still lease from the same six global slots.
  The matched SF/40 1 ps retry now completes all three variants and passes
  original DC/current/stress checks. Its superseded 50 ps LVT-N4 run was
  archived and retired near 71.9 ns; all 71 archived files and six shared-slot
  inodes remain unchanged. Resource recovery completed the untouched corners
  and fresh explicit fifteen-case admission. The original partial matrix
  remains incomplete; no electrical failure is inferred from its slowdown.
- **Separate receiver gain/balance experiments are running.** Matrix
  `receiver_gain_balance_matrix/f6d247d3b64483af` compares the exact P8/N8
  control with first-restorer P4/N8 and decision-input-pair W32 alternatives.
  All three pass all six initial DC pilots. The complete fifteen-case matrix
  admits control and W32 at 15/15 each. P4/N8 fails one FF/40 DC sample
  and is rejected at 14/15 before source clocks.
  The new source-clock, physical and native
  adapters preserve all admission gates. In `receiver_clamp/873e9ffbc7e55e38`,
  all three source-clock controls now pass 47 checks each without loss or
  repeats and receive explicit admission. The W32 layout passes DRC/LVS,
  extraction and independent audit. Both full native replays are complete:
  captured loses eighteen edges and sharp loses none. This layout is rejected.
  Full-wave restoration observation `receiver_replay/3ee72810a0ed800a/`
  `restoration_observations/f31ecf1057a06e55` preserves the diagnosis.
- **The original larger differential amplifier passes all fifteen source cases.** Separate factory/screen commits preserve the W8 decision pair
  and add a CO-versus-CL amplifier, seven-unit parallel resistor load to the
  matched trip replica, and a standard first inverter. SS/40 context
  `receiver_differential_restore_static/8241f18c7d38aac2` and FF/40 context
  `receiver_differential_restore_static/0cc939bfc9650aa0` each compare the exact
  control and two amplifier sizes in the full original 144 ns fixture with
  uniform 1 ps maximum step. All three variants pass at both initial corners.
  Full fifteen-corner matrix `receiver_differential_restore_matrix/88044ecb1112ef84`
  completes: control and `track_t16_r7` pass 15/15, while `track_t8_r7` is rejected
  at 14/15 because of its SF/0 failure. The source-clock handoff dispatches only
  the larger admitted amplifier in `receiver_clamp/60f22049d7c05297`.
  `receiver_differential_restore_clock.py` requires the selected candidate and
  control to pass all fifteen source cases before preparing the original three
  full source-clock fixtures. Only the exact unchanged reference can be reused;
  modified captured/sharp cases require fresh simulations. No new-topology
  native admission exists. All three original source-clock controls now pass
  at `receiver_clamp/60f22049d7c05297`, with 47 checks each and no missing or
  repeated edges. The ninety-device, nine-port layout
  `receiver_layout/fe64cc74ba1efc50` passes DRC/LVS, extraction and independent
  RC audit. Dimensions are 903.26 by 129.20 micrometres. Native model SHA is
  `00dfa063eaa8c4bdd030e9e04d8bcd75c2b14b7cf425431e657f651bf091c636`;
  its original full native captured/sharp replay `receiver_replay/80ceda71c5337d7a`
  completes and fails: eighteen captured-clock edges missing, zero sharp-control
  edges missing. No native transport admission exists. Read-only complete
  comparison `receiver_decision_comparison/11ec5ff01c16e3a2` remeasures the
  original W8/N8 receiver and this amplifier with identical stimuli, numeric
  policies and shared bias/digital load. Nine falling response periods are
  lost, eight without a RESTORE0 falling crossing and one without positive
  CO-minus-CL throughout its period. At the additional 56.447186 ns missed
  period, RESTORE0 does cross 0.9 V, so that case needs later-chain/pulse-width
  analysis; the other eight remain first-restoration failures. Added output
  gain has not repaired native transport.
- Complete amplifier-stage observation
  `receiver_replay/80ceda71c5337d7a/amplifier_transport_observations/53b6e8d770e8ebad`
  binds original complete native controls, input/code/deck/library/trace hashes
  and unchanged transport remeasurement. Of nine missing falling periods,
  seven never develop positive AMP_OUT-minus-loaded-CO_TRACK, including one
  without positive CO-minus-CL. At 41.823952 ns the amplifier difference does
  reach +24.624 mV but RESTORE0 bottoms at 0.9927 V, never crossing 0.9 V.
  At 56.447186 ns it reaches +56.329 mV and RESTORE0 crosses, but RESTORE1
  peaks at only 0.681132 V and never crosses. The latter loss therefore
  occurs at the next restoring stage; additional output gain has not closed
  the earlier weak-pulse or frontend-polarity failures. These are bus and
  threshold observations, not transistor-terminal gain, static trip or a
  phase-margin measurement. Native TIA and matched-family tests continue.
- The original differential factory's smaller amplifier now fails SF/0 at
  the final high-common-mode sensitivity point; the larger amplifier passes.
  All observed-device stress checks pass. The unchanged control retains the
  correct logic level. Isolated fixed-supply diagnosis
  `receiver_trip_reference/b5abcf678318f470` measures a 24.864 mV trip offset
  between whole-width first inverter and reference, while their physical
  finger equivalents agree. This isolates an additional source-model matching
  problem; it is not a loaded-reference or native timing pass.
- New `receiver_matched_trip_restore.py` constructs the reference from two
  exact parallel first-inverter units. Total widths and flattened physical
  device/connectivity multisets remain unchanged. Separate full SF/0
  `receiver_matched_trip_static/4815725ab130e6ee` and SS/40 `48704bf4e6b7438d`
  pilots now pass for control and both amplifier sizes. At SF/0's formerly
  failed 142 ns point, the smaller matched candidate gives AMP_OUT 720.154 mV,
  RESTORE0 1.012324 V and Q 1.8 V; CO minus CL remains -87.602 mV.
  Its full fifteen-corner campaign is `receiver_matched_trip_matrix/9847fc526899414a`.
  Control and both matched amplifier sizes now pass all fifteen cases and
  receive their own source DC admissions. Both variants have advanced to the
  original source-clock fixtures. Both source-clock admissions now pass; native
  and component admissions remain open; no old evidence is relabelled as qualification.
- Local differential layout and native adapters plus persistent resource
  handoffs are implemented. The amplifier, loaded reference and shunt resistors
  remain in the critical row in stage order; functional AMP nodes and CO_TRACK
  are probed in native replay. Physical followup
  `receiver_physical_followup/647205f281a50843` waits for the exact source-clock
  owner and each candidate's own complete source admissions. Scientific jobs
  retain the existing six actual slots, with no outer controller lease.
- Matched-unit source-clock and physical/native adapters now have their own
  family/profile gates and persistent handoffs. Physical followup
  `receiver_physical_followup/55c1bd46e4282c4b` waits for the exact matched-trip
  source-clock owner. Its source matrix waits for both original pilot owners
  to release their scientific locks before proceeding. Component, corrected
  110:1-driver coupling and full-versus-quick RC adapters are implemented behind
  complete native and component admissions; no downstream simulation is
  admitted yet.
- Both matched-amplifier source-clock admissions now pass all three controls,
  with 47 checks each and no missing/repeated crossings. Layouts
  `receiver_layout/89dae2ee0593cbce` (87 devices, 881.58 by 129.20 micrometres)
  and `866d09bdfac98b69` (90 devices, 903.26 by 129.20 micrometres) each pass
  zero-error DRC, LVS, extraction and independent RC audit, with nine ports.
  Fresh native contexts are `receiver_replay/5d6ec09cc0b5e515` and
  `7e767d28755ed462`. The smaller matched amplifier completes and fails:
  sixteen captured transitions missing, zero sharp-control transitions
  missing. The larger matched amplifier also completes and fails: eighteen captured
  transitions missing, zero sharp-control transitions missing. Neither has
  native/component/PHY admission. All matched-family downstream handoffs
  retain both variants without dispatching component/coupled/RC simulations.
- Complete smaller matched-amplifier stage observation is
  `receiver_replay/5d6ec09cc0b5e515/amplifier_transport_observations/c00a01def73f960f`.
  Eight falling periods are lost: one without positive CO-minus-CL, three
  without positive AMP_OUT-minus-loaded-reference, seven without RESTORE0
  crossing 0.9 V, and one despite that crossing. At the difficult 58.919554 ns
  period CO-minus-CL improves to a -2.871 mV peak but never becomes positive.
  Complete matched-fixture comparison
  `receiver_decision_comparison/267a791ef8cd2149` binds unchanged stimuli,
  numerical policies and shared bias/digital load across W8/N8, original
  larger amplifier and matched smaller amplifier. The source-reference fix
  restores fifteen-corner source sensitivity but does not close native timing.
- Complete larger matched-amplifier stage observation is
  `receiver_replay/7e767d28755ed462/amplifier_transport_observations/8401139597154c88`.
  Nine falling periods are lost: one without positive CO-minus-CL, seven
  without positive AMP_OUT-minus-loaded-reference, eight without RESTORE0
  crossing and one despite that crossing. The matching correction does not
  solve the weak-pulse restoration and frontend-polarity failures.
- Exact receiver reduction observation
  `receiver_layout/fe64cc74ba1efc50/exact_reduction_observation/e7268fd5ddd266ee`
  retains every capacitor/device/port and all eighteen native observation
  nodes. Further resistor-only algebraic elimination reduces 16,661 resistors
  to 5,365 and removes 4,209 algebraic nodes. Four independent sparse
  boundary-current witnesses pass; maximum current disagreement is
  6.661338e-15 A at 1,525 boundary nodes. The subsequent diagnostic benchmark
  below now supplies one complete transient comparison; native qualification
  models remain unchanged.
- Exact receiver transient benchmark
  `receiver_exact_benchmark/a585e2b3b0a99eaa` is running as
  `openlvds-receiver-exact-benchmark.service`. It retains both completed
  original amplifier 80 ns fixtures, 1 ps maximum step and all eighteen native
  probe vertices. All twenty-five printed voltage signals are compared across
  the complete waveform on a 1 ps observation grid with a 20 mV limit; both
  digital crossing polarities use a 20 ps limit and all original 47-period
  transport counts must agree. A failed baseline can agree and remain failed.
  The completed-trace self-check preserves all eighteen baseline losses and
  gives zero error across all twenty-five voltages. The captured-control
  comparison now passes: the candidate preserves all
  eighteen original losses, all twenty-five voltages agree within
  6.315633e-9 V and the largest digital crossing error is 1.795181e-7 ps.
  Complete simulator elapsed observations are 2672.279 seconds for the
  reference and 1565.810 seconds for this candidate under their respective
  workloads. The sharp-control comparison remains pending. Candidate
  simulations run serially at priority two through the existing six slots;
  partial output is retained. Captured complete simulator elapsed times are
  recorded as workload-dependent observations. Complete two-control agreement
  and a general speedup remain unproven; qualification models are unchanged.
- **The three-bus W32 route passes physical checks.** Layout
  `receiver_layout/677ed99567c83bfb` passes DRC/LVS, extraction and independent
  audit. Read-only wire observation `wire_capacitance_observation/d1be9c61c7463050`
  finds lower boundary wire capacitance on all five PP/PN/CO/CL/CT nets than
  the original W32 route. This does not establish timing improvement. Its own
  full native captured/sharp replay `receiver_replay/96ae8fcd14f244e4` is
  complete and rejected: eighteen captured edges missing, zero sharp-control
  edges missing. Full restoration observation is `restoration_observations/b687ae2607e5381b`.
  Complete decision comparison `receiver_decision_comparison/da25d827957d1f62`
  shows one W8/N8 missed response period without positive CO-minus-CL polarity;
  original W32 and three-bus W32 have seven and six such missed periods.
  The associated frontend observation records the weak, late PP-minus-PN
  excursion at the difficult W8/N8 period. The original larger amplifier also fails native transport; matched-unit
  amplifiers remain under test. Passive routing alone has not closed transport.
- **Both feedback-inverter variants pass all fifteen source DC cases.** Separate factory and screen
  retain the W8 decision pair and add two/four series original poly units from
  RESTORE0 to CO around a standard first inverter. The aim is lower decision
  node swing through negative feedback and faster current-to-voltage conversion. No extra differential amplifier or functional trip reference
  is used. Full SS/40 `receiver_tia_static/e00432100ec8ebad` and SF/0
  `receiver_tia_static/49580e6e4b65d68f` compare both feedback values to the exact
  control at fixed supplies and uniform 1 ps maximum step. Native, component
  and PHY admissions remain open. Both feedback values now pass both initial corners and all six pilot PVT conditions.
  Full fifteen-corner campaign `receiver_tia_matrix/33a571a155c3a105`
  completes with 15/15 for control, `tia_r2` and `tia_r4`.
  Both feedback values now pass their own source-clock fixtures. `tia_r2`
  completes all three original controls in `receiver_clamp/69a61a443f60c1e6`,
  with 47 periods each and zero missing/repeated crossings; its independent
  source admission is true. Its 77-device, nine-port layout
  `receiver_layout/0f9f54a7549bccf1` passes zero-error DRC, LVS, extraction
  and independent RC audit. Dimensions are 713.27 by 149.60 micrometres;
  its actual native network has 13,905 resistors and 1,437 capacitors.
  Fresh native captured/sharp replay is
  `receiver_replay/54143ddc298c5037`, complete and rejected: fourteen
  captured transitions missing, zero sharp-control transitions missing. `tia_r4`
  now passes all three full controls in `receiver_clamp/3d6c5bf54bb3eaff`, with
  47 checks each and no missing/repeated edges. Its 79-device, nine-port layout
  `receiver_layout/c196040b40845390` passes zero-error DRC, LVS, extraction
  and independent RC audit. Dimensions are 749.17 by 153.20 micrometres;
  the native model contains 14,246 resistors and 1,445 capacitors. Fresh
  captured/sharp replay is `receiver_replay/f03923bf25510f9a`. Its complete
  sharp control passes all 47 periods without missing/repeated crossings;
  the captured waveform now completes and fails with sixteen missing
  transitions. This four-unit candidate has no native/component/PHY admission.
  Source-clock and physical/native handoffs are implemented;
  physical context `receiver_physical_followup/ed30d5877c629f40` waits for each
  candidate's own complete source admissions. Geometry keeps four local buses
  (CT/CO/CL/RESTORE0) below the critical row and folds the unused trip reference.
  Preparation recovered from a concurrent cached-reference lock without a
  simulation retry or scientific-code change: only completed reference reads
  are serialized, and every non-lock scientific error remains fatal.
- Complete native feedback-receiver comparison
  `receiver_decision_comparison/f305aa33f9695aaa` remeasures the original N8
  receiver and four-unit feedback candidate with identical original stimuli,
  numerical policies and shared bias/digital load. The feedback candidate
  loses eight falling response periods. Four have no RESTORE0 0.9 V falling
  crossing; the other four do cross there, but RESTORE1 never reaches 0.9 V
  in any of the eight lost response windows (largest peak 0.8356 V).
  CO-minus-CL is positive somewhere in each lost feedback window, but feedback
  changes its operating-point role: this bus sign must not be interpreted as
  restored frontend current polarity or a gain/transport pass. The observed
  weak analog pulses still fail the digital restoring chain. The two-unit test now also completes and fails; faster-frontend experiments
  remain independent and running.
- Complete two-unit feedback replay `receiver_replay/54143ddc298c5037`
  loses fourteen transitions (seven rising/seven falling), while its sharp
  control loses none. Comparison `receiver_decision_comparison/81ca7d79b9b19806`
  shows all seven missing falling windows do cross RESTORE0 at 0.9 V.
  Three also reach RESTORE1 above 0.9 V, but Q never falls below 1.4917 V
  in any of the seven lost windows. The 41.823952 ns falling response lost
  by the four-unit version is recovered. The remaining losses have moved
  deeper into the restoring chain; stronger negative feedback has not yet
  produced complete native transport. Both original feedback variants remain
  held by the unchanged native/component admission gates.
- Read-only input audit
  `receiver_replay/f03923bf25510f9a/input_contract_observations/28d9763c435501a6`
  verifies the exact original link-to-pin PWL translation. All pins remain
  within 0–2.4 V, but three falling pulses never reach 100 mV differential.
  The other five lost falling responses have only 86.393–214.709 ps of
  uninterrupted support beyond 100 mV. These are descriptive pulse
  observations, not a newly invented dynamic acceptance limit or an excuse
  for all losses. The legacy source uses 60 ns/24.6 cycles of training, so
  it does not establish the required 256-cycle startup behavior. Original
  native admissions remain false; no gate or waveform is replaced.
- Separate corrected-driver interoperability diagnostics were prepared and run:
  `receiver_feedback_link_diagnostic/ffaef202466488a5` (four-unit feedback) and
  `b7f2e3dfc5f4ef78` (two-unit). They retain the fully remeasured false legacy
  verdict and use the audited current 110:1 driver, physical receiver, channel,
  shared bias/digital RX, original 188.049 ns/32-bit payload, 60 ns training
  and ideal 410 MHz phase. Maximum step is tightened to 1 ps. Each simulator
  leases one of the same six actual slots at priority two. These separate
  diagnostics cannot supply native, component, startup, DLL, aperture, full
  PVT/payload or release admission; all original qualification gates remain.
- Both original corrected-driver interoperability diagnostics terminate
  numerically at 4.5465 ns with a 1.25e-24 s attempted timestep, reporting
  `xtx.vgnd.t436`. Neither reaches its required 188.049 ns duration or
  supplies an electrical verdict. Their immutable terminal observations are
  `ffaef202466488a5/terminal_observation/b5a892d5d35eb61a` and
  `b7f2e3dfc5f4ef78/terminal_observation/b6ca51e41ffa257a`, within the
  interoperability namespace. Original raw/deck/library/log files remain.
  One fresh four-unit numerical experiment,
  `receiver_feedback_link_diagnostic/9bb548490222cab1`, increases only the
  transient Newton iteration limit to 100. Circuit bytes, fixed supplies,
  initial conditions, stimuli, 188.049 ns duration, 1 ps maximum step and
  accuracy tolerances are unchanged. Preparation requires the exact terminal
  failed owner and recorded timestep collapse; it cannot derive another
  numerical attempt from an already modified budget. Host preparation keeps
  container include paths. The original failed contexts are never overwritten
  or automatically restarted. This experiment has no result yet.
- A separate bounded frontend-settling experiment is now live in
  `receiver_tia_fast_matrix/85f2c240b81596f8` under
  `openlvds-receiver-tia-fast-dc-matrix.service`. New factory
  `receiver_tia_fast_frontend.py` duplicates all fourteen PP/PN load and
  two-unit boost resistor segments in parallel. This preserves unloaded bias
  ratios and halves resistive Thevenin impedance; original MOS, helpers,
  feedback values, ports and external bias remain unchanged. Real resistor
  capacitance remains and doubles with the duplicated cells, so any speed
  benefit must be measured. Lower DC gain is the tradeoff. Both feedback
  values are tested against the exact N8 control with original full 144 ns,
  twelve-point fixed-supply fixtures, uniform 1 ps maximum step, current
  measurements and fourteen-device stress screen. Six original PVT pilots
  gate bulk DC; all fifteen cases must pass independently before any new
  clock/native admission. Both modified candidates now pass all six complete
  SS/40, FS/40, SF/0, FF/40, TT/25 and SF/25 pilots and advance to the
  remaining nine original DC corners. The full matrix remains incomplete. The original TIA native
  simulations continue to completion; no partial result is promoted.
- Faster-frontend source-clock adapter
  `receiver_tia_fast_frontend_clock.py` and resource continuation
  `receiver_tia_fast_clock_followup/e04d75ba25739f64` are implemented and live.
  The continuation waits for the exact DC producer and admits each variant
  only after its own complete fifteen-corner pass and a passing N8 control.
  Original three full 80 ns/47-period fixtures and uniform 1 ps maximum step
  are retained. Only the attested byte-identical unchanged reference can be
  adopted; modified captures and sharp controls require new simulations.
  Failed/partial DC evidence cannot dispatch clocks. Existing six SPICE slots,
  separate variant workers and original scientific gates remain in force;
  no outer lease, geometry, native or PHY admission is supplied by this handoff.
- Gated faster-frontend physical and native adapters are implemented.
  `receiver_tia_fast_geometry.py` puts each duplicated load/boost resistor
  directly above its matching original in a second local row. Placement tests
  preserve all 91/93 flattened devices and nine ports without extending the
  original signal-row width. CT/CO/CL/RESTORE0 retain four below-row buses;
  real added resistor capacitance and upper routing remain in extraction.
  Native replay additionally probes all six frontend load/boost intermediate
  nodes and every feedback intermediate node. Each candidate must first pass
  its fifteen-corner DC and all three full source-clock controls. Live physical
  continuation `receiver_physical_followup/ec096a781a4cd3a7` waits for the exact
  source-clock owner, then independently builds DRC/LVS/extraction/RC audit
  and original two full 80 ns native controls. Its placement tests do not
  constitute actual new GDS, physical validation or positive native admission.
- Original differential-amplifier downstream handoffs have completed and held both candidates:
  `receiver_differential_downstream/d8b7381526a27796` (components),
  `1e1493bac7dd6581` (corrected-driver diagnostic) and `3496874a53a16f66` (RC).
  Only candidates with their own full native transport admission can dispatch
  component or coupled simulations. All sixty component passes are additionally
  required before RC. Neither original amplifier advances: the smaller failed
  source DC and the larger failed native transport. The controllers dispatched
  no component, coupled or RC simulation for either rejected candidate.
- Feedback-inverter downstream handoffs are now live and waiting:
  `receiver_tia_downstream/469fe88f6e83a36f` (sixty component cases),
  `82ff9c871fa9d9ef` (corrected-driver diagnostic) and `81515c914e0baf1c` (RC).
  Each candidate advances independently after its own complete native result;
  RC additionally requires all sixty component passes. No downstream scientific
  test is admitted yet, and waiting controllers hold no SPICE slot.
- Current OpenPLL contract audit `openpll_current_contract/440f3c5adb6e8f26`
  passes for both captured traces at the exact required OpenPLL revision.
  RTL/controller frequency is 400.942482 MHz; archived extracted fixed-code
  DCO frequency is 399.546838 MHz. The read-only checker uses the current
  390–410 MHz and 45–55 percent duty contract, verifies source/PDK/trace hashes
  and replays the original raw-to-CSV conversion. The frozen legacy producer
  still uses its historical 380–420 MHz range. `require_openpll_contract.py`
  provides a failing command gate for a false or incomplete current audit.
  This is clock evidence only; final PHY qualification remains required.
- Matched-unit downstream resource handoffs are now live and waiting:
  `receiver_matched_downstream/39758258f2f754b9` (components),
  `d9de4e75f3501c61` (corrected-driver diagnostic) and `39650feb10a68c33` (RC).
  Two independent variant workers bind exact live prerequisite owners and
  their report hashes. Native failure cannot dispatch components or coupling;
  all sixty component passes are required before RC. These controllers hold
  no outer SPICE lease and cannot promote a selected PHY.
- **The 16 pF DLL passes all three source-acquisition cases.** The full SS/0
  original 1500 ns trace gives 10.039 ps maximum feedback error,
  10.690 ps quarter-phase error and 0.745 mV control ripple, versus
  2.576 mV ripple for the matched 4 pF source control. Full TT/25 gives
  7.758 ps feedback error, 10.296 ps quarter-phase error and 0.861 mV
  ripple versus 3.014 mV for its matched 4 pF control. Full FF/0 passes with
  6.375 ps feedback error, 10.268 ps quarter-phase error and 0.907 mV
  ripple versus 3.163 mV for its matched 4 pF control. Independent full-wave
  remeasurement agrees. New DRC/LVS/extraction/RC audit pass, and native
  screen `dll_qualification/1a29b2389cee3d01` is running. Fresh measured
  stability and the full qualification remain gated.
- The corrected DLL native screen now has 23/24 passes and no failures.
  The complete SS/0 closed-loop fixture is 1700 ns, with its original
  1200–1500 ns metric window and 1600 ns marker. Independent observation
  `dll_qualification/1a29b2389cee3d01/completed_native_ss0_observation` agrees
  exactly with the original evaluator: feedback error 20.534656 ps,
  quarter-phase error 44.848933 ps, observed CTRL ripple 1.143592 mV and
  maximum storage-plate ripple 1.970868 mV. TT/25 now completes and passes
  its full 1700 ns fixture: feedback error 10.227319 ps, quarter error
  36.002342 ps, CTRL ripple 0.288201 mV and maximum storage-plate ripple
  0.967246 mV. FF/0 is running. Fresh measured stability and the complete
  qualification remain required.
- Full corrected-DLL continuation
  `dll_storage_full_followup/cf1fbfc6d3d44fec` is live and waiting for the exact
  measured-stability screen owner. Only passing three-corner measured margins
  and step validation can dispatch the original full 336-case qualification.
  All 336 cases and captured full/fast comparisons must pass before measuring
  all fifteen stability corners. The controller holds no outer lease;
  original scientific fixtures, 60-degree/6-dB margin gates, 390/410 MHz step
  validation and the six actual slots are retained. Recovery, readiness, OTA,
  RC and complete PHY gates remain required afterward.
- Corrected-DLL recovery/readiness/OTA continuation
  `dll_storage_signoff_followup/e5c1ab37cc91e2b2` is live behind the exact full
  native/all-PVT stability owner. It runs the original limiting-corner
  frequency-step/clock-loss recovery, RTL readiness replay including fresh
  4700 ns late-loss fixtures, then guarded OTA gm/offset/terminal-stress
  characterization. Variant profiling preserves the captured native identity;
  each actual SPICE call uses the same fair priority-one six-slot dispatcher.
  Existing output scopes and partial numerical evidence are retained, with
  no automatic overwrite/retry. Seven adapter tests exercise evidence
  binding, producer failures, partial retention, resource restoration and
  terminated owners. These gates have not run yet; RC and full PHY
  qualification remain independent requirements.
- **The corrected 110:1 driver passes all thirty component cases.** All
  fifteen source and fifteen native original full 2540 ns fixtures pass
  across five process corners and 0/25/40 °C. Native settled 100-ohm DC
  differential magnitude spans 286.789–333.012 mV, with common mode
  1.219–1.266 V; its separate loaded-eye minimum is 264.227 mV at SF/40.
  Exact-resistor SF/40 and FF/0 comparisons also pass. No active model or
  catalog is replaced, and coupled-link/PHY qualification remains open.
- **The fresh current-driver RC comparison passes.** Context
  `driver_rc_comparison/a0cec6d01291f958` completes both original full 2560 ns
  traces. Maximum differential crossing error is 0.409331 ps; differential
  plateau and common-mode errors are 0.426267 mV and 0.476026 mV, within the
  original 20 ps/20 mV limits. Independent read-only remeasurement agrees.
  Independent current-model RX, TX and delay-line RC remeasurement also passes.
  Current corrected DLL and analog-receiver comparisons plus the joint
  six-case certificate remain required.
- Both earlier matched driver/source-receiver links were verified numerically
  stalled, archived and retired with original hashes and all slot inodes
  preserved. Their partial results remain inconclusive. The original
  frontend-local native receiver loses 22 edges even with corrected-driver
  recorded pins; this motivates the new bias correction, not a relaxed gate.
- `make test-full` now checks NumPy/SciPy versions against the pinned
  `scripts/exact_rc_requirements.txt` and runs the full suite in the local
  analysis environment with ngspice. The base-image `make test` remains
  available; it can skip the sparse-math witness when SciPy is absent.
- The last full regression passes **all 1026 tests**, with no skips. Electrical
  closure still requires new receiver clock/native/component/link results,
  full driver and DLL evidence, aperture, long-payload/real-clock link cases,
  exact RC certificates and final artifact/release validation.

The entries below preserve the laboratory history. Earlier running states and
candidate pilots describe their observation time; the summary above reflects
the current branch. Detailed immutable receipts appear in the dated entries.

2026-11-02 — audited W32 native model and routing-only comparison:

- Baseline W32 layout `receiver_layout/b526c4c6eac8f676` passes zero-error
  DRC, LVS, extraction and independent RC audit. It has eighty devices,
  nine ports and 712.92 × 147.8 µm bounds. Source hash remains
  `e54332a8bee8845bf767a9b9d4e76bb97686cb67a5639677ce16ed9d1aefd78a`;
  native model hash is
  `dcb696efa0f1750a6c53f219e3db7b06c615ba304c5815bc635afa1c0c79639b`.
  Native replay `receiver_replay/3ee72810a0ed800a` runs both original full
  80 ns captured/sharp controls at 1 ps maximum step. No native transport
  verdict exists yet; component and coupled-link continuations remain gated.
- Read-only topology receipt
  `b526c4c6eac8f676/wire_capacitance_observation/38be874b2fffe5d9/summary.json`
  verifies exact audited models and physical input-finger counts. Explicit
  wire-capacitor boundary sums rise from P8/N8 to W32: CO 34.622→63.434 fF,
  CL 31.088→64.677 fF, CT 34.411→88.365 fF, PP 134.254→153.966 fF and
  PN 134.363→156.406 fF. These are wire-component incidence sums, not
  effective input capacitance, device capacitance, poles or timing proofs.
- `receiver_below_row_geometry.py` and its isolated layout/native adapters
  retain all eighty device instances, source bytes, PCell placements,
  public pins and bounds while moving CT/CO/CL/PP/PN buses into the existing
  gap below the critical row. Physical context
  `receiver_local_routing_followup/4645512382ec60e9` completes successfully;
  layout `receiver_layout/7a5ef5af6fa761c4` passes DRC/LVS, extraction and
  independent RC audit, and actual schematic/placement/public-bound equality
  checks. Native model hash is
  `c5f6578e0b8698abdfca85e764fd5a2b9e1aa5add13dc90596436b355e9948ef`.
- Its three-model wire observation is
  `7a5ef5af6fa761c4/wire_capacitance_observation/6be2146e78c630d0/summary.json`.
  Five lower buses yield CO 56.755 fF, CL 63.237 fF and CT 69.929 fF,
  but raise PP to 172.700 fF and PN to 164.450 fF. This mixed result does
  not justify assuming faster native transport. No additional SPICE or
  electrical admission is issued for this physical-only experiment.
- The refinement `receiver_three_bus_geometry.py` keeps PP/PN in their
  original upper channels and moves only CT/CO/CL below the row, at 1.6 µm
  pitch rather than 0.8 µm. Source, devices, placements, public pins and
  bounds remain constrained identically. Its isolated physical build/audit
  is running under `receiver_local_routing_followup/beadd25f824623cf`.
  Routing candidates require their own native and downstream admissions;
  the original two W32 native simulations continue with untouched models.
- All **801 regression tests pass without skips**. New routing tests verify
  identical ordered device schematics, placements and public geometry, only
  the intended internal labels moving, all existing critical classifications
  retained, and distinct native profiles with complete restoration on errors.

2026-11-02 — complete W32 source-clock admission and physical handoff:

- `receiver_clamp/873e9ffbc7e55e38` completes all three original full 80 ns
  source controls: 47 checks each, zero missing edges, zero repeats. Both
  modified W32 captured/sharp cases are fresh simulations; the exact P8/N8
  reference retains its explicit adoption receipt and original-producer
  remeasurement. The source-clock owner completes successfully.
- Positive source admission binds manifest
  `c500ea63e4d6ae4f92a14628cf389092e88e774a9d12350e3f6ed40e8b2ca4dc`
  and report `32fc505564edca730735d251288325290a24040264c8c1068be706169e9a1339`.
  Resource `receiver_physical_followup/e0fd4ab9ad39d586` validates that exact
  W32 receipt and starts the geometry flow. DRC/LVS, extraction, independent
  RC audit and both full native transport controls remain required before
  components or corrected-driver coupling can be admitted.
- Independent completed-capture receipt
  `873e9ffbc7e55e38/completed_captured_comparison/42747bdbd3192eb6/summary.json`
  remeasures both full source captures with the unchanged 15–75 ns transport
  algorithm and checks identical stimulus/numerical policy and bias/digital-RX
  circuit closures. All 47 paired edges are preserved. Relative to P8/N8,
  W32 adds 53.134–69.293 ps latency on 24 rising edges and 42.157–50.112 ps
  on 23 falling edges. Its absolute source latency ranges are
  427.426–443.805 ps rising and 338.625–390.493 ps falling. This is a source
  timing tradeoff, not native sampling margin or PHY qualification; final
  coupled data/clock behavior must still meet the original 200 ps margin.

2026-11-02 — receiver RC comparison adapter and strict component handoff:

- `validate_receiver_gain_balance_rc.py` adds the final receiver component
  RC comparison path. It requires every one of the sixty original
  source/native DC/rate reports, a passing complete component summary, and
  the exact current gain/balance selector. Its unchanged cached selector
  rechecks native transport and component evidence before model preparation;
  missing prerequisites cannot dispatch from this path.
- Physical replay and component layout identities must agree. The native
  model must match the declared source factory, GDS and independent RC audit.
  Quick-node reduction retains every non-wire device, port and directive,
  with the same exact shared bias in both views. The comparison uses the
  original full 60 ns TT/25 fixture, 100 ps maximum / 20 ps output steps and
  original 20 ps edge / 20 mV plateau limits. Partial or unattested traces
  are retained. Each actual simulation owns one fair priority-one lease.
- Resource
  `receiver_physical_followup/e0fd4ab9ad39d586/receiver_rc_followup` is live
  and waits for its exact receiver component owner. Rejected dependencies
  are retained without dispatch. No receiver RC comparison is admitted yet;
  current W32 sharp-clock testing is still running, and physical/native and
  all sixty component conditions remain required first.
- The focused admission/model-binding/cache-policy tests and full regression
  pass: **791 tests, no skips**. Driver and the independently verified RX/TX/
  delay RC cases retain their existing evidence. Corrected DLL and analog
  receiver comparisons and a consistent joint six-case certificate remain
  open. Aperture, final coupled timing/payloads and PHY admission remain open.

2026-11-02 — W32 full captured source clock passes:

- The actual modified `clamped_captured` task in
  `receiver_clamp/873e9ffbc7e55e38` completes its fresh full 80 ns simulation
  and passes all 47 original 15–75 ns transport checks with zero missing or
  repeated edges. This task has `clamped=true`; it is the W32 candidate,
  distinct from the adopted P8/N8 reference. Its saved full-wave hash,
  input-file hashes and exact new manifest binding are verified.
- The original producer advances to a fresh sharp-clock control under the
  same six actual shared SPICE slots. No joint `source_clock_admission.json`
  exists yet. Physical geometry, native replay, components and coupled-link
  diagnostics remain gated on all three original source controls. Earlier
  receiver alternatives passed source clocks and failed native transport;
  this source result therefore does not establish native or PHY admission.

2026-11-02 — current behavioral evidence independently checked:

- Read-only receipt `current_behavioral_observation/a6b4087918c430c5/summary.json`
  validates the current canonical `build/rtl/summary.json` source fingerprint,
  full exact 390/400/410 MHz × 45/50/55 percent duty × -100/0/+100 ps skew
  coverage, all fifty-four completed case PASS logs and controller/functional
  assembly PASS logs. RTL and native-TX functional modes each check 1,186,794
  bits, exceeding the original million-bit requirement. Its native mode
  retains generic RX, as declared by the original producer.
- The same observation validates all source/requirements hashes, fifty-four
  case logs and per-mode totals for current early-RX behavioral context
  `rx_buffered_rtl/3fc750281ff3b4bb`. Generic and native-RX modes each check
  1,186,794 bits. Its early RX source/reset bytes match the independently
  checked `rx_early_physical_v1` input archive and retained physical policy.
  This separate regression uses generic TX.
- These current baseline/component results do not establish the final
  combined C16 DLL/native-TX/native-RX behavioral assembly or any electrical
  timing, aperture, PVT, extracted long-payload or PHY admission. The final
  selected assembly still requires its own captured validation. No simulator,
  existing producer report or active artifact pointer is changed by this audit.

2026-11-02 — corrected DLL RC comparison adapter and native-screen handoff:

- `validate_dll_storage_rc.py` adds the remaining corrected-DLL full/fast
  RC comparison path. It requires exactly all twenty-four completed passing
  native screen cases before invoking any cached prerequisite producer. The
  original source/native admission checks remeasure the existing evidence;
  no missing prerequisite can be dispatched by this comparison adapter.
- The comparison uses the qualification's exact captured C16 DLL/PFD views,
  preserving the exact shared bias and every non-wire device, port and
  directive. It retains the original full 1500 ns TT/25 fixture, 100 ps
  maximum / 20 ps output steps, and original 20 ps edge / 20 mV plateau
  comparison limits. Existing partial or unattested traces are retained.
  Only one actual fair priority-one SPICE lease is held at a time.
- Resource `dll_qualification/1a29b2389cee3d01/rc_followup` is live and waits
  for its exact native-screen owner to complete all twenty-four cases. Six
  native screen cases pass at this observation. No DLL RC simulation has
  been admitted yet. Fresh stability and full 336-case native qualification
  remain separate prerequisites for final DLL/PHY admission.
- The focused gate/model-protection tests and full regression pass:
  **785 tests, no skips**. Independent live-model checking also confirms
  that both captured libraries have identical non-wire statements and bias
  and satisfy the original fixture's named-node probes.

2026-11-02 — complete W32 source DC admission and clock preparation:

- Matrix `receiver_gain_balance_matrix/f6d247d3b64483af` completes all
  fifteen original full 144 ns/twelve-point source cases. Control and W32
  each pass fifteen; P4/N8 passes fourteen and remains rejected. The exact
  W32 admission binds matrix manifest
  `d7f7b612b91f788886e0c2793c7a4c06054b40bd9d2d21e62f291e25af0eedd8`,
  report `802d34cfe289c9751e4ab8ae910ab4c7beb1cdde9ffe7a4fb55fc622a51e2036`
  and candidate `e54332a8bee8845bf767a9b9d4e76bb97686cb67a5639677ce16ed9d1aefd78a`.
- The continuation selects W32 only and prepares source-clock context
  `receiver_clamp/873e9ffbc7e55e38`. It verifies and adopts only the exact
  completed P8/N8 captured reference from `7cf3e0668ce610ec/clamped_captured`.
  Its new reference summary has 47 periods and zero misses; this is reference
  evidence, not a W32 clock pass. Candidate captured/sharp tasks require
  fresh full 80 ns simulations with original 1 ps maximum / 5 ps output steps.
- The source-clock producer completes its full cached DC remeasurement and
  starts the fresh W32 captured-clock simulation after acquiring an actual
  shared simulation slot. Those cached invocations can
  temporarily rewrite matrix state counts while preserving identical final
  scientific reports and admissions; they do not restart DC simulations.
  Geometry, extraction, native transport, components and coupled-link work
  remain held until their respective original gates pass.

2026-11-02 — P4/N8 rejected by FF/40 low-common-mode sensitivity:

- Full 144 ns child `receiver_gain_balance/eabe63b7dc2615a5` completes all
  three variants. Independent cached invocation of its unchanged producer
  reproduces the failure. At 22 ns, P=0.1 V and N=0 V require Q high.
  Control and W32 pass; P4/N8 produces Q=0.010607 V and fails the original
  DC threshold. Its observed twelve-device stress screen still passes.
- Control and P4/N8 both have CO=0.656583 V, CL=0.941750 V and tail current
  304.204 µA at that point. Changing only the first PMOS to W4 lowers
  RESTORE0 from 1.256321 V to 0.810161 V, raises RESTORE1 from 0.007490 V
  to 1.225346 V and changes the final output from 1.8 V to 0.010607 V.
  The intended lower restorer threshold therefore sacrifices the opposite
  polarity's DC sensitivity. This is a circuit failure, not a timeout or
  a failed stress/current-meter guard.
- The matched W32 pair instead gives CO=0.610138 V, RESTORE0=1.519668 V,
  RESTORE1=0.000187 V and Q=1.8 V, with tail current 320.759 µA.
  It retains the original P8/N8 restorer. Its other completed corners also
  pass, but the complete fifteen-case gate and fresh dynamic/native evidence
  remain required. P4/N8 cannot receive source-clock admission or trigger
  geometry, native replay, components or coupled-link simulations.

2026-11-02 — matched pilot current observations and current digital RC evidence:

- `receiver_gain_balance_matrix/f6d247d3b64483af/completed_pilot_observation/summary.json`
  remeasures only the six complete matched pilots with the unchanged source
  producer, requiring every child/variant report before any cached call.
  Across their 72 settled samples per variant, P4/N8 changes CO by at most
  0.065 mV and tail current by at most 0.0011 µA relative to P8/N8. Its
  purpose remains restoration balance, not changing decision gain.
- Pair-only W32 raises measured tail current by 3.019–59.690 µA at matched
  sample points. Its absolute tail-current range is 294.290–379.793 µA,
  versus 238.987–373.356 µA for control. The six-pilot cross-corner settled
  CO polarity gap changes from 160.005 mV to 176.366 mV. Neither this gap
  nor source DC correctness establishes dynamic restoration or inverter trip.
  Full-fixture rail-current observations are not isolated receiver power.
- Read-only receipt `current_digital_rc_observation/1711728db4fe8d29/summary.json`
  validates existing attested full/fast early RX, direct-buffer TX and
  delay-line traces against their exact current physical model hashes,
  independent RC audits, producer/runtime, original complete 60 ns TT/25
  fixtures and unchanged 20 ps edge/20 mV plateau comparisons. No simulator,
  model, certificate or active pointer is changed.
- RX native model `6def14fbd570903751f922c3a86132bbd801957c3dfd3d09c7c81729361515c3`
  preserves both sets of sixteen data crossings and high valid; its worst
  edge and plateau errors are 2.662596 ps and 0.854346 mV.
- TX native model `cdf6cbd8a901e40f450f3e5a1824c05cb48b3a5de9663aa84d5b9ebd65829713`
  preserves sixteen data and thirty-two forwarded-clock crossings; worst
  errors are 2.991435 ps and 4.159472 mV.
- Delay native model `114cb6db9709e846ad645c904dcd9a668f37c20b747fa6dc5dcd93ea37f99696`
  preserves thirty-two crossings on every output; worst errors are
  0.747545 ps and 0.078714 mV. All three component comparisons pass.
  Alongside the independently verified current-driver case, four current
  component RC cases now have evidence. Corrected DLL and analog-receiver
  RC comparisons and a consistent joint six-case certificate remain required.
  Digital functional/aperture/PVT and full PHY admission remain separate.

2026-11-02 — complete 16 pF source acquisition and native-screen handoff:

- `dll_architecture/368259f7b02c5fdc` now completes and passes all three
  original 1500 ns source-acquisition cases, including FF/0. The source owner
  exits successfully. Read-only matched FF/0 receipt
  `completed_source_ff0_observation/summary.json` independently remeasures
  both full C4 and C16 traces with unchanged original metrics and input hashes.
- C16 FF/0 feedback error is 6.375279 ps, quarter-phase error 10.267562 ps,
  CTRL mean 0.731615 V and ripple 0.907130 mV. Matched C4 values are
  6.492792 ps, 8.012954 ps, 0.731602 V and 3.162580 mV. These source results
  do not establish native phase margin.
- The exact-owner continuation prepares fresh native qualification
  `dll_qualification/1a29b2389cee3d01` with explicit
  `storage_source_admission.json`. Its original 24-case screen runs with
  three fair actual SPICE leases at most; all other fixtures remain held for
  stability. The separate stability continuation waits for the complete screen.
  Native margins, transient steps/recovery/readiness, OTA operating points,
  the full 336-case matrix and final RC/PHY qualification remain unproven.

2026-11-02 — native failure diagnosis and next receiver experiments:

- Full native N4 context `receiver_replay/973c68eea433361d` fails with eighteen
  captured misses; N8 `receiver_replay/3bb1e40442433109` fails with sixteen.
  Both complete sharp controls with zero misses. Component and coupled-link
  followups finish without dispatching tests for these rejected candidates.
- Read-only full-trace restoration observations are
  `973c68eea433361d/restoration_observations/35ec7a0fa895bbc2` and
  `3bb1e40442433109/restoration_observations/439793b8dde5e963`.
  All eight N8 missing falling-edge windows lack a first-restorer 0.9 V
  falling crossing; their CO maxima span 0.667805–0.823033 V and first-restorer
  minima 0.983952–1.704971 V. Eight of nine N4 missing falling-edge windows
  lack that crossing; a crossing alone therefore does not establish transport.
  The remaining N4 miss at 56.447186 ns has a first-restorer crossing only
  after 916.783 ps, despite a 590.328 ps input pulse. Its next-restorer peak
  is just 0.354280 V and output remains above 1.789801 V.
- `receiver_gain_balance.py` and `matrix_receiver_gain_balance.py` implement
  two independent changes against the exact source-qualified P8/N8 control:
  only first-restorer PMOS W8→W4, or only both LVT decision inputs W8→W32.
  The tail remains W16 and mirror W8. This pair-only gain intervention differs
  from the previously rejected uniformly scaled decision stage. Control and
  P4/N8 flatten to 74 devices; the W32 pair produces 80 through extra fingers.
  All added pull-up segments and pair fingers remain in the local signal row.
- The new matrix uses the original full 144 ns/twelve-point DC fixtures,
  fixed supplies, original sensitivities and current/stress limits with an
  explicitly uniform 1 ps maximum step. SS/40, FS/40, SF/0, FS/0, TT/25 and
  SF/25 pilots all pass for both interventions and their control. The other
  nine cases are running; each candidate needs all fifteen independently.
- `receiver_gain_balance_clock.py` requires complete passing DC evidence for
  candidate and control. It adopts only the completed byte-identical P8/N8
  captured reference from `receiver_clamp/7cf3e0668ce610ec`, validating source,
  library, aliases, full waveform/report and deck equality beyond the include
  path. Its unchanged scientific runner remeasures the adopted reference.
  Modified captured and sharp tasks always require fresh full 80 ns traces.
- `layout_receiver_gain_balance.py` and `probe_receiver_gain_balance.py`
  require the exact full source-clock admission before GDS, DRC/LVS,
  extraction/RC audit and the original two full native 1 ps controls. There
  is no component, coupled-link or selected-PHY admission from these adapters.
- Clock followup `f6d247d3b64483af/clock_followup` and physical handoff
  `receiver_physical_followup/e0fd4ab9ad39d586` are live and waiting for
  their exact upstream owners. Each admitted variant advances independently;
  only actual simulations lease from the same six global slots. New selectors
  `qualify_receiver_gain_balance.py` and
  `probe_corrected_driver_gain_balance.py` require both completed, passing
  native controls before preparing the original sixty component cases or the
  corrected 110:1 driver coupled-link diagnostic. Their resource followers
  are waiting under the physical context. No new component or link simulation
  has been admitted at this observation.
- Fresh driver RC evidence is `driver_rc_comparison/a0cec6d01291f958`;
  independent receipt is `comparison_observation/3b1fc04541221fef/summary.json`
  beneath that context. Both native and quick-node models retain the same
  shared bias. All 32 differential crossings are preserved, with errors
  0.409331 ps / 0.426267 mV differential and 0.476026 mV common mode. The
  quick-node reduction changes 54,491→10,629 resistors and 4,165→953
  capacitors while preserving every non-wire-R/C statement. This proves the
  driver case only, with `complete_suite=false` and `qualified_phy=false`.

Two-unit native transport failure and controlled restoration experiment:

- Both first-restorer source-clock contexts now complete all three original
  controls and receive explicit positive admissions: N4 `receiver_clamp/9b41a25364c5819f`
  and N8 `receiver_clamp/7cf3e0668ce610ec`. Every reference, modified captured
  and modified sharp trace completes the full 80 ns and passes all 47
  original edge-matching checks. Source admission report hashes are
  `dbd073d8b83d226d575d01fe07dc319ad5928e6a729e55e310715540a5495428`
  and `8f5b071a58175e64ab9c9541754561338dc2b5334abefc85655955ac03c8a682`.
- N4 physical candidate `receiver_layout/67db40203d3777f4` and N8 candidate
  `receiver_layout/98ba32c640c5e6b3` both pass DRC (zero errors), LVS,
  extraction and independent RC audit. Each has 74 devices, nine ports and
  a 670.26 by 147.8 um footprint. The exact source bytes match their own
  fifteen-case admissions; physical and audit reports bind source, GDS and
  native network hashes. Native models are respectively
  `9a7558516f07a7b1862a6098362a6780dcaea9b26e9c15497943d29df744c6d4`
  and `f232af3f9aa350f8ab77fdaaeecb4be0682a9bc6acb1b07bd2d96871451177e1`.
- Native N4 replay `receiver_replay/973c68eea433361d` and N8 replay
  `receiver_replay/3bb1e40442433109` are running both original full captured
  and sharp controls. All four simulators hold their own fair leases within
  the unchanged six-slot budget. Independent variant handoffs permit both
  candidates to progress concurrently; no native, component, coupled-link or
  PHY admission follows from the passing source/physical stages alone.
- Driver RC full reference
  `rc_validation/ngspice/driver/full_ffbc0373b1_2f56048094_cccfc614c6` completes
  its original 2560 ns fixture and records current trace attestation for the
  exact 110:1 driver and shared bias. All attested file hashes independently
  verify. The corresponding fast reference
  `fast_29d082652d_2f56048094_cccfc614c6` is running. No waveform agreement,
  approximate-model qualification or complete six-case certificate is inferred
  before it finishes and the unchanged original comparison passes.

- Commit `601f26d` adds a fresh isolated driver-only RC comparison after
  remeasuring the complete passing thirty-case component campaign. Context
  `driver_rc_comparison/a0cec6d01291f958` retains the audited 110:1 driver,
  exact shared bias and original full 2560 ns TT/25 comparison fixture.
  The 0.1 ps quick-node approximation reduces wire resistors from 54,491
  to 10,629 and capacitors from 4,165 to 953; all non-wire-passive statements,
  device terminals and public ports are retained. It remains unqualified.
  Full reference `rc_validation/ngspice/driver/full_ffbc0373b1_2f56048094_cccfc614c6`
  is running under one actual fair lease; fast comparison follows sequentially
  with the original 20 ps edge/20 mV voltage limits and trace attestation.
  Partial/unattested traces cannot be overwritten. No active library, model
  catalog or six-case certificate is written. All 746 regression tests pass.
- The new LVT-restorer source-clock contexts are `receiver_clamp/9b41a25364c5819f`
  (N4) and `receiver_clamp/7cf3e0668ce610ec` (N8). Their unchanged references
  and actual modified captured cases each complete 47 periods without
  missing/repeated edges; the sharp cases remain required. Historical task labels must be
  interpreted through manifest `clamped`: `unclamped_captured` is the
  unmodified reference, while `clamped_captured` is the modified candidate
  despite its historical name. The LVT circuits themselves are unclamped.
  A reference pass is not candidate admission; the scientific gate requires
  all three original controls and the exact declared source factory.
- Read-only receipt
  `0f010f4a46bd1d37/completed_captured_observations/386507c894fe06f4/` independently
  verifies both completed references and both actual modified captured traces.
  It checks all upstream inputs and producer hashes, the declared source factory
  and exact fifteen-case candidate hashes, full finite monotonic 80 ns waveforms,
  and exact original 15–75 ns transport and internal-node range remeasurement.
  All four reproduce their cached producer results with 47 checks and zero
  missing/repeated edges. Each record names its actual reference/candidate role.
  Missing sharp controls are never dispatched by this observer; complete source-
  clock admission and every physical/native/component/link/PHY gate remain open.

- Three-unit replay `receiver_replay/ef823b6778f2d9a5` now completes both full
  original 80 ns native fixtures. Captured transport misses nine rising and
  nine falling edges; sharp control misses none. Independent full-trace
  restoration receipt `restoration_observations/9344a19497ca9ff3/` exactly
  reproduces transport and identifies no first-restorer falling crossing in
  any of its nine missing falling-pulse windows. Six exceed 100 mV input peak;
  three do not. Across all nine windows CO peaks span 0.641–0.933 V and
  RESTORE0 minima span 1.349–1.790 V. Both bias-only native candidates are
  rejected; their component and coupled followers correctly skip both without
  dispatching any dependent electrical test.
- Commit `db2060a` introduces independent physical handoffs for the two LVT
  restorers. `continue_receiver_restore_parallel.py` keeps every scientific
  source/physical/native producer and gate unchanged, dispatches at most two
  variants in isolated subprocesses, records separate progress/results and
  owns no outer SPICE lease. One variant's completed failure cannot borrow
  another's native admission. Geometry, extraction and native replay for N8
  can advance while N4's replay runs, once N8 independently passes source clocks.
  All 742 regression tests pass, including concurrent-worker and partial-
  evidence refusal checks.
- Only the three waiting resource owners under
  `receiver_physical_followup/2a4d9c17db429082` were frozen, archived and
  retired before rebinding. Receipt
  `resident_jobs/restorer_parallel_handoff/after_stop.json` verifies nine
  archived files, all original hashes and all six shared-slot inodes; each
  old owner had no scientific subprocess. Source-clock and live SPICE jobs
  remain untouched. Fresh physical context `5896ecbb92009d53` binds the
  same live source-clock owner, and its new component/coupled followers bind
  the new exact physical owner. No active model, gate or PHY pointer changes.

- Fresh source matrix `receiver_restore_threshold_matrix/0f010f4a46bd1d37`
  completes all fifteen PVT cases for control and both first-restorer LVT
  widths, with every original DC/current/twelve-observed-device stress gate
  passing. Separate LVT-N4 and LVT-N8 admissions each report 15/15 passing
  cases and bind their own exact source bytes. All selected traces are
  independently remeasured; SF/40 uses the completed matched 1 ps retry and
  the other fourteen fixtures retain their original 50 ps maximum step.
  The source report hash is
  `1b68b65478adaac40618ec1bc59d22754e7d06c7ddd1510e25e7f0c30ce5d547`.
- Resource pipeline
  `de4b3249ef99482e/numerical_recovery_followup/pipeline/` binds that completed
  recovery admission, archives all fourteen original terminal-resource files,
  checks all six slot inodes and resets only the four exact failed dependency
  invocations. Fresh source-clock continuation uses the new matrix;
  physical continuation `receiver_physical_followup/2a4d9c17db429082` binds
  its new live clock owner. Separate component and corrected-driver coupled
  followers bind the new physical owner and wait for complete native admission.
  The original scientific helpers and admission limits are unchanged. The
  old partial matrix and failed resource contexts remain available; no passing
  report is transplanted into them, and no active model or PHY pointer moves.

- Matched numerical retry `receiver_restore_threshold/d2ad4a830399a9b2`
  completes the full original 144 ns SF/40 fixtures for control, LVT-N4 and
  LVT-N8, with all three DC/current/twelve-device stress screens passing.
  The original 50 ps N4 run remains near the first common-mode ramp at
  71.9 ns while the stricter 1 ps run completes; changing maximum step is
  sufficient to avoid this observed numerical slowdown in the matched retry.
  No transistor, supply, input, method, tolerance or scoring limit changes.
- The superseded original simulator PID 1332833 was individually frozen,
  archived and retired after the complete retry passed. Receipt
  `resident_jobs/restore_sf40_step50/after_stop.json` verifies all 71 archived
  original file hashes, the target's absence and all six shared-slot inodes.
  Other simulators and original source workers continue. The partial trace
  remains electrically inconclusive; original matrix reports are not fabricated.
- Commit `b2b4b42` adds `admit_receiver_restore_retry.py`: fresh coverage
  combines all fourteen completed original PVT cases with the complete matched
  SF/40 retry. It checks exact candidate/observed-source bytes and the sole
  maximum-step/include edits, requires all three reports in every selected
  case before calling any runner, and reuses the unchanged full fifteen-case
  per-variant DC/current/stress admission. Its manifest explicitly records
  SF/40 at 1 ps and the other fourteen cases at 50 ps. A resource-only
  `de4b3249ef99482e/numerical_recovery_followup/` waits for the original workers
  to drain, finishes untouched cases under actual fair leases, then prepares
  and remeasures this admission. Source-clock and physical/native continuations
  must bind its fresh context. All 736 regression tests pass without skips.

- Corrected-driver campaign `driver_components/a1d220a703a6ac2b` completes
  with required=30, passed_cases=30 and passed=true; the exact producer exits
  successfully. Independent completed-native observation
  `completed_native_observations/2a95092ff56f7f44/` selects all fifteen native
  tasks from the original manifest, reconstructs each original fixture against
  the audited 110:1 model, checks producer/runtime/input/trace hashes and
  remeasures every original DC/loaded-eye metric. All fifteen agree exactly
  with cached reports and pass. Earlier fifteen-source evidence remains
  separate; no observation directory is counted as a component task. This
  closes component coverage, not receiver coupling, fresh final RC certificates
  or complete PHY release.
- The 16 pF DLL completes the original full 1500 ns TT/25 source fixture
  with cadence and loop metrics passing. Independent matched read-only audit
  `dll_architecture/368259f7b02c5fdc/completed_source_tt25_observation/`
  remeasures both original 4 pF and new 16 pF traces and exactly reproduces
  their cached metrics. Ripple falls from 3.014114 to 0.860954 mV; feedback
  error changes from 7.852593 to 7.758238 ps, while quarter-phase error
  changes from 8.557648 to 10.295527 ps. Both full source fixtures pass their
  unchanged gates. FF/0 is still required; no native stability or full DLL
  admission is inferred from source acquisition.

- `receiver_replay/c130e79d2f47a246` completes both original full 80 ns,
  1 ps maximum-step fixtures. Captured transport misses nine rising and nine
  falling edges; sharp control misses none. Its explicit native admission is
  false, so the component and corrected-driver coupled-link continuations
  skip this candidate. The three-unit physical candidate
  `receiver_layout/6a56f7a2cf64a7b4` independently passes physical checks;
  its native captured/sharp replay is `receiver_replay/ef823b6778f2d9a5`.
- Immutable `c130e79d2f47a246/partial_transport_observation/` records the
  matched old/new 15–30 ns prefix comparison. Both lose the same three
  transitions despite the frontend common mode moving to 1.113–1.186 V
  and the observed CT bus to 0.170–0.378 V. CT is an extracted wire bus,
  not a MOS VDSAT measurement. Weak negative pulses drive CO to roughly
  0.77–0.79 V while RESTORE0 remains above 1.73 V, motivating a lower
  first-restorer trip point. Full completed transport, rather than the prefix,
  establishes the rejection above.
- `receiver_restore_threshold.py` and its matrix runner preserve the full
  original 144 ns/twelve-point stimuli, fixed supplies, current meters and
  twelve-device project stress screen. SS40/SF0/FS0/TT25/SF25/FS40 pilots
  include the previously limiting high-common-mode SF cases and a fast-NFET
  FS check. Bulk is held unless control and at least one intervention pass
  all six pilots. Each variant receives a separate fifteen-case admission;
  all runs acquire actual shared SPICE leases individually, at priority zero.
- `receiver_restore_threshold_clock.py` remeasures complete DC evidence
  before preparing the unchanged three full 80 ns/47-period source-clock
  fixtures. The reduced-tail reference, native shared bias and digital RX
  closures remain bound to their original producer. Missing reports cannot
  silently start DC simulations during admission checks. The new LVT model
  and W8 sizing are experimental; the older LVT-restorer-only failure remains
  rejected and contributes no passing admission to these combined candidates.
- Gated physical continuation
  `receiver_physical_followup/eb3d0b22853c2cb7` waits on the exact new
  clock-followup owner. It retains the frontend-local placement including all
  pull-up segments, builds isolated candidate geometry, requires DRC/LVS,
  extraction and independent RC audit, then runs the original two full native
  clock fixtures. Scientific producers bind the exact variant/source bytes
  and preserve the bias and digital RX closures. Tools use the container's
  NumPy-enabled `/usr/bin/python3`. No physical build starts from partial DC
  or source-clock evidence, and a native diagnostic cannot publish a PHY.
  Implementation commits are `6e10ef8` (source experiments) and `a23744f`
  (physical/native continuation). All 719 regression tests pass without skips.
- Commit `2ddf9b2` adds the restorer-specific component selector and corrected
  driver/native-receiver coupled diagnostic. Separate resource followers under
  `eb3d0b22853c2cb7/component_followup/` and `coupled_link_followup/` bind the
  exact live physical owner and wait for a completed passing native result.
  They skip rejected or unadmitted variants. Component admission requires all
  sixty original source/native DC/rate conditions. Coupling retains the audited
  110:1 driver, original channel and native bias/digital RX, exact 188.049 ns
  fixture, 20 ps maximum step, 32-bit payload and the 200 ps additional margin
  gate. This remains a short ideal-phase diagnostic; measured DLL, real-clock
  startup, full PVT/aperture and long payloads are still required. All 727
  regression tests pass without skips. These followers own no outer SPICE
  lease and do not change any active circuit or qualification pointer.
- Commit `a599b86` adds full completed-trace restoration observations. Receipt
  `c130e79d2f47a246/restoration_observations/c98be57c815cdacc/` verifies every
  input/producer/trace hash and remeasures the original 15–75 ns transport
  exactly before examining complete falling-to-falling response windows.
  All nine missing falling pulses lack a falling 0.9 V crossing at RESTORE0.
  Six have input peaks at least 100 mV: widths 519–590 ps, CO peaks
  0.754–0.959 V. The remaining three input peaks are below 100 mV. Across all
  nine misses, RESTORE0 minima range from 1.219 to 1.787 V. This supports a
  first-restorer swing/drive limitation across the full failure set; it does
  not measure a static trip voltage or prove that a threshold-only change
  suffices. Native admission still uses the unchanged original transport gate.
- The three-unit live replay's immutable
  `ef823b6778f2d9a5/partial_transport_observation/` snapshot compares the same
  complete periods in 15–30 ns against the completed two-unit replay. Both
  miss three of ten captured-period checks; both sharp controls miss none.
  Observed CT bus spans 0.131–0.342 V for three-unit versus 0.170–0.378 V
  for two-unit. The full three-unit native controls continue to 80 ns; this
  partial diagnostic supplies no native admission or completed verdict.
- Commit `b803eb5` isolates the SF/40 source numerical slowdown in
  `receiver_restore_threshold/d2ad4a830399a9b2`. All three original candidate
  and observed-source files remain byte-identical; only maximum integration
  step changes from 50 ps to 1 ps plus the include path. Full 144 ns duration,
  twelve input points, 10 ps output step, fixed supplies, Gear method,
  tolerances and original DC/current/twelve-device scoring remain. Original
  `81b4431a58df60c1/restore_lvt_n4` accepted steps shrink to roughly 0.02 fs
  near 71.901 ns but still advance; the process is not declared dead or
  electrically failed. The separate retry acquires actual fair leases and
  cannot replace the original fifteen-case source matrix or any native gate.
  The full regression after both new diagnostic helpers passes all 732 tests
  without skips.
- Independent wire-load observation in
  `receiver_layout/9d740d19bee2c0d0/compared_frontend_loads/` finds that the
  two-unit correction leaves critical mirror/tail/CO/CL/CT wire capacitances
  close to the original layout; PP/PN wire couplings grow by approximately
  23/18 fF. This excludes intrinsic device capacitance and is not an AC
  bandwidth measurement. Separate `exact_reduction_observation/` reduces
  13,309 resistors to 3,588 while retaining every non-resistor and fifteen
  explicit observation buses. Four independent boundary-current witnesses
  pass, maximum discrepancy 3.78e-15 A. Transient equivalence remains pending;
  no live model, catalog, fixture or qualification profile is replaced.

Rejected baseline DLL work retired; corrected-driver source matrix passes:

- The old 4 pF DLL's three **unfinished** 410 MHz step runs have been
  archived and retired. Its independently measured TT25/FF0 phase margins
  already fail at 47.192/34.408° against 60° required; completed 390 MHz
  validations at SS0/TT25/FF0 are retained. Further baseline 410 MHz
  agreement could not admit this circuit. Capacity now serves the 16 pF
  correction and current receiver/driver qualification instead.
- The targeted owner was `openlvds-local-delay-native-continuation`, with
  `Restart=no`. Before stopping it, the complete service was frozen and
  **222 files** were copied, including completed/partial stability evidence,
  continuation metadata, circuit snapshots and producer code. Receipt
  `resident_jobs/obsolete_dll_storage4/after_stop.json` independently
  verifies every original file hash is unchanged, every old process is
  gone, and all six shared-slot file inodes are unchanged. Exactly three
  simulators were retired; other scientific jobs were preserved. A terminal
  sidecar `dll_qualification/15cac0ba813a9333/baseline_retirement.json`
  records the intentional retirement while original producer state files
  remain byte-preserved. The partial 410 MHz traces are **inconclusive**,
  not completed electrical failures. No passing stability summary or
  baseline/native PHY admission is created.
- Freed leases were acquired by queued aperture/driver work; the global
  budget remains six actual simultaneous SPICE processes. The corrected
  source, native receiver replay, matched link and exact-driver benchmark
  owners remain live. No original scientific producer, active model or
  fixture was edited to accelerate them.
- All **15 corrected-driver schematic cases pass** across the five
  required process corners and 0/25/40 °C. Read-only observer
  `driver_components/a1d220a703a6ac2b/completed_source_observations/`
  verifies exact matrix coverage, producer/runtime/input hashes, source and
  original full 2540 ns fixture reconstruction, complete waveforms and
  exact cached metric agreement. Minimum loaded differential magnitude
  is 314.990 mV at SF40. This includes the campaign's additional loaded-eye
  screen; the voltage requirement itself remains settled DC into 100 ohms.
  Native cases remain live, so this is not the full thirty-case report or
  driver/RC/link/PHY qualification. No test gates are relaxed.

Driver exact-network benchmark dispatched; completed FF0 DLL step agrees with its model:

- Read-only exact reduction observer
  `driver_layout/086066e18f25d11a/exact_reduction_observation/` applies the
  existing degree-8 positive-conductance elimination to the corrected
  driver's 54,491-resistor network. The result has **15,783 resistors**,
  eliminating 14,304 additional algebraic nodes while preserving every
  capacitor, device, port and protected terminal statement. Four sparse
  terminal-admittance witnesses pass across 4,441 boundary nodes, maximum
  absolute current discrepancy 1.635e-13 A. Result SHA256 is
  `7f2bad3925ab4ca2bcc0801ceb47e55e53dfb3c504255090c324fdfe997ebc3d`.
  This is a mathematical result, not a measured simulation speedup or
  transient certificate. No physical catalog entry or live model changes.
- `benchmark_driver_exact.py` prepares context
  `driver_exact_benchmark/2c5e22ac31f7529b` against the complete native
  SF40 and FF0 pilots in `driver_current/89250b060d3d9825`. Preparation
  remeasures all original current-correction pilots, binds the same physical
  driver and reference resistor-network hash, verifies mathematical witness
  inputs/runtime, and preserves the shared bias. Every original printed
  node is checked against the reduced hierarchy before simulation.
- Both benchmark fixtures retain the **entire 2540 ns original waveform**,
  numerical policy, supply/reference values and 100 ohm/2 pF loads. Only
  algebraic resistor rows and the source artifact path differ. Comparison
  checks every differential crossing in 2010–2530 ns, requiring at least
  sixteen matched edges within 20 ps; plateau difference must be at most
  20 mV outside 300 ps edge windows. Common mode is compared over the
  complete interval without excluding transitions, also within 20 mV.
  All original loaded-eye/DC/polarity/cadence metrics must still pass.
- Unit `openlvds-driver-exact-native-benchmark` is dispatched with one fair
  worker inside the unchanged six-slot budget. Partial output is retained;
  completed results require scientific remeasurement. Passing these two
  comparisons cannot replace full PVT, final six-block RC certification,
  link qualification or explicit model selection. All **647 regression
  tests pass**, no skips; tests reject lost activity, common-mode errors,
  non-resistor substitution and overwriting partial output.
- Completed baseline FF0 400-to-390 MHz stability evidence now passes the
  original measured-model step comparison: amplitude error 1.293%,
  measured/predicted t90 105/112.5 ns, settling error 7.143%. The bound
  read-only report is under native stability root
  `1cdf451bf81d3ee8/completed_ff_step_observation/`. Its independently
  measured phase margin remains 34.408°, so this step agreement does not
  waive the 60° gate or admit the baseline DLL. The 16 pF correction's
  own source/native qualification remains pending.

Frontend-local native controls complete; corrected-driver pin replay dispatched:

- Context `receiver_replay/c1109a1560bd4e6e` completes both full 80 ns
  controls and cached scientific remeasurement. The native sharp control
  passes with **0 missing edges**, improving on the previous compact
  layout's 33. The retained captured stimulus improves from **39 to 18
  missing edges**. `native_clock_passed=false`; the layout correction
  alone has not admitted this receiver.
- Bound observer `c1109a1560bd4e6e/completed_clock_diagnosis/read.py` and
  `summary.json` measure 50 PP-minus-PN crossings in 15–75 ns for each
  new native case, versus 28 in the preceding captured native layout.
  Minimum magnitude at its own frontend half-cycle centers is 17.165 mV
  captured versus 205.482 mV sharp. CO has 34 versus 50 crossings at 0.9 V;
  RESTORE0 has 32 versus 50. These counts support a substantial frontend
  improvement and residual decision/restoration bandwidth loss, but do not
  independently prove correspondence for every input edge. Observed CT
  voltage spans 43.40–302.73 mV in the captured case; no saturation/VDSAT
  claim is made from this range alone.
- The 18 captured misses occur as nine lost short pulses and their paired
  transitions. Short input widths are 514.80–590.33 ps. Only three of the
  eighteen missing-edge records have below-100 mV input midpoint magnitude;
  six of the nine short pulses still exceed 100 mV. The above-threshold
  failures remain failures and cannot be excused by the weakest pulses.
- Before resizing devices, `replay_receiver_current_pins.py` now tests the
  **same native receiver library** with the actual completed corrected
  P64/N24, 110:1 native-driver pin traces from comparison
  `driver_native_restore/65d922eb5c270776`. This waveform has 137.760 mV
  minimum received-clock midpoint magnitude and no midpoint violations,
  versus 82.592 mV and three violations in the older captured fixture.
  Its minimum zero-crossing half-period is still short (523.958 ps), so
  this change is not presumed to solve the receiver's dynamic problem.
- New context `receiver_current_pins/bb736100f334c145` preserves all
  11,911 original pin-waveform knots in 50–120 ns, shifted by -45 ns into
  the original 80 ns/1 ps receiver fixture. Only four recorded voltage
  sources and the library artifact path change. Input pin ranges stay
  within 0–2.4 V. Endpoint vertices within eight floating-point ulps are
  reused, preventing artificial almost-duplicate source breakpoints; the
  original interior knots and voltages are neither compressed nor resampled.
- Unit `openlvds-frontend-current-driver-pins` is dispatched with one fair
  lease inside the existing six-slot budget. It reports
  `diagnostic_clock_passed` separately and provides **no source, native or
  PHY admission**. Ideal pin sources omit TX/channel loading feedback;
  the original failure, complete native link, components, margins and
  PVT gates remain required. All **644 regression tests pass**, no skips,
  including exact pin preservation, timestamp boundary handling, unchanged
  numerical fixture and partial-output preservation.

Compensated DLL extraction/audit complete; matched source acquisition dispatched:

- The 16 pF storage candidate `dll_layout/35555c8719890933` now passes
  distributed RC extraction, public-port verification and an independent
  wire-collapsed connectivity audit, in addition to its DRC 0/LVS checks.
  Extraction has 176,147 raw resistors and 5,682 capacitors; the standard
  exact reduction retains 146,601 resistors. Its native model SHA256 is
  `8a19960d3e85586cab3f1b14fd9819a8161bde7a6681526f54dc79330178e64d`.
- Additional exact degree-8 resistor elimination, using the unchanged
  `exact_rc_candidate.py`, produces
  `dll_layout/schur_496dde348e4fe55b`: **43,919 resistors**, removing
  another 40,137 algebraic nodes. Every device, capacitor, port and other
  non-resistor statement remains invariant. Four independent sparse
  terminal-admittance witnesses pass across 6,280 boundary nodes, maximum
  absolute current discrepancy 2.843e-13 A; a fresh independent connectivity
  audit also passes. Exact native SHA256 is
  `060530738a077cdde80c4f26b109199b54c0a65bf26a72f1c68b5c9c92633f09`.
  Native transient equivalence and electrical qualification remain pending;
  these checks do not admit loop margins or acquisition.
- `screen_dll_storage.py` prepares source acquisition context
  `dll_architecture/368259f7b02c5fdc` with explicit variant `ota_w8_c16`.
  It first remeasures all three completed baseline source controls, then
  changes only the source macro to the captured capacitor correction.
  The full source must equal the guarded transformation of the original
  source. Native PFD and shared-bias closures remain unchanged; the source
  fixture inlines its unchanged delay devices into the analog macro.
- The actual `matched_fixture_audit.json` proves that each SS0/TT25/FF0
  deck is byte-identical after normalizing only library artifact paths.
  Original full-duration clock/reset/load/numerical policies and measurement
  windows are retained. Removing exactly the twelve newly added capacitor
  rows from each flattened analog macro restores its original bytes.
  `inputs/ota_w8_c16.spice` is the exact physical candidate source, so a
  future native qualification cannot borrow the old 4 pF source screen.
- Unit `openlvds-dll-storage-source-acquisition` is live with one worker,
  initially queued for the SS0 fixture. Each child takes its own fair lease
  within the unchanged six-slot global budget; no outer lease is held.
  Partial raw/log/table output cannot be overwritten. This screen does not
  promote a model or replace the fifteen-condition native model, acquisition,
  recovery/readiness/OTA and final PHY gates. All **641 regression tests
  pass**, no skips, including source-library protection and partial-output
  preservation tests.

Native digital replay completes; measured DLL margins require a compensation correction:

- Digital-only recorded-pin context `native_rx_pin_replay/8281fd2383199c25`
  completes its entire 188.049 ns fixture and passes cached scientific
  remeasurement. Its systemd owner exits successfully. In 50–125 ns,
  RXDATA/RXCLOCK crossing times agree with the recorded inputs to numerical
  precision; Q0/Q1 crossing counts match with maximum errors
  2.2331/1.6705 ps. RXVALID has no crossings in either trace and maximum
  interpolated voltage difference is 0.412 mV. Output voltage differences
  near transitions reach 40.1/23.4 mV and are reported separately.
  Thus the digital-only test does not reproduce the analog replay's
  62.1 ns numerical stall. This narrows the next isolation to analog
  restoration/loading interaction; it does not identify a device/solver
  mechanism or repair the parent link's incorrect captured bits.
- Read-only, hash-bound observers under native stability root
  `dll_qualification/15cac0ba813a9333/stability_screen/1cdf451bf81d3ee8/`
  now measure the completed SS0/TT25 400-to-390 MHz steps. Both match the
  original model within its amplitude/settling limits: SS0 amplitude error
  1.627%, measured/predicted t90 80/90 ns; TT25 amplitude error 2.724%,
  t90 95/92.5 ns. Their 410 MHz validations remain outstanding.
- Independently measured native AC/PFD/delay models nevertheless fail the
  phase-margin gate at TT25 and FF0. Minimum margin over the two static
  clock states and averaged G/Y model is **67.042° SS0, 47.192° TT25,
  34.408° FF0**, against 60° required. Corresponding averaged unity-gain
  frequencies are 2.984/6.504/9.142 MHz. Passing step agreement does not
  waive these failures or admit the remaining DLL qualification suite.
- `completed_step_observations/` binds the two completed step reports;
  `compensation_observations/` evaluates ideal added CTRL capacitance
  0/1/2/4 pF using measured G/(Y+j*w*C). Extra 4 pF passes TT25 but FF0
  remains at 50.653°. The bounded extension in `compensation_extension/`
  evaluates 0/4/8/12 pF: extra 8 pF still gives only 59.822° at FF0;
  extra 12 pF predicts 82.872/73.771/65.688° at SS0/TT25/FF0, with all
  three model states passing at each condition. These are algebraic
  small-signal estimates at the measured operating points, not new physical
  or transient qualification. The observers preserve all original producer
  and running fixture bytes and do not dispatch simulators.
- `dll_storage_compensation.py` implements one source correction admitted
  by these bound three-condition estimates. It preserves all existing
  devices, subcircuits and public ports and adds six pairs of 30x30/10x10
  um MIM capacitors at CTRL/VSS: nominal storage 4 to 16 pF. Changed original
  capacitor topology/dimensions, repeated application, stale model inputs
  and estimates belonging to another baseline layout are rejected.
- Source context `dll_compensation/b16fb6056968bed0` has SHA256
  `e37634f60cd95b032ad8114dfc15debc3de8f3a9436853cc79bd010feb0deea4`.
  Its local-delay/local-comparator layout `dll_layout/35555c8719890933`
  passes **DRC 0 and LVS**, with 531 devices versus the original 519.
  Extraction and independent RC audit are running through the existing
  isolated DLL flow. No canonical source, live baseline or selected PHY
  pointer changes. New extracted model/margins, source/native acquisition,
  steps, all fifteen PVT conditions, recovery/readiness/OTA and full PHY
  admission remain required. All **638 regression tests pass**, no skips.

Matched corrected-driver/current-LVT link diagnostic implemented:

- The completed native-driver comparison `65d922eb5c270776` retains the
  **older native VREF fast-restoration receiver** from physical context
  `receiver_layout/64ae7a93d207703b`, through saved native-link parent
  `receiver_candidate_link/0dee72b71f4525df`. Its failed payload is not
  a test of the current schematic LVT circuit or frontend-local layout.
  The observed amplitude improvement remains useful, but these results
  must not be used to select or reject the newer receiver architecture.
- `compare_current_lvt_link.py` now prepares a paired, full-channel
  diagnostic with the admitted **same schematic LVT receiver** and the
  100:1/110:1 native P64/N24 drivers. Both children retain the original
  188.049 ns SS/40, 410 MHz, 45% duty, +100 ps skew, 100 ps peak-to-peak
  jitter fixture, 32 payload bits and 60 ns training. Maximum timestep is
  tightened identically to 20 ps. Fourteen extra probes expose both
  receivers' PP/PN/CO/CL/CT/RESTORE0/RESTORE1 voltages. The original
  decoder and an additional clock-transport measurement are retained.
- Preparation remeasures all fifteen LVT DC cases, all three source-clock
  controls and both completed driver comparisons. A different source
  circuit cannot borrow this admission. Children run sequentially with
  independent fair leases; no outer slot is held. Existing frozen
  scientific producers and live fixtures are unchanged.
- Pair `current_lvt_link/494d9c90761d8f76` is dispatched under
  `openlvds-current-lvt-matched-link`, initially waiting for a shared
  slot. Its actual `matched_fixture_audit.json` proves identical normalized
  decks and identical RX core, shared bias, DLL, delay line, digital TX
  and digital RX closures. The two native driver closures differ as
  intended; each retains its own extracted RC, so geometry parasitics
  can also differ with the declared driver intervention. Neither child
  nor the pair qualifies startup, native analog RX, final sampling margin
  or the complete PHY. There is no automatic model promotion.
- The digital-only recorded-pin replay has acquired a slot and its
  observed accepted time reached 57.871 ns; frontend-local captured and
  sharp tests reached 30.695/31.864 ns. These are live progress
  observations, not complete electrical results. All **636 regression
  tests pass**, with no skips, in the SciPy-enabled Apptainer environment.

Native digital isolation implemented; previous compact controls and corrected-driver comparison complete:

- `replay_native_rx_pins.py` isolates the unchanged native digital RX from
  completed mixed-view parent `analog_link_pilot/36b513f21de11d28`. Both
  restored inputs, RXDATA/RXCLOCK, retain all **32,104 original PWL
  vertices** with round-trip voltage/timestamp precision. The original
  reset, SS/40 PVT, 1.8 V supply and 20 fF output loads are preserved.
  The exact instantiated RX closure hash remains
  `c062ce4789c8a3e771aea7f8e309b7336bf0674dff78f8f89d6ed750fe52abb4`;
  no additional RC reduction or analog architecture substitution is made.
- Diagnostic `native_rx_pin_replay/8281fd2383199c25` is dispatched under
  `openlvds-native-rx-recorded-pins`, with one independent fair lease and
  the unchanged six-slot shared budget. Its initial observed state is
  waiting for a slot. It uses 5 ps maximum timestep and the original
  Gear/error tolerances, with no enlarged Newton-iteration budget.
  This is the next isolation after internal observations narrowed the
  stalled analog replay to data restoration/native input interaction.
  It does not rerun the stalled analog control.
- Comparison covers 50–125 ns and reports each input/output's rising and
  falling edge counts, timing disagreement and interpolated voltage error.
  An unchanged wrong bit remains wrong. Completing this ideal-source test
  cannot prove full-link agreement, analog feedback behavior, identify a
  failing transistor/solver mechanism, or qualify the PHY. Partial output
  is retained and cannot be overwritten by rerunning the same context.
- The preceding compact LVT native context `911c0f415c65ece8` is now
  complete: captured **39** and sharp **33 missing edges**. Its fair sharp
  continuation unit exited successfully; `native_clock_passed=false`.
  These completed failures remain the controls for the live frontend-local
  correction `c1109a1560bd4e6e`; corrected results are still outstanding.
- Corrected-current native-driver comparison `65d922eb5c270776` completed
  both original fixtures. The 110:1 P64/N24 driver has no below-100 mV
  midpoint samples in either reported clock view (TX minimum 121.505 mV,
  received differential minimum 137.760 mV). The source control has four
  and three respectively. This is a partial amplitude screen only.
  **Both payload decoders fail**; the corrected-current case observes
  all-zero words and only 30 restored rising-clock edges over the complete
  trace, versus 70 in the source control. Improved driver amplitude does
  not establish receiver or full-link functionality. The unchanged
  30-case driver component campaign `a1d220a703a6ac2b` has started through
  its existing guarded handoff; no model is automatically promoted.
- All **633 regression tests pass**, with no skips, using the SciPy-enabled
  Apptainer environment. New tests cover exact pin preservation including
  overshoot, analog-instance removal with original native RX/load retention,
  missing-edge/constant-output disagreement, incomplete-wave refusal and
  preservation of partial output.

Frontend routing regression identified and a circuit-preserving correction dispatched:

- All three LVT source-clock controls completed successfully (47 periods
  each), but compact native context `receiver_replay/911c0f415c65ece8`
  completed its captured case with **39 missing edges**. The complete
  schematic/native comparison shows 49 versus 28 PP-minus-PN frontend
  zero crossings in 15–75 ns. Minimum magnitude at the frontend's own
  half-cycle centers drops from 125.168 mV to 5.250 mV. Transitions are
  already being lost upstream of the decision output; CO-only optimization
  was insufficient.
- The preceding compact placement moved input mirror endpoints into the
  decision row while leaving their diode/reference and tail devices on
  long folded trunks. Independent wire-net aggregation exposes a major
  loading regression. The original uniform-layout NL/NR loads were
  60.717/61.920 fF; the compact LVT layout raised them to
  367.038/413.222 fF while reducing CO to 29.116 fF.
- `receiver_frontend_geometry.py` now keeps the complete active frontend,
  including mirrors, tails and intermediate resistor-load nodes, local with
  the decision/restoration chain. Only unused bias/monitor cells retain
  folded trunks. New layout `receiver_layout/74f1d1fd9724608e` has
  **identical source-circuit bytes**, 70 devices and the same nine ports.
  It measures 598.46 x 144.2 um. DRC, LVS, extraction and the independent
  RC audit pass; exact native model SHA256 is
  `658ce921e3a7198991113aa5a485d3af17c8f6d698fdef22e4ade332d84be949`.

| Wire-net coupling sum (fF) | Previous compact LVT | Frontend-local LVT |
| --- | ---: | ---: |
| NL | 367.038 | 62.471 |
| NR | 413.222 | 62.549 |
| PL | 280.315 | 67.381 |
| PR | 279.685 | 68.224 |
| NT | 439.189 | 87.636 |
| PT | 368.429 | 117.663 |
| PP | 93.301 | 111.443 |
| PN | 105.851 | 116.756 |
| CO | 29.116 | 34.941 |

- These are extracted wire coupling sums, excluding intrinsic MOS
  capacitance. The trade increases PP/PN/CO loading modestly while removing
  the much larger frontend mirror/tail loads. The bound observer, source-byte
  check, completed wave evidence and extraction hashes are in the new
  layout's `completed_frontend_audit/`. Transient improvement is not yet
  established.
- New native context `receiver_replay/c1109a1560bd4e6e`, owned by
  `openlvds-lvt-frontend-local-native`, retains both original captured/sharp
  fixtures, full 80 ns duration, 1 ps maximum timestep, native bias and
  digital RX load. Full source DC and source-clock admission is required.
  Extra NL/NR/PL/PR/NT/PT probes allow direct testing of the diagnosed
  frontend bottleneck. Two independently leased workers use the six-slot
  dispatcher; no outer lease or active-pointer promotion is introduced.
- The still-useful sharp control of the preceding native context was queued
  on long-running slot 3. Once its captured simulator finished, only the
  queued coordinator was frozen and archived (176 files); no simulator or
  completed waveform was stopped or changed. A second process observation
  confirmed every helper gone before starting
  `openlvds-lvt-compact-sharp-fair` on the **same scientific context**, with a
  separately captured fair resource policy. Receipts are under
  `resident_jobs/lvt_sharp_rescheduling/`. The old selected-PHY link waiter
  stays unadmitted because its required captured native screen failed.

Completed driver correction, bounded PMOS results and numerical diagnosis:

- The 110:1 current correction completed all three pilots successfully.
  Native SF40 minimum loaded-eye amplitude is **264.227 mV**, compared with
  247.550 mV in the preceding campaign; DC levels, polarity, cadence and
  common-mode checks also pass. The native FF0 upper-swing guard passes.
  This fixes the campaign's stricter loaded-eye check; the declared TX
  voltage qualification policy remains settled DC into 100 ohms, with
  loaded-eye measurements otherwise diagnostic.
- Matched native comparison `driver_native_restore/65d922eb5c270776` and
  full thirty-case context `driver_components/a1d220a703a6ac2b` are prepared
  from the exact corrected source/GDS/RC model. Owner
  `openlvds-driver-current-native-components` remeasures the three completed
  pilots, runs both original matched native controls, then admits the
  original thirty source/native component fixtures with two independent
  leases. Partial outputs cannot be silently rerun. Completion of a loaded
  comparison does not promote its decoder result or the full PHY.
- PMOS p8/t4 passed all fifteen original DC/current/six-device stress cases.
  A read-only extension checks the six downshift/restorer MOS as well over
  each full 144 ns trace: all fifteen twelve-device screens pass, with
  worst observed thin terminal difference 1.896729 V (SS0) and minimum
  absolute PMOS tail VDS 649.869 mV. This is the 1.95 V project screen,
  not a foundry rating or a VDSAT/saturation proof. The bound report is
  `receiver_architecture_matrix/66493e9dc77d72e6/completed_observations/49cf25636c9d0ee7/`.
- PMOS p8/t4 nevertheless fails its completed source-clock suite:
  retained reference 0, captured PMOS **24**, sharp PMOS **18** missing
  edges, each from 47 tested periods. Its source admission is false and
  native followup is held. The old weak stimulus has three of 48 complete
  half-cycle midpoints below 100 mV (minimum 82.592 mV); however, **21 of
  the 24 missed PMOS edges pass that midpoint amplitude screen**. This
  does not excuse its failure. A completed selected-driver mixed-view
  comparison has 133.640 mV minimum and no midpoint violations, but is not
  a final valid-source certificate. The partial contract audit is under
  `receiver_clamp/4119a08677e336d8/completed_contract_audit/`.
- The next bounded PMOS intervention doubles only tail width from 4 to
  8 um with the pair retained at 8 um. Its SS40 twelve-point static/current
  screen `receiver_architecture_static/45a626e63053c607` passes, measuring
  settled tail-current magnitudes 110.501–129.477 uA and minimum settled
  absolute VDS 608.840 mV. Matched captured-clock pilot
  `receiver_clamp/952e982341202ffb` completes with **18 missing edges**,
  improving on 24 but still failing. It is not advanced to full native or
  release admission. No unbounded width sweep is started.
- The iteration-budget replay also stalled: 0.406 ps advancement in
  109.9 seconds near 62.105 ns. It and its queued architecture watcher
  were archived (98 files) and retired. An observation-only control
  `selected_receiver_replay/4842a2e1ca90e99f` added internal voltage probes
  without circuit or numerical changes. Its immutable last-0.25-ps snapshot
  shows 0.030–1.936 fs accepted steps, 11.970 mV movement at RXDATA and
  only 5.761 uV maximum movement among observed capture/publication nets.
  This narrows the next isolation test to the data-restoration/native-input
  interface; it does not identify a particular device or solver rejection
  mechanism. The incomplete probe was archived after diagnosis (101 files)
  and retired after only 0.403 ps advancement in 108 seconds.
- SPICE exports the two public RX inputs under parent RXDATA/RXCLOCK
  names. Their voltages were present in the raw snapshot, but duplicate
  hierarchical aliases would fail strict table export. After archiving and
  stopping that context, the probe list was corrected to retain all 160
  internal observations while using the existing parent input vectors.
  Every corrected name was checked against the actual captured native raw
  header. Corrected control `selected_receiver_replay/b04d252f9f86d586` is
  prepared only; it is not another dispatched numerical retry. Prefixes,
  matching producer bytes and retirement receipts are in
  `resident_jobs/internal_replay_diagnosis/` and
  `resident_jobs/iteration_replay_progress/`.
- Conditional old-trace timing algebra finds separate causal delay ranges
  of 310.246–454.966 ps for rising edges and 0–184.217 ps for falling edges,
  despite an empty common-delay interval. This motivates duty-shaping
  investigation only if the admitted new architecture still needs it.
  No shaper is implemented or qualified; the old out-of-domain slew and
  incomplete aperture-table limitations remain. The report is in the old
  pilot's `capture_aperture_diagnosis/independent_edge_budget/`.
- Four queued controllers for the superseded uniform x4 receiver were
  archived (651 files) and retired. The completed 18-edge native failure
  and all existing data remain. No target simulator or held simulation
  lease was present. Receipts are in
  `resident_jobs/obsolete_uniform_decision/`; unrelated active jobs continue.
- Validation: all **629 tests pass** in the captured NumPy/SciPy environment.
  The exact new native result, full driver campaign, complete component/PVT,
  aperture, DLL, matched-link and release gates remain open.

Compact PMOS physical implementation and guarded clock followup:

- All three PMOS p8/t4 DC pilots (TT25, SF40, FS40) passed the twelve
  original sensitivity/common-mode points and the observed thin-device screen.
  The remaining fifteen-case matrix continues under its original owner.
  This admitted a diagnostic compact layout using the same four frontend
  columns and packed decision/restoration row as the LVT comparison.
- `receiver_layout/53336113b4769ab3` implements the actual PMOS pair,
  thick-oxide mirror/tail/downshifter and thin restoration chain. It contains
  69 flattened devices, retains all nine ports, and measures 295.4 x 357.2 um.
  DRC, LVS, extraction and independent RC audit pass. Exact native netlist
  SHA256 is `d4a9c24baa1a526f1d2048fbdd25c500aa516ede66ed8df2fe60a38035d5d2e6`;
  its file is under `build/extracted/8e145b23224749fc/`.
- An input/producer-bound wire observation compares resistor-connected
  extracted nets with the retained compact LVT layout. PMOS aggregate
  external coupling sums are CO 27.703 fF, CL 22.226 fF, CT 23.973 fF,
  PP 94.122 fF and PN 106.052 fF; LVT CO is 29.116 fF. This is a wire
  coupling screen, not intrinsic MOS capacitance or a timing prediction.
  The observer and report are in the PMOS root's
  `completed_wire_observations/` directory.
- `receiver_pmos_clock.py` requires all fifteen original PMOS DC/current/
  stress cases, then uses the unchanged three source controls at 1 ps maximum
  timestep, 5 ps output interval and full 80 ns duration. The first control
  deliberately retains the preceding reduced-tail reference. Only the two
  historically `clamped_`-labelled controls instantiate PMOS p8/t4; these
  labels do not imply that decision clamps were restored. In particular,
  the completed 47/47 `unclamped_captured` case in LVT context
  `receiver_clamp/7b715872da5a4460` proves the retained baseline reference,
  not the modified LVT or PMOS receiver.
- `probe_receiver_pmos_compact.py` reuses the strict captured/sharp native
  replay machinery with a distinct PMOS physical/source profile. It requires
  complete, remeasured DC and source-clock admission before preparation;
  checks the exact audited native model, protected bias/digital closures,
  all original 47 periods and full finite waveforms; and preserves the
  declared 1 ps integration limit. Results remain diagnostic, with no
  automatic analog promotion or full-PHY qualification.
- `openlvds-pmos-p8t4-source-native-clocks` is live as a resource-only
  handoff in the PMOS physical root's `qualification_followup/`. It waits
  for the actual matrix owner to finish successfully and all fifteen cases
  to pass. It then prepares/runs source clocks with one shared lease per
  child, followed only on source-clock success by the two independently
  leased native controls. There is no outer lease and the global budget
  remains six. A failed upstream result is held for diagnosis.
- Validation: all 617 regression tests pass in the captured NumPy/SciPy
  environment. New checks cover incomplete-pilot/rate rejection, retained
  reference versus PMOS source selection, incomplete DC admission, profile
  restoration on exceptions, and preservation of a negative native verdict
  while adapting descriptive scope text.

PMOS dynamic evidence, driver correction and current experiment owners:

- Both matched TT25 isolated analog rate tests completed at 410 MHz with
  the original 250 mV differential stimulus and 100 fF output load. LVT
  `receiver_architecture_rate/5e2ac9d9f1770d32` passes with minimum valid
  high/low windows 1148.91/1209.15 ps. PMOS p8/t4
  `receiver_architecture_rate/f9e34b2faff66573` passes with 963.02/1391.33 ps.
  These are analog rate windows, not qualified link sampling margins.
- Full 60 ns observations cover six decision/bias MOS and the six MOS in
  the downshift/restoration chain, including startup and all transitions.
  PMOS tail current is 62.08–65.62 uA in magnitude, mean 64.34 uA;
  minimum absolute tail VDS is 847.56 mV. LVT tail current is
  123.23–388.67 uA, mean 255.17 uA, with minimum VDS 63.46 mV.
  Both pass the 1.95 V project screen for the observed thin devices:
  peaks 1.88191 V (PMOS) and 1.88818 V (LVT). The PMOS downshifter
  sees a 2.35871 V terminal difference on a thick-oxide device. These
  observations do not establish foundry ratings, saturation via VDSAT,
  remaining frontend/bias stress, native timing or release qualification.
  Producer/hash-bound reports are in each rate root's
  `completed_observations/` directory.
- This supports advancing PMOS p8/t4 to full source DC PVT screening,
  without selecting it as the final receiver. Matrix
  `receiver_architecture_matrix/66493e9dc77d72e6` prepares all fifteen
  original cases and is dispatched as `openlvds-pmos-p8t4-dc-matrix`.
  The first three pilots gate further advancement. Each scientific child
  keeps its original circuit/fixture/identity and acquires one shared slot
  through a separately captured resource policy; there is no outer lease.
- The selected driver's complete thirty-case campaign
  `driver_components/f3d1cd21d727bcc8` finished **29/30 passing**. Native
  SF40 fails loaded eye amplitude at 247.5499 mV versus the required
  250 mV minimum. Its DC, polarity and cadence checks pass. Native SF25
  is also close to the limit (251.427 mV). This failure is retained; the
  selected P64/N24 driver is not electrically qualified.
- A single bounded correction adds one 20 um PMOS steering-current finger,
  changing the ideal mirror ratio from 100:1 to 110:1 while retaining the
  35 uA reference and P64/N24 restoration. Physical candidate
  `driver_layout/086066e18f25d11a` passes DRC, LVS, extraction and the
  independent RC audit; exact netlist SHA256 is
  `e8713e6a95ceb213bd7a08570147d36c21078fb0a2e90f68d9b347fad89d9965`.
  `driver_current/89250b060d3d9825`, owned by
  `openlvds-driver-current-correction`, uses unchanged full 2540 ns component
  fixtures for schematic/native SF40 and a native FF0 upper-swing guard.
  Schematic SF40 completed and passed at 314.990 mV minimum loaded eye.
  Extracted checks, all thirty final cases and new matched-link checks
  remain necessary; the selected PHY library is not changed automatically.
- Exact resistor reduction did not resolve the native replay stall:
  `76df1c52c72e5db0` advanced only 0.338 ps in 104.1 seconds near
  62.104 ns. It and its queued followup were archived (97 files) and
  retired; disappearance of all processes and unchanged archived bytes
  are verified in `resident_jobs/exact_rc_replay_stall/`. This remains
  numerically inconclusive, not an electrical failure.
- One bounded solver-effort retry, `selected_receiver_replay/e96fe5ad7e3669e1`,
  adds only `.options itl4=100`. Circuit, error tolerances, 5 ps maximum
  timestep, bounded pin stimulus and 20 ps control calibration remain
  unchanged. Owners `openlvds-selected-receiver-replay-iterations` and
  `openlvds-selected-receiver-architecture-iterations` dispatch the control
  and calibration-gated bias x2/x4/PMOS followup under the six-slot budget.
  If this also stalls, diagnose nonlinear/internal-node convergence rather
  than launching an unbounded sequence of numerical fixture variations.
- Validation: 608 regression tests pass in the captured NumPy/SciPy
  environment; the two subsequently added matrix admission tests also
  pass. The latter verify that a failed pilot or mismatched completion
  manifest cannot advance the remaining cases and that resource bindings
  restore on failure.

Exact resistor-only digital RX replay control prepared and dispatched:

- The bounded-pin control `828b7249a2cfba8e` also became numerically
  unproductive. Two observations of the same live simulator, 93.8 seconds
  apart, show only 0.255 ps of advancement near 62.107 ns, against a
  188.049 ns stop. Its last 3,000 accepted steps span only 0.941 ps;
  this incomplete trace does not establish an electrical failure.
- The control and its queued architecture followup were frozen, archived
  (94 files, including partial raw data and producer/input bytes), and retired.
  `resident_jobs/bounded_replay_stall/` records process start times, progress,
  snapshots and terminal-state verification. Systemd reported an auxiliary
  process signalling error after termination; independent checks confirmed
  every target process gone, MainPID=0 for both units and all archived bytes
  unchanged. Useful DLL, driver and aperture simulations were retained.
- `replay_selected_receiver_exact.py` applies degree-eight positive-conductance
  star-mesh reduction only to internal resistor nodes of the native digital
  RX. All capacitors, devices, protected connections and non-resistor
  statements remain unchanged. The four physical pin sources and integration
  settings match the bounded-pin control. No approximate RC model is used.
- New control `selected_receiver_replay/76df1c52c72e5db0` removes 522 internal
  nodes and reduces 4,229 resistors to 3,447. Four independent sparse
  clamped-terminal witnesses over 1,937 boundary nodes pass, with maximum
  current discrepancy 8.41 pA. The certificate captures both libraries,
  numerical runtime binaries and the invariant non-resistor signature.
  These checks support algebraic preservation; full transient calibration
  remains pending and the candidate is explicitly unqualified.
- `openlvds-selected-receiver-replay-exact` was dispatched with its own shared
  simulation lease and a calibration-gated architecture followup. Both were
  subsequently archived and superseded by the iteration-budget retry above.
  The intended comparison runs bias x2, bias x4 and PMOS p8/t4 in order,
  each with an independent lease and no enclosing lease. No
  architecture is automatically promoted. All 601 regression tests pass
  using the captured NumPy/SciPy environment, including changed-capacitor
  rejection and scoped factory restoration tests.

Dispatcher handover completed; bounded replay replaces a numerical stall:

- The aperture handover waited until the old coordinator held no simulation
  slot and its cgroup contained only the five known controller/runtime
  processes. It stopped the coordinator, verified no simulator children or
  uncommitted point outputs, and archived 2,892 files plus process/start records.
  All 229 completed boundaries and their waveform references were preserved.
  Old MainPID=0, disappearance of every old process and unchanged archived
  files were confirmed before starting the replacement. Receipts and the
  handover producer are under `resident_jobs/aperture_fair_handover/`.
- `openlvds-rx-early-aperture-fair.service` is now live on the same captured
  `20b04dcf527af283` campaign, with two workers and one shared lease per
  uncached point. Resource policy `9995397d1801cd89` binds the dispatcher and
  continuation bytes. No simulator was retired during this aperture handover.
  The old aperture unit's deliberate termination status is not an electrical
  failure. The six-slot limit and scientific manifest remain unchanged.
- The initial selected-pin control `c89c0fa91344c0df` subsequently proved
  numerically unproductive: two saved observations 137.7 seconds apart show
  simulated time moving only from 14.568309770 ns to 14.568316782 ns, before
  its payload and 188.049 ns stop. It was frozen and archived with its partial
  raw trace, logs, complete fixture and producer bytes (79 files), then retired
  with its queued architecture followup. All old processes are gone and all
  archived files remained unchanged. This is a superseded numerical fixture,
  not an electrical failure of the LVT receiver. Receipts are under
  `resident_jobs/obsolete_exact_pin_replay/`.
- `bounded_pin_replay.py` and `replay_selected_receiver_bounded.py` replace
  that numerical experiment. Only the four physical RX pins drive transient
  sources; unused TX observation vectors are restored from the parent during
  analysis instead of forcing simulator breakpoints. Piecewise-linear voltage
  error is checked at every original knot and bounded by 0.1 mV per pin.
  Every original differential zero-crossing bracket is retained exactly;
  crossing counts and times are independently checked. The receiver circuit,
  native digital RX and complete trace/calibration requirements are unchanged.
- Actual replacement `selected_receiver_replay/828b7249a2cfba8e` has a bound
  source certificate: 13,569 retained vertices from 32,104 original timestamps,
  each pin's maximum error below 0.1 mV and zero measured error for every
  differential crossing. Its separate source/producer-bound control and
  architecture followup originally ran as
  `openlvds-selected-receiver-replay-bounded` and
  `openlvds-selected-receiver-architecture-bounded`. The control advanced
  beyond the old stall, but subsequently stalled near 62.107 ns and was
  superseded as described above. It never completed calibration. Earlier
  unrun preparation revisions retain matching producers.
- Both replica-bias nominal measurements completed and passed all twelve DC
  points and the observed thin-device screen. Bias x2 measures tail current
  138.486–371.407 uA with minimum tail VDS 46.818 mV. Bias x4 measures
  150.652–353.382 uA with minimum VDS 41.931 mV, compared with baseline
  119.866–345.187 uA and 54.961 mV. Width-ratio preservation does not preserve
  actual current, and neither variant increases the minimum absolute tail
  VDS. Dynamic comparison remains necessary; these measurements alone do
  not select or reject a receiver architecture.
- The LVT source DC matrix now completes all fifteen required cases with
  `dc_all_passed=true` and a matching manifest hash. Its three source-clock
  controls are admitted as `receiver_clamp/7b715872da5a4460`; their owner is
  live. Native clock, component, full-link and release gates remain pending.
- Five new tests cover bounded curves, preserved crossing brackets,
  invalid/fine source vertices, physical-only simulator probes, postprocessed
  recorded observations and restored factory bindings. Full regression:
  598 tests, 597 passed and one skipped. The new source approximation and
  fixed pin loading remain diagnostic; the unchanged 20 ps control calibration
  and later complete native/channel qualification are still required.

Point-level dispatcher and aperture continuation prepared:

- `spice_dispatch.py` adds priority with FIFO ordering and 180-second aging,
  using the existing six shared SPICE lock-file inodes. It never replaces
  those files or creates additional simulation slots. Ticket lifetime is
  checked with file locks rather than PID assumptions, so abandoned tickets
  are discarded safely across Apptainer PID namespaces. A 100 ms release
  handoff gives existing blocking-lock users a chance before dispatcher
  workers reacquire the same slot. Legacy controllers do not yet participate
  in its priority queue; this is not a claim of universal scheduling fairness.
- `continue_rx_aperture_fair.py` keeps the original captured aperture
  fixtures, native model, numerical policy, point analyzer and all 480
  conditions. It obtains one dispatcher lease for each uncached simulation
  point, instead of holding a lease for an entire binary boundary search.
  Cached points are remeasured without taking a simulation slot. Existing
  completed boundaries are reused only after their failing, passing and
  guarded witnesses are scientifically remeasured. Uncached partial traces
  are refused for restart. Resource policy and new producer hashes are
  captured separately from the unchanged scientific manifest.
- Actual read-only preflight at `resident_jobs/fair_aperture_preflight/`
  validates the current model/context, remeasures all native seed witnesses
  and all 32 completed SS/40 boundaries, and confirms the live coordinator's
  execution lock excludes a second coordinator before any simulation or
  boundary search is admitted. This confirms compatibility with the real
  captured campaign, not only synthetic fixtures.
- The old aperture coordinator acquired a newly freed slot and has active
  simulations. It has not been retired or replaced: a completion-safe,
  evidence-preserving handover is still required before activating the new
  continuation. The replay control remains live; bias-current variants remain
  queued, and no new receiver architecture is electrically selected.
- Six new tests exercise aging/FIFO ordering, stale and live tickets,
  cross-process exclusion against all six existing locks and inode reuse,
  scientific completed-boundary witnesses, partial/cached point handling and
  exactly one lease around the original uncached point execution. Full
  regression passes: 593 tests, 592 passed and one skipped. No tracked
  running scientific producer was edited.

Native capture failure narrowed using the completed mixed-view trace:

- Bound observation `analog_link_pilot/36b513f21de11d28/ideal_capture_diagnosis/`
  compares a zero-aperture continuous DDR sampler against the actual native
  RX public outputs using the unchanged 0.80–1.05 ns publication window.
  The ideal sampler recovers all sixteen expected payload words, with preamble
  offset 3. The native outputs differ at two publications: 75.659258 ns
  (ideal word 1, native word 0) and 85.754996 ns (ideal word 3, native word 2).
  Both differences are in the rising-capture bit. This narrows the failure
  to the native capture/publication path; it does not identify a particular
  internal transistor or distinguish the input sampler from half-cycle transfer.
- The preceding rising captures occur at 73.214310 ns and 82.966242 ns.
  RXDATA is already high at those clock crossings, but its 50% setup spacing
  is only 49.754 ps and 61.577 ps. The existing early RX topology uses a
  rising sampler followed by a falling-edge held-rise/publication stage;
  internal-node observation would be needed to separate those mechanisms.
- Read-only `capture_aperture_diagnosis/` remeasures all three witnesses
  (failing, passing and guarded passing) for every one of the 32 completed
  SS/40 aperture conditions. The aperture model's exact native RX closure
  matches the failed link. No simulator is launched and no aperture evidence
  is rewritten. The producer and all input/witness hashes are retained.
- Across the 32 intended payload capture edges, data slew measures
  18.700–28.740 ps and clock slew 26.255–43.076 ps. The fastest data edge is
  outside the current 20–200 ps characterized slew domain. The complete
  480-case aperture table is also still unfinished; these completed corner
  observations cannot be promoted to full aperture or link qualification.
- For diagnosis, applying the corner's per-edge/polarity slew-endpoint
  envelopes gives minimum additional setup/hold margins of -110.246/384.217 ps.
  Requiring 200 ps additional margin would demand a common clock delay of
  at least 310.246 ps and at most 184.217 ps under the same capture assignment.
  That interval is empty, so those conservative endpoint envelopes do not
  support a phase-only fix. The out-of-domain fast edge and unqualified
  interpolation mean this is not a proof about an implemented phase change.
  Receiver latency balance, capture aperture and waveform slew remain coupled
  design issues for the bounded architecture experiments.
- The selected-pin replay control is now confirmed running in ngspice, not
  merely queued. Both bias-current variants remain queued on slot 0 and the
  automatic architecture comparison remains gated on control calibration.
  No tracked scientific producer changed in this observation step; the last
  full regression remains 587 tests, 586 passed and one skipped.

Calibrated selected-pin receiver architecture replay:

- `replay_selected_receiver.py` reuses every recorded timestamp and voltage
  from the completed selected-driver/LVT-source link; it does not resample or
  compress the pin stimuli. The source library retains the actual native
  digital RX, its output loads, shared RX bias, fixed supplies, reset waveform
  and SS/40 process condition. The receiver pair is replaced by the declared
  fingered schematic architecture. Transmitter/channel instances are omitted;
  their recorded pin response and observation vectors are replayed instead.
- An unchanged LVT source must reproduce the parent's exact receiver closure
  before preparation. Its replay compares every rising/falling data and clock
  crossing in 50–125 ns against the completed link, requiring matching counts
  and at most 20 ps crossing error. Changed variants require a completed,
  remeasured, calibrated control from this same parent and a completed passing
  source DC/current observation before they can be prepared.
- Actual control `selected_receiver_replay/c89c0fa91344c0df` is prepared and
  queued on shared slot 0 as
  `openlvds-selected-receiver-replay-control.service`. It retains the complete
  188.049 ns interval with a 5 ps integration/output policy. The initial
  preparation revision retains matching producer bytes; no simulation used it.
  Full finite monotonic traces, scientific input/code/runtime hashes and
  partial-run preservation are enforced. Cached analyses are remeasured.
- The resource-only control `followup/run.py` is verified live as
  `openlvds-selected-receiver-architecture-followup.service`. It admits exactly
  three subsequent source replays: bias x2, bias x4, then `pmos_p8_t4`.
  Each waits for its actual nominal source owner, checks that source screen,
  prepares against the calibrated control, and obtains its own slot-0 lease.
  A failed nominal hypothesis is recorded without admitting it; a failed
  control or incomplete simulation holds the comparison for diagnosis.
  Decoding, clock transport, raw edge distances and additional sampling
  margins are reported separately. No architecture is automatically promoted.
- Slot 1 had been acquired by a long driver component test, so the two
  still-queued bias-current controllers were frozen, archived and superseded
  with slot-0 waits. All old processes and 56 files were preserved and checked;
  no simulator had started, all old processes disappeared, and all case/source
  hashes remained unchanged. Receipts are retained under
  `resident_jobs/bias_current_slot0_rescheduling`; replacement units are
  `openlvds-lvt-bias2-current-slot0.service` and
  `openlvds-lvt-bias4-current-slot0.service`. The global limit remains six.
- Five tests cover exact stimulus roundtripping, retained RX/bias fixture and
  fixed rails, calibration-error rejection, unrelated-control refusal and
  preservation of partial traces without simulator admission. Full regression
  passes: 587 tests, 586 passed and one skipped. Fixed pin sources suppress
  changes in receiver loading from feeding back into the board/transmitter;
  this experiment guides dynamic architecture selection and cannot replace
  native receiver or complete selected-link qualification.

Completed mixed-view link and LVT current findings:

- The early selected-driver/fingered-LVT-source diagnostic
  `analog_link_pilot/36b513f21de11d28` completed its full waveform. The process
  succeeded, but electrical decoding failed with no correctly ordered payload
  preamble. It remains an SS/40, 410 MHz, 45% duty, +100 ps skew, short-training
  ideal-phase diagnostic; it does not establish native receiver performance.
- Bound read-only observation `completed_diagnosis/` in that context preserves
  its producer and full waveform/report hashes. In the 62.348–101.433 ns
  payload window, all 30 scored same-polarity clock periods have an output
  edge. The wider 50–125 ns window also has no missing output clock edges.
  The diagnostic minimum distance from the preceding RXDATA crossing to an
  RXCLOCK crossing is 49.754 ps; minimum distance to the following RXDATA
  crossing is 398.882 ps. These are raw logic-crossing distances, not qualified
  aperture bounds or proof of a unique decoder-error cause. Relative data/clock
  timing needs investigation even when clock transport succeeds.
- Nominal TT/25 instrumented LVT context `0c8f8fae13878a21` also completed;
  cached scientific remeasurement confirms all twelve DC points pass. Its
  measured tail-current samples span 119.866–345.187 uA and tail VDS spans
  54.961–403.565 mV. The six observed thin decision/bias devices remain under
  the project screen, with a largest recorded terminal difference of 1.748690 V.
  PMOS in the matched nominal fixture measured 60.321–65.687 uA and
  0.765–1.154 V of absolute tail VDS. Neither static comparison qualifies
  transient pulse recovery or establishes a saturation-region classification.
- The two planned replica-bias measurements are now prepared and queued on
  shared slot 1: `lvt_bias2` at `5ec4c368b3b54626` and `lvt_bias4` at
  `a110b1a054d0c74d`, under `openlvds-lvt-bias2-current-sanity.service` and
  `openlvds-lvt-bias4-current-sanity.service`. They retain the same nominal
  fixture and measure actual current/headroom; no current invariance or
  headroom improvement is assumed from device-width scaling.

Selected-library link fixture and gated execution:

- `simulate_selected_link.py` consumes the explicit eight-block selection
  through its shared loader. Its channel, actual extracted digital endpoint
  instances, payload generator and analyzer follow the existing link fixture.
  The original live link producers remain byte-for-byte unchanged. This new
  runner explicitly requires diagnostic mode and exact RC; release admission
  and migration of final release consumers remain outstanding.
- `selected_phy_phase.py` requires the selected DLL and shared-bias closures
  to match its qualification library and selects exactly one completed native
  phase case at the requested process, temperature, frequency and duty. The
  actual waveform is remeasured, with deck/waveform/report binding checked.
  Phase replay shifts only the quarter clock; clock events, deterministic
  jitter, board parasitics and source timing remain inherited from the fixture.
- The full measured phase range, scaled for the replay period, is deducted
  from both raw setup and hold margins before the 200 ps margin check. This
  accounts for observed phase variation; numerical-error convergence and
  near-limit confirmation remain separate required work. No approximate-RC
  error is hidden in this exact-view fixture.
- Actual preparation
  `selected_link/tt_25_400m_d0.5_s0_e0_ideal_32/65c3c5d14650` binds selection
  `05aad8955a1b0cf7`. It uses solved fixed supplies, 640 ns/256-cycle training,
  a 770 ns stop time, 20 ps output/integration steps and 32 payload bits.
  Native DLL case `loop_tt_25` measures 659.955500–660.204682 ps quarter
  phase; its full 0.249182 ps range is charged against sampling margin.
  This is a prepared diagnostic, not a completed link simulation.
- Captured fixture/model/runner files cannot be silently overwritten.
  Incomplete traces are retained and refused for restart; cached complete
  waveforms are hash-checked and reanalyzed. Full finite monotonic traces,
  actual source/physical/code/runtime bindings and the shared six-slot budget
  are enforced. Preparation and run scheduling choices do not change the
  scientific fingerprint.
- Resource-only `followup/run.py` is verified live as
  `openlvds-selected-phy-link-after-native.service`. It waits for successful
  completion of the exact compact-native receiver owner and its bound passing
  report, then runs the prepared selected link with its own slot-1 lease.
  It holds no outer lease while waiting or around the child. Failed upstream
  transport holds execution instead of spending a long full-link simulation.
- Four new tests cover phase replay and full-range margin accounting,
  unchanged raw clock events, partial/cached waveform preservation, immutable
  captured files, exact PVT selection and shared-bias/phase-evidence refusal.
  Full regression passes: 582 tests, 581 passed and one skipped. Full bit
  coverage, startup, aperture, PVT/timing/OpenPLL suite and release remain.

Explicit selected-PHY assembly and PMOS current results:

- `selected_phy.py` provides one versioned staging manifest and shared loader
  for all eight exact-RC blocks: driver core, receiver core, analog DLL,
  PFD, bias, delay line, digital TX and digital RX. It assembles the current
  DLL qualification context and audited digital candidates, then overlays
  the actual selected P64/N24 driver and compact LVT receiver. Public pin
  order and unrelated circuit closures are checked. Every block records its
  exact model metadata/hash, instantiated closure hash and physical origin.
- The loader reconstructs through the same physical validators used by
  staging and compares the selection and exact library bytes. It binds all
  physical evidence, scientific producer bytes, requirements and manifest
  identity. An approximate view is refused; no missing fast model silently
  falls back to a different circuit. Diagnostic and unqualified flags cannot
  be edited into qualification. No active extraction pointer is changed.
- Actual `selected_phy/05aad8955a1b0cf7` stages and reloads successfully.
  It uses DLL qualification `15cac0ba813a9333`, driver layout
  `57c38a7401ebd975`, receiver layout `5743800311436cdd`, TX buf_4 and the
  early digital RX. Library SHA256 is
  `f3bba6b33030850681a27c4f729ddf9fb80ac477126e6f4f0da7becfacaeeece`.
  Earlier preparation revisions preserve matching producer copies. Existing
  live link/release consumers retain their frozen producers; migrating them
  to this shared selection and qualifying/publishing its bytes remain work.
- Five tests cover both analog overlays and protected closures, pin-order
  refusal, identical staging/loading reconstruction, model-selection and
  file/evidence tampering, diagnostic flag protection and approximate-view
  refusal. Full regression: 578 tests, 577 passed and one skipped.
- The instrumented nominal PMOS run `ce9d010f1316caed` has now completed;
  cached scientific remeasurement confirms all twelve DC points still pass.
  Tail-current magnitudes at those points are 60.321–65.687 uA, and absolute
  tail drain/source voltages are 0.765–1.154 V. This is measured headroom,
  not a BSIM saturation-region classification. Among the six observed
  decision/bias devices, the retained NBC diode is the thin device; its
  largest recorded terminal difference is 0.896053 V, below the existing
  project screen. Remaining thin restoration devices are outside this screen.
- Sampled delivered power is 1.866–4.159 mW from VDDIO and approximately
  0.8304 mW from VDDD for the original complete fixture, including its
  retained monitor/bias branches and 100 fF output load. These are settled
  samples on the two rails, not total endpoint power, reference-source power
  or dynamic power. LVT current comparison and dynamic/native PMOS pulse
  recovery remain unproven; no architecture selection follows from DC alone.

LVT continuation resource correction:

- The seven-case-complete DC campaign was waiting on shared slot 4 behind
  the long SS/0 DLL frequency-step simulation. Its DC coordinator and the
  source-clock/native dependents were frozen and verified to contain no
  simulator. All processes/start records and 161 files were archived under
  `resident_jobs/lvt_chain_slot1_rescheduling`, including all prepared DC
  children, completed results and both resource followups. No unfinished
  simulation output existed for the waiting FF/40 child.
- Those three queued controllers were retired after the archive. MainPID=0,
  disappearance of every old process and unchanged hashes for every archived
  file were verified before replacement. Scientific producer bytes, the
  matrix identity, seven completed DC cases and physical candidate remain
  unchanged. Useful running DLL, link and aperture simulations were retained.
- `openlvds-lvt-pair-dc-slot1.service` resumes that same DC matrix with a
  blocking slot-1 wait. Resource-only `clock_followup_slot1/run.py` and
  `native_followup_slot1/run.py` follow the replacement owners and preserve
  all scientific admission gates. Their units are
  `openlvds-lvt-pair-clock-slot1.service` and
  `openlvds-lvt-compact-native-slot1.service`; all three are verified live.
  This corrects queued resource policy without increasing the six-slot budget.

PMOS architecture sanity and measurement instrumentation:

- The nominal TT/25 `pmos_p8_t4` source sanity check completed as
  `receiver_architecture_static/095f9e8483f806bf`: all twelve original DC
  points pass, including both input polarities near the bottom and top of
  the 0–2.4 V pin range. A fresh cached remeasurement confirms the result.
  Settled output levels are approximately 0.000000112 V and 1.8 V. This is
  a nominal DC implementation check, not dynamic or full-PVT qualification.
- `receiver_architecture_observations.py` adds ideal zero-volt meters at
  the decision tail and NBC diode drain, retaining all original transistor
  models, widths and terminal potentials. Unloaded 1-ohm transresistance
  outputs expose signed amperes as voltage vectors through the unchanged
  simulator adapter. Supply meters observe the existing VIO/VDIG branches.
  Public-node observations use their actual bench aliases, including IREF
  for the core's PB port; nonexistent hierarchical port aliases are avoided.
- Reports retain the original 144 ns waveform and twelve sample times, and
  add signed/absolute branch currents, signed rail-source current and
  delivered power per rail. They check the meter's zero-voltage constraint
  across the complete trace and measure all six terminal-pair differences
  for XCT/XC0/XC1/XCD/XCM/XNCB. The existing 1.95 V project screen applies
  only to the observed thin devices; no foundry absolute rating is asserted.
  Thick-device stress limits, other receiver devices, BSIM VDSAT/region and
  dynamic/native performance remain outside this observation's scope.
- Current-observed PMOS context `ce9d010f1316caed` is prepared from the same
  completed reduced-tail control. Its separate producer-bound source/deck
  are queued on shared slot 1 as
  `openlvds-pmos-decision-current-sanity.service`. No current or power value
  is claimed before the actual simulation and complete-waveform analysis.
  The uninstrumented architecture remains the physical-source candidate.
- The instrumented LVT baseline is prepared as `0c8f8fae13878a21` from the
  exact same nominal control and queued on slot 1 as
  `openlvds-lvt-decision-current-sanity.service`. This enables a matched
  schematic current/headroom comparison with PMOS; it neither selects the
  fallback ahead of native LVT results nor admits lower-overdrive variants.
- Five tests cover all nine variants' exact device/source preservation when
  meters are removed, fixed-rail fixture checks and actual public aliases,
  signed current/power conversion, a stress violation between DC samples,
  missing/nonzero meter refusal and restoration of scientific bindings.
  Full regression passes: 573 tests, 572 passed and one skipped.

Compact LVT native replay handoff:

- `probe_receiver_lvt_compact.py` accepts only the exact new compact-layout
  profile and unchanged LVT source. It requires all fifteen passing DC cases
  and all three passing source-clock controls, remeasured through their
  scientific producers. All completed source fixtures/waveforms, producer
  ancestry, physical source/GDS, extracted model and independent RC audit are
  bound into the new replay context. Missing source results cannot trigger
  an uncached source simulation through this admission path.
- The original captured and sharp native fixtures remain unchanged apart
  from replacing the receiver model, adding validated internal probes and
  tightening the maximum integration step to 1 ps. Both complete 80 ns traces
  are required, with the original 15–75 ns, 47-period edge test. Bias and
  digital receiver circuit closures and public port order are protected.
  Each worker takes its own actual shared lease; the six-slot limit remains.
  Partial traces are retained and refused for in-place execution. Cached
  results are remeasured from complete finite monotonic waveforms.
- Actual preflight under
  `receiver_layout/5743800311436cdd/native_followup/` rejects the incomplete
  fifteen-case DC matrix and creates zero native contexts. Resource-only
  `run.py` is verified live as
  `openlvds-lvt-compact-native-followup.service`. It waits for successful
  completion of the exact source-clock owner and hash-bound passing report,
  then prepares the native pair and waits independently on shared slots 1/3.
  A failed upstream or native result holds downstream admission for diagnosis.
- Seven new tests cover exact profile and numerical policy, missing physical,
  DC and source-clock evidence, preservation of partial traces, complete-wave
  cached remeasurement and rejection of a truncated cached waveform. Full
  regression passes: 568 tests, 567 passed and one skipped. This legacy-pin
  diagnostic remains separate from selected-driver, startup, PVT, stress,
  aperture, component, matched-link and final PHY qualification.
- The PMOS sanity check's polling coordinator was superseded with a blocking
  slot-1 wait to give it an opportunity between aperture boundary searches.
  The queued unit was frozen first; all five cgroup processes, start records,
  case files and producer bytes were archived, and absence of any simulator
  or raw/log/PRN output was verified. Only then was that coordinator retired.
  Old MainPID=0, disappearance of all old processes and unchanged case/source
  bytes were confirmed before launching the same scientific context with
  `--wait-slot 1` as `openlvds-pmos-decision-dc-sanity-blocking.service`.
  Receipts are under `resident_jobs/pmos_sanity_blocking_reschedule`.
  The deliberate old-unit termination is not an electrical test failure.

Compact LVT receiver physical experiment:

- `layout_receiver_compact.py` requires the three original passing TT/25,
  SF/40 and FS/40 DC pilots, rechecks their scientific results and captures
  their source/fixture/waveform hashes. This early geometry experiment does
  not replace full fifteen-case DC or source-clock admission.
- `receiver_compact_geometry.py` folds the frontend into four columns with
  shared M4 trunks. Summing-node mirrors and resistors, decision devices and
  restoration stages occupy one packed row with short M2 connections to M3
  buses. The device multiset, connectivity and public terminal order remain
  unchanged. The physical circuit has 70 devices and nine ports.
- Actual context `receiver_layout/5743800311436cdd` passes DRC with zero
  violations, LVS, extraction and independent wire-collapsed RC LVS audit.
  Its footprint is 295.4 by 357.2 um: this folds the critical circuitry, but
  does not claim a smaller total area than the original one-row macro.
  Extracted netlist SHA256 is
  `ec1ad5c7869bb8869231433c25fd91844780b6bd2485efca93b0492e9552c573`.
- The bound observation and its producer are saved under that context's
  `loading_observation/`. Incident routing capacitance is CO 29.116 fF,
  CL 26.606 fF, CT 28.888 fF, PP 93.301 fF and PN 105.851 fF. This includes
  full coupling capacitance and excludes device-model capacitance. It is
  not an effective AC-load measurement or a timing qualification.
- Earlier folded contexts and matching producer bytes remain preserved.
  `10b212fd921b8390` had CO 134.735 fF and PP/PN 433.771/421.081 fF;
  `9887011dc217851d` brought CO to 28.180 fF but PP/PN remained
  219.313/233.802 fF. Moving all summing-node devices into the packed row
  resolved that routing penalty. No native simulation was spent on those
  worse layouts. The final loads are close to the original reference;
  waveform tests must establish the LVT pair's actual benefit.
- Full regression passes: 561 tests, 560 passed and one skipped. New tests
  cover preserved device graphs/ports, complete clustering of PP/PN-connected
  devices and refusal before executing any source or layout producer when
  a required DC pilot is missing. The actual DC continuation currently has
  seven passing cases; FF/40 is next. The selected-driver/LVT-source link
  diagnostic is verified running, while the PMOS DC sanity check is still
  waiting for a shared slot. No new receiver or PHY qualification is claimed.



Implementation of the usable-macro plan:

- User selected the existing block-library/top-RTL boundary and factorized
  45-case release suite, and authorized archiving and retiring obsolete runs.
  Both obsolete source-only driver units were archived, stopped and confirmed
  to have MainPID=0. Receipts and byte-hashed snapshots are retained under
  `resident_jobs/approved_obsolete_retirement`; useful qualification jobs remain.
- All three LVT decision-pair static pilots now pass. The fifteen-case DC
  continuation is running; no full-matrix or LVT clock pass is claimed.
- `selected_analog_pilot.py` adds an early diagnostic combining the audited
  selected native driver with the fingered schematic LVT receiver. It preserves
  the saved stressed SS/40, 410 MHz, short-training ideal-phase fixture and all
  unrelated circuit closures. Its immutable model/fixture/runtime/code context
  is separate from release admission. Partial traces cannot be restarted in
  place, and cached results are remeasured from complete finite waveforms.
- Prepared context `analog_link_pilot/36b513f21de11d28` is queued as
  `openlvds-selected-analog-early-pilot.service` within the shared six-slot limit.
  This mixed-view short-training diagnostic cannot establish extracted receiver,
  qualified startup, full component or release performance. It enables early
  matched-circuit feedback while those final gates remain required.
- Three tests cover selected-core overlays/protected circuits, refusal before
  missing receiver evidence, and preservation of partial traces without a new
  simulator launch. Full regression: 555 tests, 554 passed and one skipped;
  targeted tests were repeated after strengthening ancestry/code bindings.


Receiver architecture fallback implemented:

- `receiver_architectures.py` defines nine bounded alternatives: the current
  LVT pair, two lower-overdrive replica-bias variants, and six 3.3 V PMOS
  decision-stage variants. Bias variants scale XNCB/XCT widths together by
  two or four, retaining their ratio; actual current is not assumed invariant.
- The architectural replacement uses a thick-oxide PMOS tail and input pair
  powered from VDDIO, with thick-oxide NMOS mirror loads. A new thick-oxide
  inverter powered from VDDD accepts the high-voltage decision signal and
  drives the unchanged two following 1.8 V restoration inverters. Public ports,
  complementary input frontend, resistor loads and shared bias remain intact.
  The unused original NBC reference branch is retained for this controlled
  experiment. Dynamic overshoot, power and terminal stress remain to be checked.
- The six PMOS variants combine pair widths 8/16 um with tail widths 2/4/8 um.
  Source generation rejects unknown variants and altered baseline devices.
  `receiver_architecture_experiment.py` retains the original twelve fixed-supply
  DC points, source reconstruction, manifest/runtime binding, complete-waveform
  checks and partial-trace preservation in a distinct diagnostic namespace.
- The nominal `pmos_p8_t4` sanity check is prepared as
  `receiver_architecture_static/095f9e8483f806bf` and queued in
  `openlvds-pmos-decision-dc-sanity.service`. It is a circuit implementation
  sanity check, not selection of the fallback ahead of the current LVT flow.
  No new clock, physical or release admission follows from this DC check.
- Tests exercise every PMOS variant, thick-device isolation at the decision
  interface, frontend/port preservation, both bias ratios and modified-source
  rejection. Full regression: 558 tests, 557 passed and one skipped. Compact
  layout and dynamic/extracted qualification remain outstanding.

Latest receiver decision on 2026-11-01:

- Active circuit experiment: change only the W8 decision input pair to the
  pinned SKY130 LVT NFET model on the smaller reduced-tail receiver. Three
  original source-DC pilots are prepared: SF/40 passes all twelve points;
  TT/25 and FS/40 remain queued. The preceding uniform-scaling captured native
  replay has completed all 80 ns with eighteen missing output edges.
- Uniform fourfold scaling of the DC-passing reduced-tail
  decision stage, retaining the input-pair/mirror/tail width ratios. TT/25
  `receiver_scaled_decision_static/de8b99d5cb7a5d5e` now passes all twelve
  original DC samples. SF/40 and FS/40 also pass all twelve points, including
  the conditions that rejected the PMOS-only variant. All three pilot
  waveforms have been remeasured, and full static matrix
  `receiver_scaled_decision_matrix/a3a34b4ac8e5f600` now passes all fifteen
  process/temperature cases (180 original samples, fixed supplies).
  Source-clock comparison `receiver_clamp/b9f840b0494a787c` has completed
  both its reduced-tail control and uniformly scaled captured-input candidate
  with zero missing edges. The sharp-clock fixture also passes: all three
  original 80 ns fixtures have exactly one output edge in each of 47 scored
  periods. The completed hash-bound `source_clock_admission.json` passes.
  New layout `receiver_layout/8a063d6919387667` passes DRC, LVS, extraction
  and its independent RC audit. Native replay `receiver_replay/90c2618d3cbb6f83`
  is prepared; the captured control is complete and the sharp control is queued.
  An immutable prefix ending at 33.4901 ns contains six missing edges among
  thirteen fully observed input periods. This is a diagnosed failure in the
  observed interval. The complete captured trace now confirms eighteen missing
  edges (nine rising/nine falling) over all 47 original scored periods.
- The PMOS-only W32 alternative is rejected: FS/40 fails two original
  low-common-mode points despite TT/25 and SF/40 passing. Its remaining
  twelve DC cases and all clock cases were correctly held. Monitor relocation
  alone also fails: the completed captured native replay still misses the
  same eighteen edges. Neither alternative is a qualified replacement.
- The completed uniform-scaling TT control comparison is bound in
  `de8b99d5cb7a5d5e/control_comparison.json`. Output decisions agree at every
  original sample, while CO shifts by up to 80.807 mV, CL by 45.084 mV and
  CT by 25.231 mV. Width ratios are preserved; exact operating voltages are
  not assumed invariant. The PP/PN static shifts are at most 34.856/17.900 µV.
  Dynamic behavior and native capacitance remain unproved.
- The full fifteen-case terminal-voltage report is
  `a3a34b4ac8e5f600/decision_headroom/fb9f945f405afaec/summary.json`.
  All five changed schematic decision devices pass the 1.95 V project screen
  over each complete original 144 ns trace. This is not a PDK absolute-rating
  claim or coverage of the remaining receiver/native devices.
- Fixed-supply TT/25 operating-point probe
  `receiver_operating_points/41735e88e064dc98` completed both original
  low/high common-mode input points. Its initial parser held on ngspice's
  unit-wrapped aliases; the simulation and original producer are retained.
  `scripts/analyze_receiver_operating_points.py` validates the unchanged
  manifest, producer, runtime, source fixtures and raw evidence, then compares
  each alias with the actual model parameter. No simulation is rerun.
  The bound result is `analysis/b9f35f4ed065a4af/summary.json` under that probe.
  Tail current is 147.650 uA at P/N=0/0.1 V and 1.390293 mA at 2.3/2.4 V.
  Tail VDS is approximately 14.726/278.641 mV versus modeled VDSAT
  219.187/219.236 mV: the low-common-mode point has limited tail headroom.
  Receiver/bias rail power is 2.797/6.799 mW, with the separate ideal reference
  source delivering 0.820/0.087 mW. These are schematic static points only,
  without native/dynamic/all-PVT power qualification. The low point agrees
  with its transient sample within 1.2 pV; the high point differs by up to
  2.075 mV. Neither exact operating-point invariance nor current scaling is assumed.
- `receiver_operating_point_matrix.py` extends that observation to all twelve
  original input points at every original process/temperature condition.
  Matrix `receiver_operating_point_matrix/584ff581fd63fca4` is prepared and
  `openlvds-receiver-operating-matrix.service` is active, initially waiting
  on shared slot 3. It preserves the six-slot budget and all fixed supplies.
  Preparation first remeasures the complete source matrix; every OP child is
  bound to its exact source case. Completed raw evidence is analyzed without
  rerunning SPICE; partial evidence is retained and refused for in-place retry.
  Only the known unit-vector parser hold can proceed to the separate strict
  model-parameter analysis. Other simulation/provenance errors remain errors.
  This is a static tail-current/headroom and rail/reference-power diagnostic,
  without native/dynamic power, remaining-device stress or PHY admission.
  Four additional tests verify completed-evidence reuse, partial-trace
  preservation, strict error handling and refusal of incomplete source
  coverage. Full regression: 536 tests, 535 passed and one skipped.
- Re-reading both completed 80 ns captured-source waveforms and verifying
  their saved SHA256 bindings confirms exactly one output edge in all 47
  scored periods. Reduced-tail control latency is 343.165/359.340/404.411 ps
  (minimum/median/maximum), versus 347.770/360.086/420.935 ps for uniform
  scaling. Their weakest captured pulse is identical: 83.068 mV peak,
  514.802 ps width at 58.919554 ns. The maximum latency occurs at this pulse.
  Thus the scaled schematic receiver has not demonstrated a speed improvement;
  the hypothesis still needs the actual extracted-RC replay. This source
  diagnostic includes a captured pulse below the 100 mV specified sensitivity
  and does not replace the component or aperture qualification fixtures.
- The operating-point matrix has completed all twelve TT/25 points. Its
  independently revalidated static tail current spans 116.828--1390.293 uA;
  rail power spans 2.727599--7.101542 mW, excluding reference-source power.
  At the six original low-common-mode points (P/N through 0.65 V), tail VDS
  is 11.572--17.422 mV against modeled VDSAT near 219.187 mV. At P/N of
  1.15/1.25 V the tail current is 869.507 uA, versus 485.507 uA with input
  polarity reversed. DC logic passes despite substantial common-mode and
  polarity dependence of current. Dynamic/native bandwidth must be measured;
  width scaling is not treated as a fourfold increase in operating current.
- The scaled receiver layout has 88 devices, nine ports, dimensions
  787.240 x 100.045 um, zero DRC violations and matching LVS. GDS SHA256 is
  `b83cd9b3c5d21f211274442698e38a42df0077015ab2ab814c3c5866aa0e49c1`;
  audited native RC SHA256 is
  `490276d995bbac6a227413ee0be363df2df1914535f40488133cfaf2f2198c66`
  (`build/extracted/c2c5346dfcdcd43d`). The reduced network retains 88 devices,
  16101 resistors and 1250 capacitors. All physical/source admission proofs
  are frozen in the new native replay context; component/link admission still
  requires both complete passing native waveforms.
- Reading both audited extracted networks with the existing
  `inspect_dll_stage_caps.routing_caps(..., with_components=True)` and proving
  one resistor-connected component per observed net gives incident routing C
  for monitor-after tail16 versus uniform scaling, in fF: CO 28.24057 to
  83.62715; CL 25.00120 to 100.19234; CT 30.01471 to 120.56284;
  PP 92.04186 to 126.15072; PN 99.08609 to 131.48089. NL/NR/PL/PR remain
  unchanged. These include coupling at every resistor-connected segment,
  without transistor/MIM capacitance or an effective AC-load interpretation.
  The increased routing loads reinforce the need for actual native replay;
  neither a drive-to-load improvement nor bandwidth gain is presumed.
- `qualify_selected_analog_link.py` prepares the next matched full-RC link
  comparison with both the selected receiver and P64/N24 driver. It first
  requires every original 30 driver and 60 receiver component case to exist
  and pass, then remeasures the cached suites and the completed receiver-only
  reference through their scientific producers. Profile/layout/replay identity
  must agree. The independent component reports, waveforms, fixtures, original
  inputs and producer code are bound in a separate immutable admission record.
  No missing component simulation can start from this cached admission path.
- It reuses the existing matched native driver engine with the selected
  receiver fixed in both alternatives. A failed receiver-only reference may
  supply the fixture, since its old driver may be limiting; both component
  suites must still pass. Candidate success requires actual decoding and
  sampling margins plus at least 100 mV at every measured TX/RX clock center
  in the original 60--120 ns diagnostic window. The control may fail without
  invalidating a passing candidate. Partial uncached traces are retained and
  refused for in-place retry. This remains one ideal-phase loaded-link
  diagnostic, without selected-DLL/digital assembly or full-PHY admission.
- Actual `a3a34b4ac8e5f600/combined_link_preflight.json` records rejection of
  the incomplete driver suite and zero new comparison contexts. Seven tests
  cover that gate, receiver identity mismatch, the admitted failed-reference
  path, independent candidate/control verdicts, decoder/sensitivity failures,
  changed admission inputs and partial-trace preservation.
  `selected_analog_followup/run.py` is active as
  `openlvds-selected-analog-link-followup.service`, waiting for the driver
  component and receiver integration owners. It calls the strict adapter
  after the owners finish and relies on actual scientific evidence, including
  a completed negative reference diagnostic, rather than process exit alone.
  Both matched workers retain the existing shared six-slot scheduler.
  Full regression: 543 tests, 542 passed and one skipped.
- Uniform scaling's first complete native weak-pulse period is archived in
  `receiver_replay/90c2618d3cbb6f83/prefix_observations/394802a9d7ba4636`.
  It retains the exact live binary prefix, vector/header metadata, completed-
  period transport measurements, source/runtime/fixture hashes and producer.
  The 24.777050 ns falling input has a 108.848 mV peak and 526.689 ps width.
  Neither it nor the following rising input produces an output crossing in
  its complete matching period. Over 24.777050--27.190836 ns, CO peaks at
  0.611366 V versus 0.753394 V in the completed monitor-after W16-tail replay.
  The preceding measured 3x CO routing-capacitance increase and input loading
  did not yield weak-pulse recovery. No live simulation was signalled, source
  changed, partial trace overwritten or full-waveform verdict fabricated.
- `receiver_lvt_pair_experiment.py` starts a separate controlled alternative
  from the independently DC-passing W16-tail receiver. Only XC0/XC1 change
  from `nfet_01v8` to `nfet_01v8_lvt`, retaining W8/L0.15, all connectivity,
  W8 PMOS loads, W16 tail, unloaded monitor, three restoration inverters and
  input-stage/bias circuits. The first restoration inverter keeps its standard
  NFET model; this differs from the previously rejected LVT-restorer change.
  The hypothesis is improved decision-pair headroom without uniform width/
  routing-load growth. Actual tail current, threshold changes, DC and dynamic
  behavior are to be measured rather than assumed.
- Original twelve-point, 144 ns, fixed-supply pilots are prepared at TT/25
  `receiver_lvt_pair_static/c9d35e9a59a88b47`, SF/40 `241f2a0de9bdb87c`, and
  FS/40 `0b4222c77cd81fe7`. The pinned PDK's TT corner includes the LVT model.
  Their source producer inherits immutable source/fixture/runtime checks,
  full finite monotonic waveform checks, exact intervention reconstruction,
  partial-trace preservation and shared simulator leases. Pilot campaign
  `receiver_lvt_pair_pilots/7710a87b8c66129f` initially queued at most two
  workers within the six-slot budget; its polling resource coordinator was
  replaced before any pilot simulation started, as recorded below. The
  campaign launches only these three pilots and records negative
  electrical results separately from incomplete or numerical failures.
  No remaining twelve DC simulations, new clock/physical/native context or PHY
  admission is allowed before the applicable gates. Three new tests prove the exact
  two-model change, retention of every other source device, rejection of
  modified controls and refusal of a missing completed control. Full
  regression: 546 tests, 545 passed and one skipped.
- Full original LVT decision-pair DC matrix
  `receiver_lvt_pair_matrix/ad5c6e2037ee5519` now has all fifteen fixture
  templates prepared. `receiver_lvt_pair_matrix.py` retains the exact five
  process corners and three temperatures, fixed supplies, twelve original
  points, control-source mapping and immutable child/producer proofs. It
  requires all three complete pilot reports, remeasures their actual traces,
  checks each manifest binding and requires all three electrical verdicts to
  pass before launching any of the remaining twelve simulations. Full-matrix
  DC admission still requires all fifteen actual passing reports.
- Actual `ad5c6e2037ee5519/incomplete_pilot_preflight.json` records refusal
  of the incomplete pilots and zero simulation launches. Three matrix tests
  cover missing pilots, negative remeasured pilots and changed report binding.
  The initial `followup/run.py` coordinator was replaced while childless by
  the current `followup_v3/run.py` scheduling context, waiting for the
  three-pilot owner and its actual bound results before invoking the
  scientific matrix gate. No outer simulator lease is retained;
  sequential full-matrix cases use the unchanged shared six-slot scheduler.
  Source clocks and all physical/native/component/link work remain gated.
  Full regression: 549 tests, 548 passed and one skipped.
- LVT scheduling now uses blocking slot-4 waits. The kernel lock table showed
  two long driver component runs occupying slots 2 and 3, with the current
  aperture boundary search on slot 4. The original LVT workers were merely
  polling for any free slot. They and their deferred DC coordinator were
  quiesced, every relevant thread was verified stopped, and childless state,
  absence of simulator descendants/pilot traces and unchanged fixture hashes
  were proved before retiring only those queued resource processes. Receipts
  are in `resident_jobs/lvt_pair_rescheduling/retirement.json` and
  `blocking_queue.json`. No live SPICE process was stopped or signalled.
- Replacement pilot resource context
  `receiver_lvt_pair_pilots/82d839adb65472fe` is active as
  `openlvds-receiver-lvt-pair-pilots-blocking.service`. Both initial workers
  are verified kernel-blocked behind the actual aperture owner on the same
  slot-4 inode. The unchanged scientific static contexts capture their new
  CLI scheduling policy separately; source/model/deck manifests remain intact.
  `openlvds-lvt-pair-dc-followup-v3.service` is also active and will use a
  blocking slot-4 wait for each remaining DC case after all three pilots pass.
  The global budget remains six and pilot concurrency remains at most two.
- Complete uniform-scaling captured observation
  `receiver_replay/90c2618d3cbb6f83/completed_captured/ec7e481cb41f32d6.json`
  remeasures the full original 80 ns trace, verifies every finite/monotonic
  row, original 15--75 ns transport interval, 47 periods, all saved internal
  node ranges and source/deck/model/runtime/producer/report bindings. It
  confirms eighteen missing edges, split nine rising/nine falling, and proves
  the archived live-prefix payload matches the finalized raw file byte for
  byte. Its retained `read.py` launches no simulator and does not assert
  completion of the queued sharp control or the full pair. Captured input
  failure prevents native admission regardless of the later sharp result.
- The completed SF/40 LVT pilot
  `receiver_lvt_pair_static/241f2a0de9bdb87c` passes all twelve original points
  and has been cached-remeasured through its scientific producer. At the six
  low-common-mode samples, tail CT voltage rises from 40.011--61.936 mV in
  the matched reduced-tail control to 101.281--139.870 mV. PP/PN and NBC remain
  nearly unchanged. At 10 ns CO changes from 1.384669 V to 1.072051 V;
  headroom improves while output swing also changes. Tail VDSAT/current,
  transient bandwidth and native weak-pulse recovery are not inferred from
  these DC voltages. TT/25 and FS/40 pilot results and all subsequent gates
  remain outstanding.
- `receiver_lvt_pair_clock.py` prepares the next source-clock gate for this
  alternative. It requires all fifteen original DC reports and a passing
  matrix summary before any source-clock preparation, then remeasures the
  complete matrix through its producer and binds every source fixture/report.
  The selected factory is the exact two-model LVT pair change; temporary
  factory/gate bindings are restored on success or exceptions. Existing
  immutable clock machinery retains the three original 80 ns fixtures,
  5 ps output, 1 ps maximum step, original 15--75 ns scoring interval and
  exactly one output edge in each of 47 periods per fixture.
- Actual `receiver_lvt_pair_matrix/ad5c6e2037ee5519/source_clock_preflight.json`
  records rejection of the incomplete full DC matrix with zero clock contexts
  created. Three new tests cover incomplete-DC refusal, correct selected
  factory and restoration of factory/code/gate state after errors.
  `clock_followup/run.py` is active as `openlvds-lvt-pair-clock-followup.service`,
  waiting for the full-DC owner and its actual hash-bound fifteen-case pass.
  It will use blocking slot-4 scheduling within the same global budget of six.
  No source-clock simulation or physical/native admission exists for the
  LVT alternative yet.
  Full regression: 552 tests, 551 passed and one skipped.


Latest DLL model observation on 2026-11-01:

- The local-delay native DLL candidate remains
  `dll_qualification/15cac0ba813a9333`, with measured-model work in
  `stability_screen/1cdf451bf81d3ee8`. SS/0 now has all three original
  forced-control delay traces and all four original native AC responses.
  The read-only, hash-bound observation is
  `model_observations/678afcfe509f5634.json`, with its exact `read.py` producer
  retained alongside it. The observation validates the current qualification,
  producer/runtime/source bindings, complete forced-control waves, remeasured
  PFD gain cases and AC evidence. It launches no simulator.
- Independently measured SS/0 delay sensitivity is -2.179142 ns/V and PFD
  gain is 8.894446e8 V/s. Both clock-state models and averaged G over averaged Y
  pass the existing model checks: unity gain 2.984056 MHz, minimum phase
  margin 67.042345 degrees and minimum gain margin 18.706185 dB. These are
  measured model observations, not the earlier trajectory-based gain estimate.
  The SS/0 control operating point is 0.984710 V; TT/25 and FF/0 control
  operating points in their prepared native fixtures are 0.861398/0.804140 V.
  Control ripple figures elsewhere in this history are separate quantities.
- Both original SS/0 390/410 MHz transient-step validations remain required;
  neither has a completed validation report. TT/25, FF/0 and full-PVT models,
  the complete native DLL suite, recovery and final PHY qualification remain
  incomplete. The preliminary observation issues no DLL/PHY admission.


Earlier bring-up evidence on 2026-11-01:

- All three source-matched SS/TT/FF fast-reset architecture loops pass
  (`dll_architecture/0ca8225b328ecaa1`). All 21 selected native static offsets
  pass. Combined native candidate `dll_qualification/1d201e9ed2f89f56` has 336
  prepared fixtures. Native SS acquisition completed and failed: CTRL varies
  34.693 mV against 20 mV; the omitted-pulse final section measures 731.772 ps
  against the 625 ± 100 ps section limit. TT/FF acquisition and downstream
  progression are held. Measured model and full native qualification remain gated.
- Captured native diagnosis `dll_loop_diagnosis/43f094030fe944fc` separates
  32.977 mV cycle-mean movement from at most 1.659 mV cycle ripple. This supports
  slow startup settling. All four native AC fixtures are complete. Both clock
  states and their averaged G/Y response estimate 271 kHz unity-gain frequency,
  93.54° phase margin and 42.44 dB gain margin (`summary.json` in the diagnostic
  directory). These use
  trajectory-inferred delay gain and do not provide an independent model or
  transient-step validation; no qualification verdict is issued.
  New passive-preset experiment `dll_architecture/9e0ebce74ac41dcd`
  changes only the startup divider to nominal 1.2 V. It retains W8/C4, the actual
  fast-reset PFD, fixed supplies and original three source-screen fixtures.
  Physical candidate `dll_layout/dfb62f717c9bdb42` passes DRC/LVS and independent
  RC extraction/connectivity audit. Its exact reduced network SHA256 starts
  `403eb354e54c2dc8`; all 15 ports are verified. The SS/0 °C source screen passes in its original 1200–1500 ns
  window: CTRL variation 2.576 mV, feedback error 10.045 ps and quarter
  delay 634.257–634.482 ps. TT/25 °C also passes: CTRL variation
  3.014 mV, feedback error 7.853 ps and quarter delay 633.198–633.558 ps.
  FF/0 °C passes: CTRL variation 3.163 mV, feedback error 6.493 ps and
  quarter delay 632.701–633.013 ps. All three source gates are complete.
- Routing-capacitance inspection (`dll_stage_loading/c26dc74a57838968`) finds
  monotonically increasing internal loads across the four native delay sections:
  N = 48.174/56.614/65.053/73.493 fF and S =
  53.309/63.334/73.359/83.383 fF. These are incident wire capacitances, including
  coupling, excluding device/MIM capacitance; they are not effective AC loads.
  The preset-only layout retains this gradient (`dll_stage_loading/33a2a3dbcde34f95`).
  New `dll_layout/9368e5712c444b03` uses five local delay islands (four sections
  plus the existing replica), preserving all 519 devices and the preset source.
  DRC/LVS and independent extraction/connectivity audit pass. Measured incident
  routing capacitances now match across all four sections: N = 34.472 fF,
  S = 36.991 fF, B = 36.310 fF and PCTRL = 106.921 fF
  (`dll_stage_loading/96132db0d653d2ff`). The preset-only waiting
  native handoff was archived and superseded without stopping any simulation.
  Exact resistor-only profile `dll_layout/schur_513f603fc5e6c3aa` further reduces
  146,526 resistors to 43,836 while preserving every device, capacitor and port.
  Four independent terminal-admittance witnesses and a fresh connectivity audit
  pass; native transient qualification remains mandatory. Its handoff
  (`queue_preset_native_screen.py`, receipt
  `dll_layout/schur_513f603fc5e6c3aa/native_handoff.json`) waits for the same source
  screens before running native screening. Native qualification
  `dll_qualification/15cac0ba813a9333` now runs its 24-case screen (21 selected
  static offsets and three native loops); remaining 312 fixtures are held for
  the measured model. All 21 selected static offsets now pass, with exact
  SS/0, TT/25 and FF/0 coverage at 0, ±50, ±150 and ±300 ps.
  SS/0 acquisition now completes and passes: CTRL variation 1.849904 mV,
  feedback error 19.010343 ps and quarter delay 668.380426–668.485247 ps.
  The omitted-pulse section check also passes (668.412/642.798/633.563/632.785 ps);
  mean power is 8.451226 mW. TT/25 acquisition also completes and passes:
  CTRL variation 1.671669 mV, feedback error 10.840051 ps and quarter delay
  659.955500–660.204682 ps. Cadence and omitted-pulse section checks pass;
  section delays are 660.037/649.233/639.480/640.926 ps and mean power is
  6.897270 mW. Its actual deck, waveform and raw hashes match the report.
  FF/0 acquisition now also completes and passes: CTRL ripple 1.781503 mV,
  feedback error 7.417610 ps and quarter delay 653.018658–653.408804 ps.
  Cadence/marker checks pass and mean power is 6.365241 mW. All 24 initial
  screen cases pass and the continuation has remeasured their cached traces,
  advancing to the three-corner measured-model/stability stage.
  No measured-model or full-native qualification result is claimed. The
  handoff holds on failed gates, ended producers or changed inputs. Native
  acquisition/recovery at remaining required conditions remains unqualified.
- The early-publication RX (`rx_early_physical_v1`) passes physical DRC/LVS,
  strict topology checks and an independent exact-RC connectivity audit. All
  12 loaded admissions pass. All four native continuous-data duty/jitter/skew
  cases pass (128 words). Its original 480-condition aperture campaign
  (`rx_aperture/20b04dcf527af283`) is running. All 32 SS/40 °C conditions pass,
  across both clock/data slew endpoints, both edge/data polarities and setup/hold.
  Its largest guarded setup/hold bounds are 270/110 ps; the 200 ps clock/data
  subset remains 210/50 ps. All 32 SS/0 °C conditions also pass, with global
  guarded bounds 280/120 ps. All 32 SS/25 °C conditions now also pass, with
  guarded bounds 270/110 ps. Exact 32-condition coverage is verified separately
  at each SS temperature. SF/0 and SF/40 now also have all 32 conditions
  verified, with guarded setup/hold bounds 260/150 and 250/140 ps. Twelve
  SF/25 cases also pass: 172 of 480 conditions are complete and passing.
  Remaining conditions are outstanding and the full table is unqualified. The preceding three
  publication variants remain timing failures and cannot qualify this RX.
- Staged early-RX bundle `phy_candidate/8f364c6a8fdabafb` passes all 54
  generic/native functional cases (2,373,588 bits). Its complete six-fixture RC
  comparison
  passes, with all 12 actual reference/approximation traces verified by
  `rc_certificate.valid` against the current simulator, source and trace policy.
  The driver fixture passes with 0.396 ps maximum edge difference
  and 0.541 mV maximum plateau difference. The completed DLL fixture also passes:
  each of four outputs has 232 matching edges, with at most 0.785 ps crossing
  difference and 0.123 mV plateau difference (`dll_rc_diagnostic.json` beside
  the bundle manifest). These proofs cover this bundle's original networks;
  new DLL/analog/TX networks require their own comparison evidence. The largest
  difference across this complete suite is 2.992 ps for edges and 4.160 mV for
  plateaus, below the unchanged 20 ps/20 mV limits.
- Current component evidence verifies all 90/90 distinct proofs: all 45 schematic
  driver/receiver cases, all 30 native analog receiver cases and all 15 native
  drivers. The final SF/40 °C native driver passes. Both refresh processes are
  terminal, and `component_refresh/current_evidence.json` verifies every current
  source/fixture/waveform/runtime/producer proof. The original refresh batch's
  historical failure remains recorded; it is not rewritten as a passing batch.
  This completes baseline component evidence. The new receiver candidate,
  DLL, full aperture and link qualifications remain required.
- The 32-bit exact-RC data-path diagnostic at SS/40 °C/410 MHz, 45% duty,
  +100 ps skew and 100 ps peak-to-peak jitter completed and failed payload
  alignment (`build/link/ss_40_410m_d0.45_s100_e0_ideal_32/6735242e52a2`).
  Read-only clock diagnosis `link_clock/b7266f117369574e` finds 25 receiver-pin
  rising crossings but only 16 digital receiver-clock rising edges in 60–120 ns.
  Digital TX low pulses reach 858.520 ps; receiver-pin low pulses reach 514.807 ps.
  Cumulative duty distortion and receiver clock pulse loss require a separate
  loaded pulse-width investigation; moving the payload decoder window cannot
  repair missing clock edges. This remains an ideal-phase diagnostic, without
  measured-DLL qualification.
- Loaded receiver replay `clock_restore/50565a94b3b04171` retains the captured
  analog receiver pins, exact native analog/data receivers, shared bias and
  early-RX digital load. The complete captured-input replay reproduces the link
  clock loss: 25 input rising crossings produce only 16 output rising edges
  during 15–75 ns. The complete sharper-edge control improves that count only
  to 18. Both fixtures retain the measured pulse widths. This reproduces pulse
  loss without the live TX/driver and supports a receiver bandwidth limitation
  in addition to TX duty distortion; it does not qualify the link.
- Receiver input-current candidate `receiver_layout/2ec2942caa46a841` changes
  only XNT/XPT widths from 12 to 24 µm in the source, retaining complementary
  inputs, signal mirrors, decision stage and all nine ports. Source invariants,
  DRC/LVS and the independent RC audit pass (native network SHA256 starts
  `45fbff442fad8e43`). Both original receiver-replay stimuli are retained for
  this actual network at `receiver_replay/f55b204c5e5256b7`, including native
  digital loading and new PP/PN/CO observations. The captured-input fixture is
  complete and still loses nine rising and nine falling output edges. The
  complete sharper-edge control loses none. In the first missing captured
  negative pulse, the input remains negative for 526.689 ps and PP−PN reverses
  for 367.259 ps, but CO reaches only 0.665 V and does not restore the output.
  More input current alone is insufficient with the actual pin waveform.
  Full input-range/PVT behavior and complete-link timing remain unproven.
- Matched `buf_8` TX experiment (`tx_buffer8_physical`) passes the full 54-case
  RTL/native functional regression (2,373,588 bits;
  `tx_buffer8/ed7e08ca1a8e22f7`), physical flow/topology and independent RC audit.
  Its native TX network SHA256 starts `d849e11e2470e9ec`. Diagnostic
  `tx_candidate_link/b1c1b53a01dc8564` replaces only TX in the saved SS/40 °C/
  410 MHz/45% duty/+100 ps skew link, preserving every clock/data stimulus,
  analog/RX/DLL circuit and scoring window. Its native simulation completes and
  fails payload alignment. In 60–120 ns,
  25 receiver-pin rising crossings produce only 13 digital clock rises, versus
  16 with buf_4. The experiment is not selected; the staged assembly retains
  buf_4 and no release is published.
- Snapshot `tx_training_compare/18e4e22fc301ba34` compares the original buf_4
  and buf_8 designs over the same 20–35 ns training interval. Maximum
  digital clock slew improves from 357.342 to 194.375 ps. The shortest negative
  receiver-pin clock pulse narrows from 556.159 to 460.960 ps, and the weakest
  negative peak decreases from 121.521 to 78.663 mV. Both designs miss six
  restored edges under the same per-input-period diagnostic. The completed TX
  payload run independently fails, as recorded above; the
  training observations themselves issue no qualification verdict.
- Receiver decision/restoration candidate `receiver_layout/784114a01817b339`
  retains doubled input tails, doubles decision-stage current/mirror/input widths,
  and reduces the CO inverter gate from P16/N8 to P4/N2. Three inverter stages
  restore the original output polarity and P16/N8 final drive. Source invariants,
  DRC/LVS and independent RC audit pass; native network SHA256 starts
  `30154843ced35188`. Captured and sharper-input native replays are active at
  `receiver_replay/cb6fffffb0809887`, with PP/PN/CO and both restoration nodes
  observed. The complete captured case loses nine rising and nine falling edges,
  unchanged from the input-tail-only candidate. The sharper control also
  completes and loses one rising and one falling edge; the diagnostic is terminal.
  Electrical improvement and PVT qualification remain unproven.
  Isolated full-link fixture `receiver_candidate_link/467b30dda15cf743` is
  prepared with only the analog receiver replaced. It retains buf_4 and the
  entire original stimulus/channel/scoring. Its run gate remeasures both
  completed replays and requires zero missing edges before allocating a slot;
  no full-link run or passing receiver result is claimed.
- Standalone `continue_native_dll.py` waits for the selected native screen owner
  to pass and exit, then rechecks its captured screening evidence. Measured
  SS/TT/FF models gate full native expansion; verified full-native evidence
  gates all 15 model corners. Failed or changed evidence holds progression,
  with no resident-dispatcher edits or release claim.
- Receiver placement experiment `receiver_layout/f2492f47d0df06ca` preserves
  the preceding decision-current source and all finger banks, changing only
  device-bank order. DRC/LVS and independent RC audit pass; exact network SHA256
  starts `b6d987db3ef27b9b`. Incident routing capacitance falls PP 109.141→66.413 fF,
  PN 115.726→62.576 fF and CO 45.447→42.437 fF; CT rises 138.108→165.735 fF.
  These exclude device/MIM capacitance and count full coupling values. Native
  replay `receiver_replay/17c5587a5df91855` completes its captured case and loses
  nine rising and nine falling edges. Its complete sharper control also loses
  seven rising and seven falling edges; the diagnostic is terminal. Both
  original stimuli and loads are retained. No recovery improvement is established. Matching isolated link
  fixture `receiver_candidate_link/98985df18860704a` is prepared and held behind
  both completed, zero-missing-edge replays. Both decision-current placements
  fail the captured-input cadence test, so neither is selected for integration.
- Schematic tracked-clamp comparison `receiver_clamp/e888b13239fc158e` is running
  under the shared simulator budget. It adds a diode-connected replica inverter
  with the first restoration stage's P/N ratio and two parallel precision-poly
  units from CO to the replica trip point. Three fixtures compare unclamped and
  clamped circuits on captured pins, then clamped sharper inputs. Analog cores
  use schematic fingers; the shared bias and native early RX load are retained.
  The complete unclamped/captured schematic control recovers every edge, with
  no missing rising or falling transition and diagnostic latencies 296–413 ps.
  Its CO reaches 1.792 V. The clamped/captured case also completes with zero
  missing edges; its latency is 309–442 ps and CO_TRACK moves 0.503–1.127 V,
  so reference stiffness and native performance remain unproven. Its sharper
  control also completes with zero missing edges; all three source comparisons
  are complete. The schematic/native
  contrast implicates extracted parasitics, but does not isolate wire capacitance
  from explicit extracted device junction geometry. No physical receiver fix
  or clamp improvement is claimed yet.
- `layout_receiver_clamp_candidate.py` and `probe_receiver_clamp_candidate.py`
  prepare the physical/native path behind complete zero-missing-edge clamped
  source replays. They remeasure actual source traces, require exact source
  agreement, preserve original device order except the four added clamp devices,
  and bind source/physical/native proofs. The real incomplete-source preflight
  rejects layout without creating an artifact. Full-link gating selects the
  clamp replay's own verifier. Layout `receiver_layout/f576c6a98d893590`
  now passes DRC/LVS and independent RC audit (85 devices, nine ports; native
  SHA256 starts `ad5ac6a6d26b0b33`). Its actual native replay
  `receiver_replay/7b46eef599fb6e55` is running. Matching full-link fixture
  `receiver_candidate_link/a3b07823d72b7aeb` is prepared behind native replay
  gates. The complete captured replay loses nine rising and nine falling edges;
  its sharper control continues. At its first lost pulse, CO reaches only
  0.789 V while CO_TRACK moves 0.508–0.823 V. No full-link run is admitted.
- Selected receiver component campaign `receiver_components/06ef0f1a751e6c5d`
  has all 60 original schematic/native static/rate PVT fixtures prepared.
  Baseline references verify, and the real run preflight reconstructs all
  fixtures before holding at incomplete loaded-native replay evidence. No new
  component simulation starts. Complete/unique coverage, unchanged stimuli/load/
  scoring and fresh waveform reanalysis are enforced. Loaded replay admission
  requires exactly one output edge per input period, rejecting extra pulses as
  well as missing ones. Baseline component proofs
  and canonical pointers are retained.
- Stronger schematic clamp `receiver_clamp/86e622030245e729` completes with
  P32/N16 reference widths and four parallel poly units (about 500 Ω). Other
  devices and restoration stages remain unchanged. All three original controls
  pass with exactly one output edge in each of 47 checked periods. CO_TRACK
  spans 0.647–0.962 V in the captured case, less movement than the first clamp;
  its diagnostic latency is 313–516 ps. Physical/native comparison is still
  required and no native improvement is claimed.
- Stronger-clamp layout `receiver_layout/feb7596968046dd1` now passes DRC/LVS
  and independent RC audit (91 devices, nine ports; native SHA256 starts
  `32579bcd62e88ff5`). It moves only the added replica/clamp devices beside CO;
  existing receiver devices and connections are retained. Actual native replay
  `receiver_replay/13ab38f8a7b8e217` runs under the unchanged six-slot budget.
  Its completed captured-input case misses 11 rising and 11 falling edges,
  worse than the original receiver's nine of each. The sharp control also
  completes and misses nine rising and nine falling edges. The native owner
  exits successfully after producing both diagnostic reports; the follow-up
  records `held_for_diagnosis` for failed clock recovery and starts no component
  or link simulations. The stronger clamp is not selected for qualification.
  Matching link fixture `receiver_candidate_link/37d95b09d5fb0059` and 60-case
  component campaign `receiver_components/90fff4b7107aa5ae` remain held behind
  its failed loaded native gate. The component preflight verified original fixtures;
  neither downstream campaign started a simulation. Stronger and
  first-clamp verifiers are selected explicitly; no native improvement is claimed.
- Host continuation `continue_receiver_candidate.py` waited on that actual native
  owner and held the prepared component/link jobs for failed one-to-one
  clock recovery. It binds all manifests/producers, repeats scientific checks
  in the children and preserves both running jobs on failure. No release is
  promoted by diagnostics. Its receipt is under the native replay's `followup/`.
  The stronger clamp's completed first-pulse observation has CO peak 0.822 V
  with RESTORE0 above 1.726 V; the output clock does not fall in that interval.
  Routing inspection of the first→stronger clamp finds PP 115.776→122.001 fF,
  PN 122.274→128.498 fF and CO 58.027→73.967 fF; other observed wire sums
  are unchanged. These incident capacitances do not isolate the electrical
  effect of strengthening the reference or establish a causal timing result.
- Wider input-pair source comparison `receiver_clamp/4e55a995d239fb38` is active.
  It changes only the four complementary input devices from 20 to 40 µm,
  retaining tail-device bias, stronger clamp and restoration. Its original
  three controls and native shared bias/digital load remain intact. The captured
  source case completes with exactly one output edge in all 47 checked periods,
  no missing/repeated edges and diagnostic latency 324.978–448.846 ps. Its
  unchanged unclamped control also passes. The sharp-input source control now
  completes; all three cases recover exactly one edge in every checked period.
  Physical/native improvement remains unproven.
  Dedicated layout/replay producers now bind the exact 40 µm input source and
  its three complete, one-to-one source controls. They reject earlier clamp
  evidence and preserve native shared bias, digital load, nine-port order and
  replay timing. Layout `receiver_layout/4cea0a2ca0f9868e` passes DRC/LVS
  (95 devices, nine ports) and the independent RC connectivity audit. Native
  network SHA256 starts `7f2680cc72bcaf63`; replay `5adb1f717c66c41e` is queued
  under the six-slot limit. Incident PP/PN wire sums are 124.217/131.377 fF;
  CO remains 73.967 fF (`receiver_loading/c66f016bc3569690`).
  Host service `openlvds-wide-input-native-continuation-v2` runs those
  physical/RC/native gates in sequence. It freezes
  source and parent manifests plus downstream producers; failed gates hold the
  pipeline. It stops before component/link qualification and release selection.
  Its first invocation stopped after systemd unloaded the successful transient
  source unit. The corrected predicate requires complete reports and repeats
  the exact waveform gate; the original failure receipt is archived under
  `native_continuation_history_516799b`. No scientific simulation was restarted.
  After the previous native owner/follow-up terminated, the downstream dispatcher
  gained explicit `strong_wide_input` source and native-verifier selection.
  Future component/link fixtures retain original stimuli and scoring; their
  native replay gate still requires complete, one-to-one clock recovery.
  Component root `receiver_components/f82998633770e370` prepares all 60 original
  fixtures, and link root `receiver_candidate_link/a1fe429613422650` retains the
  original loaded link diagnostic. Host service `openlvds-wide-input-receiver-followup`
  waits on the native continuation and starts them only after both native cases
  recover every edge exactly once. No component/link simulation has started.
  The live native trace already fails the first short pulse: over 24.5–26.5 ns,
  CO peaks at 0.810757 V, RESTORE0 remains above 1.744 V and the output clock
  has no falling crossing in 24–27 ns. Both original 80 ns controls continue
  to completion; these partial observations are not a qualification verdict.
  The captured native case now completes with nine missing rising and nine
  missing falling edges. This improves on the preceding strong-clamp count of
  11 each, but matches baseline pulse loss and does not pass the native recovery
  gate. The sharp control now also completes with nine missing rising and nine
  missing falling edges. Native continuation and component/link follow-up both
  record `held_for_diagnosis`. Neither downstream campaign starts a simulation.
  The wider-input candidate is not selected for qualification.
- New source comparison `receiver_clamp/af769bd4767fe6c2` restores the five
  decision-stage devices to original widths (tail 64 µm, differential pair
  and mirror devices 8 µm). It retains doubled input tails, original 20 µm
  input pairs, stronger clamp and three restoration stages. Earlier native
  traces show a larger first-pulse PP−PN excursion before the decision-stage
  doubling; reducing its input/device/routing load is a hypothesis, not a
  demonstrated improvement. Three structural tests pass. The original source
  campaign is active under the same six-slot budget; no physical result or
  release selection is claimed.
  Dedicated `layout_receiver_light_decision_candidate.py` and
  `probe_receiver_light_decision_candidate.py` bind `decision_scale=1` and the
  exact original-decision source. Physical preparation requires all three source
  cases complete with exactly one edge per input period; native preparation
  requires DRC/LVS, independent RC audit, matching source and all captured proofs.
  Host service `openlvds-light-decision-native-continuation` waits on its actual
  source owner and runs those stages in sequence. It reuses the corrected
  transient-unit handling and stops on any failed gate. Seven source/physical
  structural tests pass; no physical/native result is claimed.
  Its captured source case now completes with one missing rising edge and one
  missing falling edge around the 58.920 ns negative pulse (514.802 ps,
  83.068 mV peak). CO peaks at 0.948352 V over 58.7–60.7 ns, but the restored
  clock remains above 1.702 V. The source gate therefore cannot admit layout;
  its sharp control now also completes, with no missing edges. All three source
  cases are complete, but the captured failure remains. Native continuation
  records `held_for_diagnosis` after the physical source gate rejects lost
  clock edges. No physical artifact, RC extraction or native replay is produced
  for this candidate.
- Source comparison `receiver_clamp/7002b1f71a4ff337` removes only XCLAMP2/3,
  reducing parallel clamp units from four to two while retaining the original
  decision sizes, doubled input tails, strong replica reference and restoration.
  This tests reduced output loading after the smaller-decision source failure.
  Two structural tests pass. Service `openlvds-light-clamp-source-screen` is live
  and has completed its unchanged source control with no missing edges. Its
  modified captured source case now completes with exactly one output edge in
  all 47 checked periods and diagnostic latency 301.890–510.435 ps. The sharp
  source control now also passes; all three controls have exactly one edge per
  checked period. No native improvement is claimed;
  all original controls and scoring requirements remain.
  Dedicated reduced-clamp physical/native producers use identity
  `light_decision_1k_clamp`, original decision scale and two parallel clamp units.
  They reject source evidence from the four-unit candidate and preserve original
  pin stimuli, bias, digital RX load and scoring windows. Host service
  `openlvds-light-clamp-native-continuation-v2` waited on its actual source owner,
  then runs layout, independent RC audit and both native controls only after
  all source gates pass. The downstream dispatcher selects its exact source
  factory and native verifier. Physical root `receiver_layout/4e540d457ca789a4`
  passes DRC/LVS (77 devices, nine ports) and independent RC audit. Native network
  SHA256 starts `b8e821dc164ef55a`; replay `5c2e6e425ac65e58` now runs captured
  and sharp controls concurrently, each with its own lease from the six-slot
  pool. Incident PP/PN/CO wire sums are 102.831/109.899/44.786 fF
  (`receiver_loading/2b2f0d4e931336c9`); CL/CT sums are 25.001/70.874 fF.
  These routing sums do not establish effective AC load or native timing.
  The prior waiting continuation was retired before the concurrency change;
  its receipt is archived as `native_continuation_history_d6f80e5`. No live SPICE
  process was stopped. Tests verify independent fixture starts, separate leases,
  deterministic report order and completion of the other fixture after one fails.
  All 60 component fixtures (`receiver_components/57488d46b26d09ec`) and the
  original loaded link diagnostic (`receiver_candidate_link/cb4be133271a71ea`)
  are prepared. Service `openlvds-light-clamp-receiver-followup` waits for complete
  one-to-one native recovery before running them; no downstream result is claimed.
  Component preflight reconstructs all 60 fixtures and correctly holds at the
  incomplete native gate, with zero execution receipts or raw traces. Its
  `gate_preflight.json` binds the manifest, verifier and simulator provenance.
  The live captured native trace still fails the first short pulse: over
  24.5–26.5 ns CO peaks at 0.859699 V and RESTORE0 remains above 1.667761 V;
  there is no output falling crossing in 24–27 ns. CO_TRACK spans
  0.738464–0.836576 V in that interval. Both complete original controls continue;
  no partial trace supplies a qualification verdict.
  Both native controls now finish: captured misses 10 rising and 10 falling
  edges; sharp misses nine of each. Cached waveform reanalysis confirms both
  reports. Native continuation and downstream follow-up record
  `held_for_diagnosis`; neither the prepared component nor link campaign starts
  a simulation. The reduced-clamp candidate is not selected for qualification.
- New source comparison `receiver_clamp/0244d3fb608b9d06` connects the two CO
  resistors to the existing 1.2 V VREF port instead of CO_TRACK. The replica is
  retained unloaded as an observation node; every device size and all other
  connections are unchanged. This tests a fixed reference against movement of
  the loaded replica, using the existing fixture reference and fixed supplies.
  Two structural tests pass. Service `openlvds-vref-clamp-source-screen` has
  completed all three source controls with exactly one edge in each of their
  47 checked periods. The modified
  captured case recovers exactly one output edge in all 47 checked periods,
  with latency 260.642–508.359 ps. CO spans 0.387500–1.533384 V, while the
  unloaded replica remains near 0.832621 V. No native improvement is claimed. Reference
  loading and full input-range/PVT behavior still require qualification if selected.
  Dedicated VREF-biased physical/native producers bind the exact resistor
  reference and unloaded-monitor topology. They reject earlier tracked-reference
  source evidence, retain original replay stimuli/bias/digital RX load, and run
  both native controls concurrently within the shared six-slot pool. Downstream
  dispatch selects this variant's exact source factory and waveform verifier.
  Host service `openlvds-vref-clamp-native-continuation` rechecked the completed
  source controls, then built `receiver_layout/c9b54df2758e600a`. It passes
  DRC/LVS (77 devices, nine ports) and independent RC connectivity audit.
  Native network SHA256 starts `36e80ac228591149`; both original controls now
  run concurrently at `receiver_replay/77252e9aa3abb333`. Incident PP/PN/CO wire
  sums are 102.831/109.899/42.695 fF (`receiver_loading/3b41530840a8d2e7`), not
  effective AC loads or timing qualification.
  All 60 component fixtures (`receiver_components/a09b869f2ffff52b`) and the
  loaded link diagnostic (`receiver_candidate_link/3635f229cd4efe04`) are prepared.
  Their preflight reconstructs every component fixture, then holds at the
  incomplete native gate with no simulation started (`gate_preflight.json`).
  Service `openlvds-vref-clamp-receiver-followup` waits for complete one-to-one
  native recovery before running them. No native/component/link pass is claimed.
  The live native captured trace restores the first previously lost short pulse:
  over 24.5–26.5 ns CO reaches 1.152635 V, RESTORE0 falls to 0.329422 V,
  RESTORE1 rises to 1.780347 V and RXCLOCK falls near 25.837800 ns. The trace
  prefix reaches 28.772 ns at inspection. Both complete native controls continue;
  this partial observation does not qualify clock recovery or link timing.
  A later prefix through 62.890 ns shows failure on the weakest negative pulse
  at 58.920 ns: CO reaches 1.060980 V and RESTORE0 falls to 0.718403 V,
  but RESTORE1 reaches only 0.551259 V. No RXCLOCK falling crossing occurs
  before the next same-polarity input edge at 61.213 ns. Complete reports remain
  outstanding; the next comparison targets the internal restoration stages.
  Both native controls now complete. Captured inputs miss one rising and one
  falling edge; the sharp control misses none. Cached waveform reanalysis
  verifies both reports. Native continuation and downstream follow-up hold for
  failed captured recovery; neither component nor link simulation starts.
  This VREF-biased candidate is not selected for qualification.
- Source comparison `receiver_clamp/d2827cbf76f9eb80` retains VREF bias and all
  input/decision devices, but doubles the first two restoration stages using
  existing inverter definitions: P/N widths become 8/4 → 16/8 → 16/8 µm.
  Final output drive and overall polarity are retained. Two structural tests
  verify only those instance bindings change and the control remains identical.
  All three original source controls now complete: each recovers all 47 checked
  periods with no missing or repeated edges. Captured-source latency is
  237.406–494.897 ps, versus 260.642–508.359 ps before stage strengthening;
  the weakest negative pulse improves from 276.441 to 249.913 ps. These source
  results do not prove extracted improvement.
  Dedicated physical/native producers bind identity `vref_fast_restore` and
  widths [[8,4],[16,8],[16,8]], rejecting the previous restoration topology or
  source evidence. They retain VREF bias, unloaded monitor, all nine ports,
  original stimuli/bias/native RX load and scoring windows. Both native controls
  use separate shared simulator leases. Exact downstream source/verifier
  selection and parallel completion/error behavior are tested. Service
  `openlvds-fast-restore-native-continuation` waits on the actual source owner,
  then requires all three source controls, physical DRC/LVS and independent RC
  audit before native replay. Physical root `receiver_layout/64ae7a93d207703b`
  passes DRC (zero errors), LVS and independent RC audit, with 78 devices and
  the original nine ports. Native network SHA256 is
  `b6e0bec697e9ef60f8677d77e1817d9c0e70cd26ab45445ee57ead09a36a4d69`.
  Both original native controls complete in `receiver_replay/93c5ecd2ff603292`:
  each recovers all 47 checked periods with zero missing or repeated edges.
  The weakest captured pulse now produces RXCLOCK falling/rising crossings at
  59.977506/60.493634 ns; RESTORE0 reaches 0.456733 V and RESTORE1 1.770205 V.
  Captured latency spans 804.040–1244.370 ps. This passes the replay diagnostic,
  not component coverage, aperture or full-link qualification.
  Loading receipt `receiver_loading/820ed53b4961c8bb` reports incident CO,
  RESTORE0 and RESTORE1 wire sums 44.360, 47.681 and 58.947 fF. These exclude
  device capacitance and do not establish effective AC load or timing.
- `queue_receiver_followup.py` now waits for that complete native continuation,
  requires both original replay controls to recover every checked edge, then
  prepares the 60 schematic/native component cases and the saved loaded-link
  diagnostic. The existing follow-up independently remeasures native evidence
  before acquiring simulator slots. Service
  `openlvds-fast-restore-component-link-queue` is waiting; its frozen code,
  requirements, upstream manifest and original link receipts are under
  `receiver_clamp/d2827cbf76f9eb80/component_link_continuation/`. Six targeted
  tests cover active/incomplete/failed owners, selection, edge loss/repetition,
  path confinement and the prepare/run handoff. These diagnostics cannot
  qualify the PHY.
  Container `/work/OpenLVDS` output paths are translated to the host workspace
  before validating their artifact kind and confinement. The waiting queue was
  retired before this producer fix, with its original receipt preserved in
  `component_link_continuation_history_6438c51`; it had no scientific child.
  Container inputs use repository-relative paths because `--containall` exposes
  this repository only at `/work/OpenLVDS`. The handoff test checks both path
  directions. The second waiting receipt is retained in
  `component_link_continuation_history_bafce31`, also without a scientific child.
  Replacement service `openlvds-fast-restore-component-link-queue-v3` retains
  the same native gate, stimuli, component coverage and simulator budget.
  Actual container preparation produces component root
  `receiver_components/58bb3aa28d907d28` and loaded-link root
  `receiver_candidate_link/0dee72b71f4525df`. Component preflight reconstructs
  all 60 fixtures and holds before any simulation while native reports are
  incomplete. After both native reports pass, the queue automatically starts
  component/link diagnostics; both independently recheck native waveforms.
  The first three source static cases (TT at 0/25/40°C) fail. At TT/25, expected
  high outputs fail at common modes 0.05/0.2/0.6 V, while 1.2/1.8/2.35 V pass.
  Actual PP/PN differential polarity remains correct, but CO stays at
  1.140763/1.137516/1.127988 V in the failed samples and Q remains low. The
  original source fixture passes these samples with CO at
  0.492830/0.480999/0.451381 V. This identifies a DC decision/clamp interaction
  to isolate; the comparison also changes input-tail sizing and cannot assign
  causality to the clamp alone. The campaign continues without changing gates.
- Matched diagnosis `receiver_static_diagnosis/a6dc85becd2ad09c` now isolates
  that DC cause: it removes only XCLAMP0/XCLAMP1 from the completed TT/25
  source fixture and leaves every transistor, helper, supply, load, input and
  sampling time unchanged. All 12 static samples pass, versus three failed
  expected-high samples in the original. At common modes 0.05/0.2/0.6 V,
  CO falls to 0.560407/0.538582/0.490294 V and Q reaches 1.8 V. The new runner
  remeasures the original control, captures parent/current proofs, reconstructs
  the exact intervention and uses a shared simulator lease. This is TT/25
  source DC evidence only, without native timing or full PVT qualification.
- Source root `receiver_clamp/2c86c40885f97e87` tests that same unclamped core
  with the stronger 8/4 → 16/8 → 16/8 restoration chain. Service
  `openlvds-unclamped-restore-source-screen` queues the original three 80 ns
  source controls with unchanged scoring. Legacy `clamped_*` task names here
  denote the modified cases; the new factory removes both actual CO clamps.
  The unloaded replica monitor remains untouched. One structural test proves
  the modified core equals the passing matched DC intervention and preserves
  the existing control. No physical/native improvement is claimed.
  Dedicated physical/native producers now bind identity
  `unclamped_fast_restore`, `decision_clamped=false`, zero clamp units and no
  clamp reference. They retain the exact source, unloaded monitor, nine-port
  order, restoration widths and original native bias/digital load. Layout
  requires all three complete source traces with one edge per checked period,
  followed by DRC/LVS and an independent RC audit. Six source/physical identity
  tests pass; parallel replay tests cover both completion and one-child
  failure, including truthful unclamped result metadata. Service
  `openlvds-unclamped-restore-native-continuation` waits on the actual source
  owner before attempting these stages. No new layout or native result exists
  while the source screen remains incomplete.
  All three source controls now complete all 47 checked periods with no
  missing or repeated edge. Modified
  captured latency spans 291.168–403.633 ps; the weakest 514.802 ps/83.068 mV
  negative pulse is recovered with 403.633 ps latency. Physical root
  `receiver_layout/cc8468627923265c` passes zero-error DRC, LVS and independent
  RC audit, with 76 devices and the original nine ports. Native network SHA256
  is `5479cc708d5f7c06815b5286b5a632e386d981bfda62057c8bdd4cd08b28352d`.
  Both original controls are running in `receiver_replay/7be8ec522902db81`
  under separate shared leases. Loading root `receiver_loading/11bbf00548f00ecc`
  reports incident CO wire sum 35.917 fF versus 44.360 fF with the clamp;
  these sums exclude device capacitance and do not prove effective AC load
  or timing. Both native controls now complete: captured input loses nine
  rising and nine falling edges; the sharp control loses none. Cached trace
  reanalysis reproduces both reports. Native continuation and follow-up hold
  for failed recovery. No component/link simulation starts for this variant.
  A captured native prefix reaches 27.380 ns and misses the first short pulse:
  over 24.5–26.5 ns CO peaks at 0.676372 V, RESTORE0 stays above 1.783624 V,
  RESTORE1 stays below 0.000316 V and Q stays above 1.799909 V. No output
  falling crossing occurs in that interval. This identifies the first
  restoration threshold as the local failure point. Both complete native
  controls continue; no downstream component/link simulation is admitted.
- The current VREF-clamped component campaign has a numerical slowdown in
  `schematic_receiver_rate_ss_40`. Its simulator is confirmed active and using
  CPU, but a saved prefix advances only about 7 ps over several minutes near
  25.84 ns. Its last 10,000 saved samples span 1.244 ps, with timesteps
  1.29e−17–4.13e−16 s, fixed input pins 1.075/1.325 V and Q within
  1.799942–1.799946 V. This establishes timestep collapse, without identifying
  its internal cause or a qualification verdict. No solver tolerance, stop
  time or scoring gate is changed, and the live simulation is not interrupted.
  This case subsequently recovers and completes successfully after 2678.057 s,
  with original valid-high/low dwell minima 825.637/1504.218 ps. All 15 source
  rate cases now pass; all 15 source static cases fail. The remaining native
  component campaign continues. The numerical slowdown was finite and did not
  require a solver change or restart.
- Matched DC matrix `receiver_static_matrix/1ac68453f143818d` now prepares the
  clamp-removal intervention at all 15 required source PVT points. Every
  original static case is complete; preparation verifies each waveform,
  producer, runtime and fixture before removing only the two resistors.
  `receiver_static_matrix.py` enforces exact process/temperature coverage and
  child-to-parent identity, captures every child manifest and remeasures cached
  traces. Service `openlvds-receiver-unclamped-static-matrix-v2` runs cases
  sequentially, with each new simulation acquiring its own shared lease.
  Two targeted tests reject missing/duplicate/mislabeled cases and native/rate
  substitutions. This is source DC diagnosis only; it cannot establish rate,
  extracted, aperture or PHY qualification. No aggregate electrical result is
  claimed while the matrix is incomplete.
- The earlier matrix `dc93e971d02bb60c` completes TT/0 with all 12 unclamped
  samples passing, then holds on cached TT/25 provenance. Its re-preparation
  rewrote JSON dictionary order, changing manifest bytes; actual waveform
  reanalysis differs only in `manifest_sha256`. It is terminally failed, with
  `retirement.json` and original producers preserved. The corrected producer
  sorts code identities and preserves existing manifest bytes, rejecting
  changed content or JSON types. Matrix failures now save a terminal held
  receipt. Seven targeted tests pass; a second independent preparation process
  preserves all 16 fresh manifest hashes (`preparation_recheck.json`). The new
  matrix reruns the cases under its new producer rather than accepting the
  old cache. The old traces and reports remain unchanged.
- Loaded-link diagnostic `receiver_candidate_link/0dee72b71f4525df` completes
  its original 188.049 ns run and fails: no correctly ordered payload preamble,
  with `sampling_margin_passed=false`. Waveform SHA256 is
  `71970afeaaaed89b0a4e86b0efe9e46c2741b5bfb06fd943da6d7dfe577cbea6`.
  The earlier read-only prefix at
  137.628 ns covers the payload interval, but the unchanged decoder reports
  no correctly ordered preamble. Over 60–120 ns, matched edge transport finds
  no missing/extra edges in 47 clock and 16 data periods. Clock latency spans
  804.843–1247.376 ps; data latency spans 761.984–1432.602 ps. Observed clock
  captures at 73.893010 and 83.627458 ns lie only 13.934 ps before the next
  data edge and 63.827 ps after the preceding data edge respectively. These
  narrow separations can explain corruption after edge recovery, but without
  a decoded preamble the official aligned payload margins remain undefined.
  The original publication window and 200 ps margin gate remain.
- `qualify_unclamped_receiver.py` selects the exact unclamped source/verifier
  in the existing component and loaded-link checks without editing captured
  producers. Its identity requires no clamps, the unloaded monitor and exact
  restoration/input/decision sizing; both scientific identities capture the
  new selector code. Component root `receiver_components/599036f3ae6f5004`
  prepares all 60 original fixtures. Actual preflight reconstructs all 60 and
  holds at incomplete native replay, with no execution receipt or raw trace;
  `gate_preflight.json` captures this check. Link root
  `receiver_candidate_link/83066baeca7824fe` retains the original loaded inputs,
  payload, publication window and margin gate. Service
  `openlvds-unclamped-restore-receiver-followup` waits on both complete passing
  native controls, then lets each child independently remeasure that evidence
  before simulation. No component/link pass is claimed. Two targeted selector
  tests verify exact dispatch, captured code and restoration after a failure.
  This separate entry point now also supports `unclamped_lvt_restore`, selecting
  its exact LVT factory and native verifier and requiring the declared first
  NFET model. Mixed standard/LVT metadata is rejected. Three selector tests
  pass. Before this extension, the failed standard-device follow-up was
  verified terminal and all live manifests were checked not to capture this
  entry point. No active experiment's producer changed, and no LVT component
  or link campaign is prepared before its physical/native gates complete.
- `receiver_lvt_restore_experiment.py` proposes a controlled first-stage
  threshold change: clone the existing P8/N4 helper and change only its NFET
  model to `sky130_fd_pr__nfet_01v8_lvt`. All sizes, nodes, other helper
  definitions, unclamped input/decision circuitry, monitor and later stages
  remain. The pinned PDK contains all corner models and Magic PCell procedures
  for this device. Three structural tests prove the single device-model change,
  unchanged control and exact static/source intervention identity. Static root
  `receiver_lvt_static/6dd7065538873479`, service
  `openlvds-receiver-lvt-static-screen`, queues the original TT/25 static
  fixture with unchanged supplies, common modes, 100 fF load and thresholds.
  The original clamped fixture is its recorded control; the unclamped standard
  NFET result is available separately in the matched DC matrix. This LVT
  TT/25 screen now completes all 12 static samples successfully. Source root
  `receiver_clamp/4ea0f56c1098842a`, service
  `openlvds-lvt-restore-source-screen`, queues the three original clock source
  controls. All three source controls now pass, each with exactly one output
  transition in all 47 checked periods and no missing/extra edges.
  Its unchanged control and modified captured-clock case now complete with
  one output edge in all 47 checked periods and no missing/extra edges.
  Modified latency spans 292.325–377.720 ps; the weakest negative pulse has
  377.720 ps latency. The sharp control also passes. This source result does not establish native recovery.
  Dedicated LVT physical/native producers now require that exact passing
  TT/25 static screen plus all three complete passing clock source controls.
  The static gate remeasures actual cached waveforms and binds the exact
  receiver closure, preserving every original DC sample. Identity records
  `unclamped_lvt_restore` and the explicit first NFET model, rejecting standard
  NFET evidence, any CO clamp, wrong sizes and missing/failed static samples.
  Nine targeted gate tests and parallel completion/error tests pass; the real
  completed TT/25 screen also passes this gate. Service
  `openlvds-lvt-restore-native-continuation` waits on the live source owner
  before layout, DRC/LVS, independent RC audit and native replay. Physical
  root `receiver_layout/6642a01b473f6aa8` now passes DRC (zero violations), LVS
  and independent RC connectivity audit: 76 devices, nine ports. The exact
  reduced network hash starts `82caea7129b27b35`. Loading root
  `receiver_loading/3872354b6c62bd80` measures PP/PN/CO incident wire loads
  100.38129/107.54226/35.91650 fF, essentially unchanged from the standard-NFET
  unclamped candidate. This excludes device/MIM loading and is not a timing proof.
  Native replay `receiver_replay/eea365798223235d` runs both original 80 ns
  controls. Its captured trace has already failed the first short-pulse window
  (24.5–26.5 ns): CO peaks at 0.673319 V, RESTORE0 stays above 1.765710 V,
  and Q has no falling 0.9 V crossing. The captured run has since completed all 80 ns: nine rising and nine falling
  input periods lack their output transition. Sharp control also completes all 80 ns with no missing transition.
  Cached reanalysis repeats both reports. The captured failure holds both
  native continuation and the downstream component/link follower; all 60
  prepared LVT component fixtures still have zero executions/raw traces.
  Exact LVT follow-up roots `receiver_components/101d54670c0ac820` (60 fixtures)
  and `receiver_candidate_link/004b4f282fcea4fc` are prepared. Actual component
  preflight stops at the incomplete-native gate with zero simulation executions
  or raw traces. Service `openlvds-lvt-restore-receiver-followup` waits for the
  original two complete passing native controls; no downstream result is claimed.
- Completed clamped-link waveforms expose an upstream clock-eye limit as well
  as receiver sensitivity. In 60–120 ns, three of 49 RX clock pulse centers
  fall below the original 100 mV threshold; minimum is 85.216 mV at
  104.178171 ns. The TX-side differential is already small before the channel:
  four of 50 centers in 58.8–118.8 ns are below 100 mV, minimum 76.417 mV.
  This is interval-specific eye evidence; TX center counts use the RX threshold
  only as a diagnostic, not a replacement for driver qualification.
  `probe_driver_internal.py` prepares root `driver_internal/c9c5ccd60b8fbe69`
  with identical native library, circuit, stimulus and 188.049 ns run. Only
  unloaded voltage probes are added at AD/AB, L/R and DP/DN named buses for
  both driver instances. Scope validation passes; two targeted tests prove
  exact deck instrumentation and reject missing/ambiguous nodes. Service
  `openlvds-native-driver-internal-observation` is queued. No stage delay cause
  or driver improvement is claimed before its measured trace is available.
  A read-only 20–35 ns prefix now shows AD/AB simultaneously below 0.9 V for
  172.825–173.229 ps and above 0.9 V for 150.429–152.213 ps per interval.
  At the 1.65 V observation level, DN high widths span 123.759–734.732 ps,
  versus DP 1310.171–1488.294 ps; DN peaks at 2.837657 V. These are measured
  crossing widths, not the actual inverter switching thresholds or a claim
  about which transistors conduct. External TXCLOCK/CP/CN/RCP/RCN traces match
  the original on a 5001-point training grid with zero interpolated difference.
- Source driver comparison `driver_restore/cff36fa92d24e01b` tests original
  P48/N40 restoration against P64/N24, retaining 88 µm total gate width per
  inverter. Private helpers change only the two 3.3 V restoration buffers in
  the driver level converter. The matched control and candidate both use
  schematic drivers in the same saved native link; unrelated circuits,
  supplies, stimulus, load, payload, publication window and full 188.049 ns
  transient remain. Three structural/fixture tests pass; actual preparation
  verifies protected closures and probe/node names. Service
  `openlvds-driver-restore-source-comparison` runs both independent cases
  through the shared slot budget. It is source-only evidence, without native
  driver or PHY qualification; no improvement is claimed before both finish.
- Xyce 7.10.0 parses the actual native receiver replay successfully in a
  parser-only check (`xyce_compatibility/ba10c72ce84ed18a`). It reports BSIM4
  4.5→4.6.1 substitution. Inspected upstream commit `e5b7b9bb5b221630` retains
  that fallback. No speed or numerical-equivalence result is claimed, and no
  running qualification campaign changes runtime.
- Last full unit suite: 417 tests, 416 passed and one skipped in the pinned ngspice
  environment. The shared native budget
  remains six real simultaneous simulator leases. Captured active producers,
  fixed supplies, PVT coverage, voltage windows and timing margins are unchanged.
- Full DLL/PVT/model/recovery/readiness/operating-point evidence, all 480 RX
  boundaries, certificates for any replacement networks and the full link matrix remain
  required. No PHY release has been published.

Earlier entries below preserve the bring-up history; their running-state and
coverage statements describe the snapshot at the time, not the current status.

The pulse-area comparison milestone on 2026-10-29 is described at the end of
this document and in [the experiment workflow](dll-experiments.md). Its circuits
remain separate from the active PHY. Subsequent bring-up evidence is recorded below.

The preceding canonical checks on 2026-10-28 include:

- RTL: 2,373,576 bits across 54 cases: 1,186,788 each for generic RTL and native
  SKY130 serializer cells, plus DLL control and generic/native PHY assembly.
- Schematic characterization previously passed all 60 cases. The revised receiver
  passes 15 static and 15 rate canonical cases at tt/ff/ss/fs/sf and 0, 25, and
  40 °C.
- Extracted driver: all 15 corners pass, including edge identity, polarity,
  amplitude, common mode, and propagation measurements.
- The compact receiver passes all 15 full-RC static and 15 full-RC rate corners. The rate test uses 840 Mb/s,
  250 mV differential input, and 100 fF output load.
- Physical checks: all five analog macros and three digital macros pass
  DRC/LVS. The integrated phase-qualifier DLL and PFD pass fresh physical
  checks and exact RC extraction. All five analog networks pass independent
  RC connectivity audits. Electrical qualification of the new DLL is pending.
- The completed steering-only DLL baseline passes its 1500 ns exact-RC nominal
  test at tt, 25 °C, 400 MHz, and 50% duty. The integrated phase-qualifier
  revision is now undergoing its own nominal test.
- Unit tests: 72 pass, including stale-evidence rejection, parallel input timing,
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

The phase-selected mux completes its 32-bit diagnostic payload with zero errors,
349 ps setup margin, 476 ps hold margin, and passing electrical levels. The
transient is still running through its final idle interval. The separate
100 mV averaged phase-detector prototype passes all 70 extreme-PVT/slew cases.
The reusable `lvds_phase_qualifier` analog subcircuit now implements its matched
clock-input filters, error averaging, matched-unit reference, and comparator.
It is not yet connected into the canonical DLL; integrated PVT and extracted
qualification remain required.

The stronger pump/buffer prototype passes all 15 schematic PVT cases, but its
600 ns patched-extraction diagnostic fails feedback error: 110 ps for the
8-times pump and 117 ps for the 16-times pump. Correctly measured control-copy
errors are 17 and 33 mV, respectively. The original diagnostic producer used
the BAD column for its copy-error field; the retained waveform headers and
independent `copy_audit.json` files identify and correct that analysis error.
Neither candidate is qualified. The 420 MHz, 55% duty delayed-enable retry
finishes successfully, with 37 ps feedback error and 14 mV copy error.

The first DLL repair now uses 32 reference units per pump branch, complementary
steering gates, the 8-times follower with 2 pF output storage, and matched native
buf_8 PFD output drivers. The physical policy retains direct reference clocks
and explicitly verifies both drivers and buffered reset coincidence. The phase
qualifier component is preserved for the next integration step. This source
revision still requires its own physical and extracted qualification.

The averaged qualifier is now connected in the canonical DLL and native PFD.
The analog macro has 22 terminals and the PFD has 12; the public DLL core and
PHY ports are unchanged. Sense inputs remain independently drivable in the
phase-fault bench. The reference inverter now has 16/8 µm drive, and PH270/FB
carry matched passive sensing loads. The physical policy verifies each native
qualifier cell and connection, including the two-buffer window, independently
of the UP/DN steering paths. Full RTL regression passes 2,373,576 bits in 54
cases, and all 72 unit tests pass. The regenerated analog DLL passes DRC
(zero errors), LVS, exact RC extraction with the expected 22 ports, and an
independent RC connectivity audit. The native PFD also passes DRC/LVS and
its explicit cell-path policy, and its 12-terminal exact RC extraction assembles
with the DLL by terminal name. Complete extracted nominal, PVT, phase-fault,
clock-duty, RC-comparison, and link release evidence remains outstanding.
Earlier prototype results do not qualify this integrated source.

The integrated DLL has 329 devices, zero DRC errors, and exact RC network hash
`00bdf5fce102`; the PFD exact network hash is `2dce4c008a2d`. The fresh
0.1 ps TICER models remain unqualified until comparison with these exact
networks completes. The release checker accepts the current physical and RTL
evidence and rejects missing phase-fault, DLL, and complete link qualification.
A queued nominal test preserves the preceding steering-only baseline and starts
the integrated full-RC test only after that baseline completes successfully.

The completed stressed 32-bit TICER approximate-RC diagnostic at 420 MHz, 45% duty, +100 ps data
skew, and 100 ps peak-to-peak jitter has zero bit errors but fails the current
margin and dynamic transmitter-level checks: setup margin −47 ps and minimum
loaded data/clock eye-center amplitudes 179/225 mV. Receiver sample amplitude
remains above 100 mV. These are diagnostics with ideal DLL phases and shortened
training, not a release result. The captured-waveform driver replay remains
in progress; output-level and aperture requirements have not been relaxed.

The full/fast DLL fixture now includes the same 40 fF PH0 and PH90 launch
loads as the nominal electrical bench and delays enable by 200 ps after
precharge. The previous 20 fF PH90 fixture is not sufficient for the current
six-fixture certificate. All 72 unit tests pass in the pinned ngspice image.

Both hierarchical-schematic driver replays terminate before payload: the dense
replay fails at an ideal-source branch near 10.25 ns, and its bounded-waveform
retry fails at a MOS body node near 10.73 ns. They cannot establish a driver
bandwidth result. The replacement routing-isolation circuit keeps all 266
extracted device instances, removes only parasitic R/C, and passes an independent
LVS audit. Its full 110 ns replay completes with 32 checked bits and zero
word errors, but only 37 ps setup margin and 438 ps hold margin. Data eye-center
swing improves to 228 mV; clock ringing creates extra zero crossings and still
fails the loaded transmitter-eye check. Receiver decision voltage remains at
least 167 mV. This routing-only change fails the existing 200 ps margin and
250 mV transmitter requirements. A separate exact-RC driver replay is running
with the original approximate receiver/capture models. These mixed-model and
routing-isolation runs remain diagnostic and unqualified. The complete replay
analysis is retained in
`build/diagnostics/driver_stress_replay/routing_removed_driver/complete_analysis.json`.

An isolated source-terminated driver experiment is prepared in
`analog/experiments/source_terminated_driver.spice`. It doubles the output
mirrors and switches using parallel copies of the original devices, preserves
the input stage and 35 µA external reference, and adds a nominal 100 Ω source
shunt made from 22 PDK resistor units. The test circuit retains extracted
finger geometry and diffusion parameters; its LVS comparison against the
experimental schematic passes. A controlled transient is queued only if the
exact-driver replay confirms a swing failure with a complete, correctly decoded
payload and valid common mode. The PHY continues to instantiate the existing
driver. This experiment has no electrical or GDS qualification yet.

The steering-only repair completes its full 1500 ns exact-RC nominal transient.
Scoring 117 cycles in the settled window gives 43.53 ps maximum feedback error,
29.35 mV maximum control-copy error, and 687.43–687.70 ps quarter-cycle delay.
These meet the unchanged 100 ps feedback, 50 mV copy, and 625 ± 100 ps phase
limits. The run uses fixed 3.3/1.8 V supplies, a 1.2 V reference, a 35 µA sink,
and the pinned native ngspice engine at tt/25 °C. An independent audit verifies
file hashes, the completed waveform, engine and conditions, and recomputes all
settled metrics.

This is the preceding 16-terminal analog DLL / 9-terminal PFD circuit, with
exact network hashes `7cb9f30e214c` and `d2b3f284fdde`. Its archived evidence is
under `build/diagnostics/phase_integration/steering_baseline/`. Scope validation
accepts that evidence for its own circuit and rejects it for the integrated
22/12-terminal revision. The latter's fresh full-RC nominal transient has
started. Its complete nominal result, PVT/clock matrices, and phase-fault
reports remain required for release.

The current integrated 22/12-terminal DLL completes its full 1500 ns exact-RC
nominal test at tt/25 °C: feedback error 28.34 ps, control-copy error 29.92 mV,
quarter-cycle delay 666.73–666.96 ps, and maximum settled PHASE_BAD 0.624 mV.
All nominal gates pass. The same current extraction also passes tt/0 °C;
tt/40 °C is running in the sequential, fail-fast PVT queue. These are two of
the required 15 PVT cases. Extracted standalone phase-fault testing has started
in the second simulation slot; the full 105/70 fault matrices remain required.

The completed exact-driver replay reproduces the stressed swing failure with
zero errors over 32 bits: minimum data/clock eye-center amplitudes 179/224 mV
and setup margin −47.58 ps. The source-terminated, routing-free extracted-device
experiment also completes 32 bits with zero errors and passes electrical levels:
minimum data/clock amplitudes 281/259 mV and receiver decision voltage 247 mV.
Its setup margin is only 11.61 ps against the unchanged 200 ps target; hold
margin is 499.09 ps. It is not promoted to the PHY. Timing diagnosis and fresh
physical/PVT qualification are still needed; electrical success in this
mixed-model diagnostic cannot establish release.


## Pulse-area DLL comparison

The active PHY still uses the preceding DLL; the new circuits are isolated
experiments. The corrected, immutable architecture campaign is
`build/diagnostics/dll_architecture/6d99d42cf3eb5d31/`. The preceding campaign
`2c89de68294cda33` was stopped because its loop fixture duplicated the bias
generator already present in the DLL wrapper. No loop result from that fixture
is accepted. All prepared cases now check for exactly one reference generator.
The unchanged monitor waveforms were hash-checked and reanalyzed in the corrected
campaign; the affected loop and follower cases run afresh.

The monitor averages UP and DN independently, applies a signed window, and
checks for inactive/stuck PFD outputs. All 21 offset and six stuck-output
diagnostics pass at SS/0 °C, TT/25 °C and FF/0 °C with the captured PFD and
schematic monitor. This includes quiet 0/±50 ps and asserted ±150/±300 ps cases.
These results do not qualify a fresh extracted monitor.

Three NMOS-follower pump repairs and four averaged-PFD/current-mirror-OTA loops
are prepared. Completed loaded replay peaks are 48.72 mV for `cp_b1_c4` and
43.47 mV for `cp_b2_c2`, against the unchanged 50 mV limit. The comparison
supervisor prioritizes `cp_b2_c2` at SS/0 °C alongside the three `ota_w4_c8`
corners. Startup-only traces interrupted to make this comparison earlier are
archived within their task directories. On 2026-10-30 the user authorized two
additional concurrent simulations. The comparison now runs six transients,
adding `ota_w8_c8` at SS/0 °C and TT/25 °C while preserving the original four.

All 15 fixed-supply OTA characterization cases complete. Transconductance is
39.35–48.69 µS with the correct control direction; the largest equivalent input
offset is 14.51 mV over the characterized signal range. These cases fail the
prototype's 10 mV offset screen. They do not establish loop failure or passing
phase accuracy: complete acquisition, phase, ripple and stability checks remain
necessary. The largest measured thin-oxide signal-node magnitude is 1.4 V;
this limited signal check is not a general device-stress qualification.

The eight-terminal PFD, `ota_w4_c8` and `cp_b2_c4` analog layouts pass DRC,
strict LVS, exact RC extraction, and independent RC topology audits. Their
analog interface has 15 ports. Clock paths, pump controls and averaging inputs
remain within the control island; the window/reference bank occupies the quiet
island. Exact analog network hashes are `3502faf1b5c1` and `62713ea94c5a`;
the new PFD network is `11fa96b45bbb`. The assembled full-RC OTA circuit also
passes an operating-point-only parser/solver check. No transient qualification
is implied by that check.

The matched native `buf_4` serializer experiment passes 54 functional cases
(2,373,588 checked bits), DRC/LVS, positive timing slack, direct-output cell
policy, exact RC extraction and its independent audit. The initial routed retry
that inserted extra output buffers is preserved and rejected. The passing
direct-output network is `cdf6cbd8a901`; it is not promoted to the active PHY.

Native DLL qualification is prepared for both physical candidates, with 313
transients per candidate and prerequisites on its three-corner architecture
screen. It covers 15 PVT points, nine clock/duty conditions, the 105/70 phase
fault matrices, frequency endpoints, stuck outputs, frequency steps and clock
loss/rearm. Full/fast DLL comparisons include nominal and phase-fault fixtures.
An omitted pulse after the settled scoring window checks unwrapped delay
through every section. CTRL and VCOPY measurements bind actual storage-capacitor
terminals, whose names survive extraction and RC reduction. Every voltage
probe is checked before a case is queued. These DLL comparisons do not replace
the complete six-fixture RC certificate.

Full-RC receiver aperture characterization is queued behind the same simulator
lease. It has 480 setup/hold boundaries across 15 PVT points, both capture edges,
both data polarities and all 20/200 ps clock/data slew combinations. It observes
the published pair and valid output, bisects to 5 ps, adds 20 ps guard and rounds
up to 10 ps. Link release evidence now requires a complete current table and
rechecks its boundary witnesses. The extra 200 ps link margin is unchanged.
Legacy 200/80 ps aperture estimates are permitted only for diagnostic runs.

The completed architecture comparison selects W8/C4 for continued OTA work:
SS/0 °C, TT/25 °C and FF/0 °C pass the schematic loop screen. Its new layout
passes DRC, strict LVS, exact RC extraction and the independent RC topology audit.
The exact network is `0f0c41cbc75c`; its 15 analog ports are verified. Native
qualification `d4d687cf4e0b5e1e` passes the initial SS/0 °C 0/+50 ps monitor
cases but fails SS/0 °C ±150/±300 ps and TT/25 °C ±150 ps. The old coordinator
has finished draining submitted cases and is retired; no old-campaign worker remains.
Its 336-case manifest holds the full matrix until the 24-case native screen and
measured stability gates pass. The active release remains unchanged.

The controller now requires 615 acquisition cycles after a phase fault, alongside
the existing 32-cycle precharge and 64-good-cycle counters. The complete RTL
regression passes 54 cases and 2,373,588 checked bits. The candidate qualifier
now covers 27 clock/duty points across TT/25 °C, SS/0 °C and FF/0 °C and
frequency-step/rearm cases at each of those three corners.

The stability runner measures native G/Y with the clock held low and high,
PFD pulse-area gain at ±50 ps, and delay sensitivity at CTRL ±10 mV. It tests
the two clock states and their averaged model with one-cycle latency, then
compares predicted amplitude and settling against native 400→390/410 MHz
steps. Expansion requires at least 60° phase margin and 6 dB gain margin and
at most 25% model disagreement. The AC backend and schematic OTA
instrumentation smoke tests pass; extracted W8/C4 stability results are pending.

An isolated bundle assembler captures the audited DLL/PFD and buf_4 serializer
with the current driver, receiver and bias. It checks public TX terminals and
proves that DLL/TX replacement leaves the other instantiated circuit closures
unchanged. A smoke assembly with the previously extracted W4/C8 circuit passes;
this is tool validation, not W8/C4 qualification. The automatic workflow stages
W8/C4 only after its native electrical and all-PVT stability gates pass.

The staged bundle now connects to the six-fixture RC validator, the stressed
32-bit diagnostic and the full 45-case regression. Its certificate and matrix
summary stay within the bundle directory. The OpenPLL mean duty is captured
as a native TT DLL qualification input; the link phase reader checks the matching
native trace instead of consulting active-circuit characterization. The automatic
workflow waits for a complete RX table before the non-diagnostic link matrix.
These tools have not yet produced passing W8/C4 bundle results.

W8 OTA signal characterization `c1c03f8e7a5e8dd9` is queued for two shared
simulator slots. It covers all 15 PVT points, input common modes 0.32–0.75 V
(including FF's observed 0.34 V), and CTRL 0.82–1.09 V, with unchanged fixed
supplies and bias. It is a schematic diagnostic; it does not replace extracted
loop qualification or general device-stress verification.

Native limiting-corner recovery and readiness replay runners are implemented
and connected before staged PHY validation. Recovery includes the lowest phase
margin, lowest gain margin and slowest modeled settling corners. Readiness uses
the actual controller RTL and native all-PVT step waveforms; added 4700 ns loss
fixtures allow lock both before and after a 2200–2300 ns clock interruption.
The backend passes actual RTL tests for settled lock, BAD-fault requalification,
late clock-loss/rearm and rejection of unsafe native phase with a quiet BAD flag.
Production W8/C4 recovery/readiness evidence remains pending.

A further exact RC profile is captured in `dll_layout/schur_00f7e3a63d66eb41`.
Degree-8 algebraic elimination reduces 95,814 resistor-graph nodes and 280,285
resistors to 10,484 nodes and 36,372 resistors. Protected nodes include every
capacitor/device terminal and public port. The new network `fae3e67dab9c` passes
an independent topology audit and four complete-graph sparse numerical witnesses
at all 7,431 protected resistor terminals. Maximum current difference is
1.137e-12 A; relative solve residuals are below 2.84e-16. Capacitor, device and
port statements are unchanged.

Native equivalence benchmark `rc_equivalence/ebcffa26f586eebf` passes both
SS/0 °C 0/+50 ps comparisons. Maximum crossing/plateau differences are
0.858 ps/0.232 mV; native execution is 3.75–3.76× faster, excluding slot wait.
The profile is eligible for fresh native qualification. These two quiet-offset
comparisons do not qualify the electrical matrix or correct monitor failures.

The native SS/0 °C +150 ps BAD output remains low through 160 ns. At +300 ps,
BAD returns high only at 147.6 ns (+300 ps) and 137.5 ns (−300 ps),
too late for the unchanged 120–160 ns fault
window. The filtered UP−DN difference remains approximately 89/161 mV,
respectively. SS/0 °C −150 ps and TT/25 °C +150 ps also miss the fault.
Exact-name extracted capacitance sums incident on PA/PB are 530/561 fF;
comparator XPOS O/OB have 223/221 fF. These are network capacitance sums,
including coupling. Slow readout under these loads is a hypothesis, not yet a
confirmed cause; distributed resistance, device junctions and bias remain
possible contributors.

Monitor diagnostic `monitor_repair/9a9a9300e6682a18` uses two shared
slots. The loaded-baseline SS/0 °C +150 ps control reproduces the missed
fault (filtered error 89.51 mV, BAD below 4.5 µV). The repaired loaded +150 ps
case passes: BAD returns high at 88.271 ns and stays near 1.8 V throughout
120–160 ns; comparator O averages 1.127 V versus 0.643 V in the control.
Remaining controls and repaired offsets are pending. Its repaired source divides monitor resistor lengths by four, replicates
the two averaging capacitors four times and increases comparator branch widths
fourfold. Nominal divider ratios and averaging R×C are preserved. Explicit
unloaded/loaded baseline controls test the capacitive-loading hypothesis, then
all seven offsets run at SS/0 °C, TT/25 °C and FF/0 °C. The proxy retains native
extracted PFD/bias, but omits analog distributed resistance and device junction
geometry; it cannot replace fresh layout and native qualification. The held
unchanged-profile campaign `4f6072867e73460a` and advancement service remain
inactive while this failure is diagnosed. RX characterization continues.

A source-specific three-corner screen producer now accepts the exact repaired
source, captures native-finger schematic analog/delay devices with extracted
PFD/bias, and binds its fixtures, source and producer hashes. Its prepared screen
`dll_architecture/d8b9a06ef038cd76` is queued on one shared simulator slot. The repaired layout
`dll_layout/88342cdbe6c80ac2` passes DRC (zero errors), strict LVS, exact RC
extraction and the independent topology audit. It has 518 devices and 15
verified public ports. Further exact degree-8 reduction
`schur_e4b240c20b314964` retains 53,508 resistors and 14,631 resistor-graph
nodes, with four passing sparse witnesses at 10,035 protected terminals
(maximum current difference 3.91e-13 A). The new native qualification
`0cc06862af2fae63` has completed its early SS/0 °C +150 ps probe and fails:
BAD never reasserts through 160 ns. The first loaded +150 ps proxy passes;
the difference requires further native diagnosis before full dispatch. Advancement accepts an explicit
matching screen; it cannot reuse the old architecture evidence for new source
bytes. A hold survives restarting the same candidate; selecting a new candidate
clears only the previous OTA hold/stage, preserving the RX and CP settings.

`ota_operating_points.py` implements correlated operating-point characterization
from native loop and all-PVT step traces. Each observed UF/DF common mode and
CTRL point receives ±20 mV/±10 mV guards, with finite-difference gain at zero
and actual differential input, offset and thin-device terminal checks. It keeps
corner/condition correlations instead of combining unrelated extremes. This
production gate has not run and requires passing native/model evidence first.

The current host test run completes 214 tests: 209 pass and five skip for the
container/analysis backends checked separately in earlier runs. Native W8/C4
qualification, the complete RX aperture table, operating-point characterization,
readiness replay, limiting-corner recovery, six-fixture RC certification and the
full 45-case link regression remain outstanding. No candidate is released.


The staged release checker now accepts a bundle plus all-PVT model, recovery,
readiness and correlated OTA reports. It reconstructs the audited DLL and PHY
libraries, rechecks all native DLL cases and full/fast waveform comparisons,
then checks the unchanged analog/RTL/OpenPLL evidence and the full link matrix.
Source reuse is limited by circuit closure; obsolete CP/copy and raw-clock
qualifier gates are replaced by native OTA/PFD-area/readiness evidence for this
path. All 336 current native fixtures reconstruct exactly under the pinned
container. A missing-bundle negative control fails with a saved isolated report;
there is no positive production release result. Advancement runs this gate after
the matrix. Exact-byte promotion tooling is implemented below; electrical
qualification and a passing production release remain required.


Candidate RTL assembly now uses the matching 15-port analog macro and 8-port
PFD while preserving the external DLL/TX/RX interfaces and 615-cycle controller.
Bundle `65f795152adf2bfb` passes its isolated full 54-case regression with
2,373,588 checked bits, controller, generic/native PHY tests and physical-interface
elaboration. Its source/probe wiring agrees with the characterized SPICE core.
The canonical development wrapper remains unchanged. Staging now keeps the
exact shared bias in both views before applying the protected-circuit checks.
The six-fixture certificate and electrical qualification remain pending.


Local release promotion is now implemented. It repeats the staged checker,
seals exact full/fast library bytes, the eight GDS/LEF macro pairs, the matching
candidate schematic/RTL sources and evidence summaries, then atomically publishes
`build/release/current.json`. The prior pointer is retained on gate or copy
failure. Unit tests cover stale/failed input, mandatory reanalysis, byte copying,
immutable-package rejection and LEF pin mismatches; all eight real macro LEF
interfaces match the corresponding extraction port sets. No production package
or current release pointer has been published. The workflow invokes promotion
only after candidate RTL, native electrical/model/recovery/readiness/OTA gates,
six-fixture RC certification and all 45 link cases pass.


A further exact degree-12 performance candidate, `schur_5dc0fd57ddac9cbc`,
passes topology audit and four numerical witnesses. It reduces the repaired
resistor graph to 11,826 nodes and 51,305 resistors, versus 14,631/53,508 for
degree eight. Every capacitor/device/port statement is preserved. Maximum
witness current difference is 4.41e-13 A. Source matching and unchanged unrelated
DLL definitions are checked against physical reference qualification
`e4b01eb8a59d0c93`. Native equivalence and runtime comparisons remain required
before selecting this profile; the active and prepared qualification selections
have not changed.


The repaired physical monitor has larger incident external capacitance sums than
its proxy baseline: PA/PB are 664.7/699.2 fF (previously 530.2/560.7 fF), and
positive-comparator O is 396.3 fF (previously 222.7 fF). These sums include
coupling and are not independent grounded loads. An early native SS/0 °C
+150 ps static monitor probe under qualification `0cc06862af2fae63` has failed.
It uses the unchanged full-RC fixture and the same six-slot lease, with no claim
of campaign or PHY qualification. The source-specific SS loop remains running;
all architecture/model/full-matrix requirements still apply.


Architecture provenance is independently rechecked before registering a native
campaign and during release verification. The screened candidate source must
match the audited physical source byte for byte, and source-specific screen
producer files must match both current files and their captured archive hashes.
The original and repaired campaign bindings pass these checks. Fault-injection
unit tests reject changed screened sources, producer files and archived copies.
Running simulation producers were not modified.


The unloaded SS/0 °C +150 ps control passes with BAD reasserting at 28.794 ns;
the matched loaded control fails, and the repaired loaded control passes at
88.271 ns. Filtered differences are 90.03, 89.51 and 85.86 mV respectively.
This controlled triplet strengthens the loading diagnosis. At +300 ps the
unloaded/loaded controls assert at 22.119/121.023 ns and both pass reference-cycle
scoring, while the native old layout asserts at 147.595 ns and fails. The proxy
therefore does not reproduce the full native delay; its original negative-control
expectation remains recorded as a mismatch. No limits or expectations were edited
in response to these results.

The original qualification coordinator is confirmed retired after its final
TT/25 °C −150 ps case failed (no BAD reassertion, filtered difference −93.17 mV).
The repaired native SS/0 °C +150 ps probe completed on the actual exact-RC
network and failed. A between-transient priority handoff held only the slot-free proxy
coordinator for about 0.15 seconds, then resumed it after the probe acquired its
slot; no SPICE process was signalled. The native failure remains recorded with the original limits; remaining proxy
conditions are pending.


The repaired native SS/0 °C +150 ps trace has BAD below 7.66 µV throughout
120–160 ns and no rising edge after startup. UF−DF averages 85.287 mV, close
to the passing loaded proxy's 85.863 mV. CTRL averages 0.752208 V. These
measurements do not establish whether the remaining failure is settling time or
DC gain/headroom. `diagnose_native_monitor.py` prepares source-bound internal-node
transients and a separate DC diagnostic using the same native devices and R/C,
with UF, DF and CTRL clamped to this trace's measured means. The DC task completes with BAD at 1.80 V and comparator O at 1.457 V,
supporting a settling problem at this measured fault operating point. An
internal-node transient is queued on the existing slot pool. Neither diagnostic can qualify the PHY, and
extended traces retain the original 120–160 ns phase result. Full dispatch and
promotion of this failed candidate remain held.


A circuit-preserving local comparator layout, `dll_layout/0a4253d72e392de9`,
now passes zero-error DRC and strict LVS with 518 devices and 15 public ports.
`layout_dll_candidate.py --local-comparators` puts the passive network, each
of the four comparators and the output logic in separate child islands.
Comparator O/OB/L/T nodes remain local. The candidate schematic and control
island bytes match layout `88342cdbe6c80ac2`; extracted capacitance, the RC
audit and native electrical response remain to be checked.


The first local layout's RC extraction/audit passes. Exact degree-8 profile
`schur_7d612d8097709e6d` passes four independent witnesses at 9,935 protected
terminals (maximum current difference 1.14e-12 A); qualification
`a101ed246a85e135` is prepared but has not been dispatched. Incident positive
O capacitance falls from 396.255 to 93.272 fF and OB from 199.656 to 41.225 fF.
However PA/PB increase to 706.290/832.032 fF and LAD1 to 1281.820 fF, because
its child signal ports extend across the passive bank. These are external
network capacitance sums including coupling. This layout is retained as a
diagnostic, not selected for full native dispatch.

The revised local-port variant `dll_layout/b0aa9ac2faf0887f` reuses the DLL's
local signal-port escapes within each child. It passes zero-error DRC and
strict LVS with the same source and control-island bytes. Its extraction,
audit and immutable native preparation are running. The failed original
physical monitor's internal transient is also running with added probes.


The revised local-port layout now passes extraction and the independent RC audit.
Its incident O/OB/L/T capacitances are 50.792/25.048/49.620/75.144 fF;
PA/PB are 491.374/527.494 fF, NA/NB 405.852/455.232 fF and S 418.688 fF.
LAD1/LAD12 are 313.825/333.271 fF, slightly higher than the preceding layout's
279.620/313.360 fF. The source-bound comparison is retained under
`b0aa9ac2faf0887f/monitor_capacitance_comparison.json`. Exact degree-8 profile
`schur_6ce2c5e21bf17f36` and native qualification `c47b7dc98d92327b` are prepared.
Its unchanged SS/0 °C +150 ps fixture is queued as an early diagnostic; full
dispatch remains held.

The repaired source-specific SS/0 °C loop screen `d8b9a06ef038cd76` has now
completed and fails. In 1200–1500 ns CTRL averages 1.783719 V, feedback error
reaches 845.001 ps, quarter delays span 223.578–223.622 ps and BAD is high.
Cadence and CTRL ripple (1.509 mV) pass, which does not establish phase lock.
UF/DF means are 0.760554/0.601174 V. Local monitor routing alone cannot establish
passing acquisition for this source. The earlier passing screen used a different
captured PFD and an extracted standalone delay line; the newer screen uses the
8-port PFD and native-finger schematic delay. Those changes must be separated
from the monitor R/C repair before attributing the acquisition failure. The next
loop investigation should check detector area polarity over the startup phase
range and compare reset-path timing/precharge, while preserving these failed
traces and all original limits. TT/FF screen work and RX characterization remain
under their original coordinators.


The original failed monitor's internal transient has completed with phase metrics
identical to the original test. It confirms a positive 11.292 mV comparator
input difference but O averaging only 0.640525 V, with normal PC/local VDDD
and quiet LOW/HIGH flags. The local-port variant's early native +150 ps probe
is now running. Detector capture controls `pfd_capture/b65a8cceadd819c0` are
prepared and waiting for a slot: exact-RC native output-reset PFD, matched PDK
schematic output-reset PFD and schematic internal-Q-reset PFD at −850/+850/0 ps.
No physical PFD change or passing acquisition result is claimed.


The local-port layout's native SS/0 °C +150 ps probe passes under the original
120–160 ns scoring window. BAD falls after startup at 26.275 ns and reasserts
at 54.619 ns, remaining at about 1.8 V throughout scoring. UF−DF averages
85.641 mV, close to the failed preceding layout's 85.287 mV. Native waveform
`da0b12b5e298762284281cc41440625e6a77638fbff604a0e4f5eb421ff7e285`
and its unchanged fixture are retained under `c47b7dc98d92327b/phase_ss_0_150ps`.
Conditional native quiet 0 ps and −150 ps follow-ups are queued and stop on
failure. Full qualification remains held by acquisition and remaining gates.

The separate exact-RC PFD −850 ps input control reproduces the wrong pulse-area
sign: UP/DN average 0.894585/0.633516 V in 60–80 ns, giving +261.069 mV.
Both input clocks have eight rising edges in that interval, while UP has five
and DN six; the longest complete UP high spans 2.858485 ns, exceeding the
2.5 ns reference period. The native schematic analog load and PFD/bias library
is identical to the failing source-specific loop library. This isolates a
wide-range PFD capture problem from feedback acquisition dynamics. The matched
schematic output-reset and internal-Q-reset controls remain in progress.


An isolated internal-Q-reset PFD implementation now passes physical checks under
its separate strict topology policy. Magic and KLayout report zero DRC errors;
LVS reports zero device, net, property and pin errors. Source/archive fingerprint
is `4806b668e84e4f0d173affb62cea988375034d0f6330206882d6734cfb9dcf9f`.
The previous policy's rejection is retained, and the summary explicitly records
`pulse-area-q-reset`. Actual RC extraction/audit are running. The preceding PFD
source, policy, active manifests and frozen producers remain unchanged.

At −850 ps the matched schematic output-reset and Q-reset controls both give
correct negative area (−617.441/−612.378 mV); they do not reproduce the native
+261.069 mV error. The new physical variant therefore needs native proof before
selection. No passing acquisition result is inferred from these controls.


The physical Q-reset PFD's RC extraction and independent connectivity audit
now pass. GDS SHA-256 is
`bb3a28c1372cd12ba24160dc91341b51b056aad6da37595e028f4d0f8416e3dd`
and extracted netlist SHA-256 is
`810a134361f82d9051ca1524bbc44ef14e25c22f64a3e44be88317fe77a9f8e6`.
`probe_pfd_physical_candidate.py` verifies source/producer archives, actual
post-route connectivity, GDS/netlist/audit hashes and matched reference fixtures
before preparing native −850/+850/0 ps capture probes. The probe coordinator is
active, waiting for the shared simulation slots. No physical capture or
closed-loop pass is claimed yet.


The local-port native SS/0 °C quiet 0 ps follow-up passes: BAD remains below
0.713 nV in 120–160 ns, with UF−DF = −1.595 mV. Its native waveform is
`d9081dfbd79416c63fd16120a83d020a8e4cd976e2a6e5ef2763af8eade0a26f`.
The −150 ps follow-up is running.

The physical internal-Q-reset variant fails the −850 ps capture control:
UP−DN = +260.742 mV, close to the preceding native PFD's +261.069 mV.
The passing schematic controls therefore did not predict a working physical
repair. This candidate remains unselected, with +850/0 ps controls continuing.
A distinct single-AOI reset experiment replaces the two-gate coincidence/clear
chain with `a22oi_4`, using a high-tied fourth input to implement
`clear_b = !(raw_up & raw_dn | disallow)`. A separate `nand2_1` derives disallow
from RESET_N/PD_ENABLE outside the Q-to-reset critical path. The new structural
policy checks this exact wiring, high ties, direct clocks and buffered outputs.
Its first build stopped at lint on a reserved instance name and is preserved;
corrected `pfd_fast_reset_physical_v2` is undergoing physical implementation.
No native success or acquisition result is claimed for it.


The local-port −150 ps native follow-up passes, with BAD reasserting at
59.249457 ns and remaining high throughout 120–160 ns. Its waveform SHA-256 is
`dd8757242626a9339c04be5d757b7b69106ec870d27d30bc2ec801710ff3d0ab`.
All three initial SS/0 °C static probes (0, +150, −150 ps) pass; this is not
full static/PVT or closed-loop qualification.

The single-AOI reset physical build passes zero-error Magic/KLayout DRC, zero
LVS device/net/property errors and its explicit structural policy. RC extraction
and the independent connectivity audit also pass. GDS SHA-256 is
`5051c9d97f0f8330f60a36dd07a69aaa3a0e3b0eec115e6b2edb09cfd78e22b5`
and extracted netlist SHA-256 is
`0806d75fcec1e4648580d6bec6370362efe1815a592585287b1cab785b8b2fc5`.
Matched native capture root `pfd_physical_capture/6562211b6d43fb89` is prepared
and its coordinator is waiting for a slot. Selection still requires actual
capture, quiet/activity, near-zero phase response and acquisition evidence.


The single-AOI physical PFD passes its −850 ps native capture-direction check:
UP/DN average 0.380123/1.016338 V, giving −636.215 mV instead of the preceding
PFD's incorrect +261.069 mV. UF/DF average 0.341069/0.861005 V. Its waveform
SHA-256 is `1303e4bda86a02e4731b0017b622f1a16149771601a370b73629f67ac3db8a97`.
The +850 and 0 ps controls remain pending; this is not a closed-loop result.

`screen_fast_reset_dll.py` prepares source-matched SS/0 °C, TT/25 °C and
FF/0 °C loops using the actual single-AOI PFD extraction, the same native-finger
schematic analog/delay devices and exact bias. Proposed source changes only
the PFD definition; all other circuit definitions remain unchanged. It reuses
the captured architecture stimuli, startup and loads, with the original
1200–1500 ns scoring window and 1500 ns stop. Input, source, extraction and
producer archives are validated. Native capture reports are checked against
their waveforms before admission, and missing or wrong-sign large-offset
controls hold dispatch. The 0 ps area-balance diagnostic is retained; integrated
quiet behavior remains subject to the unchanged loop/phase gates.

Prepared screen `dll_architecture/0ca8225b328ecaa1` validates its actual inputs
and is held for the remaining capture controls. Its conditional coordinator is
active and will run all three loops only after admission succeeds. No new
architecture-screen result or native/full-PHY qualification is claimed.


All three single-AOI physical PFD capture controls now pass: raw UP−DN is
−636.215 mV at −850 ps, +640.506 mV at +850 ps and +1.800 mV at 0 ps.
The +850/0 ps waveform hashes are
`7c0d35c2bde4ec93cc70ebd6d234b3b9e66d5fb7422d00da693177f526bbc386`
and `64d1b57258e825b73a05a7986958525e8200206f5c26817b547b334e210b9294`.
The three-corner source screen passes admission and is running; FF/0 °C is
active while SS/TT wait for slots. No settled-loop result is available yet.

Audited analog source binding `dll_layout/pfd_bind_1583499260541bb4` associates
proposed source `fc18ef4ca882d3bc38e8216a9b9b2ef16055ee74b9f73691a0af6fc49599334c`
with the existing analog GDS. The tool proves that only the unrelated PFD
definition changed; the flattened analog scope remains
`371e858737298457a8a17215ca8b2e8e279918ad7c240193b21dd4b7cae8eb91`.
GDS `d5fb7db80c22210b8521fd5442fe40d77e401eb56d429baab4b9f6acd189e23d`
and exact network `1113fdcdc6f8a5af7037155c9e2fbb42a7ca267b640145d5fcd3b8521f2a2573`
are unchanged, and a fresh strict RC audit passes. No electrical qualification
is inherited by this source binding.

The obsolete monitor-proxy and original capture-control coordinators were retired
while holding no SPICE lease and having no active SPICE descendants. Their
18/5 completed per-case summaries and all traces are preserved with retirement
receipts. The old source's current TT loop continues unchanged; a watcher will
retire only its remaining queued FF case after TT completes. Current-source
loop tests and the frozen RX campaign continue.


Staged release topology checking now selects the explicitly declared PFD policy.
The preceding buffered-reset and single-AOI designs retain distinct strict
checks; missing, unknown or internal-Q-only policy labels cannot qualify. Both
actual post-route netlists pass their corresponding structural checks. Saved
release reports bind the policy selector, fast-reset checker and base physical
checker hashes, and promotion/current-release inspection reject changed helpers.
A missing-candidate negative control still fails and writes its isolated report
(561 checks); no release package or passing production report is produced.
Native qualification assembly support will be integrated after the remaining
old-source simulation drains, preserving its producer snapshot.


Native DLL assembly now accepts the explicitly declared single-AOI reset policy
and archives both policy helpers. Prepared candidate
`dll_qualification/1d201e9ed2f89f56` contains 336 original fixtures, the exact
repaired analog network and the fast-reset physical PFD. Input validation passes.
Advancement accepts an explicit `--pfd` selection instead of silently substituting
the preceding PFD. The full campaign remains held pending the source screen.

Architecture evidence now compares the actual PFD and bias dependency closures
in each of the three screen libraries against the native library. Matching source
text alone cannot authorize a different physical detector. The prepared candidate
passes this check; a preceding-PFD substitution is rejected. Unit regressions
also reject changed PFD, bias and private physical implementation bodies.
Host validation: 216 tests, 211 passed and 5 backend-dependent skips.

The frozen RX aperture campaign has completed all 480 conditions; its table has
`passed: false` and cannot qualify a release. Its original artifacts are retained
for diagnosis. All three new source-screen loops are now running concurrently;
there is no settled-loop qualification result yet.


Combined native static service `openlvds-fast-reset-native-static.service` now
runs SS/0 °C +150/0/−150 ps full-RC cases from candidate `1d201e9ed2f89f56`
with three workers. Alongside the three source-screen loops this occupies all
six native SPICE slots. No active simulation was interrupted or restarted.
Host regression after the concurrency change: 219 tests, 214 passed, 5 skipped.
The source-screen FF/TT/SS traces have reached approximately 501/118/72 ns;
these are partial progress observations, before the 1200–1500 ns scoring window.

RX diagnosis rechecks all 248 endpoints of the 124 failed conditions. Both
endpoints fail in every condition; every +800 ps endpoint has high VALID but
illegal data levels. The detailed receipt and proposed isolated RX controls
are recorded in `dll-failure-analysis.md`. The complete PHY remains unqualified.


RX publication diagnostic `rx_publication/dd89f11b1af99f29` prepares six
source-bound SS/TT/FF endpoint controls with internal extracted output-stage
and supply probes. Three preserve 20 fF data loading; three remove only that
external load to isolate its contribution. All use the original observation
window. Native terminal discovery passes on the actual extraction. Host tests:
221 total, 216 passed, 5 skipped. Service `openlvds-rx-publication-controls`
will use one worker, waiting for a global SPICE slot while the six current DLL
simulations continue. Results do not qualify RX or the PHY.


The combined fast-reset physical PFD plus repaired analog macro now passes all
three original SS/0 °C static seed fixtures under 120–160 ns scoring. At +150 ps,
BAD stays at 1.8 V and filtered UF−DF is +107.721 mV; at −150 ps BAD stays at
1.8 V and filtered UF−DF is −103.105 mV. At 0 ps, BAD remains below 1 nV and
filtered UF−DF is +1.826 mV. Waveform hashes (+150/−150/0 ps):
`c65660edb4987a757042a06c1a535b246759f1048056d6caa3def3285ef01792`,
`62985221b3935b6c3e23b5a646a4840ba6984a658d07439cf7238a63b799b74c`,
`896088cdbe0a82ad4d40c2d297d776ed22500cf3275e4ae8b5be33df52daf6d4`.
The conditional follow-up rechecked all seed artifacts and dispatched the
remaining 18 static SS/TT/FF cases. Architecture acquisition is still pending.

RX SS/0 °C internal publication control with 20 fF external loads reproduces
the baseline public measurements exactly (maximum reported limit difference
0 V). The publication flop output is already near 1.8 V and the final buffer
input near 0 V while the public outputs still charge. Final-driver local VDD
remains above 1.77 V. Removing only the two 20 fF external data loads makes the
same fixture pass: Q0/Q1 minima become 1.79890/1.79842 V. This demonstrates an
external-load contribution in the native circuit, with the original window and
VALID load preserved. Other controls and a separately hardened stronger-driver
candidate must establish the repair before any RX qualification.


Isolated RX `buf_4` candidate `rx_buffer4_physical_v1` completes its physical
flow with zero final routing, Magic and KLayout DRC errors; zero LVS device,
net, property and pin errors; no antenna violations; and a passing retained
native topology policy. Source identity is
`5f8b2734b05398da11153ad596a40c0c037ed21e6c775e37586acdd7de7bb1af`.
It preserves publication/sampling logic and explicit unit-strength VALID drive.
Its isolated functional scoreboard passes all 54 generic/native-RX cases,
1,186,794 bits per implementation, across the requested clock/duty/skew points
with jitter and reset behavior (`rx_buffered_rtl/5b4107f583cb8aee`). Host unit
checks: 224 total, 219 passed, 5 skipped. Actual GDS extraction and independent
RC connectivity LVS are now running. Loaded native endpoint and full aperture
qualification remain pending; this RX has not been selected or promoted.


Buffered RX actual GDS extraction and independent strict RC connectivity LVS
both pass. GDS SHA-256:
`39552fad4164d50bf619b9c535a09eb422ea5688fbfe85abfe8db871adf84bf4`;
exact reduced network SHA-256:
`f6e4ef38f920772c845917e4e121929642fc9a897c65e1d6d40195c669a4d61e`.
All 1,208 extracted capacitors and protected terminals are retained; exact
positive-conductance algebraic elimination reduces 21,690 resistors to 4,267.
The independent audit has zero topology errors. Native loaded endpoint tests
and a fresh complete aperture matrix are still required for this network.


Source-bound buffered RX aperture artifact `7636dbd7a4c55979` is prepared with
all 480 original conditions and exact native network `f6e4ef38f920772c...`.
Service `openlvds-rx-buffer4-aperture` queues six loaded both-polarity SS/TT/FF
endpoints, then expands only after their intact passing waveforms are rechecked.
The full matrix uses up to three workers under the global six-slot budget.
Original frozen producer files are unchanged. Unit checks: 230 total, 225
passed, 5 skipped; admission rejects incomplete/duplicate matrices and missing,
failed or changed endpoint evidence, and the selected-slot lease is exclusive.
No buffered native endpoint or aperture qualification result is claimed yet.

Combined native DLL static follow-up now passes six SS/0 °C offsets: 0, ±50,
±150 and +300 ps. −300 ps and TT/FF static coverage remain in the queue, and
all three source architecture loops are still running. The complete PHY remains
unqualified.


Buffered RX loaded native endpoints now pass both SS/0 °C data polarities and
TT/0 °C rising data at slow clock slew, using the original windows and limits.
Remaining seeds continue under service `openlvds-rx-buffer4-aperture`.
A separate six-case SS/0, SS/40 and SF/40 slow-clock diagnostic is queued under
`openlvds-rx-buffer4-limiting` to expose limiting publication behavior early.
Both services use the existing six real SPICE leases without signalling any
active simulator. Full aperture, full DLL and PHY qualification remain pending.


Staged integration supports an explicitly selected audited RX in both circuit
views, archived-source RTL verification, matching physical package selection
and exact-model aperture/link checks. Diagnostic bundle `712bb74a908d85f4`
passes all 54 functional cases (2,373,588 bits), including native TX+RX and PHY
assembly/control. All three digital GDS identities and exact/approximate model
hashes match their staged inputs (`digital_model_binding.json`). Canonical RTL
also passes after the verifier update. Unit checks: 234 total, 229 passed and
5 skipped. A staged release negative control remains failing with 565 checks;
missing native DLL, all-PVT model/proofs, analog/current-analysis, aperture,
RC certificate and full link evidence are not bypassed. No release is produced.

The early limiting RX test fails SS/0 °C rising-data setup at 200 ps clock slew
under the original 20 fF load: Q0/Q1 minima are 1.40981/1.29742 V. Thus passing
the 20 ps clock-slew SS endpoints and TT endpoints does not qualify `buf_4`.
The original limits remain fixed. Remaining broad RX work is being held at an
idle coordinator boundary, preserving native traces, before a stronger native
publication/output path is evaluated. The DLL source/static jobs continue.


The current selected-RX staged bundle `712bb74a908d85f4` passes actual physical
reconstruction, archived RTL and canonical source-fingerprint gates in a fresh
565-check release negative control. Release remains false because required
native DLL/PVT/proofs, current analog evidence, complete RX aperture, six-fixture
certificate and full link matrix are incomplete. Exact/fast digital model and
GDS metadata agree. No package or current release pointer is published.

The `buf_4` RX fails both polarities at SS/0 and SS/40 with 200 ps clock slew.
A hold request is active for its full matrix coordinator at the next idle search
boundary. Current native work is not interrupted. Stronger source
`openlvds_ddr_rx_buffer8_publish4.v` retains data `dfrtp_4` publication and
`buf_8` outputs, with unchanged pipeline and VALID behavior. Its 54-case generic
and native RX functional regression passes 1,186,794 bits per mode. Physical
and loaded native timing validation remain pending. Shared RX producer helpers
stay unchanged while the preceding active users drain.


The failed `buf_4` aperture dispatcher has been retired after its active native
children finished. Receipt `rx_aperture/7636dbd7a4c55979/drain.json` preserves
12 collected point reports and separately reanalyzes one completed uncollected
trace. No native SPICE process was signalled; its partial matrix is unqualified.
The limiting coordinator was retired while idle after both SS/0 and SS/40
polarities failed. Old source/producer archives and native traces remain intact.

Stronger RX `rx_buffer8_publish4_physical_v1` passes Magic/KLayout DRC and strict
LVS with zero errors, retains its declared native publication/driver topology,
and passes actual GDS extraction plus independent RC connectivity LVS. Source:
`b3125079c567f616dfd9985185f8d9f16942961bb3b1bc46fc7386a893d6a21f`;
GDS `e1fa7f2fcbade1245e4ee29dd6e77011cfeecbbf0c08a7dd013189d449d366ac`;
exact native network `4a62593449b1e94de0c224de1e00caff25f197eae0397b8ed82899631407865b`.
All 1,413 extracted capacitors are retained. Exact algebraic reduction reduces
22,046 resistors to 4,633 without removing protected terminals or devices.

Aperture artifact `f99deb414f62ab19` is prepared. Service
`openlvds-rx-buffer8-publish4-aperture` runs 12 stronger loaded admission points,
then only on success the complete 480-condition matrix with worst SS/SF cases
first. Failure now holds queued work while active searches finish, and incomplete
coverage cannot produce a complete table. The shared six-slot budget is intact.
Unit checks: 239 total, 234 passed, 5 skipped. The stronger RX has no loaded
native endpoint or full-aperture qualification result yet.


The fast-reset source-matched architecture screen completes FF/0 °C successfully
under the unchanged 1200–1500 ns window: maximum feedback error 6.5465 ps,
quarter-cycle delay 632.6245–632.9995 ps, CTRL mean 0.731602 V and total variation
3.1627 mV; BAD maximum 0.423 µV. Raw waveform SHA-256:
`793a3351d06c56c8523e6489b2f31e1580bdc06adc01cfc87101b723d8b54dbf`;
exported waveform:
`015ef69ccdf88f033ac37066a78998e9c514da1c551860a0ada8057700bcfe72`.
TT/SS source screens and full native-RC loop qualification remain outstanding.

Release checking also exposes stale driver/analog-receiver characterization.
A refresh coordinator now runs all 15 PVT points for schematic and exact native
views of driver, static receiver and rate receiver (90 component cases), using
fixed solved supplies and no voltage sweep. Every new simulator subprocess now
acquires a real shared SPICE slot; cached valid waveforms are reanalyzed without
acquiring a slot. Mismatched prior evidence is moved to content-hashed case
history before regeneration, preserving original traces, decks, sources and
producer files. Tests verify cache/slot behavior and archived file hashes.

The initial refreshed TT/0 °C driver passes both settled polarities into 100 Ω:
differential 0.31558–0.31612 V and common-mode 1.24470–1.25612 V. TT/25,
TT/40, FF/0 and FF/25 schematic drivers also pass with current analysis. Service
`openlvds-component-evidence-refresh` continues the remaining component cases.
The shared SPICE budget remains six; active DLL/RX fixtures and producers were
not modified. Unit regression remains 239 tests (234 passed, 5 skipped).


The stronger RX's first loaded native admission point fails SS/40 °C with
200 ps clock slew: Q0/Q1 minima are 1.21208/1.10179 V, below 1.44 V in the
unchanged publication window. Its fail-stop logic correctly holds the remaining
11 endpoints and never expands the full aperture matrix. Root
`rx_aperture/f99deb414f62ab19` records the failed witness and held cases.
Physical/functional passes do not qualify this timing result.

New staged bundle `754e8b6301c3cc78` with the stronger RX passes the complete
54-case generic/native TX+RX functional regression (2,373,588 bits). Its native
publication timing remains a failure. Internal diagnostics at
`rx_publication/3efd83d2a44327ab` now target this exact failed SS/40 condition,
retain the original stimulus/window, observe actual output-stage, clock-input
and clock-controlled transistor terminals, and compare 20 fF versus zero
external data loading. The diagnostic accepts a source-bound failed seed report
without requiring a complete aperture table. Service
`openlvds-rx-strong-publication-probe` is queued under the six-slot budget.
Another width change is held until those native internal traces identify delay.


All three source-matched fast-reset DLL architecture loops now pass their
original window. SS/0 °C maximum feedback error is 10.0304 ps (CTRL mean
0.815841 V, variation 2.5738 mV); TT/25 °C error is 7.8211 ps (0.759505 V,
2.9996 mV); FF/0 °C error is 6.5465 ps (0.731602 V, 3.1627 mV).
All 21 selected full-RC static offsets at SS/0, TT/25 and FF/0 also pass.
Service `openlvds-fast-reset-native-screen` now runs the three native-RC
acquisition cases using those unchanged captured libraries/fixtures, reusing
intact completed static evidence without simulation restart.
`openlvds-native-dll-gated-progression` waits for actual native screen success,
then runs measured three-corner stability/step validation; only passing model
reports admit full 336-case native qualification, followed by all-PVT model
measurement. Failed gates hold expansion. The resident automatic OTA/CP entries
remain disabled, avoiding duplicate native dispatch. Full PHY remains unqualified.

The controlled `buf_8`/publication-1 RX passes its 54-case generic/native
functional regression (1,186,794 bits each), zero-error physical DRC/LVS and
strict native topology, actual GDS extraction and independent RC connectivity
LVS. Source identity:
`e842ec085bc658245c8dde9fefb33ef799ac173fb9d9a77f964519b7887d6918`;
GDS `8732722a02671ed4377dc4948c50139c0a2e91c201c3544a09325d35742bac4f`;
exact network `83e0a24d2f74c0885c4b512688b54833a33473e88b4a2b631b20b190cc479315`.
All 1,352 extracted capacitors are retained; exact algebraic reduction reduces
21,951 resistors to 4,515. The distinct `public-data-buf8-publish1` policy checks
its actual publication cells and driver wiring; it cannot inherit publication-4
success. Native artifact `rx_aperture/4032d9b01f924bfd` runs the same 12 admission
points and conditionally the full matrix under
`openlvds-rx-buffer8-publish1-aperture`. No native timing result is claimed yet.
Unit checks: 240 total, 235 passed, 5 skipped.

All 45 distinct schematic driver/static-receiver/rate-receiver PVT cases now
have current passing reports. The SF/0 driver initially hit a timestep collapse
at 2470.05 ns in a thick-oxide level-shifter source-body node. Repeating that
same case with a tighter 20 ps maximum integration step completes normally and
passes the original DC and transition criteria. Its original failed data is
preserved in case history; the batch's original failure returncode is retained.
Repair receipt: `component_refresh/sf0_driver_repair.json`. Three native driver
PVT cases have passed so far; the remaining exact-RC component refresh continues.

The publication-cell comparison also fails native SS/40 °C at 200 ps clock
slew: publication-1 with buf_8 gives Q0/Q1 minima 1.56645/1.26103 V.
Artifact `rx_aperture/4032d9b01f924bfd` holds its remaining 11 admissions.
Internal publication-4 traces (`rx_publication/3efd83d2a44327ab`) distinguish
the causes: local clock input crossings are within 0.343–0.711 ps, but the
publication Qs cross 1.44 V only after 664–672 ps. Loaded public outputs reach
1.44 V after 817.283/824.523 ps, outside the unchanged 800 ps window start;
unloaded outputs cross at 764.879/772.168 ps. Further drive-strength tuning
is therefore superseded by an isolated half-cycle publication experiment.

`rtl/experiments/openlvds_ddr_rx_early.v` prepares a completed pair on the falling
edge: a held rising sample and the falling sampler drive buf_4 public outputs.
VALID is held on that falling edge too, preserving the first valid word for a
positive-edge consumer. Explicit native cells and the distinct
`half-cycle-publish-buf4` policy retain all sampler clocks, enables, word holding
and VALID wiring through routing. This changes public update phase; integration
must respect the positive-edge consumption contract. It remains an experiment,
not a promoted receiver.

Fresh functional evidence `rx_buffered_rtl/3fc750281ff3b4bb` passes 54 cases,
1,186,794 bits per generic/native model. Directed evidence
`rx_early_contract/711c7d2a275a2c4a` passes 18 frequency/duty/model cases, including
four asynchronous reset phases, first-valid word ordering, pre-edge consumer
streams and post-edge pair agreement with the original RX. Physical artifact
`rx_early_physical_v1` is being built for independent native RC audit and the
unchanged 12-admission / 480-condition timing gates. No native timing pass is
claimed from these functional checks.

Both parallel native analog receiver batches complete successfully: 15 static
receiver and 15 rate-receiver cases, fixed supplies and 0/25/40 °C. Exact-RC
driver refresh and native DLL acquisition remain running; their captured
producers are unchanged.

The early RX physical artifact completes with zero routing, Magic, KLayout and
LVS errors. Its independent native RC audit passes. GDS SHA-256:
`723b7149cab3a7ea6c936da1d15eff9ec255db889c6ce1f345f374807ce6bd9c`;
exact network `6def14fbd570903751f922c3a86132bbd801957c3dfd3d09c7c81729361515c3`.
All 1,171 capacitors are retained; exact algebraic elimination reduces 21,701
resistors to 4,229. The nominal routed STA has no setup/hold violations; worst
setup slack is 68.315 ps and hold slack 134.170 ps. These nominal checks are not
PVT timing qualification.

Native admission/full campaign `rx_aperture/20b04dcf527af283` now runs under
`openlvds-rx-early-aperture`, with unchanged acceptance and fail-stop gates.
Combined diagnostic bundle `phy_candidate/8f364c6a8fdabafb` selects this exact RX
and its matching functional cell model. Its full RTL regression is running.
No promotion or release claim is made. Current unit regression: 241 tests,
236 passed and 5 skipped. A second native-driver refresh service uses two workers
with shared slots and existing per-case locks, accelerating the remaining cases
without overwriting running evidence.

The selected early RX bundle passes all 54 full generic/native TX+RX functional
cases (2,373,588 bits), including DLL-control and functional-PHY checks. Evidence:
`8f364c6a8fdabafb/rtl_validation/c7d7efce94da841f`. Its first two native admissions
both pass SS/40 °C with 200 ps clock slew and 20 fF loads. Rising data Q0/Q1
minima are 1.79999958/1.79999895 V; falling-data maxima are 0.300/0.0133 µV.
The original window and 0.36/1.44 V thresholds are unchanged. Remaining ten
admissions and the full 480-condition matrix remain outstanding.

`openlvds-early-phy-rc-validation` now compares all six exact/approximate nonlinear
fixtures for this bundle with two workers. Shared leases keep actual native
DLL, driver refresh, RX and certificate simulations within six total. There
is no passing RC certificate, complete native RX table or released PHY yet.

Supplementary native burst artifact `rx_burst/0a6a8b72e9d5e53d` now probes the
new half-cycle path under continuous data. Its first SS/40 °C case passes all
32 consecutive words at 410 MHz, 45% duty, -100 ps skew, independent ±50 ps
clock-edge jitter, 200 ps clock/data slew and 20 fF public loads. Across the
unchanged publication windows, the minimum high is 1.79999127 V and maximum low
95.912 µV. Three further duty/skew cases remain; this is supplementary evidence,
not a replacement for aperture or link qualification. Six original RX admissions
have now passed. New diagnostic and corruption/fixture tests are committed as
`03fcd7a`; unit suite: 243 tests, 238 passed, 5 skipped. All active producers and
original coverage/limits remain unchanged.

All four native continuous-data burst cases now pass and their service exits 0:
128 checked words at SS/40 °C and 410 MHz, both 45/55% duties and both ±100 ps
skews, independent ±50 ps edge jitter, 200 ps clock/data slew and 20 fF loads.
Across every word's original public window, minimum high is 1.79999126 V and
maximum low 96.1872 µV. Artifact `rx_burst/0a6a8b72e9d5e53d` has four actual
source-bound reports; no missing case is counted as coverage. This completes the
supplementary half-cycle diagnostic, while the full aperture and link gates
remain mandatory. Eleven original admissions have passed and the final FF/0
falling-data case is live. DLL, driver refresh and six-fixture RC comparison
continue without source changes or simulation restart.

The early RX clears all 12 original loaded native admission points with zero
held cases. `rx_aperture/20b04dcf527af283/seed_summary.json` binds each actual
waveform witness to manifest
`bd12c38ce8362bd289826175a9ee3b650f3a49fafd0116ab9d3092aa231e16bc`.
The same coordinator has rechecked those admissions and entered `running_full`
with three boundary workers for the original 480-condition matrix. Actual
simulator dispatch remains limited by the six shared leases. This clears the
publication admission failure that held the preceding three RX variants; it
does not yet prove complete aperture bounds or full PHY qualification.

The independent current-component receipt now verifies 80/90 actual proofs:
all 45 schematic cases, all 30 native analog receiver cases and five native
drivers. FF/40 and SS/0 native drivers are live; the other eight native drivers
still have stale reports awaiting refresh. The native FF/25 driver completes
and passes its original DC and transition criteria. The receipt distinguishes
running/stale evidence from electrical failure, retains historical batch errors,
and checks exact case names rather than overlapping receiver globs. Source:
`scripts/verify_component_evidence.py`; output:
`component_refresh/current_evidence.json`. Read-only shared locking has also
been exercised on this workspace's NFS filesystem. No active producer changed.


The early RX completes its first full boundary condition at SS/40 °C with
200 ps clock and data slew, rising clock edge and rising data: 87.5 ps fails,
90.625 ps passes, resolution 3.125 ps, retained guard 20 ps, rounded setup bound
120 ps. This is one actual condition in the required 480, not a complete table.
All three boundary workers now have real simulator leases. Current component
receipt advances to 81/90 after the FF/40 native driver passes.

The staged driver's completed exact/approximate comparison passes with 32
matching transitions, maximum edge difference 0.395436 ps, differential plateau
difference 0.540915 mV and common-mode plateau difference 0.367787 mV. Both traces
are reverified through their captured circuit/simulator/fixture attestations;
no resimulation or looser comparison was used. Supplementary result:
`phy_candidate/8f364c6a8fdabafb/driver_rc_diagnostic.json`. The original six-fixture
coordinator continues and no complete certificate is claimed from this subset.


Three original full-aperture conditions now pass at SS/40 °C with 200 ps clock
and data slew. Rising-clock/rising-data setup retains its 120 ps guarded bound.
Rising-clock/falling-data setup brackets 178.125 ps failing and 181.25 ps passing,
then verifies the 210 ps guarded witness. Rising-clock/falling-data hold brackets
-181.25 ps failing and -178.125 ps passing; the original guard/rounding policy
conservatively clamps the reported hold requirement to zero and verifies that
actual zero-offset witness. Remaining conditions continue under unchanged code.

The native SS/0 °C driver completes and passes, with settled differential levels
0.294919–0.295079 V into 100 Ω and common mode 1.24841–1.25159 V for its positive
polarity. Its delayed transition stream also passes original polarity/cadence
checks (propagation 1.34898–1.38597 ns). The independent current receipt verifies
82/90 component proofs. Eight native driver PVT cases remain outstanding.


Both SS/40 °C falling-clock setup conditions now pass with 200 ps clock/data
slew. Rising data brackets -28.125 ps failing and -25 ps passing; the unchanged
guard/rounding policy produces a conservative zero requirement and the actual
zero-offset witness passes. Falling data brackets 59.375 ps failing and 62.5 ps
passing, with a verified guarded 90 ps bound. Together with both rising-clock
setup and hold results, six of 480 full-aperture conditions pass. The remaining
falling-clock hold searches are active; no complete PVT aperture table is claimed.

A release handoff review found that digital GDS/LEF and synthesis sources were
included, but the routed digital netlists were omitted. Promotion now includes
both logical and power-aware netlists for the exact selected TX, PFD and RX.
Their expanded interfaces, logic connectivity and cell supply/body connections
are checked before packaging; validated byte hashes also prevent a changed file
from being copied after validation. The native tap cell's two supply terminals
are handled explicitly, while logic cells require all four supply/body ties.

The new non-publishing `--check-netlists` preflight passes against actual selected
bundle `8f364c6a8fdabafb`, including the early RX. Its receipt is
`netlist_preflight.json`, with no electrical qualification or release pointer
change. Tests reject swapped/missing power ties, changed logic, wrong bus widths,
wrong directions and duplicate cells, and verify that preflight preserves an
existing current release. Unit suite: 253 tests, 248 passed, five skipped. Active
DLL, RX, component and RC producers remain unchanged.

A link-analysis review identified an observation mismatch: payload decoding used
one sample at half a period, outside the RX's characterized +0.80–1.05 ns window.
For the early RX, that sample can approach the next falling-edge publication
under duty/jitter stress. The link analyzer now requires stable legal data and
high VALID over all 51 points in the original window, with no timing/voltage
relaxation. Input capture margins, analog checks, payload lengths and complete
qualification coverage are unchanged.

New tests cover early next-word updates after the window, brief illegal data or
VALID inside it, and both window boundaries. The analyzer also decodes three
actual completed native guarded witnesses correctly (rising setup 120/210 ps and
falling-clock hold 50 ps). Unit suite: 256 tests, 251 passed, five skipped.
The analyzer's runner fingerprint gives future link runs a fresh identity; no
active native DLL, aperture, component or RC producer was modified.

Supplementary exact-RC integration probe `openlvds-early-exact-link-probe` is
queued under the six-slot budget. Its artifact is
`build/link/ss_40_410m_d0.45_s100_e0_ideal_32/6735242e52a2`. It uses 32 bits at
SS/40 °C, 410 MHz, 45% duty, +100 ps data skew and 100 ps peak-to-peak jitter,
actual full-RC data-path macros, ideal quarter-phase clocks and solved fixed
supplies. A 60 ns diagnostic training override shortens this supplementary test;
it does not replace the required measured-DLL-phase diagnostic or full trained
link matrix. The new window analyzer is committed as `d9d73eb`; this producer is
now held unchanged while the test runs. No integration result is claimed yet.


The complete SS/40 °C group at 200 ps clock and data slew passes all eight
original boundary conditions. Each guarded witness was actually simulated:

| Capture clock edge | Data transition | Setup bound (ps) | Hold bound (ps) |
| --- | --- | ---: | ---: |
| Rising | Rising | 120 | 0 |
| Rising | Falling | 210 | 0 |
| Falling | Rising | 0 | 50 |
| Falling | Falling | 90 | 0 |

These are guarded/rounded requirements, including conservative zero clamping
of negative boundaries. This group does not replace the other original slew
combinations or remaining PVT points. Eleven of 480 conditions currently pass,
with no failed completed condition.

Native SS/40 °C driver characterization also completes successfully. Its settled
differential output is 0.288671–0.288713 V into 100 Ω; positive-polarity common
mode is 1.249158–1.249705 V. Original polarity, cadence and transition checks
pass (propagation 1.37523–1.39375 ns). The independent current-proof receipt now
verifies 83/90 cases. Native SS/25 and FS/0 drivers are active; five subsequent
native driver cases remain stale until refreshed. The exact-RC integration
probe remains queued under the six-slot limit, with no result claimed.

The downstream workflow now has an explicit completed-native resume path:
`advance_ota_candidate.py --qualified-native ... --all-pvt-stability ...`.
It reanalyzes complete native qualification and verifies the all-PVT model before
any downstream command. It carries the selected RX/table through all original
operating-point, recovery, readiness, RTL, RC, diagnostic, full-link and release
gates, without preparing a new native campaign or modifying resident dispatcher
configuration. A qualification-wide nonblocking lock prevents duplicate owners.

Tests cover incomplete/failed/native-damaged/model-damaged evidence, rejection
of CP artifacts, selected RX preservation, unchanged resident configuration and
exclusive advancement ownership. An actual attempt against the currently
incomplete native campaign stops at the native gate, creates no advancement
directory and starts no downstream job. Unit suite: 261 tests, 256 passed, five
skipped. Active qualification producers and fixtures remain unchanged.

Runtime inspection found that the base image contains no Apptainer executable,
while the downstream orchestrator previously called `env.sh` for every child.
Its child-command builder now executes base jobs directly inside the established
container and enters the existing Nix shell for tool jobs. Host-side command
construction retains the environment wrapper. Literal arguments are preserved
with proper shell quoting for the Nix command string.

Actual smoke checks pass for both paths: a base child validates the selected
TX/PFD/RX netlist handoff, and a Nix-shell child exposes the advancement CLI.
The waiting downstream watcher was stopped for this correction; no native
simulation was stopped or restarted. Unit suite: 264 tests, 259 passed, five
skipped. The resume path retains complete native/all-PVT and downstream gates.


The native SS/25 °C and FS/0 drivers complete successfully. Their original
transition propagation ranges are 1.36533–1.39077 ns and 1.16675–1.22170 ns,
respectively. The independent current receipt verifies 85/90 component cases;
five native driver PVT cases remain outstanding. Thirteen RX aperture conditions
have passed, with no failed completed condition. The exact-RC link simulator has
started its operating-point solve; absence of a raw file during that solve is
not evidence that the job is queued or stopped.

Service `openlvds-early-phy-post-native` now waits on the existing standalone
native/model progression, then invokes the completed-native resume path with
the explicit early RX/table. Its source and qualification/RX manifest hashes are
bound in `resident_jobs/early_phy_post_native.json`; source drift, RX failure or
terminal upstream failure holds downstream execution. It tolerates transient
status-read failures and checks actual service state. Resume itself repeats
complete native and all-PVT verification before signoff. Current state is
`waiting_for_native_and_all_pvt_model`; no native or model completion is claimed.
The prior waiting watcher's source and receipt are preserved in resident job
history. No scientific simulator was stopped for the workflow corrections.


Bring-up update on 2026-11-01 (input-bias investigation):

- Corrected matched DC matrix `receiver_static_matrix/1ac68453f143818d` is
  complete; an independent cached run remeasures all 15 waveform pairs. Twelve
  modified cases pass. SF/0, SF/25 and SF/40 fail only the original 130 ns
  sample (2.35 V common mode, P=2.3 V, N=2.4 V). Q remains high; CO is
  0.703679/0.726471/0.743371 V respectively. Thus clamp removal fixes the
  low-common-mode loading problem but does not establish full DC coverage.
- The LVT native initial operating point has CT=0.0467892 V and NBC=0.936557 V,
  with PP=1.07999 V and PN=0.903624 V. The low tail drain voltage motivates
  checking input common-mode/headroom; it does not by itself prove a device
  operating region or establish the short-pulse cause.
- New isolated `receiver_input_bias_experiment.py` retains standard-NFET
  unclamped 8/4 → 16/8 → 16/8 restoration and doubles only the four existing
  PP/PN ground-branch resistor lengths, 1.25 → 2.5 µm. Nominal Thevenin bias
  rises from 0.9 to 1.028571 V, with resistance 1 to 1.142857 kΩ. This changes
  gain/RC as well as common mode; no improvement is assumed. Clock controls
  use the exact unchanged standard-NFET unclamped receiver. Three structural
  tests prove the four resistor-only changes, unchanged ports/devices/helpers,
  rejection of changed topology/reapplication, and identical static/clock cores.
  `receiver_input_bias_static.py` first queues the unchanged original 12-sample
  TT/25 fixture (`38a7bc88524f7fab`) and failing SF/40 fixture
  (`7c4866221b0fca57`), preserving supplies, common modes, load, thresholds and
  sample times. Their recorded parent control is the clamped fast receiver;
  the matched unclamped DC matrix above supplies the separate standard-NFET
  reference. No one-factor claim is made against that clamped parent. Both
  static screens must pass before clock/physical/native advancement. TT/25
  now passes all 12 samples, but SF/40 fails the same 130 ns high-common-mode
  sample: PP=1.197507 V, PN=1.313036 V, CO=0.443083 V and Q=1.8 V. Thus
  this candidate is held before source-clock, physical or native work. No
  live campaign or original criterion changed.
- Unchanged native driver observation `driver_internal/c9c5ccd60b8fbe69`
  completes the full 188.049 ns transient and passes cached waveform reanalysis.
  The five original external signals match exactly on its declared comparison
  grid. In 60–120 ns AD/AB and L/R each have 25 rising/falling crossings at
  their declared observation levels. DP has 24/25 crossings at 1.65 V; DN
  has only 16/15, with complete high intervals 369.055–714.148 ps. These levels
  are diagnostic thresholds, not transistor switching points or a PHY gate.
  This localizes substantial pulse compression to the level-converter output
  path, without yet separating its CML and restoration contributions. The
  controlled P64/N24 source comparison remains in progress; its candidate
  has now aborted at 15.366 ns: timestep 1.25e−22 s, trouble at
  `m.xct.xls.xb1.xn.msky130_fd_pr__nfet_g5v0d10v5#dbody`. The simulator PID
  is gone; its actual log/raw/deck hashes are recorded in
  `restore_64_24/failure_observation.json`. The unchanged source control
  continues independently, so the comparison owner remains active while
  this candidate is numerically failed. No comparative improvement is available. No live simulator was stopped.

- `receiver_decision_observation.py` now isolates the unchanged standard-NFET
  unclamped receiver at SF/40, adding only unloaded CL/CT/NBC voltage columns
  to the original static deck (`receiver_decision_observation/2da7f2f39d63c3af`).
  All original 12 samples, stimuli, load and scoring remain. Its purpose is to
  distinguish decision-pair/mirror headroom from a restoration threshold issue
  at the failed high-common-mode point before choosing another circuit change.
  Two tests prove exact source equality to the unclamped factory and that deck
  changes are restricted to the include path and three print columns; absent
  or ambiguous print rows are rejected. The probe completes all 144 ns. Every original P/N/Q/PP/PN/CO sample
  matches the completed unclamped SF/40 reference exactly;
  `sample_comparison.json` binds both reports and the twelve-sample check. Full regression before this observer: 420 tests, 419 passed
  and one skipped; its two additional targeted tests pass.


Decision-tail repair on 2026-11-01:

- The completed SF/40 probe measures CL=0.341373 V, CT=0.170393 V and
  PN=1.182045 V at the failed 130 ns sample. The diode-side input transistor
  therefore has VDS=170.980 mV and VGS=1.011653 V. This supports branch
  headroom loss under high common mode, rather than establishing the compact
  model's operating region from voltage alone. At low common mode, CT is
  only 14–24 mV; the original W64 decision tail has substantial compliance
  variation across the required input range.
- `receiver_tail_headroom_experiment.py` changes only XCT width 64 → 16 µm
  in the standard-NFET unclamped receiver. Input tails, pairs, mirrors, loads,
  all three restoration inverters, monitor, pins and fixed supplies remain.
  The unchanged control uses that same unclamped core with XCT=64. Three
  structural tests verify the one-parameter intervention, reject changed
  topology/reapplication, and bind the exact static and clock source.
- Original TT/25 static screen `receiver_tail_headroom_static/5d065800619f4692`
  and SF/40 screen `c11fd7604ba0838a` both pass all twelve original samples.
  At the previously failing SF/40 sample, PP/PN remain
  1.078740/1.182046 V while CL=0.653296 V and CT=0.348148 V
  (VDS=305.148 mV). CO now reaches 1.417706 V and Q correctly goes low.
  This demonstrates the source DC repair at those two corners; no native
  timing or full-PVT claim follows from it.
- Full fifteen-corner matrix `receiver_tail_headroom_matrix/eaf3b93c66400e6c`
  now runs all original source DC fixtures. Its first four completed cases
  pass, including TT at 0/25/40 and FF/0; remaining cases are outstanding.
  Source clock root `receiver_clamp/d9d7143b8bf2b7a7` runs the original three
  80 ns controls, retaining the original saved pins, bias, early digital RX
  and scoring window. No completed clock result is claimed yet.
- Dedicated physical/native producers require all fifteen complete passing DC
  cases with all twelve samples each, plus all three complete passing source
  clock comparisons. Each gate remeasures the actual cached waves and checks
  the exact receiver closure. Actual preflight holds both incomplete gates
  (`physical_gate_preflight.json`), starting no layout or missing simulation.
  Metadata explicitly binds tail scale 0.25 / width 16 µm and standard NFET
  restoration; mixed old-tail or LVT identities are rejected. Native replay
  retains both independent shared leases, all 80 ns, original pins/stimulus
  and 15–75 ns scoring, and adds unloaded CL/CT/NBC probes. Tests also reject
  a 79 ns prefix as incomplete and let the other control finish after a failure.
- Service `openlvds-receiver-tail-headroom-native-continuation` captures all
  source/matrix/child manifests and transitive producers. It waits on both
  actual upstream owners, then repeats the gates before DRC/LVS, independent
  RC audit and native replay. It is currently waiting for source/full DC.
  No layout or native tail-repair result is claimed. Regression: 434 tests,
  433 passed and one skipped.
- A read-only comparison of complete standard-NFET source/native clock traces
  in the first failed 24.5–26.5 ns window finds maximum PN−PP of
  174.968 mV source versus 58.625 mV native. CO peaks at 1.602605 V versus
  0.676372 V. The LVT pair gives essentially the same internal attenuation.
  This supports a front-end bandwidth limitation in addition to the measured
  DC headroom issue; tail-repair native timing must demonstrate improvement.

- The unclamped follow-up selector now also supports `unclamped_tail_headroom`,
  dispatching its exact source factory and native verifier into the unchanged
  sixty component fixtures and original loaded link. It requires explicit
  tail width 16 µm, scale 0.25 and standard first-stage NFET metadata; carrying
  reduced-tail metadata under an older profile is also rejected. Four selector
  tests pass, including transitive producer capture and restoration after an
  exception. Both previous standard/LVT follower services were confirmed
  terminal before the selector changed; the live tail native continuation
  does not capture this selector. No tail component/link artifact or simulation
  is claimed before its actual physical/native model is available.


Driver numerical retry on 2026-11-01:

- The prior original-circuit repair `component_refresh/sf0_driver_repair.json`
  records the same class of thick-oxide source/body timestep collapse clearing
  with a 20 ps maximum integration step. This motivates a numerical retry,
  without assuming that it will cure the current SS/40 loaded fixture.
- `driver_restore_timestep_retry.py` prepares a separate comparison
  `driver_restore/00fe9eaeef273780`, retaining both source control and P64/N24
  candidate, fixed rails, complete 188.049 ns run, original sources/channel,
  loads, payload, publication window and 200 ps sampling-margin gate. Only
  maximum integration step changes from 100 to 20 ps; output step stays 20 ps.
  `retry_comparison.json` proves byte-identical circuit libraries against
  `cff36fa92d24e01b` and exact deck identity after include-root rebinding and
  that single transient-field substitution. The wrapper captures its own
  producer and restores shared dispatch in `finally`; unexpected original
  timestep commands are rejected. Three targeted tests pass.
- Service `openlvds-driver-restore-20ps-comparison` is active with both fixtures
  waiting for shared leases. The original failed candidate and still-running
  original control remain untouched. No numerical recovery or performance
  improvement is claimed. Regression now covers 438 tests: 437 passed and
  one skipped.
- The smaller-tail source campaign's unchanged captured-clock control now
  completes with no missing output transitions. Its modified captured case
  is running; the sharp case remains outstanding. The full DC matrix has
  five passing completed cases (all TT temperatures and FF/0, FF/25), with
  FF/40 waiting/running next. Native advancement remains gated on the complete
  fifteen-case matrix and all three original source clock reports.


Receiver precision retry and complete predecessor results on 2026-11-01:

- The original smaller-tail modified source clock run remains live but advances
  extremely slowly near 43.840 ns with its original 5 ps maximum integration
  step. No abort is reported. `receiver_tail_timestep_retry.py` prepares a
  separate three-control source campaign `receiver_clamp/dee37af388e0ca28`
  with 1 ps maximum integration step, unchanged 5 ps output step, full 80 ns
  run and original 15–75 ns scoring. Original supplies, saved pin waveforms,
  bias, early digital RX and all receiver devices are preserved.
- The retry's three candidate/library pairs are byte-identical to the original
  campaign. Its decks differ only by include-root rebinding and the final
  `.tran` field, 5 → 1 ps. `preparation_recheck.json` verifies all eleven
  manifest/policy/fixture hashes survive actual re-preparation unchanged.
  Five tests cover exact field substitution, fixed duration/output step,
  immutable cached manifests, changed fixtures and refusal to edit any executed
  control. Service `openlvds-receiver-tail-headroom-1ps-source` queues this
  independent numerical retry under the same shared six-slot budget. The
  original scientific run is not stopped or reinterpreted as failed.
- Source numerical policy is now checked explicitly by physical/native gates.
  Every source producer is captured transitively, including extra numerical
  leaves; policy hashes and the declared maximum step are bound into the
  physical identity. Native fixtures retain all original circuit/stimulus/
  observation/scoring fields and use the same declared 1 or 5 ps maximum
  integration step. Undeclared, mixed, changed, shortened or noninteger
  numerical policies are rejected. Both native controls still require their
  complete original 80 ns traces and independent shared leases.
- Before changing these waiting downstream producers, host PID 1194345 was
  confirmed childless in `waiting_for_source_and_full_dc`. Only that watcher
  was stopped; its original producer, manifest and state are preserved under
  `d9d7143b8bf2b7a7/native_continuation_history_20261101T034425Z`, with a
  retirement receipt. All scientific simulations continue. Replacement
  `openlvds-receiver-tail-headroom-1ps-native-continuation` is now bound to
  the new retry root and the unchanged fifteen-corner DC matrix. It waits on
  both actual owners before repeating complete source/DC gates, layout,
  DRC/LVS, independent RC audit and audited native replay. A real preflight
  validates the numerical policy and stops at the incomplete source gate.
- The complete predecessor clamped fast-restoration component campaign
  `receiver_components/58bb3aa28d907d28` is now reanalyzed from all sixty
  cached child waveforms, without starting SPICE. It passes 27/60: all fifteen
  schematic rate cases and twelve native rate cases. All thirty schematic/
  native DC cases fail. Native SS rate cases fail at all three temperatures
  with zero rising/falling output transitions; at SS/40 Q ranges only
  −1.304 to +1.426 mV in 20–60 ns, versus −23.497 mV to 1.881633 V
  schematically under identical ±250 mV differential drive, 100 ps edges,
  1.2 V common mode and 100 fF output load. Those decks did not save internal
  decision nodes, so no unique analog failure mechanism is claimed from them.
  Full-rate native component checks remain necessary after clock recovery.
- The smaller-tail DC matrix now has seven passing completed cases, adding
  SS/0 to all TT/FF temperatures. Remaining source/static/native/link gates
  are still outstanding. Regression: 447 tests, 446 passed and one skipped.


Completed unchanged-control precision check on 2026-11-01:

- The 1 ps source retry's `unclamped_captured` control completes all 80 ns
  with exactly one output transition in all 47 original checked input periods,
  zero missing and zero repeated edges. Its circuit is the unchanged standard
  unclamped fast-restoration receiver, not the smaller-tail modified case.
- `receiver_clamp/dee37af388e0ca28/unchanged_control_precision_comparison.json`
  binds both complete original/retry waveform, deck and report hashes. Across
  the 47 ordered corresponding transitions, maximum absolute output-crossing
  difference is 0.055405 ps. On a separate diagnostic 5001-point 20–75 ns grid,
  P/N source differences are below 4.45e−16 V; maximum PP/PN/CO differences
  are 39.584/17.265/245.467 µV. Both complete traces are finite and monotonic
  through 80 ns. This is numerical agreement of the unchanged control, not a
  modified-receiver/native/PHY verdict or a new acceptance threshold. The
  modified captured and sharp-control cases remain outstanding.
- The 20 ps driver ratio candidate has now obtained a shared lease (ngspice
  PID 1199093); unchanged driver control remains queued. No full driver
  comparison result is available. The smaller-tail DC matrix now has eight
  passing completed cases, including SS/25; SS/40 and FS/SF remain pending.


Matched native driver experiment on 2026-11-01:

- The 20 ps source P64/N24 run remains live but has entered a second very
  slow interval near 13.447 ns, earlier than the original 15.366 ns abort.
  It has not reported an abort and provides no full-run comparison yet.
  The original native driver observation completed 188.049 ns, motivating
  a matched extracted-geometry experiment while source numerical issues
  remain under diagnosis. No source simulation is stopped.
- `layout_driver_restore_candidate.py` builds isolated control/candidate GDS
  without changing active pointers. Both retain the original nine driver
  ports and exact declared source factories. Immutable captured geometry,
  source, DRC/LVS reports and producer hashes are checked on re-use.
  Control `driver_layout/2457353bd0bd4650` and candidate `57c38a7401ebd975`
  both pass with 266 devices, nine ports, zero DRC errors and strict LVS.
  Their footprints are 4029.07/4030.19 × 154.22 µm respectively. These are
  diagnostic physical results; neither establishes electrical qualification.
- `driver_restore_candidate_rc.py` extracts both GDSs and runs independent
  strict connectivity LVS on their wire-collapsed networks. Both audits pass.
  Control has 3970 capacitors and 63664 → 53633 resistors, exact network hash
  `189a2d70f025fad24ffa5329bcc0e9cfb694085f1fc9b903e186ee23ba3bf372`;
  candidate has 4023 capacitors and 63660 → 53641 resistors, hash
  `e3afbae2c9c91bbf17e6e45bf9649ab625407fb1d4929cc285d6053bfbd2847f`.
  Every capacitor is retained by the degree-four exact resistor reduction;
  approximate transient certification remains separate.
- `probe_native_driver_restore.py` prepares matched native experiment
  `driver_native_restore/0e89103385daf182` from the original completed
  `receiver_candidate_link/0dee72b71f4525df` loaded fixture. Both drivers
  (clock/data) use their selected audited native model. All receiver, bias,
  DLL, delay, serializer and early-RX closures remain exact. Original supplies,
  channel, 32-bit payload, full 188.049 ns run, publication window and 200 ps
  sampling-margin requirement are retained. The declared numerical change
  is a stricter 20 ps maximum integration step in both cases, with unchanged
  20 ps output step. Twelve unloaded driver-stage observations are added.
  `fixture_recheck.json` verifies exact deck restoration and protected/model
  closure hashes for both actual prepared cases. A manual comparison initially
  normalized the experiment root rather than each case directory; correcting
  that comparison confirms the generated fixtures themselves are unchanged
  except for their explicitly declared model/probe/integration differences.
- Each native case owns an independent shared lease. Both complete even if
  one raises an error, and errors leave terminal held receipts. Reports include
  original decoder/margin checks, clock centers, internal stage voltage/edge
  observations and control differences against the saved parent. Every result
  remains `qualified_phy=false`; diagnostic thresholds do not replace PHY
  criteria. Service `openlvds-native-driver-restore-comparison` is queued
  under the existing six-slot limit. No native ratio improvement is claimed.
  Electrical qualification still requires source/native component coverage,
  headroom/power evidence, RC certificates and the full selected link matrix.
- Five physical/cache/extraction tests and three matched native scope/parallel
  tests pass. Full regression: 455 tests, 454 passed and one skipped. The
  smaller-tail DC matrix remains at eight passing completed cases.


Queue-starvation correction on 2026-11-01:

- Real `/proc/locks` inspection identifies the aperture coordinator holding
  slots 1 and 4. Four long scientific runs hold the other four slots. The DC
  matrix and matched native driver cases repeatedly wait while aperture
  searches finish and reacquire leases. The existing
  `rx_candidate_aperture.lease(wait_slot)` already provides a kernel-blocking
  alternative to the shared allocator's 250 ms polling; that exact lease
  implementation is reused, without changing the global six-slot budget.
- `run_spice_wait_slot.py` is an execution-scheduling wrapper, with separate
  receipts bound to the original scientific manifest and all producer hashes.
  It preserves the scientific manifest, fixtures, cached reports, waveform
  data and engine settings. Each parallel simulation still owns a real shared
  lease; selecting one slot serializes independent cases safely. The serial
  DC matrix can retain one real lease across its remaining short cases and
  cached checks. Retained allocation is unavailable for parallel profiles.
  This scheduling receipt carries no qualification verdict.
- The resource handoff is preserved in
  `resident_jobs/queued_spice_handoff_20261101.py` and
  `resident_jobs/kernel_wait_handoff_20261101.json`. Each retired scientific
  coordinator was quiesced alone, with every thread stopped, then verified
  childless and waiting on incomplete cases with no simulation data. Only
  that coordinator was terminated; no process group or simulator was stopped.
  Actual original manifest, deck, source, cached report and raw/ordered
  waveform hashes are verified unchanged before/after the handoff and bound
  in per-artifact `execution_scheduling/handoff_20261101T045020Z` /
  `handoff_20261101T045021Z` receipts. Cached cases are remeasured by the
  unchanged original producers rather than being recopied into a new context.
- `openlvds-receiver-tail-headroom-matrix-blocking` now waits for slot 1,
  retaining it only for the serial matrix. Its scientific artifact remains
  `receiver_tail_headroom_matrix/eaf3b93c66400e6c`. Both cases of
  `openlvds-native-driver-restore-comparison-blocking` independently wait for
  the same slot after that batch, retaining the original
  `driver_native_restore/0e89103385daf182` manifest. Kernel waiter states are
  captured in `b74f93ef596be915` / `e1c3f4b1772fad30` scheduling receipts.
- The source receiver was deliberately left alone: its modified 1 ps case had
  just started and already had an actual raw file. Ngspice PID 1204428 is
  progressing normally (33.174 ns at the latest recorded prefix), so the
  handoff guard refused to retire that coordinator. Its full 80 ns result
  remains pending; no numerical fix is claimed from the prefix.
- The old childless native watcher is archived at
  `dee37af388e0ca28/native_continuation_history_20261101T044631Z`. Updated
  `continue_receiver_tail_headroom.py` captures the scheduling producer and
  supports an explicit native wait slot. Replacement
  `openlvds-receiver-tail-headroom-native-kernel-wait` watches the unchanged
  active source owner and resumed DC owner. Future native controls use slot 4,
  with all original source/DC/DRC/LVS/RC and complete native waveform gates.
- Four scheduling tests prove real blocking exclusion, unchanged six-slot
  reservation bounds, a single retained serial lease, restoration on failure
  and byte-preserved scientific manifests. Two command tests preserve the
  default native invocation and reject invalid explicit slots. Full regression:
  461 tests, 460 passed and one skipped. No acceptance criterion changed.

The upstream search finds [ngspice issue 887](https://sourceforge.net/p/ngspice/bugs/887/),
which reports failures exactly at coincident PWL corners and an experimental
`minbreak` workaround. It does not establish the cause of these local stalls:
current receiver, original driver control and 20 ps candidate trace endpoints
are about 0.346 / 3.563 / 32.369 ps after their nearest PWL corners. These are
local read-only observations, not a proof that the reported mechanism is absent.
No such workaround, model-version edit or engine substitution is applied.
[Upstream ngspice news](https://ngspice.sourceforge.io/news.html) lists newer
releases, but their compatibility or effect on these fixtures is unverified;
all live campaigns retain the pinned ngspice-42 runtime and SKY130 model set.


Reduced decision-tail source gates on 2026-11-01:

- Matrix `receiver_tail_headroom_matrix/eaf3b93c66400e6c` completes all
  fifteen source DC cases: TT/FF/SS/FS/SF at 0, 25 and 40 °C. All 180
  original static samples pass, including the previously failing SF
  high-common-mode polarity. The physical admission gate remeasures every
  cached waveform and verifies the exact smaller-tail factory closure. Its
  `physical_gate_recheck.json` records 77 proof files and the complete matrix
  summary hash. This is source DC evidence; native DC/rate coverage is pending.
- Modified `clamped_captured` in the 1 ps source retry
  `receiver_clamp/dee37af388e0ca28` completes all 80 ns. Every one of the
  47 original checked periods contains exactly one output transition, with
  zero missing/repeated edges. Transport latency is 343.165203–404.410922 ps.
  The historical task label is retained, but this factory has no CO clamps.
  The final sharp control must still pass before layout/native admission.
- After the modified captured case completed, its coordinator was verified
  childless with only the sharp control pending and no sharp waveform. The
  same guarded scheduling-only handoff preserves both completed control
  traces and the original manifest; no simulator is signalled. Receipt
  `execution_scheduling/handoff_20261101T050300Z/receipt.json` records this
  handoff. Replacement source owner
  `openlvds-receiver-tail-headroom-1ps-source-blocking` has acquired slot 4
  and started the sharp control. Native watcher
  `openlvds-receiver-tail-headroom-native-kernel-wait-v2` follows this owner
  and the completed DC owner; all source/DC/physical/native gates remain.
- The completed serial DC batch released slot 1. The matched native driver
  candidate has acquired it and reached 23.195 ns, beyond the two slow source
  intervals. Its full 188.049 ns result and matched native control remain
  pending. This prefix establishes progress only. The six-slot budget and
  all scientific settings remain unchanged.


Automatic smaller-tail follow-up on 2026-11-01:

- `queue_receiver_followup.py --receiver-profile unclamped_tail_headroom`
  waits for the exact native continuation owner to end successfully, verifies
  both original native clock reports and the selected layout, and rejects a
  replay with another receiver profile. It captures the selected verifier's
  complete producer set plus the source/native continuation inputs. The
  default baseline dispatch remains available.
- After admission, the queue uses `qualify_unclamped_receiver.py` for both
  preparation actions and `continue_receiver_unclamped_candidate.py` for
  execution. Thus all 60 source/native component fixtures and the unchanged
  saved loaded-link fixture use the exact smaller-tail source/native model.
  Children independently remeasure native replay evidence before acquiring
  simulator slots. Terminal failures hold downstream work; final child
  reports must pass and match their captured manifests. These diagnostics
  retain `qualified_phy=false` and do not replace release qualification.
- Unit `openlvds-receiver-tail-headroom-component-link-followup` is active,
  waiting on `openlvds-receiver-tail-headroom-native-kernel-wait-v2.service`.
  Its captured state under `dee37af388e0ca28/component_link_continuation`
  confirms waiting for native replay; no component/link simulation has yet
  started. Original score windows, fixed supplies and six shared slots apply.
- Tests cover baseline/tail dispatch, producer capture, an active owner,
  native failure, a mismatched receiver profile and both child reports. Full
  regression: 462 tests, 461 passed and one skipped.


Reduced-tail source clock admission completes on 2026-11-01:

- All three 1 ps controls in `receiver_clamp/dee37af388e0ca28` complete
  their original 80 ns. Each has exactly one output edge in all 47 original
  checked periods and no missing/repeated edge. Modified captured latency
  is 343.165203–404.410922 ps; modified sharp-control latency is
  288.299607–329.646269 ps. The original source owner exits successfully,
  and the native continuation advances to layout with source/DC remeasurement.
- `matched_source_transport_comparison.json` and its local
  `compare_source_transport.py` bind both completed captured-control reports
  and waveforms. All 47 corresponding input crossings match exactly. Rising
  median latency changes from 299.946 to 360.412 ps; falling median latency
  changes from 337.269 to 355.776 ps. Thus the smaller tail adds latency but
  reduces polarity imbalance. Adjacent unique output crossings imply a
  shortest output low pulse of 473.286 ps versus the unchanged control's
  402.375 ps. These are matched source diagnostics, not native or aperture
  qualification; no threshold or scoring window changes.
- Source/DC admission alone does not qualify the receiver. Physical
  DRC/LVS, independent extraction/connectivity audit, both complete native
  controls, all 60 source/native component checks and the loaded-link result
  are still required before the remaining full-PHY release gates.


Reduced-tail physical result and downstream preflight on 2026-11-01:

- `receiver_layout/30a2456cc94d73ea` passes zero-error DRC and strict LVS:
  70 devices, nine ports, 657.160 × 100.045 µm. Reducing XCT from 64 to
  16 µm removes six parallel device fingers; the declared source topology,
  port order and other devices remain unchanged. GDS hash is
  `fc8dd0bd8d34171f0a279e79ad5ed3a45153d9567e916c33ba1bb9b488cf0fd3`.
- Independent extraction and wire-collapsed connectivity audit both pass.
  Exact degree-four resistor reduction retains all 1015 capacitors and
  reduces 15232 resistors to 12472. Reduced native network hash is
  `1e5eff314a14e905135f523518e47b61fc3ac3c3aa761d974a03fb6a2461aeb5`
  (`build/extracted/86f003b3def20c85/openlvds_receiver_core/`).
  These physical checks do not establish electrical qualification.
- Native replay `receiver_replay/54184829d6357e3c` captures the exact new
  layout and unchanged original captured/sharp stimuli. Both cases retain
  full 80 ns duration, original 5 ps output step and 15–75 ns scoring, with
  declared 1 ps maximum integration inherited from their admitted source
  policy. Each independently waits on slot 4 under the existing shared budget.
- Prepared `receiver_components/d01c4ab5952b857c` contains all 60 original
  source/native static/rate conditions. Prepared loaded-link diagnostic
  `receiver_candidate_link/e5dfd3c8e0281ae5` selects the same physical model
  and original full-RC ideal-phase 32-bit reference. Both are prepared early
  to validate fixture construction; their execution is still native-gated.
- Actual invocation of both run commands refuses execution with
  “Both receiver replay cases must complete first.” Both manifests remain
  byte-identical; neither artifact has execution receipts or waveform/raw
  files. Native replay's `downstream_preflight/receipt.json` records the two
  expected holds and zero simulations started. The automatic follow-up will
  reuse these exact immutable fixtures only after successful native admission.


Native driver training-prefix observation on 2026-11-01:

- The live P64/N24 native case has advanced beyond 56 ns. Its completed
  20–35 ns training window is compared with the original completed native
  observation, using copied finite, strictly monotonic prefixes through
  40 ns. `driver_native_restore/0e89103385daf182/training_prefix/` stores
  the analysis producer, prefix arrays, column maps, prefix/model-manifest
  hashes and diagnostic report. No live producer, circuit or simulator setting
  is edited, and this prefix is not substituted for a complete experiment.
- Complete DN high pulses at the diagnostic 1.65 V crossing level span
  621.448–923.655 ps in the new case versus 123.759–734.732 ps in the
  original observation. DP spans 1644.217–1877.569 ps versus
  1310.171–1488.294 ps. Both are threshold observations, not transistor
  conduction-region measurements.
- At the thirteen clock-pulse centers in this same training window, minimum
  TX/RX magnitudes are 149.443/152.267 mV in the new case versus
  113.389/120.907 mV in the original. Both windows have zero centers below
  100 mV. This does not address the original failing centers in 60–120 ns.
- The matched control remains pending. Original and new diagnostics use
  different extracted GDSs and maximum integration steps, so these results
  do not isolate the sizing effect, establish full-run improvement or qualify
  the driver/PHY. Complete matched native traces and original source/native
  component, headroom/power, RC and loaded-link checks remain necessary.
- Receiver native replay remains kernel-queued on slot 4, now held by the
  live 20 ps source-driver control during operating-point solution. That
  simulation is left undisturbed; no scientific job is restarted or stopped.


Driver component flow and receiver queue retargeting on 2026-11-01:

- `qualify_driver_restore_components.py` prepares all thirty original
  source/native driver process/temperature fixtures for either matched
  physical variant. It verifies both declared source factories, physical
  DRC/LVS/GDS/extraction audits and current baseline component proofs. Only
  the selected driver closure, source include and exact unloaded native
  observation aliases change; bias, stimulus, supplies, loads, transient
  settings and original 2510 ns scoring window remain unchanged.
- Execution requires both complete matched native driver reports before
  calling their producer for cached waveform remeasurement; missing cases
  cannot be launched through that gate. All thirty conditions must pass
  original DC polarity/levels, transition order/cadence and loaded-eye
  voltage criteria. A component verdict cannot qualify the PHY. Prepared
  fixtures, manifest and source/runtime/model inputs are checked around
  slot waits and before final reporting. Parallel cases use independent
  shared leases and finish even when another case fails.
- Actual candidate `driver_components/f3d1cd21d727bcc8` contains all thirty
  fixtures. Its `pending_native_preflight.json` binds the manifest and log:
  execution holds with “Both matched native driver cases must complete
  first,” with zero simulations started. Earlier preparation `00f96295947be647`
  is preserved as historical evidence from before additional integrity checks.
- Five tests verify all required conditions, exact source fixture/bias
  preservation, refusal before complete native coverage, strict waveform/eye/DC
  admission and independent parallel completion on simulator failure. Full
  regression passes: 467 tests, 466 passed and one skipped. Implementation
  commit: `55d30fc`. No existing live producer was edited.
- Real coordinator file descriptors identify DLL slot 3 and the source-driver
  operating-point solve in slot 4. The receiver's two native controls had
  queued behind slot 4 without starting. Guarded handoff
  `receiver_replay/54184829d6357e3c/execution_scheduling/`
  `handoff_20261101T053258Z/receipt.json` verifies every queued coordinator
  thread stopped, no descendants, no native data and unchanged scientific
  manifests/decks/libraries before moving only that coordinator to slot 3.
  No simulator is signalled. The exact handoff command/producer is recorded
  in `resident_jobs/receiver_native_slot3_handoff_20261101.{py,json}`.
- Replacement native owner
  `openlvds-receiver-tail-headroom-native-kernel-wait-v2-blocking.service`
  is active with both controls kernel-waiting on slot 3. Replacement
  `openlvds-receiver-tail-headroom-direct-followup.service` directly watches
  that owner and the exact prepared 60-component/link fixtures. The original
  source-to-native watcher ends after its queued subprocess is retired; its
  old dependent queue consequently holds. Supplemental `superseded.json`
  receipts connect their unchanged historical states to the new owners.
  This operational retirement is not an electrical receiver failure.


Automatic driver component continuation on 2026-11-01:

- `continue_driver_restore_components.py` captures the prepared component
  manifest, all scientific input/producer hashes, its own producer and the
  environment launcher. It verifies the exact matched native comparison
  manifest binding and selected physical variant before observing the owner.
  Active/activating/deactivating owners hold work; observation errors retry.
  A terminal owner must finish successfully, and both complete native child
  reports must exactly match their aggregate and current comparison manifest.
- Only then does the continuation invoke the pinned driver component runner,
  which independently remeasures both native traces and all original fixture
  reconstructions before acquiring any simulator lease. A successful process
  exit alone cannot admit the component campaign: its final report must pass
  and match the exact component manifest. Every continuation state remains
  `qualified_phy=false`; full-PHY release gates remain outstanding.
- Unit `openlvds-driver-restore-component-followup.service` is active,
  waiting on `openlvds-native-driver-restore-comparison-blocking.service`
  for `driver_components/f3d1cd21d727bcc8`. Two eventual workers independently
  use the existing shared six-slot allocator. Its identity/state/producer
  receipts are under the component artifact's `followup/` directory.
- Three tests cover incomplete/wrong native manifests and actual child
  reports, active/failed owners, a component command that exits successfully
  but reports failure, a wrong component-report manifest and changed or
  mismatched physical/producer inputs. Full regression: 470 tests, 469 passed
  and one skipped. Implementation commit: `16d992f`.
- The 20 ps source-driver control has solved its operating point and started
  transient analysis, but advances extremely slowly near 14.9978 ns. This
  is a new numerical stall observation, not a completed comparison or proof
  of repair. The matched native candidate remains live near 97 ns, and
  native FF/0 DLL acquisition remains live near 1608 ns of 1700 ns.


Completed initial native DLL screen and driver steady window on 2026-11-01:

- `dll_qualification/15cac0ba813a9333/loop_ff_0` completes all 1700 ns
  and passes. CTRL ripple is 1.781503 mV, feedback error 7.417610 ps and
  quarter delay 653.018658–653.408804 ps. Marker section delays are
  653.295344/649.270988/638.576953/641.094580 ps; cadence/marker checks
  pass and mean power is 6.365241 mW. Actual deck, ordered waveform and raw
  hashes match the report. All 21 static offsets and SS/TT/FF acquisition
  loops now pass: exactly 24 screen cases. `screen_completion_recheck.json`
  verifies 98 file bindings across all 24 reports/decks/waveforms/raw files.
- The existing native continuation remeasures its completed screen and enters
  `running_stability_screen`, with `measure_dll_stability.py` active for
  SS/0, TT/25 and FF/0. This stage still needs simulator leases and verified
  measured-model/step evidence. Remaining 312 cases of the full 336 and all
  fifteen PVT stability models remain gated; the initial screen is not release.
- Receiver native `sharp_control` in `receiver_replay/54184829d6357e3c`
  acquires the released DLL slot 3 and starts; captured control remains queued
  independently behind it. No receiver native result is yet available.
- The native driver candidate completes the entire diagnostic 60–120 ns
  window and advances past 125 ns. Immutable prefix arrays, column maps,
  producer/manifest/prefix hashes and observations are saved under
  `driver_native_restore/0e89103385daf182/steady_prefix/`. Original/new
  TX clock-center minima are 76.416519/117.255151 mV; RX minima are
  85.215528/133.034402 mV. Among 49 centers per lane in this raw-prefix
  comparison, original TX/RX have 4/3 below 100 mV, whereas the candidate
  has zero below 100 mV on either lane. The full 188.049 ns run and matched
  native control still must finish; different baseline GDS and integration
  settings prevent attributing this unmatched comparison solely to sizing.
- At the same diagnostic 1.65 V crossing level, clock DN changes from
  16 rises/15 falls to 25/24 within 60–120 ns; complete high pulses widen
  from 369.055–714.148 ps to 532.731–1097.661 ps. DP remains 24/25;
  AD/AB and L/R remain 25/25. These are stage observations, not transistor
  conduction-state proof, full decoder admission or a PHY verdict.
- Fresh audited loading inspections `receiver_loading/11bbf00548f00ecc`
  and `f8866328c8821f78` compare standard and reduced-tail receiver GDSs.
  PP/PN incident routing capacitance changes from 100.38130/107.54226 fF
  to 96.07947/103.21285 fF; CT changes from 70.87449 to 30.01471 fF.
  CO/CL/RESTORE0/RESTORE1 remain 35.91650/25.00118/47.75790/58.94737 fF.
  These full-coupling wire values exclude device/MIM capacitance and are
  not effective AC loads. Native replay therefore includes both the intended
  smaller-tail electrical change and its new extracted routing.


Isolated 1 ps source-driver integration experiment on 2026-11-01:

- Both existing 20 ps source cases are live but very slow: the ratio
  candidate near 13.447 ns and unchanged control near 14.998 ns. The
  completed receiver precision experiment motivates a separately captured
  driver retry; it does not establish that the same change will repair these
  source-driver numerical intervals. No earlier simulator is stopped.
- `driver_restore_precision_retry.py` uses the exact original source-driver
  comparison with a 1 ps maximum integration step in both matched controls.
  The original 20 ps output command, complete 188.049 ns duration, initial
  time, circuits, supplies, waveform stimulus, observation nodes, scoring
  windows and original sampling margin remain unchanged. Unexpected original
  durations/output/start/maximum steps are refused. The original fixture/CODE
  bindings are scoped to this process and restored even on exceptions.
- Artifact `driver_restore/5a976ac3781d6832` captures the producer and a
  `numerical_policy.json` binding the original manifest, parent and numerical
  fields. Actual `fixture_recheck.py` / `precision_comparison.json` verify
  both source libraries byte-identical to the original 100 ps experiment and
  both decks identical after only include-path and maximum-step normalization.
  Re-preparation preserves every captured manifest, policy, deck and library
  byte. Tampered policies are rejected before the original runner can execute.
- `openlvds-driver-restore-1ps-source-comparison.service` is active with both
  cases waiting for the existing shared allocator. No additional slot or
  reservation is introduced; no result or numerical repair is yet claimed.
  Full native/component/RC/headroom/link gates remain unchanged.
- Four tests cover exact integration-only changes, refusal of changed or
  shortened fixtures, restoration after failure, policy binding, byte-stable
  preparation and tamper refusal. Full regression: 474 tests, 473 passed and
  one skipped. Implementation commit: `92f6abc`.


Receiver cached-verification race corrected on 2026-11-01:

- The component and loaded-link follow-ups run in separate processes and
  both invoke the same native replay producer for cached remeasurement.
  That producer deliberately uses a nonblocking execution lock; simultaneous
  healthy cache checks could therefore make one follow-up fail before any
  component/link simulation. `qualify_unclamped_receiver.recheck` now uses
  a separate blocking cached-verification lock around this shared operation.
  It revalidates the selected profile and requires all three completed replay
  report files inside that lock, preventing a missing case from launching a
  simulation through the cached path. Exceptions propagate and release the
  lock. All source/waveform/model/PVT/timing gates are retained.
- Only cached replay verification is serialized. The independent component
  and loaded-link simulations retain their parallel workers and the original
  shared six-slot allocation. A real-lock concurrency test proves the second
  check waits, never overlaps the first and resumes after the first throws;
  a separate test proves missing cached cases cannot call the producer.
  Full regression: 476 tests, 475 passed and one skipped. Code commit `52f2891`.
- The waiting direct follow-up watcher is verified childless after all its
  threads quiesce, then retired without signalling a simulator. Exact evidence
  is in `resident_jobs/retire_receiver_cached_check_watcher_20261101.{py,json}`
  and the old watcher's `superseded.json`. Current native/physical/driver
  manifests are checked not to capture the modified selector, so those live
  scientific jobs and their producers remain unchanged.
- Fresh components `receiver_components/e5095fc389735754` and loaded-link
  `receiver_candidate_link/15d06853a0ad3ce1` capture the new selector. Actual
  recheck `receiver_cached_check_fixture_recheck_20261101.py` verifies all
  sixty component libraries byte-identical and all decks identical after only
  include-path normalization, including the loaded-link library/deck. Identity
  contexts differ only in the selector producer hash. The replay's
  `followup_context_replacement.json` captures 248 bindings and verifies zero
  simulations started in either the old or new component/link artifacts.
- Replacement `openlvds-receiver-tail-headroom-serialized-cache-followup.service`
  is active and waiting on the unchanged native owner, selecting these fresh
  artifacts. Its receipts are in replay `followup/e9500fb9e650e5ea`; the
  previous watcher's `replacement.json` links the new owner/context proofs.
  Native sharp replay is progressing beyond 22 ns and the native driver
  candidate beyond 170 ns; complete native results are still required.


Native driver candidate completes; retained receiver clock failure localized
on 2026-11-01:

- `driver_native_restore/0e89103385daf182/restore_64_24` completes the
  original 188.049 ns, with 29904 raw rows and ngspice return code zero.
  The per-case `completion_recheck.json` verifies current manifest, library,
  deck, ordered waveform and completed report hashes. The full report
  preserves the improved clock-center minima: TX 117.255151 mV and RX
  133.034402 mV, with zero checked centers below 100 mV in 60–120 ns.
- The original decoder nevertheless fails: no correctly ordered payload
  preamble and all published words zero. Sampling-margin admission fails.
  This is a complete negative loaded-link result, not electrical/PHY success.
  Matched native control remains queued, so the sizing effect is not isolated.
- `completed_link_localization/analyze.py` and `summary.json` independently
  verify finite, strictly monotonic complete original/new traces through
  188.049 ns, binding the waveform, manifest and report hashes. In 60–120 ns
  the new driver's retained analog receiver clock output stays between
  −7.239 and +5.945 mV, with zero 0.9 V crossings; Q0/Q1 stay near zero.
  RXVALID is high. Thus the recovered-clock signal disappears before the
  digital capture/publication stage, despite improved differential clock pins.
- Data is still driven: TX data has 7 rises/8 falls at 0.9 V; differential
  RX data has 9 rises/9 falls at zero and spans −327.882 to +328.143 mV.
  The retained receiver's RXDATA has only 4 rises/4 falls. Its prior complete
  native SS rate tests likewise held the output near zero. These observations
  support replacing the clamped receiver rather than claiming that better
  driver pin swing alone closes the link. No receiver internal nodes were
  saved here, so a unique internal analog mechanism is not asserted.
- The original completed diagnostic's RXCLOCK still has 24 rises/25 falls
  in this same window and RXDATA has 9/10. Different driver GDS/numerical
  settings mean this remains an unmatched localization comparison. Both
  receiver and driver must still pass their selected native/component gates
  before the combined analog link and full selected PHY are qualified.
- After the candidate releases its lease, the queued 1 ps source-driver
  control acquires slot 1 and starts (ngspice PID 1214447). Matched native
  control remains kernel-waiting on that slot; no process is stopped. The
  receiver native sharp control and DLL measured-model coordinator remain
  active, with the native captured receiver and remaining source cases queued.


Reduced-tail sharp prefix and input placement experiment on 2026-11-01:

- Native sharp replay `receiver_replay/54184829d6357e3c` advances beyond
  50 ns. Its `first_sharp_pulse/` stores immutable prefixes through 30 ns,
  column maps, producer/model/deck hashes and the same 24.5–26.5 ns diagnostic
  window used previously. Standard/new reduced-tail CO peaks are
  1.356111/1.233518 V; RESTORE0 minima 82.448/236.534 mV. Both recover
  this sharp pulse: standard output fall/rise 25.723799/26.128155 ns, new
  25.809655/26.187368 ns. This local observation does not qualify the full
  80 ns sharp control or the still-queued weak captured-input control.
- `layout_receiver_input_island.py` explores placement only: it preserves
  every exact source device/finger/model/dimension/node and moves the four
  input mirror output banks and ten load resistors immediately before the
  decision stage. All other device order, including the admitted unloaded
  monitor placement, is retained. The source is byte-identical to reduced-tail
  reference `30a2456cc94d73ea`; source/DC gates are remeasured unchanged.
- Alternative `receiver_layout/f0f9ee68d2a80ba2` passes zero-error DRC,
  strict LVS and independent extracted connectivity audit: 70 devices,
  nine ports, 657.160 × 100.045 µm. Its GDS hash is
  `ec1687c02706de3876e6cbf0e785359c77625a75be3f2e8eac6cbae3e24bea13`.
  Exact reduction retains all 1031 capacitors and reduces 15234 resistors to
  12507, network hash
  `469e760c9619668808006f992d1c61ebf1e6386ab9d1cacb9af2c9df0e3da250`
  (`build/extracted/8736fe0c98351e95/openlvds_receiver_core/`).
- Loading `receiver_loading/c540d6e865f9d33a` reduces PP/PN incident wire
  capacitance from 96.07947/103.21285 fF to 80.78245/74.77354 fF. However,
  the full `input_loading_comparison.json` also checks upstream mirror nodes:
  NL/NR increase from 60.71743/61.92002 to 81.91689/85.17926 fF; PL/PR
  increase from 62.79109/70.95722 to 67.63202/73.33675 fF. CO/CL/CT
  remain 35.91650/25.00118/30.01471 fF. These incident full-coupling wire
  loads exclude device capacitance and are not effective AC loads or timing
  proof. The mirror-node penalty may offset the smaller decision-input load.
- Consequently this alternative is retained for diagnosis, without replacing
  the running native layout or launching a new native replay. A useful next
  layout experiment should reduce decision-node routing without lengthening
  upstream mirror-control nets, for example by changing sensitive-net bus
  priority while preserving the original device order. It must still pass
  exact source/physical/audit and complete native controls.
- Immutable caching records every actual GDS/schematic/DRC/LVS/source/report
  hash and refuses changed or partial geometry. Actual cached evidence is
  verified without redrawing. Three structural/cache tests pass; full
  regression: 479 tests, 478 passed and one skipped. Code commit `dc06552`.
- The 1 ps unchanged source-driver control terminates numerically at
  13.782610 ns (14326 raw rows), reported timestep 1.25e−24 s and node
  `xtx.vgnd.t436`. `driver_restore/5a976ac3781d6832/source_control/`
  `failure_observation.json` binds its log/raw/deck/library/manifest/policy.
  Its inherited execution receipt remains stale `running`; actual PID 1214447
  is gone and ngspice explicitly reports aborted. No performance verdict is
  issued. The ratio case remains queued, so the comparison is incomplete.
  The released slot now runs matched native driver control, PID 1215510.
  Further precision-only changes are not established as a repair.


Receiver bus-order experiment and captured-prefix diagnosis on 2026-11-01:

- Reduced-tail native `receiver_replay/54184829d6357e3c/sharp_control`
  completes all 80 ns. All 47 original checked periods contain exactly one
  output transition; zero missing/repeated edges. Latency is
  853.026050–1072.241020 ps. Its `completion_recheck.json` verifies the
  exact library, manifest, deck and ordered waveform bindings. Captured-input
  replay has acquired slot 3 and is running; the full native gate is pending.
- `layout_receiver_bus_priority.py` changes only the internal bus-order
  assignment in the captured drawing function. A guarded syntax-tree
  specialization preserves every other drawing statement, including device
  transforms, bus widths and public pins. The order is PP/PN/CO/CL/CT/
  NL/NR/PL/PR, followed by remaining internal nets. Source/DC admission and
  immutable physical caching remain. Unknown routing code or missing nets
  is refused. This alternative does not alter active layout pointers.
- `receiver_layout/5fae56c00f7706ad` passes zero-error DRC, strict LVS
  and independent extraction/connectivity audit. All 70 devices, nine ports,
  657.160 × 100.045 µm dimensions and public pin positions match reference
  `30a2456cc94d73ea`. Actual `routing_scope_recheck.json` verifies identical
  source bytes, flattened schematic and every device transform. GDS hash is
  `c7fd75bb4aaf5a2b0f2b7bd08987f20e33e4891b8b43cf41bed28413df1d843b`;
  native network hash
  `edc3c2af481a47140dad7d000a995b14ce2fde858f34b5c6019994b29298c969`
  (`build/extracted/ae0110e5e51039e6/openlvds_receiver_core/`). Exact
  reduction retains all 1058 capacitors and reduces 15232 resistors to 12502.
- The result is a negative routing experiment. Its full
  `input_loading_comparison.json` reports PP/PN increasing from
  96.07947/103.21285 fF to 98.78515/111.21920 fF; CO/CL increase from
  35.91650/25.00118 fF to 39.83411/28.85147 fF. NL/NR/PL/PR improve
  modestly, but sensitive-node incident capacitance does not. Wire length
  alone did not predict full coupling capacitance. No native replay is
  launched for this alternative. Three routing/geometry tests pass; full
  regression: 482 tests, 481 passed and one skipped. Code commit `54ab292`.
- Captured replay's `first_captured_pulse/` stores immutable prefixes through
  30 ns. In the original 24.5–26.5 ns local observation, reduced-tail CO peaks
  at 0.709227 V versus standard-tail 0.676372 V, and RESTORE0 remains
  above 1.783265 V. `known_complete_periods.json` applies the unchanged
  15–75 ns matching rule only to periods whose next same-polarity edge
  already exists in the prefix. Both layouts have three missing edges in
  ten complete available periods. Specifically the 24.777050 ns falling
  pulse is 526.689 ps wide, peaks at 108.848 mV and has no corresponding
  output crossing before the next input period. This confirms a local missed
  edge, while the original full 80 ns run continues for its complete report.
- Source-only `decision_threshold_envelope.json` sidecars bind all 180
  original DC samples for standard-tail matrix `1ac68453f143818d` and
  reduced-tail matrix `eaf3b93c66400e6c`. Standard-tail expected-output-high
  CO can reach 0.915188 V (FS/40) while expected-output-low CO can be as
  low as 0.703679 V (SF/0); a single ideal fixed threshold cannot separate
  that complete set. Reduced-tail extrema are 0.934215 V and 1.380087 V,
  a 0.445871 V gap. These envelopes are not measured inverter transfer
  curves or native admission, but support preserving the DC headroom fix.
- A concrete next placement test is to move the six unloaded reference
  monitor devices after all functional devices, preserving their circuit and
  all other device order. That removes them from the physical decision-output
  to first-restorer span without lengthening upstream mirror nets. Measure
  CO and all input-stage loads before deciding to simulate this alternative.
- The 1 ps source-driver pair is explicitly held after its unchanged control
  aborts. Its remaining ratio case was unstarted; its coordinator is quiesced,
  verified childless, then retired alone. No simulator is signalled and all
  failed-control/fixture/manifest bytes are preserved. Exact receipt/procedure:
  `resident_jobs/hold_failed_driver_precision_20261101.py` and
  `driver_restore/5a976ac3781d6832/held_after_control_abort.json`. Required
  coverage remains two, with zero complete, one numerically failed and one
  unstarted. No incomplete source comparison is admitted as passing.


Decision-output placement improvement on 2026-11-01:

- `layout_receiver_monitor_after.py` moves only the six unloaded XTRACK
  fingers after all functional devices. `receiver_layout_reference.py`
  shares the source-bound validation/cache/build policy for this experiment.
  Before drawing it captures the original device multiset and refuses any
  change of model, parameter, node, instance or count, including accidental
  in-place mutation by a placement callback. Policy overrides cannot replace
  source/admission metadata. Original source/DC gates are remeasured.
- New `receiver_layout/8be736a2b11e5b89` passes zero-error DRC, strict
  LVS and independent extracted connectivity audit: 70 devices, nine ports,
  657.160 × 100.045 µm. Actual `placement_scope_recheck.json` verifies
  identical source bytes and the complete flattened device multiset, with
  every functional device retaining its relative order. CO-connected device
  origin span falls from 71.10 to 28.44 µm. That geometric observation is
  not itself a capacitance/timing verdict.
- Extraction confirms the intended load change. Its
  `input_loading_comparison.json` reports CO incident routing capacitance
  35.91650 → 28.24057 fF; PP/PN 96.07947/103.21285 →
  92.04186/99.08609 fF. NL/NR/PL/PR remain effectively unchanged at
  60.71743/61.92006/62.79109/70.95722 fF; CL/CT also remain essentially
  unchanged. These are full incident coupling wire values, excluding device
  capacitance, and still require native timing verification.
- GDS hash is
  `7d668f0234c7419ec42e0cae7684ad95ef84ea7105484d7d6a80db55cea3ee32`.
  Exact reduction preserves all 1012 capacitors and reduces 15236 resistors
  to 12499, native hash
  `178acfa1051455861d35031f91a4deeeea21edf12a9d844a680287e6bebd8293`
  (`build/extracted/d351f4892818f104/openlvds_receiver_core/`). Five tests
  cover exact monitor-only movement, malformed device mutations, missing
  monitor fingers, immutable/partial caches and protected admission metadata.
  Full regression: 487 tests, 486 passed and one skipped. Code `030df0e`.
- Native `receiver_replay/822c30476339d818` prepares both original full
  80 ns controls with the inherited declared 1 ps maximum step, 5 ps output
  command and 15–75 ns analysis window. Actual `fixture_recheck/summary.json`
  verifies both decks identical to previous native replay after include-path
  normalization; the selected receiver matches its audited RC and both
  unrelated replay closures (bias and digital RX) are identical. A manual
  checker initially assumed the full-link library's roots; correcting it to
  this replay's actual two protected roots passes without changing fixtures.
- `openlvds-receiver-monitor-after-native.service` has both cases queued
  independently on shared slot 3. Prepared full 60-case component campaign
  `receiver_components/d6fda107c33d401a` and loaded link
  `receiver_candidate_link/e8fada5af2c6c3a0` select this exact layout/replay.
  `openlvds-receiver-monitor-after-followup.service` is active, waiting for
  both native controls to pass. Actual downstream run preflights refuse
  execution before native completion, preserve both manifests and start zero
  simulations; replay `downstream_preflight/receipt.json` records this.
  No voltage/timing/PVT/coverage gate or active pointer is changed.

Capacity review on 2026-11-01:

- Four live source diagnostics currently occupy four of six simulator slots.
  Two observations 137.215 seconds apart measure advances of
  0.000190260 / 0.000010773 / 0.000000361 / 0.000168779 ns for
  PIDs 1191416 / 1194729 / 1199093 / 1207333. These are live processes,
  not jobs declared terminal from an observation timeout. Required native
  receiver and driver controls are still progressing in the other slots.
- `resident_jobs/stalled_source_retirement_proposal/proposal.json` binds
  exact three source-diagnostic units, process start ticks, commands/cgroups,
  immutable available raw-prefix snapshots, scientific inputs and protected
  completed-case proofs. It proposes retiring only these four simulations,
  preserving incomplete evidence rather than admitting any result as passing.
- This proposal changes the current practice of leaving live simulations
  untouched, so user approval was requested asynchronously. Its status is
  `pending_user_approval`; no simulator has been signalled. Native/PVT work
  and the unchanged six-slot budget continue while a decision is pending.


Decision-load circuit experiment on 2026-11-01:

- Monitor-after native replay `822c30476339d818` still runs its original
  full 80 ns captured case. Its `first_captured_pulse/summary.json` measures
  CO peak 0.753394 V versus 0.709227 V before relocation, but neither
  layout produces an output crossing for the original 526.689 ps pulse.
  `first_captured_pulse/check_periods.py` applies the original scoring rule
  only to complete available periods: both prefixes have three missing
  edges in ten periods. This is a negative prefix observation, not a
  completed native report; the full controls remain required.
- `receiver_decision_load_experiment.py` changes only the decision PMOS
  diode/mirror XCD/XCM from W8 to W32, retaining L0.15, original W64/L0.5
  decision tail, W8 input pair, removed clamps and original stronger
  restoration buffers. This compares against the standard unclamped W64
  control, not against the reduced-tail W16 circuit. The hypothesis is to
  raise the decision common-mode/headroom while retaining higher charging
  current. Actual static and dynamic results must decide whether that works.
- `receiver_decision_load_static.py` remeasures a completed original control
  and verifies its exact factory closure, immutable fixtures, inherited input
  hashes, producer hashes and pinned runtime. The candidate changes only
  those two widths and adds unloaded CL/CT/NBC observations. It preserves
  the original 144 ns, all twelve sampling points and 100 fF output load.
  Full finite, monotonic waveforms are required; cached reports are
  remeasured, and partial executions are retained rather than overwritten.
- Three pilots are queued on actual shared slot 1, within the six-slot
  budget: TT/25 `receiver_decision_load_static/e33c866803601b0d`, SF/40
  `51e8be8847013846`, FS/40 `21e1c870086d1f65`. Services are
  `openlvds-decision-load-{tt25,sf40,fs40}`. All remain waiting at this
  observation; no passing electrical result is claimed. A preparation-only
  TT artifact `abd07dedf91fbbfc` predates the stronger inherited-input and
  partial-run guards and has never been queued.
- Admission order remains: three pilots, all fifteen source static corners,
  original three source clock controls, physical DRC/LVS/RC audit, both
  full native replay controls, full component and loaded-link gates. Do not
  queue clock or physical work for this circuit before its static gate passes.
  The reduced-tail circuit retains its demonstrated DC evidence separately.
- Matched native driver comparison `driver_native_restore/0e89103385daf182`
  is now complete for both cases. Both fail the full decoder/margin gates.
  In the matched 60–120 ns observation, receiver-input minimum magnitude
  improves from 86.644 to 133.034 mV, but the stronger-driver clock output
  has no crossings. Component campaign `driver_components/f3d1cd21d727bcc8`
  has started independently; its first schematic TT/0 case passes. Full
  thirty-case component admission is still pending and cannot establish
  complete link qualification by itself.
- Four targeted tests cover the exact two-device intervention, unchanged
  static fixture, all original sampling points, and rejection of incomplete,
  nonfinite, nonmonotonic or missing-observation data. No live simulator was
  stopped, scientific gate weakened, or active analog pointer promoted.

- Validation after the decision-load addition: 491 regression tests, 490
  passed and one skipped. All four new targeted tests pass.


Full decision-load DC gate prepared on 2026-11-01:

- `receiver_decision_load_matrix.py` prepares exactly the fifteen required
  source process/temperature points from the completed standard unclamped
  control matrix, ordered with TT/25, SF/40 and FS/40 first. It captures the
  complete child manifests, source selection, current requirements and code.
- Matrix `receiver_decision_load_matrix/6fd0fd7ce4169f32` reuses the three
  live pilot artifacts without changing their manifests. Before running any
  remaining case it requires every pilot's complete report, remeasures each
  actual waveform through the scientific runner, and requires all three to
  pass. Incomplete or failed pilots cannot launch remaining simulations.
- Actual run preflight refuses incomplete pilots and records
  `incomplete_pilot_preflight.json`: fifteen required cases, zero complete,
  zero new simulations. This is an expected admission hold, not a numerical
  failure. Four targeted matrix tests exercise exact coverage, pilot order,
  missing results, failed results and mandatory remeasurement/hash binding.
- The full matrix is prepared but not running. Once all independent pilot
  owners finish successfully, resume with
  `./scripts/env.sh --ngspice python3 scripts/receiver_decision_load_matrix.py run build/diagnostics/receiver_decision_load_matrix/6fd0fd7ce4169f32 --wait-slot 1`.
  It holds a shared lease only during each actual uncached child simulation;
  it does not retain a lease while invoking nested runners.

- Matrix regression: 495 tests, 494 passed and one skipped; all eight
  decision-load factory/static/matrix tests pass.

Completed monitor-after captured replay on 2026-11-01:

- `receiver_replay/822c30476339d818/captured` has finished its complete
  original 80 ns. The scientific report checks 47 periods and finds eighteen
  missing edges (nine rising and nine falling), matching the previous
  monitor-before reduced-tail layout. The sharp-control simulator has now
  started; no aggregate completion or downstream admission is claimed.
- `completed_captured_comparison/analyze.py` independently remeasures both
  complete captured waveforms with the original 15–75 ns period rule and
  verifies reports against waveform/deck/library/manifest hashes, current
  code, inherited inputs and runtime. Both layouts miss exactly the same
  eighteen input edges and have no extra edges. The lower wire capacitance
  and larger first-pulse CO swing therefore do not resolve the captured
  clock failure. Continue the stronger-PMOS circuit's static pilots before
  another physical receiver build.


First stronger-PMOS pilot result and DC continuation on 2026-11-01:

- SF/40 pilot `receiver_decision_load_static/51e8be8847013846` completed
  and passes all twelve original static samples. At the previously failing
  130 ns high-common-mode sample, the unchanged standard-tail control gives
  CO 0.743371 V and Q 1.799990 V (incorrect high). The stronger PMOS
  candidate gives CO 1.186662 V, CL 0.674832 V, CT 0.206839 V and
  Q approximately 0 V (correct low). This is source DC evidence at one
  corner; no dynamic or native performance is inferred.
- TT/25 and FS/40 pilots still wait on the original shared slot. The DLL
  delay_0 trace completed and delay_1 is live and advancing; the native
  monitor-after sharp control is also live. No stalled source run is stopped.
- Resource-only `receiver_decision_load_matrix/6fd0fd7ce4169f32/followup/run.py`
  was first attempted as `openlvds-decision-load-dc-followup.service`. It captures
  current code/environment/matrix hashes and waits for all three exact pilot
  units to become inactive with successful status. Transient observation
  failures retry; unsuccessful terminal owners hold. The existing scientific
  matrix runner then remeasures the pilot waveforms before any remaining
  simulation, so successful process exit alone cannot admit a failed pilot.
  The follow-up uses slot 1 and the unchanged six-slot budget. It will
  report full DC success only from the actual fifteen-case passing report;
  source clock, physical and native admission remain separate requirements.

- The first follow-up correctly held before launching any case because
  systemd had garbage-collected the successful SF/40 transient unit. Its
  original failed receipt is preserved. New resource context `followup_v2/`
  (`openlvds-decision-load-dc-followup-v2.service`) accepts an inactive,
  not-found owner only when its complete child report binds the expected
  manifest; loaded unsuccessful owners still hold. This does not substitute
  for waveform validation: the scientific matrix remeasures all pilots before
  running any remaining case. The v2 service is verified active and waiting
  for the still-live TT/25 and FS/40 owners.


Gated stronger-PMOS source clock implementation on 2026-11-01:

- `receiver_decision_load_clock.py` first requires a completed, passing
  fifteen-case DC matrix and remeasures every existing child through its
  scientific runner. Missing reports are refused before preparing any clock
  artifact, so cached admission cannot start missing DC simulations.
- Clock preparation derives a fresh immutable context from the declared
  stronger-PMOS factory. All original source/library bytes, pin stimuli,
  print observations, full 80 ns duration, 5 ps output step and original
  15–75 ns scoring window remain; only the maximum integration step becomes
  1 ps for all three controls. The new identity directly captures every DC
  proof, source-template file and numerical policy. Existing or executed
  source contexts are never edited. Legacy task names `clamped_*` identify
  the modified factory here; neither source variant contains CO clamps.
- Source admission requires exactly the three original controls, 47 scored
  periods per control, zero missing and zero repeated edges, with complete
  finite monotonic waveforms. `source_clock_admission.json` is separate from
  the diagnostic report and never establishes physical/native/PHY admission.
  Partial failed traces are preserved and refused for in-place retry.
- Actual `6fd0fd7ce4169f32/source_clock_preflight/receipt.json` proves
  preparation refuses the incomplete DC matrix and creates zero new source
  contexts. Five new tests cover byte-preserving fixture derivation,
  immutable re-preparation, changed/incomplete fixtures, incomplete or failed
  DC admission, missing controls and missing/repeated clock edges.
- Resource-only `clock_followup/run.py` is verified active as
  `openlvds-decision-load-clock-followup.service`. It waits for the exact
  full-DC owner to finish and requires its full passing report; it then calls
  the gated scientific prepare/run commands. Context/code/environment hashes
  are captured. A collected systemd owner is accepted only with complete
  manifest-bound passing evidence; missing evidence or failed owners hold.
  Clock runs use actual shared slot 1 within the unchanged six-slot budget.
- Full regression: 500 tests, 499 passed and one skipped; all thirteen
  decision-load tests pass. No new clock case is running or claimed passing
  at this observation. SF/40 remains the sole completed static pilot.


PMOS-only rejection and uniform decision scaling on 2026-11-01:

- All three PMOS-only W32 pilots are now complete. TT/25 and SF/40 pass;
  FS/40 fails original 22 ns and 46 ns low-common-mode, positive-polarity
  samples. CO is 1.033041 / 0.984529 V and Q remains approximately
  0 V instead of the required high. The standard-load control at these
  same samples gives CO 0.915188 / 0.858569 V and correct high Q.
  Increasing only the PMOS mirror raises CO in both polarity conditions;
  its SF headroom benefit does not establish all-corner restoration.
- `receiver_decision_load_matrix/6fd0fd7ce4169f32/rejected_static_pilot.json`
  binds the failed report and actual waveform. The automatic full-DC gate
  remeasures the completed pilots and holds on the actual FS failure.
  Its clock continuation also holds. Exactly three pilot simulations ran;
  zero of the remaining twelve DC cases and zero clock cases were launched.
  The gate prevented unnecessary downstream work without moving criteria.
- `receiver_scaled_decision_experiment.py` implements a different hypothesis:
  uniformly scale all five decision devices by four from the independently
  DC-passing reduced-tail receiver. XCT goes W16 to W64; XC0/XC1 and
  XCD/XCM each go W8 to W32, with original models, nodes, lengths and all
  other circuit devices unchanged. This preserves decision-device sizing
  ratios and seeks more charging current. It also increases PP/PN gate
  loading, so a DC pass cannot establish dynamic improvement.
- Preparation remeasures the completed reduced-tail static control, verifies
  its exact declared source closure and full waveform, and binds inherited
  inputs, code and runtime. The original 144 ns deck already contains the
  unloaded CL/CT/NBC observations; only its source inclusion is rebound.
  All twelve sampling times, supplies, stimuli and 100 fF load remain.
  New waveform validation rejects incomplete/nonfinite/nonmonotonic data;
  partial failures are retained and cached measurements rechecked.
- New pilots under `receiver_scaled_decision_static/` are queued on actual
  shared slot 1: TT/25 `de8b99d5cb7a5d5e`, SF/40 `aeb25b9ac3f5874e`,
  FS/40 `d3d3385283fb72cb`. Units are `openlvds-scaled-decision-{tt25,sf40,fs40}`.
  None is yet complete. The original six-slot budget and live jobs remain.
- Three new tests verify the exact five-device intervention and every other
  circuit/device, all five width ratios, refusal of wrong/repeated topology,
  and prevention of an uncached control simulation during preparation.
  Full regression: 503 tests, 502 passed and one skipped. No analog pointer
  or physical/native/PHY admission is promoted.


Uniform-decision full DC admission prepared on 2026-11-01:

- `receiver_scaled_decision_matrix.py` prepares exactly all fifteen original
  process/temperature source DC conditions from completed reduced-tail matrix
  `eaf3b93c66400e6c`. Each control is independently remeasured before cloning
  the uniform five-device width scaling. Selection uses the existing exact
  coverage/name checker; the new matrix captures that helper's code as well.
- Matrix `receiver_scaled_decision_matrix/a3a34b4ac8e5f600` reuses the same
  TT/25, SF/40 and FS/40 pilot contexts. Before any remaining case it requires
  complete manifest-bound pilot reports and remeasures all three actual
  waveforms. Any failed pilot holds the remaining simulations. Every child
  retains the original twelve points and full 144 ns static fixture.
- Actual `incomplete_pilot_preflight.json` binds an expected hold with zero
  additional nonpilot simulations. Resource-only `followup/run.py` is verified
  active as `openlvds-scaled-decision-dc-followup.service`, waiting for those
  exact pilot owners. Its immutable code/context receipts and handling of
  successful collected units follow the prior corrected resource policy.
  The scientific matrix, rather than service exit alone, decides admission.
- Three targeted tests verify that missing reports cannot invoke the runner,
  failed remeasured pilots block advancement, and passing flags require
  complete reports bound to the expected manifests. Full regression: 506
  tests, 505 passed and one skipped. All six uniform-decision tests pass.
- At this observation all three uniform-scaling pilots still wait on actual
  shared slot 1. The live native sharp-control simulator continues separately.
  No old scientific code, live simulator, supply, sampling rule or six-slot
  resource limit was changed. Source clock and downstream physical/native
  gates have not been admitted for the uniformly scaled circuit.


Uniform-decision clock handoff and completed native rejection on 2026-11-01:

- FS/40 uniform-scaling pilot `receiver_scaled_decision_static/d3d3385283fb72cb`
  passes all twelve original DC samples. In particular Q is high at both
  22 and 46 ns, which failed with PMOS-only scaling. TT/25 already passes;
  SF/40 is still queued. The remaining twelve DC cases stay held until all
  three pilots pass and their actual waveforms are remeasured.
- `receiver_scaled_decision_clock.py` reuses the immutable source-clock
  reconstruction and admission helpers with an explicit uniform-scaling
  factory profile. Its control is the reduced-tail receiver, and the modified
  source scales all five decision devices together. The profile restores
  every temporary factory/gate binding on success or error. Preparation
  captures inherited code from all actual DC manifests, including source
  factory dependencies, before deriving a fresh full three-control context.
- Clock admission retains all original stimuli and probes, full 80 ns,
  5 ps output step, 1 ps maximum integration and original 15–75 ns scoring.
  All three controls must have exactly one output per original 47 periods,
  complete finite monotonic traces, and unchanged static evidence. This is
  source-clock admission only; all physical/native/component/link gates remain.
- Actual `a3a34b4ac8e5f600/source_clock_preflight/receipt.json` proves that
  incomplete full DC evidence refuses preparation and creates zero clock
  contexts. `clock_followup/run.py` is verified active as
  `openlvds-scaled-decision-clock-followup.service`, waiting for the exact
  full-DC owner and a manifest-bound fifteen-case passing report. It freezes
  the leaf and shared helper code/environment and uses the unchanged global
  six-slot budget and actual shared slot 1.
- Three new tests verify exact profile selection, restoration of temporary
  factories/code on errors, and refusal of uncached DC or clock preparation
  from incomplete evidence. Full regression: 509 tests, 508 passed and one
  skipped; all nine uniform-decision tests pass.
- Native monitor-after replay `receiver_replay/822c30476339d818` is now
  fully complete and independently remeasured through the serialized cached
  verifier. Both original 80 ns cases contain 47 scored periods. Sharp
  control has zero missing/extra edges; captured control has eighteen
  missing (nine rising, nine falling), zero extra. `completion_recheck.json`
  binds the full scientific reports, waveforms, decks and manifest. The
  native owner exits successfully as a completed diagnostic; its actual
  electrical failure correctly holds the downstream owner. Both prepared
  component `d6fda107c33d401a` and link `e8fada5af2c6c3a0` still have
  zero simulations. No failed native branch is promoted.


Uniform-decision physical gate prepared on 2026-11-01:

- `layout_receiver_scaled_decision_candidate.py` requires all three completed
  source-clock controls, their passing admission, and the exact correlated
  full DC matrix before any geometry is drawn. It serializes cached source
  remeasurement separately from the scientific execution lock; missing
  results cannot launch missing simulations through a cache-verification path.
- The source is reconstructed from the exact uniform-scaling factory. New
  metadata explicitly identifies `unclamped_uniform_decision_scale4`,
  decision input/load W32 and tail W64, retaining input-tail scale 2 and
  original three restoration buffers. This is distinct from the old reduced-
  tail profile and cannot acquire its native/component admission implicitly.
- Placement reuses the monitor-after ordering and verifies the full device
  multiset before drawing, including all nodes, models and parameters.
  Geometry caches verify all seven physical evidence files, preserve partial
  builds for diagnosis and refuse changed source or identity. The source
  flattening has 88 devices and nine ports; those are not yet GDS/LVS counts.
- `a3a34b4ac8e5f600/physical_preflight.json` binds the actual expected refusal
  from missing source-clock results and zero generated layouts. Resource-only
  `physical_followup/run.py` is verified active as
  `openlvds-scaled-decision-physical-followup.service`. It waits for the exact
  clock owner and hash-bound passing source report, then invokes the gated
  Magic DRC/LVS build and independent extracted-connectivity audit. It freezes
  code/context/environment, handles completed collected owners, and leaves
  native/component/link/PHY admission explicitly pending after extraction.
- Three tests check exact scaled devices and functional placement order,
  incomplete-clock refusal before rechecking or launching simulations, and
  prevention of drawing after a failed source gate. Full regression: 512
  tests, 511 passed and one skipped; all twelve uniform-decision tests pass.
  No geometry or source-clock case has yet run for this branch. SF/40 remains
  queued; TT/25 and FS/40 are the only completed uniform-scaling pilots.


Uniform-decision pilot gate passed on 2026-11-01:

- SF/40 `receiver_scaled_decision_static/aeb25b9ac3f5874e` completes and
  passes all twelve original samples. All three pilots now pass. The actual
  scientific matrix remeasures their waveforms and advances to the remaining
  source DC corners; TT/0 also completes by this observation. All required
  fifteen conditions remain; no partial matrix is admitted as complete.
- `a3a34b4ac8e5f600/pilot_threshold_envelope.json` binds all thirty-six
  completed pilot samples and their actual manifests/reports/waveforms.
  Expected-output-high CO is at most 0.913786 V (FS/40 at 22 ns);
  expected-output-low CO is at least 1.426299 V (FS/40 at 10 ns), leaving
  a 0.512513 V ideal fixed-threshold separation for these pilots only.
  This is not a measured inverter transfer curve or a full-PVT/native bound.
- The full-DC owner remains live. Clock and physical continuations wait for
  their exact upstream owners and actual passing full reports. No clock case
  or new geometry is started from the pilot result alone. All shared slot
  ownership, fixed supplies, original fixtures and failure criteria remain.


Uniform-decision native replay prepared on 2026-11-01:

- `probe_receiver_scaled_decision_candidate.py` implements a distinct native
  profile for decision scale four, tail W64 and input/mirror W32. It rejects
  the old reduced-tail and PMOS-only metadata, then requires the exact source
  factory, current full source/DC proofs, DRC/LVS, GDS/source binding and an
  independent native connectivity audit before preparing either replay case.
- Assembly preserves the exact shared bias and digital RX closures. Both
  original captured/sharp fixtures retain full 80 ns, 5 ps output, original
  pin stimuli/load and 15–75 ns scoring; maximum integration is explicitly
  1 ps in both. Prepared library/deck/manifest caches cannot be rewritten.
  Both case IDs must be present exactly once. No new native context exists
  at this observation because the required audited geometry is not built.
- Each actual simulator takes its own shared lease, with zero, one or two
  selected wait slots allowed only inside the existing six-slot budget.
  Resource receipts are separate from the immutable scientific manifest.
  Complete finite monotonic waveforms and current hashes are required;
  cached reports are remeasured and partial failed traces retained rather
  than rerun in place. Failed case execution is recorded explicitly, while
  the independent other control is allowed to finish.
- The native aggregate distinguishes a completed diagnostic from passing
  clock transport: both original 47-period cases must have exactly one output
  edge per period. `native_clock_passed` does not imply full PVT, component,
  stress, power, aperture, loaded-link or PHY qualification. Existing legacy
  selectors do not silently admit this new profile.
- Actual `a3a34b4ac8e5f600/native_preflight.json` proves missing audited
  geometry refuses preparation and creates zero native contexts.
  `native_followup/run.py` is verified active as
  `openlvds-scaled-decision-native-followup.service`, waiting for the exact
  physical owner and its completed extraction/audit. It freezes code and
  parent context, then calls the scientific prepare/run gates using selected
  slots 1 and 3 independently. Failed native transport holds further admission.
- Five new tests verify strict profile selection, original numerical fixture,
  missing-geometry refusal, preservation of both partial traces without any
  simulation launch, and actual cached waveform remeasurement/incomplete-
  waveform refusal. Full regression: 517 tests, 516 passed and one skipped.
  All seventeen uniform-decision tests pass. The actual full DC campaign has
  eight passing cases; SS/0 is queued for its shared lease. Source clock,
  physical and native continuations remain gated on completed evidence.


Uniform-decision component/link selector prepared on 2026-11-01:

- `qualify_scaled_receiver.py` explicitly selects the new native profile for
  the unchanged receiver component and saved reference-link engines. It
  requires the exact uniform-decision metadata; old reduced-tail and PMOS-only
  profiles cannot be substituted. Factories, verifiers and producer-code
  bindings are restored after preparation/run success or any error.
- Before integration can start, both actual native waveforms are remeasured
  through their scientific producer. Complete case reports must already
  exist, so this cache path cannot launch a missing native simulation. A
  shared blocking cache-verification lock serializes the independent component
  and link consumers. The new `native_clock_passed` result must be true and
  bound to the current manifest, in addition to the existing transport gate.
- The original component engine retains all sixty source/native DC/rate
  conditions and exact fixture reconstruction. The link engine retains the
  saved full-RC ideal-phase SS/40, 410 MHz, 32-bit diagnostic reference
  `build/link/ss_40_410m_d0.45_s100_e0_ideal_32/6735242e52a2`.
  This receiver-only diagnostic does not establish final selected-driver,
  measured-DLL, early-digital-RX or full-PHY qualification. Uncached partial
  integration traces are refused for in-place retry and retained for diagnosis.
- Actual `a3a34b4ac8e5f600/integration_selector_preflight.json` binds the
  current selector and completed old native replay. Both component and link
  preparation reject that profile before creating any diagnostic context.
- Resource-only `integration_followup/run.py` is verified active as
  `openlvds-scaled-decision-integration-followup.service`. It waits for the
  exact native owner and passing hash-bound report, then prepares the full
  sixty-case suite and reference-link check. Two component workers and one
  link process use independent actual shared leases within the unchanged
  six-slot limit; no outer lease is retained around child workers. Both
  diagnostics must report passing results bound to their actual manifests.
  Fresh selected-analog/digital assembly and complete release gates remain.
- Six tests verify exact profile selection, restoration of temporary bindings,
  missing-case refusal, rejection of false native admission despite successful
  exit, real flock serialization for both cache consumers, and partial-trace
  preservation. Full regression: 523 tests, 522 passed and one skipped.
- The actual full DC campaign now has nine completed passing cases, including
  SS/0. SS/25 is next in the live campaign. No new receiver clock, geometry,
  native replay, component or reference-link simulation is admitted yet.


Changed-decision terminal observations on 2026-11-01:

- `receiver_decision_headroom.py` measures all six terminal-pair differences
  for each of the five changed thin decision devices from every recorded
  time point in each completed original 144 ns schematic trace. Settled
  drain/source magnitudes use the original twelve sampling times separately.
  It remeasures the actual waveforms, verifies their saved results, code,
  input/fixture/runtime hashes, exact five-width source intervention, fixed
  3.3/1.8 V rails and required process/temperature coverage. It launches no
  simulator and changes no existing producer, fixture or waveform.
- Immutable report
  `a3a34b4ac8e5f600/decision_headroom/5c8b09f2bb46fee8/summary.json`
  covers eleven completed source cases, not all fifteen. All five observed
  devices remain below the existing project thin-device screening guard of
  1.95 V. This is the guard already used by `ota_operating_points.py`, not
  a newly asserted PDK safe-operating-area rating.
- The largest recorded difference is 1.793156 V at XC1 drain/body in FF/0,
  83.953226 ns. Minimum settled tail drain/source magnitude is 5.530552 mV
  in SS/0. The CL-side and CO-side input-device minima are 298.724 mV and
  25.429 mV respectively. These are measured terminal voltages, not BSIM
  VDSAT values or saturation-region classifications. Source currents and
  power are explicitly unmeasured; remaining receiver devices and all native
  parasitics are outside this observation's scope.
- Initial observation `decision_headroom/6fa068f689870e81` is retained with
  its matching `producer.py`; the current report additionally validates the
  exact matrix coverage and producer context. More completed cases generate
  a new content-bound report rather than rewriting earlier observations.
- Three tests cover all five declared devices, a transient guard violation
  between the static sampling times, separate settled headroom measurement,
  and refusal of incomplete waves or unobserved terminal nodes. Full
  regression: 526 tests, 525 passed and one skipped.
- The actual DC campaign has now completed twelve passing cases, including
  FS/0; FS/25, SF/0 and SF/25 remain. Clock and downstream continuations
  still require the complete actual upstream reports; no partial voltage
  observation is promoted to full receiver or PHY qualification.


Passive receiver common-mode full DC matrix launched on 2026-11-01:

- `matrix_receiver_common_mode.py` prepares the original fifteen PVT fixtures
  for each of the unchanged LVT control, VREF-return correction and rail-pullup
  correction. Every process corner and 0/25/40 degree case occurs exactly once;
  each variant uses identical physical circuit bytes across all fifteen cases.
  Original full 144 ns sensitivity stimuli, fixed supplies, current observations
  and twelve-device project stress screening remain unchanged.
- Immutable context `receiver_common_mode_matrix/225f22209016b597` binds the
  completed original LVT matrix, requirements, producers and all fifteen child
  manifests. SS/40, TT/25 and FS/40 pilots gate the remaining twelve PVT cases.
  Each candidate has a separate fifteen-case DC admission report; a passing
  control or another candidate cannot supply its missing or failing results.
- `openlvds-receiver-common-mode-matrix.service` is running two workers. Each
  actual simulation independently acquires its existing fair shared lease;
  there is no outer lease and the global six-SPICE limit is unchanged. Cached
  SS/40 is remeasured, and incomplete traces cannot be overwritten for retry.
- Three new tests cover exact PVT coverage and labels, separate candidate
  admission, incomplete coverage and the independent DC/stress pass flags.
  Full SciPy-enabled Apptainer regression: all 659 tests pass, no skips.
  This campaign provides source DC/current/observed-device evidence only.
  Source-clock, layout/extraction, native receiver and coupled-link validation
  remain required before selecting either correction for the usable PHY.


Passive receiver source-clock handoff prepared on 2026-11-01:

- Both corrections and their matched control pass SS/40, TT/25 and FS/40 DC
  pilots in `receiver_common_mode_matrix/225f22209016b597/pilot_summary.json`.
  The remaining twelve process/temperature cases have been released.
- `receiver_common_mode_clock.py` admits each correction separately after all
  fifteen DC/current/observed-device stress cases pass. Aggregate reports with
  missing child reports cannot trigger simulation during cache verification.
  The admission consumer waits for the DC producer execution lock to release
  before cached scientific remeasurement, avoiding its final-report race.
- Clock preparation derives all three original full 80 ns fixtures from the
  completed LVT source-clock context `receiver_clamp/7b715872da5a4460`.
  It remeasures that reference, preserves its reduced-tail comparison control,
  pin waveforms, 1 ps maximum step, native shared bias and digital receiver,
  and changes only the selected receiver closure. Modified candidate bytes
  must exactly match the full DC candidate. Missing, duplicated or repeated
  edges still fail the original three 47-period source-clock gates.
- Resource-only `225f22209016b597/clock_followup/run.py` is verified active as
  `openlvds-receiver-common-mode-clock-followup.service`. It binds its own
  bytes, scientific adapter, original clock manifest, matrix manifest and
  exact live matrix owner PID/invocation. It waits for completed DC evidence,
  then starts independent producer processes only for admitted variants.
  Those simulations each own a shared slot; no outer lease or extra slot is
  introduced. Failed clocks are retained for diagnosis, not auto-promoted.
- Three new tests cover exact declared candidate/reference source, restoration
  of adapter bindings after failure, and refusal of an aggregate DC report
  missing actual child reports without calling the DC runner. All 662 full
  regression tests pass; the three adapter tests also pass after the handoff
  lock adjustment. No new source-clock, native or PHY result is claimed yet.


Passive receiver physical path and SF/40 failure diagnosis on 2026-11-01:

- `layout_receiver_common_mode.py` builds either declared passive correction
  using the existing frontend-local geometry after complete fifteen-case DC
  and three-case source-clock admission. Candidate source bytes must match
  the admitted DC candidate. The original frontend-local physical reference
  `receiver_layout/74f1d1fd9724608e` is revalidated against its physical cache,
  source/GDS binding, producer/input hashes and independent RC audit. Each
  correction receives a distinct immutable profile and physical identity.
- `probe_receiver_common_mode.py` retains the original captured/sharp native
  fixtures, full 80 ns duration, 1 ps maximum step, native shared bias and
  digital RX. New geometry must first pass DRC/LVS, extraction and independent
  RC audit. The unchanged native engine requires exactly one output edge per
  original period in both 47-period controls. Frontend probes are retained;
  native simulations independently lease existing shared slots at priority 1.
- Four tests verify the actual 70/72-device flattened candidates and local
  placement of every changed resistor, reject a clock from the other variant,
  refuse missing physical evidence without creating native contexts, and
  restore all temporary producer/resource bindings after failure while
  preserving idempotent probes and exact numerical policy. Actual
  `225f22209016b597/physical_preflight.json` proves both layout preparations
  reject incomplete DC and both native preparations reject missing geometry;
  zero new layout/native contexts were created. All 666 regression tests pass.
- The live matrix now contains a decisive negative result: VREF return fails
  SF/40 at the original 130 ns sensitivity point (P=2.3 V, N=2.4 V). Q is
  1.799999955 V instead of low. Its twelve observed devices still pass the
  project stress screen. Control and rail pullup pass the identical point.
  Full fifteen-case candidate admission remains pending; no passing nominal
  case can override this failure for the VREF-return candidate.
- Read-only bound diagnosis is saved at
  `225f22209016b597/completed_sf40_diagnosis/summary.json` with its reader.
  All three complete traces are scientifically remeasured before reporting.
  At the failed point VREF-return PP/PN=1.38934/1.48970 V,
  CT=0.625579 V, CL=0.674634 V and CO=0.725255 V. Restoration stage zero
  stays high at 1.26404 V, leaving Q high. XC0 drain-source voltage is only
  49.055 mV despite improved tail headroom. This supports decision-stage
  drain-headroom/swing compression at high input common mode; BSIM VDSAT or
  operating-region classification has not been measured.
- At the same point rail pullup gives PP/PN=1.31905/1.38462 V,
  CT=0.594818 V, CO=0.771745 V, restoration zero=0.627263 V,
  restoration one=1.75218 V and Q=-4.793 microvolt, passing the original
  output criterion. Its observed twelve-device stress screen also passes.
  Continue the remaining PVT cases; the clock handoff already excludes any
  correction without fifteen passing DC cases. Source-clock, native, loaded
  link, full component/stability/aperture and final PHY qualification remain.


Passive correction physical continuation launched on 2026-11-01:

- `continue_receiver_common_mode_physical.py` is a resource-only controller
  for the existing scientific layout, extraction/audit and native replay
  producers. Immutable context `receiver_physical_followup/0a0d014ea640cbda`
  binds its producer and adapters, original frontend-local physical reference,
  captured replay parent, passive matrix and exact source-clock owner identity.
- `openlvds-receiver-common-mode-physical-followup.service` is verified live,
  waiting for full DC and source-clock evidence. It accepts only variants
  passing their own fifteen-case DC gate and exact source-clock admission.
  The VREF-return SF/40 failure cannot borrow the rail-pullup result.
- Each admitted variant then runs DRC/LVS geometry, native RC extraction and
  independent wire-collapse LVS audit, followed by the two original captured
  and sharp native controls. The native producer owns both individual fair
  leases; the controller has no outer lease. No component or PHY selector is
  changed, and even native diagnostic success keeps `qualified_phy=false`.
- Four tests verify exact clock receipt/variant/matrix/report binding,
  rejection of escaped paths and failed clock status, separate native-pass
  and PHY qualification flags, and refusal to overwrite prior controller
  state without launching any subprocess. A source-clock owner exit racing
  its final receipt is resolved by checking that receipt again.
  Full regression: all 670 tests pass, no skips.


Corrected native-driver/source-receiver link numerically retired on 2026-11-01:

- Specific corrected-link ngspice PID 1317195, start ticks 420907902, was
  measured three times over 40.008 seconds. Accepted transient time moved
  only 9.191e-15 seconds (0.009191 ps), from 80.28482108 ns to
  80.28483027 ns, while CPU ticks increased. The smallest recent accepted
  step was 4.335e-17 seconds. This independently verifies numerical stalling
  of corrected child `analog_link_pilot/86dc1c67c50cb1a2`; its original
  matched 100:1 control was already retired separately.
- `resident_jobs/corrected_link_progress/` preserves the observer, progress
  receipt, retirement script and frozen snapshot. The exact
  `openlvds-corrected-current-lvt-link.service` process group was frozen,
  98 files were archived and verified, then that one simulator and its
  coordinator were stopped. Every original file hash and all six shared
  slot-file inodes remain unchanged; all old PIDs are gone, MainPID is zero
  and Restart=no. systemctl emitted its auxiliary-process signal warning,
  but independent post-stop process/hash checks prove retirement completed.
- The old control retirement receipt is preserved byte-for-byte. New sidecar
  `current_lvt_link/494d9c90761d8f76/corrected_child_retirement.json` records
  the corrected child as numerically inconclusive. Neither partial trace is
  an electrical failure or completed comparison. No scientific source,
  model, stimulus or solver tolerance was changed. One actual shared slot
  is now available to the required receiver/driver/aperture campaigns.
- The passive receiver-bias matrix remains active, with eleven complete PVT
  cases. The physical continuation remains active waiting for admitted source
  clocks; it does not restart either stalled old link or promote a partial
  waveform into native/component/link/PHY evidence.


Full passive-bias rejection and weaker-pullup experiment on 2026-11-01:

- `receiver_common_mode_matrix/225f22209016b597` completed all fifteen
  original DC/current/stress cases for all three variants. Control passes
  15/15, VREF return 12/15 and one-unit rail pullup 13/15. VREF return fails
  the original 130 ns high-common-mode negative-polarity sensitivity point
  in SF/0, SF/25 and SF/40. Rail pullup fails that same point in SF/0 and
  SF/25. All failing cases pass the twelve observed-device stress screen;
  the rejection is electrical sensitivity, not numerical incompleteness.
- At SF/0, rail-pullup PP/PN=1.31649/1.39082 V, CT=0.557599 V,
  CL=0.609942 V and CO=0.662832 V. Restoration zero stays at 1.71003 V,
  leaving Q high. VREF return gives CO=0.638150 V and CT=0.577434 V.
  These matched terminal measurements support too much common-mode lift
  compressing the decision branch drain headroom at the high input limit;
  no BSIM VDSAT or operating-region assertion is inferred from voltage alone.
- Source-clock followup terminated with neither candidate admitted. Physical
  followup completed with zero admitted variants and no new geometry/native
  simulations. Both original candidates remain rejected; their complete
  evidence and previously prepared producers are preserved.
- `receiver_soft_common_mode.py` instead adds two or three series original
  precision-poly resistor units from each PP/PN node to fixed VDDD. No
  original device, return connection, supply, stimulus or numerical setting
  changes. The uninstrumented candidate adds four/six resistors. Solving the
  actual unloaded network gives 1.08 V/1.028571 V centers and 0.4R/(3R/7)
  equivalent resistance, versus baseline 0.9 V and R/2. These are analytical
  unloaded values, not assumed loaded performance or qualification.
- New immutable `receiver_soft_common_mode_matrix/d3271555fcb702b9` binds
  all fifteen original DC PVT fixtures. SF/0 and SF/25 now join SS/40, TT/25
  and FS/40 as the five pilots gating the remaining ten cases. The original
  current and twelve-device stress observations remain. Two independent
  workers are live in `openlvds-receiver-soft-common-mode-matrix.service`,
  sharing the same six-slot dispatcher without an outer lease. New source
  clocks and native/physical evidence will be required for either correction.
- Three new tests solve the actual two series networks, prove that only the
  declared unit resistors are added and repeated correction is rejected,
  and verify formerly failing corners lead the pilots with independent
  variant/full-coverage admission. Original failed-candidate code and
  manifests were not edited to repurpose their evidence.

16 pF DLL native admission adapter prepared on 2026-11-01:

- `qualify_dll_storage.py` admits the exact corrected physical source to the
  original native qualification engine only after all three complete matched
  SS/0, TT/25 and FF/0 source-acquisition cases pass and are remeasured.
  It captures immutable source proofs bound to the native manifest and its
  producer, preserves independently leased native workers, and refuses
  partial native traces instead of overwriting them for an in-place retry.
- The original 24-case native screen and full 336-case requirements remain;
  full expansion still requires a measured stability report bound to the
  corrected model inputs. The adapter does not grant source, native,
  stability or PHY admission on the strength of the old compensation model.
  Four tests cover incomplete/failed source refusal without dispatch,
  restoration of temporary bindings and preservation of partial native output.
- The exact current SS/0 source-acquisition process is verified live and
  reached 1368 ns of its original 1500 ns fixture; TT/25 and FF/0 remain
  required. Native preparation/dispatch has not bypassed this source gate.

Full regression after both additions: all 677 tests pass, no skips.


Weaker receiver-bias clock/physical continuation prepared on 2026-11-01:

- Both weaker variants complete and pass SF/0 and SF/25 full 144 ns,
  twelve-point DC/current/observed-device-stress controls in
  `receiver_soft_common_mode_matrix/d3271555fcb702b9`. At the formerly
  failing SF/0, 130 ns high-common-mode point, CO is 0.900370 V for the
  two-unit pullup and 1.018675 V for the three-unit pullup; both Q outputs
  are below 0.2 nanovolt and pass the original low-output criterion. At
  SF/25, CO is 0.961600/1.058458 V and both outputs also pass. These are
  actual matched loaded measurements, not the unloaded network estimates.
  SS/40, TT/25 and FS/40 still gate the remaining ten PVT conditions.
- `receiver_soft_common_mode_clock.py` requires full fifteen-case admission
  for each specific weaker variant, then reconstructs the original three
  80 ns source-clock controls with exact candidate bytes. The original
  reduced-tail reference, captured/sharp waveforms, 1 ps maximum step,
  native shared bias and digital RX remain. Old strong-bias matrices and
  nominal/partial reports cannot admit either new candidate.
- `receiver_soft_frontend_geometry.py` keeps all four/six added resistor
  segments local, including the final boost-to-VDDD segments that would
  otherwise fall into the unused-monitor region. It temporarily extends
  the original critical-net predicate and restores it after every exit.
  `layout_receiver_soft_common_mode.py` and
  `probe_receiver_soft_common_mode.py` require the exact softer profile,
  source DC/clock proofs, new DRC/LVS/extraction and independent RC audit
  before original captured/sharp native replays. Original failed-candidate
  producers and physical artifacts are preserved.
- `openlvds-receiver-soft-common-mode-clock-followup.service` is verified
  live, bound to the exact active new DC matrix owner, waiting for full
  source DC admission. Its immutable resource adapter is under
  `d3271555fcb702b9/clock_followup/`.
- `continue_receiver_soft_common_mode_physical.py` runs as verified-live
  `openlvds-receiver-soft-common-mode-physical-followup.service`, context
  `receiver_physical_followup/948f4f24130c3d2f`. It waits for exact admitted
  clock receipts, then runs the scientific layout/extraction/native gates
  with independently leased SPICE processes and no outer lease. Even a
  future passing native diagnostic grants no component or PHY admission.
- Eleven new tests cover exact candidate/reference clocks and exclusion of
  old matrices, missing-child refusal without dispatch, full local placement
  of all actual 74/76-device candidates, restoration after failure, strict
  native profile separation, receipt/path binding, qualification scope and
  preservation of prior controller state. Native GDS and clock results for
  these new candidates are still pending upstream electrical evidence.

Full regression after the weaker clock/physical continuation: all 688 tests pass, no skips.


16 pF DLL first completed source result and native handoff on 2026-11-01:

- The exact original 1500 ns SS/0 source-acquisition fixture completed and
  passed for `dll_architecture/368259f7b02c5fdc/ota_w8_c16_loop_ss_0`.
  Its original cadence, 10.038821 ps maximum feedback error, 10.690115 ps
  maximum quarter-phase error and 0.744964 mV control ripple all pass.
  TT/25 is now running; FF/0 remains queued in the same unchanged source
  controller. One completed corner does not admit the new native DLL.
- Read-only `368259f7b02c5fdc/completed_source_observation/read.py` validates
  both original and corrected scientific manifests, complete source traces,
  input-file hashes, report hashes and the matched-fixture audit. Actual
  full-wave remeasurement reproduces every loop metric exactly for both
  SS/0 circuits. Its immutable summary binds the reader and every input.
- The original 4 pF SS/0 source case gives 2.576440 mV control ripple,
  10.045246 ps feedback error and 9.481937 ps quarter-phase error. The
  corrected 16 pF case gives 0.744964 mV ripple, 10.038821 ps feedback
  error and 10.690115 ps quarter-phase error. Both pass original acquisition
  criteria. This source-only observation does not establish the new native
  loop margins or predict the remaining process/temperature cases.
- Resource-only `368259f7b02c5fdc/native_followup/run.py` is verified live
  as `openlvds-dll-storage-native-followup.service`. Its manifest binds the
  exact source owner PID/invocation, source manifest, source/native adapters,
  corrected exact-resistor layout `dll_layout/schur_496dde348e4fe55b` and
  fast-reset PFD physical/extraction/audit evidence. It waits for all three
  original source reports before invoking `qualify_dll_storage.py`.
- If source admission passes, the continuation prepares the exact corrected
  native library and runs only the original native screen with three workers,
  each owning an independent actual shared lease. No outer lease is held.
  Fresh measured stability, full 336 native cases, all PVT, steps/recovery,
  readiness, OTA operating points and the remaining PHY gates still apply.
  Numerical pauses and source/physical failures do not silently restart or
  promote a partial run. No source, fixture, model or existing producer was
  modified by either new resource/observation helper.
- Both weaker receiver corrections now pass all five pilot PVT cases in
  `receiver_soft_common_mode_matrix/d3271555fcb702b9/pilot_summary.json`.
  The full matrix is live with seven completed PVT cases; candidate-specific
  fifteen-case DC and downstream clock/native/PHY admission remain pending.
  Canonical scientific code is unchanged since the passing 688-test regression.


Corrected DLL measured-stability adapter prepared on 2026-11-01:

- `measure_dll_storage_stability.py` admits only the exact 16 pF native
  qualification and its hash-bound complete source-admission proofs. Every
  required native operating-point and PFD report must already exist and pass
  cached scientific remeasurement; this admission path cannot launch a missing
  native qualification case. Default coverage is SS/0, TT/25 and FF/0;
  `--all-pvt` requires all fifteen corresponding native operating points.
- The original `measure_dll_stability.py` still produces all forced-control
  delay, two-clock-state G/Y, averaged return-gain and both original
  390/410 MHz step measurements. Its numerical fixtures and strict original
  stability attestation remain unchanged. The new adapter temporarily enables
  the corrected qualification profile and independently fair-leases AC and
  transient simulations through the same global six slots, with no outer lease.
- The adapter derives the exact original scientific context before dispatch.
  An existing incomplete measurement context is retained without retry;
  a complete passing context must pass the original full stability verifier
  before reuse. A separate resource policy binds the adapter/dispatcher and
  native inputs without substituting for scientific evidence. Passing
  stability alone grants neither full native DLL nor PHY qualification.
- Four tests cover old-variant refusal without execution, refusal of missing
  native operating points without dispatch, restoration of both AC/transient
  resource bindings on failure, and preservation of partial measurement data.
  Actual `368259f7b02c5fdc/native_followup/stability_preflight.json` proves
  the rejected 4 pF native qualification cannot be used by the corrected
  stability adapter and creates zero measurement contexts. All 692 full
  regression tests pass, no skips.
- Resource-only `native_followup/stability_followup/run.py` is verified live
  as `openlvds-dll-storage-stability-followup.service`. It binds the exact
  current corrected-native-screen owner PID/invocation, handoff manifest and
  scientific/resource producers, then waits for native-screen admission before
  invoking fresh corrected stability measurements. No old 4 pF stability or
  compensation estimate is promoted into a corrected measured result.
- The weaker receiver full DC matrix remains live with eleven completed
  PVT cases. Its own source-clock and physical/native continuations remain
  gated on exact candidate-specific fifteen-case and clock evidence.


Weaker receiver bias complete DC admission on 2026-11-01:

- `receiver_soft_common_mode_matrix/d3271555fcb702b9/summary.json` now
  completes all fifteen original fixed-supply process/temperature cases.
  Control, two-unit pullup and three-unit pullup each pass 15/15 full
  144 ns/twelve-point DC/current/observed-device stress cases. Separate
  `source_dc_admission/rail_pullup_2r.json` and `rail_pullup_3r.json` bind
  each exact candidate circuit and full matrix report. No old strong-bias
  failure is overwritten or relabelled as a weaker-candidate result.
- Read-only `completed_pilot_headroom/read.py` scientifically remeasures all
  five original completed pilot traces, verifies every input hash and stores
  actual twelve-point tail drain voltage/current and decision input VDS in
  its immutable summary. At SS/40 the minimum sampled tail VDS is
  34.012 mV for control, 139.007 mV for two-unit pullup and 100.992 mV
  for three-unit pullup. Measured settled tail-current ranges are
  73.882–344.727, 238.987–356.129 and 189.816–353.431 microampere.
  These terminal/current observations do not assert BSIM saturation regions.
- Both weaker corrections retain passing SF/0 and SF/25 high-common-mode
  sensitivity, unlike the rejected stronger corrections. The complete
  fifteen-case source DC screen supports moving both candidates to original
  source-clock tests, not selecting a final native receiver or PHY.
- The exact live source-clock followup automatically advanced to
  `running_source_clocks` with both admitted variants. Three-unit context
  `receiver_clamp/1ea95c4cfc1e34f4` has been prepared through cached source
  remeasurement and exact candidate/fixture reconstruction. Two-unit
  preparation is also in the live handoff. Actual dynamic clock results,
  new geometry/extraction/native transport and full component/link timing
  remain required; the physical followup still waits for passing clocks.
- Scientific code is unchanged from the passing 692-test regression. The
  new pilot observation and live state checks are read-only/resource work;
  no extra SPICE slot or in-place partial retry was introduced.


Weaker receiver complete component selector prepared on 2026-11-01:

- `qualify_receiver_soft_common_mode.py` accepts only the exact selected
  weaker-bias native profile and current native producer. Before component
  preparation, both complete captured/sharp native controls are scientifically
  remeasured under a serialized cache lock; missing controls cannot dispatch
  native or component jobs. Native admission must explicitly pass and bind
  the exact replay manifest, retaining both original 47-period gates.
- The existing component engine retains every original schematic/native DC
  and rate fixture: 60 unique conditions across all five corners and three
  temperatures. It reconstructs the original fixtures and selected physical
  model, revalidates replay admission before execution, and requires all sixty
  results to pass. Partial component traces cannot be overwritten for retry.
- Each worker uses the existing fair priority-1 dispatcher through the frozen
  component worker's local slot import. Temporary component-code, replay-gate
  and resource bindings are restored after success or error. No outer lease
  is held, and the global six-slot limit remains unchanged. Source-clock or
  native success cannot substitute for this full component campaign.
- Four tests verify missing and failed native-admission refusal without
  dispatch, restoration of selector/resource bindings on failure, and exact
  preservation of partial component data. All 696 regression tests pass.
- Resource-only `receiver_physical_followup/948f4f24130c3d2f/component_followup/run.py`
  is verified live as
  `openlvds-receiver-soft-common-mode-component-followup.service`. Its
  immutable manifest binds the exact physical/native owner PID/invocation,
  physical handoff manifest, selector and scientific producers. It waits for
  passing per-variant native receipts, then prepares/runs the full sixty-case
  suite with two independent workers. Failed/unadmitted variants are held;
  neither native diagnostics nor component passes promote a PHY selection.
- Both weaker source-clock contexts are prepared and actively simulating:
  `receiver_clamp/efcc143161073193` (two-unit) and
  `receiver_clamp/1ea95c4cfc1e34f4` (three-unit). Actual original control
  traces were observed at 14.0265 ns and 17.0515 ns of their full 80 ns
  fixtures. No dynamic verdict is inferred from these partial times. New
  native geometry/replays, all components, corrected-driver coupling, DLL,
  sampling aperture and final release evidence remain required.


Corrected native-driver/native-receiver coupled diagnostic prepared on 2026-11-01:

- `probe_corrected_driver_soft_receiver.py` first requires both exact admitted
  weaker-bias native receiver controls, then remeasures the completed corrected
  driver comparison and reaudits its physical models. The preserved corrected
  link must contain exactly the audited P64/N24 110:1 native driver closure.
  Actual read-only checking confirms closure SHA
  `c9bc8c12c14ab1ee4395a6ede6f5d77b540689f572c56e9f3f9c599c34f72a64`.
- The new fixture replaces only the analog receiver closure with the admitted
  native model. Driver, shared bias, digital RX, original channel and all
  other protected closures remain. Full original SS/40, 410 MHz, 45% duty,
  +100 ps skew/100 ps peak-to-peak jitter, 188.049 ns duration, 20 ps maximum
  step, 60 ns training and 32-bit payload remain. Exact internal receiver
  probes are rebound to the new audited native node aliases. The original
  incomplete schematic-RX link is preserved; no partial waveform is reused.
- The diagnostic checks complete waveform/clock coverage, payload decoding,
  clock transport and at least 200 ps setup/hold sampling margin. Passing
  this short ideal-phase fixture cannot admit real-DLL startup, qualified
  aperture, full components/PVT, required long payloads or the complete PHY.
  Every result retains `qualified_phy=false`, and partial outputs cannot be
  overwritten for an in-place retry.
- Four tests prove only the library path/native probe aliases change,
  shortened/coarse/ambiguous fixtures are refused, missing native admission
  cannot launch driver/link work, and partial coupled output remains intact.
  Actual `d3271555fcb702b9/coupled_link_preflight.json` proves the old failed
  frontend native profile cannot substitute and creates zero new coupled
  contexts. All 700 regression tests pass, no skips.
- Resource-only `receiver_physical_followup/948f4f24130c3d2f/coupled_link_followup/run.py`
  is verified live as
  `openlvds-corrected-driver-soft-receiver-coupled-followup.service`. Its
  immutable manifest binds the exact physical/native owner PID/invocation,
  corrected parent fixture, driver comparison and scientific producers. It
  waits for admitted per-variant native receipts, then runs each new coupled
  diagnostic with one actual fair lease and no outer lease. A completed
  electrical failure is recorded as a failure, not promoted or automatically
  retried. Actual new coupled-link results remain pending upstream gates.


Completed unchanged clock-control reproducibility audit on 2026-11-01:

- `receiver_soft_common_mode_matrix/d3271555fcb702b9/completed_clock_controls/read.py`
  revalidates the completed original clock producer using cached evidence only,
  verifies both new completed reference controls and every saved source/deck/
  waveform/runtime/code binding, and retains an immutable summary.
- The complete active library statements are equal after excluding comments
  and blank lines, including unchanged receiver, native shared-bias and
  digital RX closures. Complete original numerical/stimulus decks match after
  replacing only their include paths. Both independently simulated waveform
  files are byte-identical to the original reference, and all transport/node
  observations agree exactly. Each has 47 periods with zero missing or
  repeated edges. Neither partial candidate trace is read or reused.
- Both duplicate reference jobs had already completed when this audit ran;
  no healthy process was stopped. The two weaker-circuit captured cases are
  actively simulating, with sharp controls still queued. No weaker-candidate
  source-clock or native qualification is inferred from the reference results.
- Architecture and top-level status prose now reflect the rejected stronger
  corrections, full weaker source admission and remaining dynamic/native gates.
  Canonical scientific code remains unchanged from the 700-test regression.


Matched partial captured-clock observation on 2026-11-01:

- Both weaker-bias captured-clock simulations are verified live, exact
  ngspice PIDs 1325342/1325278. Read-only
  `receiver_soft_common_mode_matrix/d3271555fcb702b9/partial_captured_clock_observation/read.py`
  snapshots only complete accepted binary rows, verifies the specific process
  start identity and unchanged source/deck/library bindings, and stores the
  snapshots separately from the original producer outputs. Live headers and
  metadata explicitly identify these as partial, unqualified observations.
- The common fixed 15–40 ns interval contains eighteen complete input
  periods. Both two-unit and three-unit pullups have zero missing edges
  and exactly one same-polarity output crossing in every observed input
  period. The original completed LVT reference also has eighteen such
  periods with no missing edges in that same interval.
- Two-unit source-clock latency ranges are 337.265–344.134 ps rising
  and 325.926–362.624 ps falling. Three-unit ranges are
  335.353–342.094 ps and 324.925–360.044 ps. The completed original
  reference gives 334.520–342.101 ps and 325.680–357.928 ps. These
  are diagnostic edge delays, not sampling-aperture or full-clock admission.
- The actual accepted snapshots extend to 54.9335 ns (two-unit) and
  59.2 ns (three-unit), but only complete periods in the declared common
  15–40 ns interval are analyzed. CO ranges in that interval are
  0.19444–1.79496 V and 0.15113–1.79784 V. Neither a future portion of a
  trace nor an incomplete input period contributes to the observation.
- Full 80 ns captured runs, sharp controls and all downstream physical,
  native, component, corrected-driver coupling and PHY gates remain required.
  No simulation was stopped, changed or restarted, no live waveform file
  was modified, and no partial observation supplies qualification evidence.
  Canonical science remains unchanged from the passing 700-test regression.


Both weaker receivers complete captured-clock transport on 2026-11-01:

- `receiver_clamp/efcc143161073193/clamped_captured` and
  `receiver_clamp/1ea95c4cfc1e34f4/clamped_captured` now complete the full
  original 80 ns source transient. Each passes all 47 rising/falling
  same-polarity input-period checks in the full original 15–75 ns analysis
  window, with zero missing and zero repeated output crossings.
- Bound observer `d3271555fcb702b9/completed_captured_clocks/read.py`
  verifies exact declared candidate source, every captured input/code hash,
  completed waveform/report bindings, finite strictly increasing full trace,
  and independently reproduces the original transport and internal-node
  range measurements exactly. It never calls a producer run and therefore
  cannot launch or duplicate a pending sharp simulation. Its immutable
  summary grants no overall source-clock or PHY admission.
- Both original unchanged reference controls have already passed. The two
  sharp controls are verified live at exact SPICE PIDs 1326515 (two-unit)
  and 1326474 (three-unit). Each must still complete and pass before the
  existing source-clock gate can release new layout/extraction/native replay.
  Pending physical/native/component/coupled-link continuations remain gated.
- Source-waveform results do not establish native wire-RC performance or
  sampling margin. Full component, corrected driver, DLL, aperture, real-clock
  long-payload and release obligations remain. Scientific code is unchanged
  from the passing 700-test regression; no solver policy or gate was relaxed.


Manifest-bound completed native-driver remeasurement on 2026-11-01:

- `driver_components/a1d220a703a6ac2b/completed_native_observations/read.py`
  selects only completed native tasks named in the original thirty-case
  manifest. It validates exact original coverage, pinned runtime/code/input
  hashes, audited physical model and reconstruction of every original source
  and complete 2540 ns fixture. Every DC/loaded-eye metric must reproduce its
  saved result exactly; it never calls a simulator or the live campaign runner.
- Immutable report `completed_native_observations/8f73f56942c52e6b/summary.json`
  covers nine complete native TT/FF/SS cases, all three required temperatures,
  and all nine pass. Settled differential output across both polarities is
  307.698760–331.571597 mV into 100 ohms; common mode is
  1.219365891–1.261373535 V. The campaign's additional loaded-eye screen
  also passes, with minimum 279.746968 mV at native SS/40. Loaded-eye
  limits remain separate from the settled DC voltage contract.
- Combined with the already remeasured fifteen source cases, this is
  twenty-four actual completed manifest conditions out of thirty. Directory
  glob counts also included an observation summary and are not condition
  counts. Status reporting now uses actual manifest tasks. FS/0, FS/25,
  FS/40, SF/0, SF/25 and SF/40 native conditions remain required.
- The report explicitly records `native_all_passed=false`; these nine cases
  cannot replace the six missing native results, full driver campaign, RC
  certificates, loaded coupling or PHY qualification. Model/code/fixtures and
  live output files are unchanged. No additional SPICE slot was acquired.
- Both weaker receiver captured-clock cases remain completely passing;
  their exact sharp-control SPICE processes and source-clock owner are still
  verified live. Existing source/native/physical continuations remain gated
  on complete reports. Canonical code is unchanged since all 700 tests passed.


Full weaker source-clock admission and physical recovery on 2026-11-01:

- Both `receiver_clamp/efcc143161073193` and `1ea95c4cfc1e34f4` complete
  all three original full 80 ns controls. Each original/captured/sharp case
  has 47 edge-matching checks and no missing/repeated crossings. Their
  exact `source_clock_admission.json` records are true. This admits physical
  work only; native receiver/PHY qualification remains separate.
- The initial physical handoff failed before geometry: the Nix tools shell
  selected a Python without NumPy. Failed context
  `receiver_physical_followup/948f4f24130c3d2f` and its logs/manifests are
  preserved, including its dependent followers' terminal records. It produced
  no new scientific layout/native result and invalidates no source-clock pass.
- `resume_receiver_physical_tools.py` admits only that specific pre-geometry
  import failure with unchanged old inputs and both complete source-clock
  admissions. New context `receiver_physical_followup/aa7ff15e63569672`
  records the recovery scope and explicit container `/usr/bin/python3`.
  The adapter changes only the Python executable in tools-shell commands;
  scientific scripts, models, fixtures, solvers and original failed producer
  remain byte-preserved. Actual tools-shell import confirms NumPy 1.26.4.
- `openlvds-receiver-soft-common-mode-physical-tools.service` is verified
  live. Two-unit geometry `receiver_layout/9d740d19bee2c0d0` passes DRC/LVS,
  extraction and independent RC audit: 74 devices, nine ports, dimensions
  670.26 by 147.8 micrometres. Native model SHA is
  `8a329f739f158b3aa0014b182bf891edce519b684596ece44a2e0970ef7fe0c2`.
  Both original native fixtures at `receiver_replay/c130e79d2f47a246` are
  running; no native transport verdict exists yet. Three-unit physical work
  remains in the source-admitted continuation after these diagnostics.
- Fresh `component_followup/` and `coupled_link_followup/` under the recovered
  context bind its exact live owner and unchanged scientific producers.
  `openlvds-receiver-soft-common-mode-component-tools` and
  `openlvds-corrected-driver-soft-receiver-coupled-tools` are verified live,
  waiting for exact passing native receipts before component/link dispatch.
  Old followers are not restarted or relabelled.
- Three new tests verify tools-only interpreter replacement with all science
  arguments unchanged, restoration after failure, and refusal to recover an
  unrelated failure without mutating prior state. All 703 regression tests
  pass, no skips. No extra actual SPICE slot, partial retry, model promotion
  or qualification waiver was introduced.
