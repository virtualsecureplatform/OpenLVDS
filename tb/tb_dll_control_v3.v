// SPDX-License-Identifier: GPL-3.0-only
`timescale 1ns/1ps
// Native raw codes are deliberately reverse ordered; the synthetic observer
// decodes that physical mapping. Only external paths and arbiter are synthetic.
// Actual calibration,
// configuration CDC, sequencer, isolated launch, event guards and watchdog run.
module tb_dll_control_v3;
    parameter ADMITTED=1,TABLE_ADMITTED=1,HOLD_SETTLE=0;
    reg clk=0,raw=0,run_clock=1,reset_n=1,enable=1,train=0;
    always #20 clk=~clk;
    always #1.25 if(run_clock)raw=~raw;
    wire present,busy,locked,failed,applied,raw_separate,commit;
    wire [3:0] failure,measure_failure;
    wire [15:0] codes,raw_codes,raw_indices,configuration_sequence,route_sequence;
    wire mapping_valid;
    wire period_mode,swap,positive,arm,launch,reference;
    wire [1:0] section_a,section_b;
    reg [15:0] settled_sequence=0,applied_route_sequence=0;
    reg settled=0,a=0,b=0,qa=1,qb=1;
    integer settle_count=0,commits=0,launches=0,period_results=0;
    openlvds_dll_control_v3 #(.CODE_WIDTH(4),.RAW_WIDTH(4),.CODE_COUNT(16),.NATIVE_CODE_COUNT(16),
        .MODEL_ADMITTED(ADMITTED),.TABLE_MODEL_ADMITTED(TABLE_ADMITTED),.RAW_CODES(64'h0123456789abcdef),
        .TIMEOUT_CYCLES(HOLD_SETTLE ? 200 : 2500000)) dut(
        .mgmt_clk_25(clk),.raw_reference(raw),.reset_n(reset_n),.enable(enable),.train_req(train),.frontend_ready(1'b1),
        .clock_present(present),.cal_busy(busy),.dll_locked(locked),.cal_fail(failed),
        .failure_code(failure),.measurement_failure_code(measure_failure),.codes(codes),.raw_codes(raw_codes),.raw_indices(raw_indices),.mapping_valid(mapping_valid),
        .configuration_applied(applied),.raw_separated(raw_separate),.raw_commit(commit),.raw_sequence(configuration_sequence),
        .raw_update_allowed(!locked),.raw_settled(settled),.raw_settled_sequence(settled_sequence),
        .route_next_period(period_mode),.route_swap(swap),.route_positive_offset(positive),
        .route_section_a(section_a),.route_section_b(section_b),.route_sequence(route_sequence),
        .routes_applied(1'b1),.routes_sequence(applied_route_sequence),.arm(arm),.launch_pulse(launch),
        .reference_pulse(reference),.observed_a(a),.observed_b(b),.qa(qa),.qb(qb));
    // Physical backend deliberately presents a stale ready generation first.
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
            $fatal(1,"Launch before exact physical code/mode settling");
    end
    always @(posedge clk)begin
        if(dut.control.measure_valid && !dut.control.separated)period_results=period_results+1;
        if(failed && ADMITTED && TABLE_ADMITTED && !HOLD_SETTLE)$fatal(1,"Integrated DLL failed reason=%d measurement=%d",failure,measure_failure);
    end
    integer frozen_commits,frozen_launches,loss_cycles;
    reg [15:0] frozen_codes;
    initial begin
        #0.001;reset_n=0;#10;reset_n=1;
        @(negedge clk);train=1;@(negedge clk);train=0;
        if(HOLD_SETTLE)begin
            wait(failed);#1;
            if(failure!=2 || locked || launches)$fatal(1,"Missing physical settling escaped timeout");
        end else if(!ADMITTED || !TABLE_ADMITTED)begin
            wait(failed);#1;
            if(failure!=5 || measure_failure!=8 || locked || launches)$fatal(1,"Unadmitted controller released evidence");
        end else begin
            wait(locked);#1;
            if(period_results<64 || dut.control.calibration.confirmations!=63 || raw_codes==0 || raw_separate || busy)
                $fatal(1,"Premature lock confirmations=%d results=%d",dut.control.calibration.confirmations,period_results);
            frozen_codes=raw_codes;frozen_commits=commits;frozen_launches=launches;
            repeat(50)@(negedge clk);
            if(raw_codes!=frozen_codes || commits!=frozen_commits || launches!=frozen_launches || !locked)
                $fatal(1,"Locked configuration/measurement did not freeze");
            run_clock=0;loss_cycles=0;
            while(locked && loss_cycles<12)begin @(negedge clk);loss_cycles=loss_cycles+1;end
            if(locked || loss_cycles>10)$fatal(1,"Stopped raw clock retained lock");
        end
        $display("PASS v3 mapped native codes preserve atomic configuration, 64 confirmations, admission and clock-loss invalidation");$finish;
    end
    initial begin #10000000;$fatal(1,"DLL control watchdog state=%d config=%b",dut.control.calibration.state,applied);end
endmodule
