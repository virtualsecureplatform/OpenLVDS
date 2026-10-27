// SPDX-License-Identifier: GPL-3.0-only
`timescale 1ns/1ps
`default_nettype none
// Simulation adapter only: genuine OpenPLL calibrated behavioral DCO, exposed
// through the hard-macro thermometer interface. No independent clock stub.
module IntegerPLL_DCO_EINVP_COARSE(
    input wire RESET_N,input wire [46:0] COARSETHERMAL_CODE,
    input wire [254:0] DCO_THERM,output wire PLLOUT
);
    integer i;
    reg [5:0] coarse;
    always @* begin
        coarse=0;
        // Coarse uses THERM_INVERT=0; fine uses DCO_THERM_INVERT=1.
        for(i=0;i<47;i=i+1) coarse=coarse+COARSETHERMAL_CODE[i];
    end
    IntegerPLL_DCO dco(.RESET_N(RESET_N),.COARSEBINARY_CODE(coarse),
                       .DCO_THERM(DCO_THERM),.PLLOUT(PLLOUT));
endmodule
`default_nettype wire
