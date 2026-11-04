// SPDX-License-Identifier: GPL-3.0-only
`timescale 1ns/1ps
// Logic model deliberately reproduces the observed SF failure mode: releasing
// RESET_B while CLK is HIGH may resample D. It is NOT native timing evidence.
module sky130_fd_sc_hd__conb_1(output HI,LO);assign HI=1;assign LO=0;endmodule
module sky130_fd_sc_hd__inv_1(input A,output Y);assign #0.005 Y=~A;endmodule
module sky130_fd_sc_hd__inv_4(input A,output Y);assign #0.005 Y=~A;endmodule
module sky130_fd_sc_hd__or2_1(input A,B,output X);assign #0.005 X=A|B;endmodule
module sky130_fd_sc_hd__a21oi_1(input A1,A2,B1,output Y);assign #0.005 Y=~((A1&A2)|B1);endmodule
module sky130_fd_sc_hd__and2b_1(input A_N,B,output X);assign #0.005 X=~A_N&B;endmodule
module sky130_fd_sc_hd__dfrtp_1(input CLK,D,RESET_B,output reg Q);
    always @(posedge CLK or negedge RESET_B or posedge RESET_B)
        if(!RESET_B)Q<=#0.020 0;else if(CLK)Q<=#0.020 D;
endmodule
module tb_dcc_clock_hold_v2;
    reg phase0=0,phase180=0,reset_n=1;
    initial begin #2;forever begin phase0=1;#0.75;phase0=0;#1.75;end end
    initial begin #3.25;forever begin phase180=1;#1.75;phase180=0;#0.75;end end
    wire clock_out;
    openlvds_dcc_clock_hold_v2 dut(.phase0(phase0),.phase180(phase180),.reset_n(reset_n),.clock_out(clock_out));
    integer a_count=0,b_count=0,out_count=0,before_a,before_b,before_out,i;
    always @(posedge dut.a)a_count=a_count+1;
    always @(posedge dut.b)b_count=b_count+1;
    always @(clock_out)out_count=out_count+1;
    always @(posedge dut.areset)if(reset_n && phase0 && $realtime>2)$fatal(1,"Reset rearmed during phase0 HIGH");
    always @(posedge dut.breset)if(reset_n && phase180 && $realtime>3.25)$fatal(1,"Reset rearmed during phase180 HIGH");
    initial begin
        #0.001 reset_n=0;#0.999 reset_n=1;#10;
        for(i=0;i<20;i=i+1)begin
            @(posedge phase0);before_a=a_count;before_b=b_count;before_out=out_count;
            #2.49;
            if(a_count-before_a!=1 || b_count-before_b!=1 || out_count-before_out!=2)
                $fatal(1,"Missing or repeated pulse despite clock-high reset hold");
        end
        $display("PASS v2 clock-aware reset blocks HIGH-level retriggering at 30/70 duty");$finish;
    end
    initial begin #1000;$fatal(1,"Clock-hold watchdog");end
endmodule
