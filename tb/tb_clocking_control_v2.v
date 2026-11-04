// SPDX-License-Identifier: GPL-3.0-only
`timescale 1ns/1ps
module tb_clocking_control_v2;
    reg mgmt=0, fast=0, run_fast=1, reset_n=0;
    always #20 mgmt=~mgmt;
    always #1.25 if (run_fast) fast=~fast; else fast=0;
    wire present;
    openlvds_clock_watch_v2 watch(.reset_n(reset_n),.observed_clk(fast),.mgmt_clk_25(mgmt),.clock_present(present));
    reg train=0, enable=1, valid=0, epoch=1, balanced=1, short_period=0, long_period=0, detector=1;
    reg [1:0] fastest=0;
    wire request, separate, busy, locked, fail;
    wire [3:0] reason;
    wire [15:0] codes;
    openlvds_dll_calibrate_v2 #(.CODE_WIDTH(4),.LAST_CODE(2),.TIMEOUT_CYCLES(1000)) dut(
        .mgmt_clk_25(mgmt),.reset_n(reset_n),.enable(enable),.train_req(train),.clock_present(present),
        .codes_applied(1'b1),.measure_valid(valid),.measure_epoch_valid(epoch),.measure_balanced(balanced),
        .measure_fastest(fastest),.measure_period_short(short_period),.measure_period_long(long_period),
        .measure_detector_valid(detector),.measure_request(request),.separated_mode(separate),
        .codes(codes),.cal_busy(busy),.locked(locked),.cal_fail(fail),.failure_code(reason));
    task start;
        begin @(negedge mgmt);train=1;@(negedge mgmt);train=0; end
    endtask
    task respond;
        begin
            wait(request); @(negedge mgmt);valid=1;
            @(negedge mgmt);valid=0;
        end
    endtask
    integer i;
    reg [15:0] frozen;
    initial begin
        #83 reset_n=1;
        // Train is allowed before the clock-watch synchronizers report present.
        start(); repeat(6) @(negedge mgmt);
        if (!present || fail) $fatal(1,"400/25 alias or startup clock-watch failure");
        for(i=0;i<63;i=i+1) begin respond();respond(); end
        if (locked) $fatal(1,"Locked before 64 independent confirmations");
        respond(); respond(); #1;
        if (!locked || busy || fail) $fatal(1,"64-confirmation lock failed");
        frozen=codes; short_period=1;
        repeat(5) @(negedge mgmt);
        if (codes!==frozen) $fatal(1,"Payload codes changed");
        // Clock loss uses an independent management clock and invalidates lock.
        run_fast=0; repeat(12) @(negedge mgmt);
        if (present || locked || !fail || reason!=1) $fatal(1,"Clock-loss handling failed");
        run_fast=1; repeat(6) @(negedge mgmt);
        start(); respond(); epoch=0; respond(); #1;
        if (!fail || reason!=4) $fatal(1,"Ambiguous epoch admitted");
        epoch=1; start();
        for(i=0;i<3;i=i+1) begin respond();respond();end
        if (!fail || reason!=3) $fatal(1,"Range saturation wrapped");
        short_period=0; detector=0; start();respond();#1;
        if (!fail || reason!=5) $fatal(1,"Invalid detector admitted");
        detector=1;start(); repeat(1002) @(negedge mgmt);
        if (!fail || reason!=2) $fatal(1,"Management timeout missing");
        enable=0;@(negedge mgmt);
        if (busy || locked || fail) $fatal(1,"Disable failed");
        $display("PASS v2 calibration confirmations, range, epoch, timeout, clock loss");
        $finish;
    end
    initial begin #1000000; $fatal(1,"Testbench watchdog"); end
endmodule
