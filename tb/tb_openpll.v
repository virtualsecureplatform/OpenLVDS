// SPDX-License-Identifier: GPL-3.0-only
`timescale 1ns/1ps
module tb_openpll;
    reg ref25=0,reset_n=1,enable=1;
    wire clk,tracking,valid;
    integer file;
    openlvds_openpll dut(ref25,reset_n,enable,clk,tracking,valid);
    always #20 ref25=~ref25;
    initial begin
        file=$fopen("build/openpll/clock.csv","w");
        $fdisplay(file,"time_ns,level");
        #1;reset_n=0;
        #79;reset_n=1;enable=1;
        #24000;
        $display("PLL diagnostic target=%0d coarse=%0d adapter=%0d code=%0d model_mhz=%f",
            dut.pll.TARGET_MHZ,dut.pll.coarse_code,
            dut.pll.hard_macro.oscillator.coarse,dut.pll.DCO_CODE,
            dut.pll.hard_macro.oscillator.dco.freq_mhz);
        if(tracking !== 1'b1 || valid !== 1'b1 || dut.pll.TARGET_MHZ !== 16'd400 ||
           (^dut.pll.DCO_CODE) === 1'bx)
            $fatal(1,"OpenPLL did not enter configured 400 MHz tracking");
        $fclose(file);$display("PASS OpenPLL configured 400 MHz source");$finish;
    end
    always @(clk) if ($realtime>=8000) $fdisplay(file,"%0.6f,%0d",$realtime-8000,clk);
    always @(posedge clk) if ($realtime>=8000 && ((^dut.pll.DCO_CODE) === 1'bx || tracking !== 1'b1))
        $fatal(1,"Unknown DCO code or lost tracking in captured clock window");
endmodule
