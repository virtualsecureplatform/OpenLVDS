# Implementation status

The SKY130 macro implementation and reproducible build flows are present.
**The link is still in electrical bring-up and is not released.**

The latest completed checks on 2026-10-28 include:

- RTL: 1,186,812 bits across 27 clock/duty/skew cases, plus DLL control and PHY assembly.
- Schematic electrical characterization: all 60 driver, receiver, receiver-rate,
  and DLL cases across tt/ff/ss/fs/sf at 0, 25, and 40 °C.
- Extracted receiver: all 15 static corners and all 15 rate corners. The rate
  test uses 840 Mb/s, 250 mV differential input, and 100 fF output load.
- Physical checks: five analog macros and three digital macros pass DRC/LVS;
  the five analog extracted networks also pass an independent connectivity audit.
- Unit tests: 27 pass, including stale-evidence rejection, parallel input timing,
  link measurement boundaries, and binding results to their required regression cases.

Extracted driver and DLL corner simulations and the full/approximate RC
comparison are still running. Completed driver cases are recorded individually
under `build/analog_extracted/`. No approximate network is qualified until the
complete comparison certificate passes.

A partial extracted DLL trace shows approximately 508 ps quarter-cycle delay
and 310 ps detector-input error. Its physical netlist contains automatically
inserted clock-delay buffers on the phase detector's inputs and outputs.
The physical flow is being corrected before restarting the affected DLL tests.

A short extracted link diagnostic with late parallel input changes shows payload
ordering errors. The earlier receiver clock-load problem was corrected and
checked independently.
The bench now launches parallel data according to the existing physical input
constraints. An isolated transistor-level TX diagnostic using the unqualified
approximate RC view and 80 fF output loads decodes all 64 payload bits correctly;
the corresponding end-to-end run is still in progress. That diagnostic uses a
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
