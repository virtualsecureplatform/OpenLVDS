// SPDX-License-Identifier: GPL-3.0-only
`timescale 1ns/1ps
module tb_dll_control;
    reg clk=0, reset_n=0, clock_ready=0, phase_bad=0;
    wire pd_enable,locked;
    openlvds_dll_control dut(clk,reset_n,clock_ready,phase_bad,pd_enable,locked);
    always #1.25 clk=~clk;
    initial begin
        #5; reset_n=1; clock_ready=1;
        repeat(31) begin
            @(posedge clk); #0.01;
            if (pd_enable) $fatal(1,"PFD enabled before preset settled");
        end
        @(posedge clk); #0.01;
        if (!pd_enable) $fatal(1,"PFD did not enable after startup hold");
        repeat(10) begin
            @(posedge clk); #0.1; phase_bad=1; #0.2; phase_bad=0;
        end
        if (locked) $fatal(1,"Locked during phase errors");
        repeat(70) @(posedge clk);
        #0.1; if (!locked || !pd_enable) $fatal(1,"Good phase failed to qualify");
        phase_bad=1;
        repeat(5) @(posedge clk);
        #0.1; if (locked) $fatal(1,"Persistent phase error did not revoke lock");
        phase_bad=0;
        repeat(70) @(posedge clk);
        #0.1; if (!locked) $fatal(1,"Failed to relock");
        clock_ready=0;
        #0.1; if (locked || pd_enable) $fatal(1,"Clock readiness not enforced");
        $display("PASS DLL lock qualification, error rejection, and restart");
        $finish;
    end
    initial begin #10000; $fatal(1,"Timeout"); end
endmodule
