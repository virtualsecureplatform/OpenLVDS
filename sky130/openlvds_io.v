// SPDX-License-Identifier: GPL-3.0-only
// Released asynchronous LVDS I/O hard macros (contract io_300.json).
// Circuits: openlvds_io_tx / openlvds_io_rx in analog/openlvds.spice.
// Each instance contains its own bias mirror and needs its own 35 uA IREF
// sink; never tie two IREF pins together. VREF is a buffered 1.2 V reference.
// Pads, ESD and the 100 ohm receiver termination are outside the macros.
`default_nettype none
(* blackbox *) module openlvds_io_tx(
`ifdef USE_POWER_PINS
    inout wire VDDIO, inout wire VDDD, inout wire VSS,
`endif
    input wire D, inout wire OUTP, inout wire OUTN, inout wire VREF, inout wire IREF
); endmodule
(* blackbox *) module openlvds_io_rx(
`ifdef USE_POWER_PINS
    inout wire VDDIO, inout wire VDDD, inout wire VSS,
`endif
    inout wire INP, inout wire INN, output wire Q, inout wire VREF, inout wire IREF
); endmodule
`default_nettype wire
