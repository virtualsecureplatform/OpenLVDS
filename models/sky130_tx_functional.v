// SPDX-License-Identifier: GPL-3.0-only
// Functional models ONLY. Electrical behavior is checked with PDK transistor models.
`default_nettype none
module sky130_fd_sc_hd__inv_4(input wire A,output wire Y);
    assign Y=~A;
endmodule
module sky130_fd_sc_hd__xor2_1(input wire A,B,output wire X);
    assign X=A^B;
endmodule
module sky130_fd_sc_hd__xor2_4(input wire A,B,output wire X);
    assign X=A^B;
endmodule
module sky130_fd_sc_hd__dfrtp_4(input wire CLK,D,RESET_B,output reg Q);
    always @(posedge CLK or negedge RESET_B)
        if (!RESET_B) Q<=1'b0;
        else Q<=D;
endmodule
`default_nettype wire
