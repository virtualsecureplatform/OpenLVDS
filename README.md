# OpenLVDS

SKY130 source-synchronous LVDS prototype: one 600 Mb/s data lane, a forwarded
300 MHz clock, and two-bit parallel ports. The receiver uses that clock directly;
there is no CDR. OpenPLL supplies the transmitter clock.

The active implementation target is now **300 MHz / 600 Mb/s DDR**, checked at
290/300/310 MHz and 40/50/60% duty. See the [300 MHz implementation status](docs/implementation-300mhz.md).
Historical 400 MHz evidence remains in the implementation notes; the new target
requires fresh qualification.

The implementation includes synthesizable DDR logic, transistor circuits,
generated analog GDS/LEF, digital place and route, DRC/LVS, GDS-based distributed
RC extraction, and reproducible simulation runners. **The link is still
in electrical bring-up and has no published release.** Its staged workflow must
pass all release gates before publishing an exact-byte macro package. Generated layouts alone do not qualify
the link, and functional analog models do not establish electrical performance.
See [implementation status](docs/implementation-status.md) for completed checks
and the remaining link bring-up work.

The selected [digital clocking v2](docs/digital-clocking-v2.md) architecture is
under implementation: calibrated four-phase clock generation, symmetric DCC,
RX deskew and explicit framed startup training.

The current delay-bank candidate uses doubled transmission gates and split fine
capacitors. Its five-case SS/40 C, 310 MHz source pilot passes the original
zero-code, fine-duty, coarse/fine-overlap and fresh numerical-pair checks.
Independent replay reproduces the complete fresh pair. This is sparse source
proof, with full code/PVT and common-routing qualification still required.

Actual two-bank loading exposes an electrical failure at 20 ps entry: the
first coarse cell exceeds its 1.95 V terminal-span limit, and the selected ENB
control exceeds its 180 mV deviation limit. Independent replay preserves both
failures despite passing timing. Three candidate repairs test coarse midpoint
shunts, stronger decoded ENB drive, and their combination. Their 12-case native
pilot checks 20/250 ps entry and fresh unmodified controls, including every
added fixed shunt gate from DC through the complete trace. Repair results are
pending; the roughly 6 ps slow-entry quarter headroom remains a hard gate.

Four-section native transport, combined DCC loading, and SMP numerical-control
experiments remain in progress. The first two combined runs failed numerically
before the clock started. A separate complete two-bank input-current reference
passes independent numerical parity; transfer to the combined circuit still
requires its own fresh control. Fresh 270-point counter and 810-point source-DCC
campaigns cover the 300 MHz profile.

Common monotonic legal codes, complete delay range, all PVT, shared physical RC,
calibrated clock-chain integration, startup training and full-link qualification
remain required. Exact receipts and retained failures are recorded in the
[300 MHz implementation status](docs/implementation-300mhz.md); historical
experiments remain in the [implementation notes](docs/implementation-status.md)
and [digital-clocking notes](docs/digital-clocking-v2.md).

All project implementation and generated artifacts stay in this repository.
`thirdparties/OpenPLL` is the pinned clock-source dependency; OpenSERDES was used
as a reference and is not required at run time.

| Contract | Value |
| --- | --- |
| Data / parallel interface | 600 Mb/s DDR / 2 bits at 300 MHz |
| Supplies | fixed 3.3 V analog, 1.8 V digital; no supply sweep |
| External reference | buffered 1.2 V VREF; 35 µA sink at each PHY IREF |
| Process / temperature | tt, ff, ss, fs, sf; 0, 25, 40 °C |
| TX differential / common mode | 250–450 mV / 1.125–1.375 V |
| Termination | external 100 Ω across each receiver pair |
| Board model | 20 cm, 100 Ω differential, 1.2 ns delay |
| Per-pin model | 1 nH package inductance; 2 pF pad capacitance |
| Stress | 290/300/310 MHz; 40/50/60% input duty; ±100 ps skew; 100 ps pp jitter |
| Sampling margin target | 200 ps |

The hardware baseline is [requirements.json](requirements.json). The current
calibrated-clock policy is [clocking_v2.json](clocking_v2.json), with the
approved input-duty amendment in [clocking_duty_v2_2.json](clocking_duty_v2_2.json).
These are reusable macros: pads, ESD protection, package design, and a complete
chip assembly are outside their boundary. VREF must be buffered because the
receiver input stages exchange current with it.

The OTA candidate uses a 15-port analog DLL, an 8-port PFD and matched native
`buf_4` transmitter outputs. Its [qualification workflow](docs/dll-experiments.md)
checks the actual candidate RTL and physical networks, measured stability and
recovery, receiver aperture and the full link matrix. After successful publication,
`make release-library` locates the tested package and `make release-current`
rechecks its proof selection. The commands below operate on the canonical
development sources; `make release` checks that development baseline.

Build the pinned Apptainer image with `make setup`, or import the matching
OpenPLL image:

```sh
./scripts/setup.sh --import /path/to/openpll-release-modern.sif
make tools
make test rtl
make analog-corners
make layout digital-physical extract
./scripts/env.sh python3 scripts/verify_analog.py --extracted --corners --settled-start
make openpll
make dll-clocks
make regression
make release
```

`scripts/env.sh` mounts this repository at `/work/OpenLVDS` in the container.
Use `--tools` for Magic, Netgen, OpenROAD, Yosys and LibreLane; Xyce, Icarus and
Python runners can use the base image. The PDK and OpenPLL revisions are pinned
in the requirements. `build/tool_versions.json` records the actual tools.

An optional ngspice 42 runtime can be installed from Ubuntu 24.04 package
metadata without changing system packages: `make ngspice` on the host. Its
executable, loader, shared libraries and hashes stay in `build/tools/`.
Select it with `scripts/env.sh --ngspice ...`, or use
`OPENLVDS_SPICE=ngspice make analog-corners`. The adapter enables KLU, converts
only simulator directives and hierarchical probe syntax, and exports ordered
waveform columns for the same analyzers. Results identify the actual simulator;
RC certificates cannot be reused across simulators.

For the complete software regression, including the sparse-math witnesses,
prepare the [pinned NumPy/SciPy environment](docs/dll-experiments.md#further-exact-resistor-elimination)
inside `build/tools/exact-rc-venv`, install the ngspice runtime, and run:

```sh
make test-full
```

This runs the suite with the pinned analysis environment and ngspice adapter.
The base-image `make test` can skip the sparse-math test when SciPy is absent.
Passing the software suite does not establish electrical qualification; current
simulation results and outstanding gates are in the implementation status.

Full RC simulations can be expensive. An optional TICER approximation retains
positive R/C elements and exact DC behavior, but approximates transient behavior:

```sh
make fast-rc compare-rc
./scripts/env.sh python3 scripts/verify_analog.py --fast-rc --corners
./scripts/env.sh python3 scripts/regression.py --fast-rc
```

The fast runners reject absent or stale comparison certificates. `--diagnostic`
on the link runner explicitly permits bring-up with an unqualified approximation;
those results cannot satisfy the release gate. A fast comparison certificate
only describes the listed nonlinear fixtures and tolerances; it is not a blanket
equivalence proof across all processes or operating points.

See [the architecture](docs/architecture.md) for interfaces and timing, and
[the validation map](docs/verification.md) for evidence locations and limits.
