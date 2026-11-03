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
invocation and terminal receipts. The live handoff is
`dll_slew_expansion_followup/c7d283a388cd40e0`, owned by
`openlvds-dll-slew-expansion-followup.service`. It waits without an outer
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
