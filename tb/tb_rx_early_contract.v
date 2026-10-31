// SPDX-License-Identifier: GPL-3.0-only
`timescale 1ns/1ps
module tb_rx_early_contract;
    reg clk=0,reset_n=1,serial=0;
    wire [1:0] old_data,new_data;
    wire old_valid,new_valid;
    real period=2.5,duty=0.5;
    integer seed=3871,old_count=0,new_count=0,segments=0,total=0;
    reg [1:0] old_words[0:2047],new_words[0:2047];
    reference_rx baseline(clk,reset_n,serial,old_data,old_valid);
    openlvds_ddr_rx candidate(clk,reset_n,serial,new_data,new_valid);
    initial begin
        if ($value$plusargs("PERIOD=%f",period)) begin end
        if ($value$plusargs("DUTY=%f",duty)) begin end
        forever begin #(period*duty) clk=0; #(period*(1-duty)) clk=1; end
    end
    // Exercise pre-NBA consumers: the early interface may lead by one cycle,
    // but neither the first word nor subsequent words may disappear or repeat.
    always @(posedge clk) if (reset_n) begin
        if (old_valid) begin old_words[old_count]=old_data; old_count=old_count+1; end
        if (new_valid) begin new_words[new_count]=new_data; new_count=new_count+1; end
        if (old_count>new_count || new_count-old_count>1) $fatal(1,"consumer count mismatch");
        if (old_valid && old_words[old_count-1] !== new_words[old_count-1]) $fatal(1,"consumer word mismatch");
        #0.010;
        if (old_valid !== new_valid) $fatal(1,"post-edge valid mismatch");
        if (old_valid && old_data !== new_data) $fatal(1,"post-edge pair mismatch");
    end
    // Change away from the sampling edges; use random and alternating words.
    always @(clk) begin
        #0.150;
        serial=$random(seed);
    end
    task reset_segment;
        input real phase;
        begin
            #(phase) reset_n=0;
            #0.020;
            if (new_data !== 0 || new_valid !== 0) $fatal(1,"asynchronous reset failed");
            total=total+old_count;old_count=0;new_count=0;
            #(period*2+phase) reset_n=1;
            repeat(180) @(negedge clk);
            segments=segments+1;
        end
    endtask
    initial begin
        #0.030;
        reset_segment(0.073);
        reset_segment(0.381);
        reset_segment(0.917);
        reset_segment(1.117);
        if (total<500 || segments!=4) $fatal(1,"insufficient coverage");
        $display("PASS first-word/reset consumers words=%0d segments=%0d",total+old_count,segments);
        $finish;
    end
endmodule
