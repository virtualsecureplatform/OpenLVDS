// SPDX-License-Identifier: GPL-3.0-only
`timescale 1ns/1ps
`default_nettype none
// Digital integration models of the released I/O macros. They carry logic
// values only: no levels, edge rates, common mode or offset. Electrical
// behaviour is qualified by transistor-level SPICE against io_300.json.
// Delays are typical extracted values and are not a timing sign-off source;
// use the published Liberty views for timing.
module openlvds_io_tx(
`ifdef USE_POWER_PINS
    inout wire VDDIO, inout wire VDDD, inout wire VSS,
`endif
    input wire D, inout wire OUTP, inout wire OUTN, inout wire VREF, inout wire IREF);
    assign #0.5 OUTP=D;
    assign #0.5 OUTN=~D;
endmodule
module openlvds_io_rx(
`ifdef USE_POWER_PINS
    inout wire VDDIO, inout wire VDDD, inout wire VSS,
`endif
    inout wire INP, inout wire INN, output wire Q, inout wire VREF, inout wire IREF);
    // An undriven or non-complementary pair is unknown: the macro has no failsafe.
    assign #0.3 Q=(INP===1'b1 && INN===1'b0) ? 1'b1 :
                  (INP===1'b0 && INN===1'b1) ? 1'b0 : 1'bx;
endmodule
`default_nettype wire
