// SPDX-License-Identifier: GPL-3.0-only
`timescale 1ns/1ps
// Stage flags are explicit synthetic protocol stimuli, not admitted clocks.
module tb_clock_sequence_v2;
    parameter LIMIT=8;
    reg clk=0,reset_n=1,enable=1,train=0,locked=0,dll_fail=0,ready=0,startup_fail=0;
    reg [3:0] dll_reason=5,startup_reason=8;
    always #20 clk=~clk;
    wire bank,start,startup,valid,busy,failed;
    wire [3:0] reason;
    openlvds_clock_sequence_v2 #(.TIMEOUT_CYCLES(LIMIT)) dut(
        .mgmt_clk_25(clk),.reset_n(reset_n),.enable(enable),.train_req(train),
        .dll_locked(locked),.dll_fail(dll_fail),.startup_ready(ready),.startup_fail(startup_fail),
        .dll_failure_code(dll_reason),.startup_failure_code(startup_reason),.bank_enable(bank),
        .start_dll(start),.startup_enable(startup),.outputs_valid(valid),.cal_busy(busy),.cal_fail(failed),.failure_code(reason));
    task tick;begin @(negedge clk);end endtask
    task begin_cal;
        begin
            train=0;dll_fail=0;startup_fail=0;tick;
            locked=0;ready=0;train=1;#0.001;
            if(valid || startup)$fatal(1,"Retrain did not invalidate immediately");
            tick;
            if(LIMIT>0 && (!bank || !start || !busy || valid || failed))$fatal(1,"Missing one-cycle DLL start");
        end
    endtask
    task make_ready;
        begin
            begin_cal;tick;
            if(start)$fatal(1,"DLL start was not a pulse");
            locked=1;tick;if(!startup || valid)$fatal(1,"Warmup stage bypassed");
            ready=1;tick;if(!valid || busy || failed)$fatal(1,"Completed stages did not publish readiness");
        end
    endtask
    integer i;
    initial begin
        #0.001;reset_n=0;#10;reset_n=1;tick;
        if(bank || start || startup || valid || busy || failed)$fatal(1,"No-request startup was active");
        if(LIMIT<=0)begin
            begin_cal;if(!failed || reason!=8 || bank || startup || valid)$fatal(1,"Invalid timeout was admitted");
        end else begin
            make_ready;
            repeat(12)begin tick;if(start || !valid || failed)$fatal(1,"Held training level retriggered calibration");end
            // Holding completed stages cannot spend or renew a startup timer.
            begin_cal;
            while(dut.age<5)tick;
            locked=1;tick;if(!startup || failed)$fatal(1,"Late DLL lock was rejected prematurely");
            while(!failed)tick;
            if(reason!=2 || dut.age!=LIMIT-1 || valid || bank)$fatal(1,"Warmup received a fresh timeout budget");
            repeat(4)begin tick;if(!failed || reason!=2)$fatal(1,"Timeout did not latch");end
            // Success observed on the final allowed cycle still completes.
            begin_cal;tick;locked=1;tick;
            while(dut.age<LIMIT-1)tick;
            ready=1;tick;if(!valid || failed)$fatal(1,"Ready at the deadline was rejected");
            locked=0;#0.001;if(valid)$fatal(1,"Lost DLL lock retained validity");
            tick;if(!failed || reason!=1)$fatal(1,"Lost DLL lock was not latched");
            begin_cal;tick;dll_fail=1;tick;dll_fail=0;
            repeat(3)begin tick;if(!failed || reason!=5)$fatal(1,"DLL reason was not retained after stage disable");end
            begin_cal;tick;locked=1;tick;startup_fail=1;tick;startup_fail=0;
            repeat(3)begin tick;if(!failed || reason!=8)$fatal(1,"DCC reason was not retained after stage disable");end
            make_ready;ready=0;#0.001;if(valid)$fatal(1,"Delivered-clock loss retained validity");
            tick;if(!failed || reason!=1)$fatal(1,"Delivered-clock loss was not latched");
            enable=0;tick;if(failed || bank || valid || busy || reason)$fatal(1,"Disable did not clear status");
        end
        $display("PASS v2 overall clock sequence retains one deadline, stage failures and explicit retraining");$finish;
    end
    initial begin #100000;$fatal(1,"Clock sequence watchdog state=%d age=%d",dut.state,dut.age);end
endmodule
