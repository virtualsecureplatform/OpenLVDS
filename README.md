# OpenLVDS

SKY130 source-synchronous LVDS prototype: one 800 Mb/s data lane, a forwarded
400 MHz clock, and two-bit parallel ports. The receiver uses that clock directly;
there is no CDR. OpenPLL supplies the transmitter clock.

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

The current delay-bank candidate uses two-level transmission-gate selection,
switched fine-capacitor loads, a P40/N16 loaded inverter and a final P20/N16
inverter. The new loaded driver passes native layout and local RC qualification.
Its recorded-input native fine-stage test at SS/40°C, 410 MHz and 60% duty
passes the original 20 ps period/history limits: maximum period error is
8.589 ps and loaded-stage rising history is 5.345 ps, with all eight startup
events retained. The complete-bank four-point screen is queued to test actual
input loading, zero-code quarter headroom, both fine-duty endpoints and coarse
range overlap. The retained baseline still fails common coarse/fine range.

The counter startup repair adds a native 5×5 µm MIM shunt. Ten of twelve
SS0/SS40, 40/50/60% duty and stopped-clock boundary points now pass with
independent full native replays. The added capacitor passes DRC, strict LVS
and fresh actual-GDS local RC. The complete boundary screen and new whole-counter
geometry/shared-wire RC remain required. Earlier physical and simulation
artifacts, including failures, remain available in the implementation notes.

Input-clock checks use **40/50/60% duty at 390/400/410 MHz**. Whole-bank coarse/fine timing,
dense common legal codes, complete delay range, all PVT, calibrated clock-chain
integration and full-link qualification remain open. The broad regression and separate CAD tests
pass; software and physical/RC passes do not establish electrical PHY release.
Retained experiment results and exact receipts are in the implementation status
and digital-clocking notes.

All project implementation and generated artifacts stay in this repository.
`thirdparties/OpenPLL` is the pinned clock-source dependency; OpenSERDES was used
as a reference and is not required at run time.

| Contract | Value |
| --- | --- |
| Data / parallel interface | 800 Mb/s DDR / 2 bits at 400 MHz |
| Supplies | fixed 3.3 V analog, 1.8 V digital; no supply sweep |
| External reference | buffered 1.2 V VREF; 35 µA sink at each PHY IREF |
| Process / temperature | tt, ff, ss, fs, sf; 0, 25, 40 °C |
| TX differential / common mode | 250–450 mV / 1.125–1.375 V |
| Termination | external 100 Ω across each receiver pair |
| Board model | 20 cm, 100 Ω differential, 1.2 ns delay |
| Per-pin model | 1 nH package inductance; 2 pF pad capacitance |
| Stress | 390/400/410 MHz; 40/50/60% input duty; ±100 ps skew; 100 ps pp jitter |
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
