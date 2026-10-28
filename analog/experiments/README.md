# Driver experiment

`source_terminated_driver.spice` defines an experimental macro and is not
instantiated by the PHY. Include `analog/openlvds.spice` for its shared helpers.
It retains the existing input stage, common-mode feedback, fixed supplies,
1.2 V reference, and 35 µA bias-reference sink.

The output-current mirrors and bridge switches have parallel copies of the
original devices. Twenty-two identical PDK resistor units form a nominal
100 Ω differential source shunt. With the existing 100 Ω far-end termination,
the doubled steering current is intended to preserve the nominal loaded swing
while absorbing returning waves. The additional current and switching load
require fresh electrical and physical characterization.

The diagnostic test circuit retains extracted finger geometry and diffusion
parameters. Its LVS comparison against this schematic passes. The controlled
transient test ran after a complete, correctly decoded exact-driver replay
confirmed an output-swing failure. It completed 32 bits with zero errors and
passing electrical levels (281 mV minimum data, 259 mV minimum clock), but its
11.61 ps setup margin fails the unchanged 200 ps target. The original receiver,
bias, and capture networks remain approximate in this diagnostic. All diagnostic artifacts reside under
`build/diagnostics/driver_stress_replay/source_terminated_driver/`.

Promotion requires loaded-channel results, fixed-supply process/temperature
checks, new GDS DRC/LVS and extraction, and the full release matrix. A schematic
LVS comparison or a single diagnostic pass cannot qualify this macro.
