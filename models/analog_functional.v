// SPDX-License-Identifier: GPL-3.0-only
`timescale 1ns/1ps
`default_nettype none
// Digital integration models only. These do not model voltages, bandwidth,
// current, DLL acquisition, or transistor-level phase error. Transistor SPICE
// simulation is mandatory for electrical and extracted qualification.
module lvds_bias(inout wire IREF,output wire NB,inout wire VDDIO,VSS);
    assign NB=1'b1;
endmodule
module openlvds_driver_core(input wire D,output wire OUTP,OUTN,
    input wire VREF,PB,NB,inout wire VDDIO,VDDD,VSS);
    assign #0.2 OUTP=D;
    assign #0.2 OUTN=~D;
endmodule
module openlvds_receiver_core(input wire INP,INN,output wire Q,
    input wire VREF,PB,NB,inout wire VDDIO,VDDD,VSS);
    assign #0.2 Q=(INP===1'b1 && INN===1'b0) ? 1'b1 :
                  (INP===1'b0 && INN===1'b1) ? 1'b0 : 1'bx;
endmodule
module openlvds_dll_analog(input wire CLK,PD_ENABLE,
    output reg PH0=0,PH90=0,PH180=0,PH270=0,FB=0,
    output wire PD_REF,PHASE_BAD,input wire UP,DN,ERR,PB,inout wire VDDIO,VDDD,VSS,
    output wire QREF,QFB,QWIN,input wire SENSE_REF,SENSE_FB,SENSE_WINDOW);
    real period=2.5,previous=0;
    always @(posedge CLK) begin
        if (previous>0) period=$realtime-previous;
        previous=$realtime;
    end
    always @(CLK) begin
        PH0 <= #0.05 CLK;
        PH90 <= #(0.05+period/4) CLK;
        PH180 <= #(0.05+period/2) CLK;
        PH270 <= #(0.05+period*3/4) CLK;
        FB <= #(0.05+period) CLK;
    end
    assign {QREF,QFB,QWIN}={SENSE_REF,SENSE_FB,SENSE_WINDOW};
    assign PHASE_BAD=1'b0;
    assign #0.05 PD_REF=~PH0;
endmodule
// Logical PFD model for the integration test; physical lvds_pfd is hardened
// from explicit SKY130 cells and verified independently in SPICE.
module lvds_pfd(input wire REF,FB,RESET_N,PD_ENABLE,output reg UP=0,DN=0,output wire ERR,
    input wire QREF,QFB,QWIN);
    wire clear_n=RESET_N & PD_ENABLE & ~(UP & DN);
    always @(posedge REF or negedge clear_n)
        if (!clear_n) UP<=0; else UP<=1;
    always @(posedge FB or negedge clear_n)
        if (!clear_n) DN<=0; else DN<=1;
    assign ERR=(QREF^QFB)&QWIN;
endmodule
`default_nettype wire
