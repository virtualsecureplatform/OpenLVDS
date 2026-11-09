// SPDX-License-Identifier: GPL-3.0-only
`timescale 1ns/1ps
// Freeze either delivered HDL clock at its current HIGH/LOW level across
// one period, using independent phases. No scan result/status is forced.
// Functional test-cell and synthetic backend fixtures only; no electrical claim.
module tb_rx_frozen_clock_loss_300_v1;
    parameter MHZ=300,DUTY_PERCENT=50;
    localparam real PERIOD=1000.0/MHZ,HIGH=PERIOD*DUTY_PERCENT/100.0,LOW=PERIOD-HIGH;
    reg mgmt=0,raw=0,raw90=0,raw180=0,raw270=0,source_running=1,held0=0,held90=0,reset_n=1,enable=0,train=0,stop0=0,stop90=0;
    always #20 mgmt=~mgmt;
    initial begin #(PERIOD);forever begin raw=source_running;#(HIGH);raw=0;#(LOW);end end
    initial begin #(PERIOD*1.25);forever begin raw90=source_running;#(HIGH);raw90=0;#(LOW);end end
    initial begin #(PERIOD*1.5);forever begin raw180=source_running;#(HIGH);raw180=0;#(LOW);end end
    initial begin #(PERIOD*1.75);forever begin raw270=source_running;#(HIGH);raw270=0;#(LOW);end end
    wire native0,native90,reset0_n,reset90_n,ready,valid,failed;
    wire clock0=stop0 ? held0:native0,clock90=stop90 ? held90:native90;
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
    openlvds_dcc_clock_hold_v2 dcc0(.phase0(raw),.phase180(raw180),.reset_n(reset0_n),.clock_out(native0));
    openlvds_dcc_clock_hold_v2 dcc90(.phase0(raw90),.phase180(raw270),.reset_n(reset90_n),.clock_out(native90));
    integer phase,which,cycles,worst=0,low0=0,high0=0,low90=0,high90=0;
    initial begin
        for(which=0;which<2;which=which+1)for(phase=0;phase<80;phase=phase+1)begin
            @(negedge mgmt);enable=0;train=0;reset_n=0;stop0=0;stop90=0;
            repeat(2)@(negedge mgmt);reset_n=1;enable=1;train=1;
            wait(dut.startup.seen0 && dut.startup.seen90);
            #(phase*PERIOD/80.0);
            if(dut.startup.warm0 || dut.startup.warm90 || ready || dut.transaction_busy)
                $fatal(1,"Clock loss fixture missed initial real warmup");
            if(which==0)begin held0=clock0;stop0=1;if(held0)high0=high0+1;else low0=low0+1;end
            else begin held90=clock90;stop90=1;if(held90)high90=high90+1;else low90=low90+1;end
            cycles=0;
            while(!failed && cycles<9)begin @(posedge mgmt);#0.001;cycles=cycles+1;end
            if(!failed || failure!=1 || cycles>8 || ready || valid || reset0_n || reset90_n)
                $fatal(1,"Warmup clock loss escaped bound phase=%d which=%d cycles=%d",phase,which,cycles);
            if(cycles>worst)worst=cycles;
        end
        if(low0==0 || high0==0 || low90==0 || high90==0 || low0+high0!=80 || low90+high90!=80)
            $fatal(1,"Frozen clock coverage omitted a held level");
        $display("PASS 300 RX frozen-clock loss: mhz=%0d duty_percent=%0d phases=160 worst=%0d low0=%0d high0=%0d low90=%0d high90=%0d",MHZ,DUTY_PERCENT,worst,low0,high0,low90,high90);$finish;
    end
    initial begin #1000000;$fatal(1,"RX clock-loss watchdog");end
endmodule
