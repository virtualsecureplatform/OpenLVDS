// SPDX-License-Identifier: GPL-3.0-only
// Functional RX candidate models only; electrical checks use native PDK MOS.
`default_nettype none
module sky130_fd_sc_hd__inv_1(input wire A,output wire Y);
    assign Y=~A;
endmodule
module sky130_fd_sc_hd__buf_1(input wire A,output wire X);
    assign X=A;
endmodule
module sky130_fd_sc_hd__dfrtp_1(input wire CLK,D,RESET_B,output reg Q);
    always @(posedge CLK or negedge RESET_B)
        if (!RESET_B) Q<=1'b0;
        else Q<=D;
endmodule
`default_nettype wire
