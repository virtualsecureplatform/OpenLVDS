// SPDX-License-Identifier: GPL-3.0-only
// Physical interfaces; corresponding circuits are in analog/openlvds.spice.
// IREF accepts a 35 uA external current sink. PB is that diode-connected
// reference node's voltage. Share ONE bias generator among a PHY's cores.
`default_nettype none
(* blackbox *) module lvds_bias(
    inout wire IREF, output wire NB, inout wire VDDIO, inout wire VSS
); endmodule
(* blackbox *) module openlvds_driver_core(
    input wire D, output wire OUTP, output wire OUTN, input wire VREF,
    input wire PB, input wire NB, inout wire VDDIO, inout wire VDDD, inout wire VSS
); endmodule
(* blackbox *) module openlvds_receiver_core(
    input wire INP, input wire INN, output wire Q, input wire VREF,
    input wire PB, input wire NB, inout wire VDDIO, inout wire VDDD, inout wire VSS
); endmodule
(* blackbox *) module openlvds_dll_analog(
    input wire CLK, input wire PD_ENABLE,
    output wire PH0, output wire PH90, output wire PH180, output wire PH270,
    output wire FB, output wire PD_REF, output wire PHASE_BAD, input wire UP, input wire DN,
    input wire ERR, input wire PB,
    inout wire VDDIO, inout wire VDDD, inout wire VSS
); endmodule
`default_nettype wire
