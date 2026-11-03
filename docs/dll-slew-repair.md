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

The full regression at this checkpoint passes 1,277 tests without skips.
