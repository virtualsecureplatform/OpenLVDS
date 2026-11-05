// SPDX-License-Identifier: GPL-3.0-only
`timescale 1ns/1ps
// Stop either actual delivered clock throughout one period at all supported
// frequencies, before warmup finishes. No scan result/status is forced.
module tb_rx_clock_loss_v3;
    parameter HALF_PERIOD=1.25;
    reg mgmt=0,raw=0,raw90=0,reset_n=1,enable=0,train=0,stop0=0,stop90=0;
    always #20 mgmt=~mgmt;
    always #(HALF_PERIOD) raw=~raw;
    initial begin #(HALF_PERIOD/2);forever #(HALF_PERIOD)raw90=~raw90;end
    wire native0,native90,reset0_n,reset90_n,ready,valid,failed;
    wire clock0=native0 && !stop0,clock90=native90 && !stop90;
    wire [3:0] failure;
    openlvds_rx_training_v3 #(.CODE_WIDTH(7),.CODE_COUNT(101),.CODE_MODEL_ADMITTED(1),
        .DESKEW_MODEL_ADMITTED(1),.DCC_MODEL_ADMITTED(1),.TIMEOUT_CYCLES(1000)) dut(
        .mgmt_clk_25(mgmt),.source_clk(raw),.raw_phase0(raw),.raw_phase90(raw90),.clock0(clock0),.clock90(clock90),
        .reset_n(reset_n),.enable(enable),.train_req(train),.dll_locked(1'b1),.dll_failed(1'b0),.dll_failure_code(4'd0),
        .dll_enable(),.dll_train(),.table_ready(1'b1),.table_index(),.delay_lo_ps(16'd0),.delay_hi_ps(16'd1),
        .update_allowed(1'b0),.physical_settled(1'b0),.physical_settled_sequence(16'd0),.deskew_index(),
        .deskew_sequence(),.deskew_commit(),.dcc_reset0_n(reset0_n),.dcc_reset90_n(reset90_n),
        .clocks_ready(),.source_clock_present(),.captured_pair(2'b0),.captured_valid(1'b0),
        .rx_data(),.rx_valid(valid),.rx_ready(ready),.cal_busy(),.cal_fail(failed),.failure_code(failure),.selected_clearance_ps());
    openlvds_dcc_clock_hold_v2 dcc0(.phase0(raw),.phase180(!raw),.reset_n(reset0_n),.clock_out(native0));
    openlvds_dcc_clock_hold_v2 dcc90(.phase0(raw90),.phase180(!raw90),.reset_n(reset90_n),.clock_out(native90));
    integer phase,which,cycles,worst=0;
    initial begin
        for(which=0;which<2;which=which+1)for(phase=0;phase<80;phase=phase+1)begin
            @(negedge mgmt);enable=0;train=0;reset_n=0;stop0=0;stop90=0;
            repeat(2)@(negedge mgmt);reset_n=1;enable=1;train=1;
            wait(dut.startup.seen0 && dut.startup.seen90);
            #(phase*2*HALF_PERIOD/80.0);
            if(dut.startup.warm0 || dut.startup.warm90 || ready || dut.transaction_busy)
                $fatal(1,"Clock loss fixture missed initial real warmup");
            if(which==0)stop0=1;else stop90=1;
            cycles=0;
            while(!failed && cycles<9)begin @(posedge mgmt);#0.001;cycles=cycles+1;end
            if(!failed || failure!=1 || cycles>8 || ready || valid || reset0_n || reset90_n)
                $fatal(1,"Warmup clock loss escaped bound phase=%d which=%d cycles=%d",phase,which,cycles);
            if(cycles>worst)worst=cycles;
        end
        $display("PASS v3 RX warmup clock loss: 160 phases half_period=%g worst=%d cycles",HALF_PERIOD,worst);$finish;
    end
    initial begin #1000000;$fatal(1,"RX clock-loss watchdog");end
endmodule
