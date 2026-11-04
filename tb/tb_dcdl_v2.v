// SPDX-License-Identifier: GPL-3.0-only
`timescale 1ns/1ps
// Logic-only topology check. Unit gate delays break Icarus combinational
// expression folding on the long mirror lattice; they are not SKY130 timing.
// Native timing is measured only by the SPICE runner.
module sky130_fd_sc_hd__buf_4(input A,output X);assign #0.001 X=A;endmodule
module sky130_fd_sc_hd__nand2_4(input A,B,output Y);assign #0.001 Y=~(A&B);endmodule
module sky130_fd_sc_hd__nand2b_4(input A_N,B,output Y);assign #0.001 Y=~(~A_N&B);endmodule
module sky130_fd_sc_hd__einvp_1(input A,TE,output Z);assign #0.001 Z=TE?~A:1'bz;endmodule
module tb_dcdl_v2 #(parameter BIG_COARSE=32);
    reg clock_in=0,big_in=0;
    reg [14:0] coarse=0;
    reg [BIG_COARSE-2:0] big_coarse=0;
    reg [30:0] fine=0;
    wire out,big_out;
    openlvds_dcdl_v2 #(.COARSE_COUNT(16),.FINE_COUNT(32)) small_dut(
        .clock_in(clock_in),.coarse_therm(coarse),.fine_therm(fine),.clock_out(out));
    openlvds_dcdl_v2 #(.COARSE_COUNT(BIG_COARSE),.FINE_COUNT(32)) big_dut(
        .clock_in(big_in),.coarse_therm(big_coarse),.fine_therm(fine),.clock_out(big_out));
    integer c,f;
    initial begin
        for(c=0;c<16;c=c+1) begin
            coarse=(16'b1<<c)-1;
            for(f=0;f<32;f=f+1) begin
                fine=(32'b1<<f)-1;
                clock_in=0;#1;
                if(out!==0)$fatal(1,"Noninverting low failed coarse=%d fine=%d",c,f);
                clock_in=1;#1;
                if(out!==1)$fatal(1,"Noninverting high failed coarse=%d fine=%d",c,f);
            end
        end
        for(c=0;c<BIG_COARSE;c=c+1) begin
            big_coarse=({{(BIG_COARSE-1){1'b0}},1'b1}<<c)-1'b1;
            for(f=0;f<32;f=f+31) begin
                fine=(32'b1<<f)-1;
                big_in=0;#1;
                if(big_out!==0)$fatal(1,"Large lattice low failed coarse=%d fine=%d",c,f);
                big_in=1;#1;
                if(big_out!==1)$fatal(1,"Large lattice high failed coarse=%d fine=%d",c,f);
            end
        end
        $display("PASS v2 noninverting DCDL 16/32 coarse and 32 fine code logic");$finish;
    end
endmodule
