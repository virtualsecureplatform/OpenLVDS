// SPDX-License-Identifier: GPL-3.0-only
`timescale 1ns/1ps
// Actual clock-hold DCC topology with explicit test-only cell delays. This is
// startup/CDC/protocol evidence, never a SKY130 electrical timing certificate.
module tb_clock_startup_v2;
    parameter ADMITTED=1,WARMUP=256,MISSING_CLOCK=0;
    reg clk=0,ph0=0,ph90=0,reset_n=1,enable=1,locked=0,present=1,train=1;
    reg stop0=0,stop90=0,capture=0,stream_done=0;
    always #20 clk=~clk;
    always #1.25 ph0=~ph0;
    initial begin #0.625;forever #1.25 ph90=~ph90;end
    wire reset0_n,reset90_n,native0,native90;
    wire clock0=MISSING_CLOCK==1 ? 1'b0 : native0 && !stop0;
    wire clock90=MISSING_CLOCK!=0 ? 1'b0 : native90 && !stop90;
    openlvds_dcc_clock_hold_v2 dcc0(.phase0(ph0),.phase180(!ph0),.reset_n(reset0_n),.clock_out(native0));
    openlvds_dcc_clock_hold_v2 dcc90(.phase0(ph90),.phase180(!ph90),.reset_n(reset90_n),.clock_out(native90));
    wire ready,busy,failed,valid,payload_active;
    wire [3:0] failure;
    wire [1:0] pair;
    openlvds_tx_training_control_v2 #(.DCC_MODEL_ADMITTED(ADMITTED),.WARMUP_CYCLES(WARMUP),
        .TIMEOUT_CYCLES(MISSING_CLOCK ? 40 : 2500000)) dut(
        .mgmt_clk_25(clk),.raw_phase0(ph0),.raw_phase90(ph90),.clock0(clock0),.clock90(clock90),
        .reset_n(reset_n),.enable(enable),.dll_locked(locked),.source_clock_present(present),.train_req(train),
        .payload(2'b01),.dcc_reset0_n(reset0_n),.dcc_reset90_n(reset90_n),.clocks_ready(ready),
        .cal_busy(busy),.cal_fail(failed),.failure_code(failure),.pair_data(pair),.pair_valid(valid),.payload_active(payload_active));
    // Also elaborate the production default without an admission override.
    wire closed0,closed90,closed_ready,closed_run0,closed_run90;
    openlvds_clock_startup_v2 default_closed(
        .mgmt_clk_25(clk),.raw_phase0(ph0),.raw_phase90(ph90),.clock0(clock0),.clock90(clock90),
        .reset_n(reset_n),.enable(enable),.dll_locked(locked),.source_clock_present(present),
        .dcc_reset0_n(closed0),.dcc_reset90_n(closed90),.clocks_ready(closed_ready),
        .ready0(closed_run0),.ready90(closed_run90),.cal_busy(),.cal_fail(),.failure_code());
    always @(posedge clk)if(reset_n && (closed0 || closed90 || closed_ready || closed_run0 || closed_run90))
        $fatal(1,"Production default admitted an unqualified DCC");
    integer observed0=0,observed90=0,count=0;
    always @(posedge clock0 or negedge reset0_n)
        if(!reset0_n)observed0=0;else observed0=observed0+1;
    always @(posedge clock90 or negedge reset90_n)
        if(!reset90_n)observed90=0;else observed90=observed90+1;
    always @(posedge ready)begin
        if(observed0<WARMUP || observed90<WARMUP || !locked || !present || failed)
            $fatal(1,"Warmup released early actual_edges=%d/%d",observed0,observed90);
    end
    always @(posedge clock0)if(valid && capture)begin
        $display("PAIR %d %b%b %b",count,pair[0],pair[1],payload_active);
        if(count==349)train<=0;
        if(count==431)begin capture=0;stream_done=1;end
        count=count+1;
    end
    task acquire;
        begin
            @(negedge clk);locked=0;train=1;
            repeat(4)@(negedge clk);
            if(valid || ready || failed)$fatal(1,"DLL restart retained startup status");
            locked=1;wait(ready && valid);#0.001;
            if(observed0<WARMUP || observed90<WARMUP || failed || busy)$fatal(1,"Fresh acquisition skipped delivered-clock warmup");
        end
    endtask
    task stop_phase;
        input select90;
        integer cycles;
        begin
            if(select90)begin @(negedge clock90);stop90=1;end
            else begin @(negedge clock0);stop0=1;end
            cycles=0;
            while((ready || valid || !failed) && cycles<9)begin @(posedge clk);#0.001;cycles=cycles+1;end
            if(ready || valid || payload_active || !failed || failure!=1 || cycles>8)
                $fatal(1,"Stopped delivered phase retained validity phase90=%b cycles=%d",select90,cycles);
            @(negedge clk);locked=0;stop0=0;stop90=0;
        end
    endtask
    initial begin
        #0.001;reset_n=0;#10;reset_n=1;
        repeat(6)@(negedge clk);
        if(ready || valid || reset0_n || reset90_n)$fatal(1,"DCC released before DLL lock");
        locked=1;
        if(!ADMITTED || WARMUP<256)begin
            wait(failed);#0.001;
            if(failure!=8 || ready || valid || reset0_n || reset90_n)$fatal(1,"Unadmitted startup released clocks/data");
        end else if(MISSING_CLOCK)begin
            if(MISSING_CLOCK==2)begin
                wait(dut.startup.warm0);#0.001;
                if(ready || valid)$fatal(1,"One warm phase qualified the absent phase");
            end
            wait(failed);#0.001;
            if(failure!=2 || ready || valid)$fatal(1,"Missing clocks escaped bounded startup timeout");
        end else begin
            capture=1;wait(stream_done);
            stop_phase(1);acquire;
            stop_phase(0);acquire;
            @(negedge clk);enable=0;#0.01;
            if(ready || valid || payload_active || reset0_n || reset90_n)$fatal(1,"Disable did not invalidate asynchronously");
            @(negedge clk);enable=1;wait(ready && valid);
            present=0;#0.01;
            if(ready || valid || payload_active || reset0_n || reset90_n)$fatal(1,"Source loss did not invalidate asynchronously");
        end
        $display("PASS v2 actual DCC release, both delivered-clock warmups, training framing and stopped-clock invalidation");$finish;
    end
    initial begin #100000;$fatal(1,"Clock startup watchdog warm=%b/%b resets=%b/%b failure=%d",dut.startup.warm0,dut.startup.warm90,reset0_n,reset90_n,failure);end
endmodule
