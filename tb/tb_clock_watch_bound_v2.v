// SPDX-License-Identifier: GPL-3.0-only
`timescale 1ns/1ps
module tb_clock_watch_bound_v2;
    parameter real RAW_HALF_NS=1.25;
    reg clk=0,raw=0,run_clock=1,reset_n=1,ready=0;
    always #20 clk=~clk;
    always #(RAW_HALF_NS) if(run_clock)raw=~raw;
    wire present;
    openlvds_clock_watch_v2 dut(.reset_n(reset_n),.observed_clk(raw),.mgmt_clk_25(clk),.clock_present(present));
    // A downstream registered readiness/status consumer gets one full cycle.
    always @(posedge clk or negedge reset_n)
        if(!reset_n)ready<=0;else ready<=present;
    integer phase,cycles;
    initial begin
        for(phase=0;phase<80;phase=phase+1)begin
            reset_n=0;run_clock=1;#5;reset_n=1;
            repeat(15)@(negedge clk);
            if(!present || !ready)$fatal(1,"Continuous 400/25 clock aliases");
            // Cover the full 40 ns management phase and both stopped levels.
            #(phase*0.5);run_clock=0;cycles=0;
            while(ready && cycles<9)begin @(posedge clk);#0.001;cycles=cycles+1;end
            if(present || ready || cycles>8)$fatal(1,"Clock-loss bound exceeded phase=%d cycles=%d",phase,cycles);
        end
        $display("PASS v2 clock loss clears registered readiness within eight management cycles at 80 stop phases");$finish;
    end
    initial begin #1000000;$fatal(1,"Clock-watch bound watchdog");end
endmodule
