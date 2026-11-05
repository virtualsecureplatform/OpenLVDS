// SPDX-License-Identifier: GPL-3.0-only
// Interface declarations only; no delay or functional clock model.
`default_nettype none
(* blackbox *) module openlvds_buf_8_o4_shunted_v2 (
    input wire A,
    output wire X,
    inout wire VGND,
    inout wire VPWR
);
endmodule
(* blackbox *) module openlvds_mim_switch_2x3_v2 (
    input wire NODE,
    input wire EN,
    input wire ENB,
    inout wire VDD,
    inout wire VSS
);
endmodule
(* blackbox *) module sky130_fd_sc_hd__buf_1 (
    input wire A,
    inout wire VGND,
    inout wire VNB,
    inout wire VPB,
    inout wire VPWR,
    output wire X
);
endmodule
(* blackbox *) module sky130_fd_sc_hd__buf_4 (
    input wire A,
    inout wire VGND,
    inout wire VNB,
    inout wire VPB,
    inout wire VPWR,
    output wire X
);
endmodule
(* blackbox *) module sky130_fd_sc_hd__inv_1 (
    input wire A,
    inout wire VGND,
    inout wire VNB,
    inout wire VPB,
    inout wire VPWR,
    output wire Y
);
endmodule
(* blackbox *) module sky130_fd_sc_hd__mux4_4 (
    input wire A0,
    input wire A1,
    input wire A2,
    input wire A3,
    input wire S0,
    input wire S1,
    inout wire VGND,
    inout wire VNB,
    inout wire VPB,
    inout wire VPWR,
    output wire X
);
endmodule
`default_nettype wire
