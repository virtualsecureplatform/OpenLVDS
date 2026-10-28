// SPDX-License-Identifier: GPL-3.0-only
`default_nettype none
// Explicit assembly of two real physical macros; no opaque DLL placeholder.
module openlvds_dll_core(
    input wire CLK, input wire RESET_N, input wire PD_ENABLE,
    output wire PH0, output wire PH90, output wire PH180, output wire PH270,
    output wire FB, output wire PHASE_BAD, output wire UP, output wire DN,
    input wire PB, inout wire VDDIO, inout wire VDDD, inout wire VSS
);
    wire error_pulse,pd_ref,qref,qfb,qwin;
    openlvds_dll_analog analog(
        .CLK(CLK),.PD_ENABLE(PD_ENABLE),.PH0(PH0),.PH90(PH90),
        .PH180(PH180),.PH270(PH270),.FB(FB),.PD_REF(pd_ref),
        .PHASE_BAD(PHASE_BAD),.UP(UP),.DN(DN),.ERR(error_pulse),
        .PB(PB),.VDDIO(VDDIO),.VDDD(VDDD),.VSS(VSS),
        .QREF(qref),.QFB(qfb),.QWIN(qwin),
        .SENSE_REF(pd_ref),.SENSE_FB(PH180),.SENSE_WINDOW(PH90)
    );
    lvds_pfd phase_detector(
`ifdef USE_POWER_PINS
        .VPWR(VDDD),.VGND(VSS),
`endif
        .REF(pd_ref),.FB(PH180),.RESET_N(RESET_N),.PD_ENABLE(PD_ENABLE),
        .UP(UP),.DN(DN),.ERR(error_pulse),
        .QREF(qref),.QFB(qfb),.QWIN(qwin)
    );
endmodule
`default_nettype wire
