// SPDX-License-Identifier: GPL-3.0-only
`timescale 1ns/1ps
// Full TX control composition. Only the external physical bank, signed paths
// and arbiter are synthetic. Actual DLL/configuration/trial/launch RTL, actual
// clock-hold DCC topology and actual startup/framing controllers are exercised.
module tb_tx_control_v3;
    parameter DLL_ADMITTED=1,DCC_ADMITTED=1,TABLE_ADMITTED=1,HOLD_SETTLE=0,BAD_TABLE=0,INVALID_POLICY=0;
    reg clk=0,raw=0,reset_n=1,enable=1,train=0,stop90=0,expect_fault=0;
    always #20 clk=~clk;
    always #1.25 raw=~raw;
    wire present,busy,locked,ready,failed,applied,raw_separate,commit;
    wire [3:0] failure,measure_failure;
    wire [15:0] codes,raw_codes,raw_indices,configuration_sequence,route_sequence;
    wire mapping_valid;
    wire period_mode,swap,positive,arm,launch,reference;
    wire [1:0] section_a,section_b,pair;
    wire valid,payload_active,reset0_n,reset90_n,clock0,native90;
    wire clock90=native90 && !stop90;
    reg ph0=0,ph90=0,ph180=0,ph270=0;
    reg [15:0] settled_sequence=0,applied_route_sequence=0;
    reg settled=0,a=0,b=0,qa=1,qb=1;
    integer settle_count=0,commits=0,launches=0,period_results=0;
    openlvds_tx_control_v3 #(.CODE_WIDTH(4),.RAW_WIDTH(4),.CODE_COUNT(16),.NATIVE_CODE_COUNT(BAD_TABLE ? 15 : 16),
        .TABLE_MODEL_ADMITTED(TABLE_ADMITTED),.RAW_CODES(64'h0123456789abcdef),.DLL_MODEL_ADMITTED(DLL_ADMITTED),
        .DCC_MODEL_ADMITTED(DCC_ADMITTED),.CONFIRMATIONS(INVALID_POLICY==1 ? 1 : 64),
        .WARMUP_CYCLES(INVALID_POLICY==2 ? 255 : 256),
        .TIMEOUT_CYCLES((HOLD_SETTLE || BAD_TABLE) ? 200 : (INVALID_POLICY==3 ? 2500001 : 2500000))) dut(
        .mgmt_clk_25(clk),.raw_reference(raw),.raw_phase0(ph0),.raw_phase90(ph90),.clock0(clock0),.clock90(clock90),
        .reset_n(reset_n),.enable(enable),.train_req(train),.frontend_ready(1'b1),.payload(2'b01),
        .clock_present(present),.cal_busy(busy),.dll_locked(locked),.clocks_ready(ready),.cal_fail(failed),
        .failure_code(failure),.measurement_failure_code(measure_failure),.pair_data(pair),.pair_valid(valid),
        .payload_active(payload_active),.dcc_reset0_n(reset0_n),.dcc_reset90_n(reset90_n),
        .codes(codes),.raw_codes(raw_codes),.raw_indices(raw_indices),.mapping_valid(mapping_valid),.configuration_applied(applied),.raw_separated(raw_separate),
        .raw_commit(commit),.raw_sequence(configuration_sequence),.raw_update_allowed(!valid),
        .raw_settled(settled),.raw_settled_sequence(settled_sequence),
        .route_next_period(period_mode),.route_swap(swap),.route_positive_offset(positive),
        .route_section_a(section_a),.route_section_b(section_b),.route_sequence(route_sequence),
        .routes_applied(1'b1),.routes_sequence(applied_route_sequence),.arm(arm),.launch_pulse(launch),
        .reference_pulse(reference),.observed_a(a),.observed_b(b),.qa(qa),.qb(qb));
    openlvds_dcc_clock_hold_v2 dcc0(.phase0(ph0),.phase180(ph180),.reset_n(reset0_n),.clock_out(clock0));
    openlvds_dcc_clock_hold_v2 dcc90(.phase0(ph90),.phase180(ph270),.reset_n(reset90_n),.clock_out(native90));
    always @(negedge raw)begin
        if(commit)begin commits=commits+1;settle_count=12;settled=0;end
        else if(settle_count>0)begin
            settle_count=settle_count-1;settled=!HOLD_SETTLE;
            settled_sequence=settle_count>0 ? configuration_sequence-1 : configuration_sequence;
        end
    end
    always @(negedge clk)applied_route_sequence<=route_sequence;
    integer delays[0:3];
    integer total,k;
    real delay_a,delay_b;
    always @(launch)begin
        total=0;
        for(k=0;k<4;k=k+1)begin
            delays[k]=600+8*k+8*(15-((raw_codes>>(4*k))&15));
            total=total+delays[k];
        end
        delay_a=1.0+delays[section_a]/1000.0+(positive ? 0 : 0.02);
        delay_b=1.0+(period_mode ? total : delays[section_b])/1000.0+(positive ? 0.02 : 0);
        if(!period_mode)a<=#(delay_a)launch;
        b<=#(delay_b)launch;
    end
    always @(reference)if(period_mode)a<=#(1.0+(positive ? 0 : 0.02))reference;
    always @(negedge arm)begin qa=1;qb=1;end
    always @(posedge a)if(arm && qa && qb)begin qa=swap ? 1 : 0;qb=swap ? 0 : 1;end
    always @(posedge b)if(arm && qa && qb)begin qa=swap ? 0 : 1;qb=swap ? 1 : 0;end
    always @(posedge launch)begin
        launches=launches+1;
        if(!applied || settled_sequence!=configuration_sequence || raw_indices!=codes || raw_codes!=(codes^16'hffff) || !mapping_valid || raw_separate==period_mode)
            $fatal(1,"TX launched an unapplied physical configuration");
    end
    // This external protocol model publishes cascaded phases after DLL lock.
    // Their actual test delays derive from the committed four-code bundle.
    // Pre-lock switching, analog transients and SKY130 timing are unqualified.
    integer q0,q1,q2,q3;
    always @(raw)begin
        if(locked)begin
            q0=600+8*(15-((raw_codes>>0)&15));q1=608+8*(15-((raw_codes>>4)&15));
            q2=616+8*(15-((raw_codes>>8)&15));q3=624+8*(15-((raw_codes>>12)&15));
            ph0<=#((q0+q1+q2+q3)/1000.0)raw;
            ph90<=#(q0/1000.0)raw;ph180<=#((q0+q1)/1000.0)raw;ph270<=#((q0+q1+q2)/1000.0)raw;
        end else begin ph0<=0;ph90<=0;ph180<=0;ph270<=0;end
    end
    always @(posedge clk)begin
        if(dut.dll.control.measure_valid && !dut.dll.control.separated)period_results=period_results+1;
        if(failed && DLL_ADMITTED && DCC_ADMITTED && TABLE_ADMITTED && !HOLD_SETTLE && !BAD_TABLE && !INVALID_POLICY && !expect_fault)
            $fatal(1,"TX controller failed reason=%d measurement=%d",failure,measure_failure);
    end
    integer observed0=0,observed90=0,count=0;
    reg stream_done=0;
    always @(posedge clock0 or negedge reset0_n)if(!reset0_n)observed0=0;else observed0=observed0+1;
    always @(posedge clock90 or negedge reset90_n)if(!reset90_n)observed90=0;else observed90=observed90+1;
    always @(posedge clk)if(ready && (period_results<64 || observed0<256 || observed90<256))
        $fatal(1,"TX published readiness before calibration and both delivered warmups");
    always @(posedge clock0)if(valid && !stream_done)begin
        $display("PAIR %d %b%b %b",count,pair[0],pair[1],payload_active);
        if(count==431)stream_done=1;
        count=count+1;
    end
    always @(negedge clk)if(count>=350)train<=0;
    integer frozen_commits,frozen_launches,loss_cycles;
    reg [15:0] frozen_codes;
    initial begin
        #0.001;reset_n=0;#10;reset_n=1;
        repeat(5)@(negedge clk);
        if(busy || ready || valid || locked)$fatal(1,"TX started without an explicit request");
        train=1; // held throughout calibration and until the lab ends training
        if(HOLD_SETTLE || BAD_TABLE || INVALID_POLICY || !DLL_ADMITTED || !DCC_ADMITTED || !TABLE_ADMITTED)begin
            wait(failed);#0.001;
            if(failure!=(HOLD_SETTLE ? 2 : 8) || ready || valid || payload_active || reset0_n || reset90_n)
                $fatal(1,"TX admission/timeout did not close output reason=%d",failure);
            if(BAD_TABLE && (launches || mapping_valid))$fatal(1,"Invalid native DLL word escaped mapping guard");
        end else begin
            wait(ready && valid);#0.001;
            if(period_results<64 || dut.dll.control.calibration.confirmations!=63 || raw_codes==0 || raw_separate || busy)
                $fatal(1,"TX skipped 64 actual DLL confirmations");
            wait(stream_done);
            frozen_codes=raw_codes;frozen_commits=commits;frozen_launches=launches;
            repeat(20)@(negedge clk);
            if(raw_codes!=frozen_codes || commits!=frozen_commits || launches!=frozen_launches || !valid)
                $fatal(1,"TX calibration was not frozen during payload");
            expect_fault=1;@(negedge clock90);stop90=1;loss_cycles=0;
            while((ready || valid || !failed) && loss_cycles<9)begin @(posedge clk);#0.001;loss_cycles=loss_cycles+1;end
            if(ready || valid || payload_active || !failed || failure!=1 || loss_cycles>8)
                $fatal(1,"TX retained validity after delivered-clock loss cycles=%d",loss_cycles);
            repeat(4)@(negedge clk);
            if(!failed || failure!=1)$fatal(1,"TX lost the original failure after disabling stages");
        end
        $display("PASS v3 TX composes actual DLL/configuration/measurement, DCC startup and training under one deadline");$finish;
    end
    initial begin #10000000;$fatal(1,"TX composition watchdog state=%d DLL=%d",dut.sequence_control.state,dut.dll.control.calibration.state);end
endmodule
