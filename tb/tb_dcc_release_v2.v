// SPDX-License-Identifier: GPL-3.0-only
`timescale 1ns/1ps
// Gate delays below test topology/phase protocol, never SKY130 timing.
module sky130_fd_sc_hd__conb_1(output HI,LO);assign HI=1;assign LO=0;endmodule
module sky130_fd_sc_hd__inv_1(input A,output Y);assign #0.001 Y=~A;endmodule
module sky130_fd_sc_hd__inv_4(input A,output Y);assign #0.001 Y=~A;endmodule
module sky130_fd_sc_hd__and2_1(input A,B,output X);assign #0.001 X=A&B;endmodule
module sky130_fd_sc_hd__or2_1(input A,B,output X);assign #0.001 X=A|B;endmodule
module sky130_fd_sc_hd__dfrtp_1(input CLK,D,RESET_B,output reg Q);
    always @(posedge CLK or negedge RESET_B or posedge RESET_B)if(!RESET_B)Q<=#0.002 0;else if(CLK)Q<=#0.002 D;
endmodule
module sky130_fd_sc_hd__a21oi_1(input A1,A2,B1,output Y);assign #0.001 Y=~((A1&A2)|B1);endmodule
module sky130_fd_sc_hd__and2b_1(input A_N,B,output X);assign #0.001 X=~A_N&B;endmodule
module tb_dcc_release_v2;
    reg ph0=0,ph90=0,reset_n=0,enable=1,present=1,locked=0;
    always #1.25 ph0=~ph0;
    initial begin #0.625;forever #1.25 ph90=~ph90;end
    wire ph180=~ph0,ph270=~ph90;
    wire release0_n,release90_n,out0,out90;
    openlvds_dcc_release_v2 release_control(.raw_phase0(ph0),.raw_phase90(ph90),.reset_n(reset_n),.enable(enable),
        .clock_present(present),.dll_locked(locked),.reset0_n(release0_n),.reset90_n(release90_n));
    openlvds_dcc_clock_hold_v2 first(.phase0(ph0),.phase180(ph180),.reset_n(release0_n),.clock_out(out0));
    openlvds_dcc_clock_hold_v2 second(.phase0(ph90),.phase180(ph270),.reset_n(release90_n),.clock_out(out90));
    integer i,j;
    realtime start,next;
    initial begin
        #10 reset_n=1;
        for(i=0;i<25;i=i+1)begin
            locked=0;#5.1;
            #(0.1*i);locked=1;
            wait(release0_n && release90_n);#10;
            for(j=0;j<4;j=j+1)begin
                @(posedge out0);start=$realtime;
                @(posedge out90);next=$realtime;
                if(next-start<0.624 || next-start>0.626)$fatal(1,"DCC startup inverted quadrature %g",next-start);
            end
            present=0;#0.01;
            if(release0_n!==0 || release90_n!==0)$fatal(1,"Clock loss did not asynchronously reset DCCs");
            present=1;
        end
        $display("PASS v2 phase-specific DCC resets preserve +90deg through all release offsets");$finish;
    end
    initial begin #10000;$fatal(1,"DCC release watchdog");end
endmodule
