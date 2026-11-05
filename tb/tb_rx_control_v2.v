// SPDX-License-Identifier: GPL-3.0-only
`timescale 1ns/1ps
// Actual DLL measurement/calibration, RX scan, startup and framing RTL.
// The external delay bank, signed paths, arbiter, eye and settling are explicit
// synthetic fixtures; this bench gives no SKY130 electrical timing admission.
module tb_rx_control_v2;
    parameter MODE=0,DEADLINE=0;
    localparam HOLD_SETTLE=MODE==5;
    localparam LIMIT=DEADLINE>0 ? DEADLINE : (HOLD_SETTLE ? 200 : 2500000);
    reg clk=0,raw=0,post=0,reset_n=1,enable=1,train=0,stop90=0,source_running=1;
    always #20 clk=~clk;
    always #1.25 if(source_running)raw=~raw;else raw=0;
    wire present,dll_present,busy,locked,clocks_ready,ready,failed,applied,raw_separate,commit;
    wire [3:0] failure,measure_failure;
    wire [15:0] codes,raw_codes,configuration_sequence,route_sequence;
    wire period_mode,swap,positive,arm,launch,reference;
    wire [1:0] section_a,section_b,tx_pair,data;
    wire valid,reset0_n,reset90_n,clock0,native90;
    wire clock90=native90 && !stop90;
    reg ph0=0,ph90=0,ph180=0,ph270=0;
    reg [15:0] settled_sequence=0,applied_route_sequence=0,deskew_settled_sequence=0;
    reg settled=0,deskew_settled=0,a=0,b=0,qa=1,qb=1;
    wire [6:0] table_index,deskew;
    wire [15:0] deskew_sequence,clearance;
    wire deskew_commit;
    integer settle_count=0,commits=0,launches=0,period_results=0,deskew_commits=0,deskew_settle_count=0;
    wire [15:0] lo=table_index*10;
    wire good_code=deskew>=20 && deskew<=90;
    // The post-deskew clock remains real in the interface: only this test
    // backend supplies a synthetic propagation delay, including code changes.
    always @(raw)post<=#(deskew*0.01)raw;
    openlvds_rx_control_v2 #(.DLL_CODE_WIDTH(4),.DLL_LAST_CODE(15),.DESKEW_CODE_WIDTH(7),.DESKEW_CODE_COUNT(101),
        .DLL_MODEL_ADMITTED(MODE!=1),.CODE_MODEL_ADMITTED(MODE!=2),.DESKEW_MODEL_ADMITTED(MODE!=3),
        .DCC_MODEL_ADMITTED(MODE!=4),.TIMEOUT_CYCLES(LIMIT),.CONFIRMATIONS(MODE==10 ? 1 : 64)) dut(
        .mgmt_clk_25(clk),.source_clk(raw),.raw_reference(post),.raw_phase0(ph0),.raw_phase90(ph90),
        .clock0(clock0),.clock90(clock90),.reset_n(reset_n),.enable(enable),.train_req(train),.frontend_ready(1'b1),
        .clock_present(present),.dll_reference_present(dll_present),.cal_busy(busy),.dll_locked(locked),
        .clocks_ready(clocks_ready),.cal_fail(failed),.failure_code(failure),.measurement_failure_code(measure_failure),
        .table_ready(1'b1),.table_index(table_index),.delay_lo_ps(lo),.delay_hi_ps(lo+16'd1),
        .deskew_index(deskew),.deskew_sequence(deskew_sequence),.deskew_commit(deskew_commit),
        .deskew_update_allowed(!reset0_n && !reset90_n),.deskew_settled(deskew_settled),
        .deskew_settled_sequence(deskew_settled_sequence),.captured_pair(good_code ? tx_pair : tx_pair^2'b01),
        .captured_valid(1'b1),.rx_data(data),.rx_valid(valid),.rx_ready(ready),.selected_clearance_ps(clearance),
        .dcc_reset0_n(reset0_n),.dcc_reset90_n(reset90_n),.codes(codes),.raw_codes(raw_codes),
        .configuration_applied(applied),.raw_separated(raw_separate),.raw_commit(commit),.raw_sequence(configuration_sequence),
        .raw_update_allowed(1'b1),.raw_settled(settled),.raw_settled_sequence(settled_sequence),
        .route_next_period(period_mode),.route_swap(swap),.route_positive_offset(positive),
        .route_section_a(section_a),.route_section_b(section_b),.route_sequence(route_sequence),
        .routes_applied(1'b1),.routes_sequence(applied_route_sequence),.arm(arm),.launch_pulse(launch),
        .reference_pulse(reference),.observed_a(a),.observed_b(b),.qa(qa),.qb(qb));
    openlvds_dcc_clock_hold_v2 dcc0(.phase0(ph0),.phase180(ph180),.reset_n(reset0_n),.clock_out(clock0));
    openlvds_dcc_clock_hold_v2 dcc90(.phase0(ph90),.phase180(ph270),.reset_n(reset90_n),.clock_out(native90));
    openlvds_training_tx_v2 tx(.clk_pair(raw),.reset_n(reset_n),.run(1'b1),.train_req(train),
        .payload(2'b01),.pair_data(tx_pair),.payload_active());
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
            delays[k]=600+8*k+8*((raw_codes>>(4*k))&15);
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
        if(!applied || settled_sequence!=configuration_sequence || raw_codes!=codes || raw_separate==period_mode)
            $fatal(1,"RX launched an unapplied physical configuration");
    end
    // This external protocol model publishes cascaded phases after DLL lock.
    // Their actual test delays derive from the committed four-code bundle.
    // Pre-lock switching, analog transients and SKY130 timing are unqualified.
    integer q0,q1,q2,q3;
    always @(post)begin
        if(locked)begin
            q0=600+8*((raw_codes>>0)&15);q1=608+8*((raw_codes>>4)&15);
            q2=616+8*((raw_codes>>8)&15);q3=624+8*((raw_codes>>12)&15);
            ph0<=#((q0+q1+q2+q3)/1000.0)post;
            ph90<=#(q0/1000.0)post;ph180<=#((q0+q1)/1000.0)post;ph270<=#((q0+q1+q2)/1000.0)post;
        end else begin ph0<=0;ph90<=0;ph180<=0;ph270<=0;end
    end
    integer lock_count=0,frozen_commits=0,frozen_launches=0,frozen_periods=0,payload_pairs=0,loss_cycles;
    reg [15:0] frozen_codes;
    reg scanning=0;
    always @(posedge clk)if(dut.dll.measure_valid && !dut.dll.separated)period_results=period_results+1;
    always @(posedge locked)begin
        lock_count=lock_count+1;
        if(dut.dll.calibration.confirmations!=63 || period_results<64*lock_count || raw_separate || !applied)
            $fatal(1,"RX skipped actual 64 DLL confirmations");
        frozen_commits=commits;frozen_launches=launches;frozen_codes=raw_codes;frozen_periods=period_results;scanning=1;
        $display("DLL_LOCK age=%d time=%g",dut.training.age,$realtime);
    end
    always @(posedge clk)if(scanning && locked &&
        (commits!=frozen_commits || launches!=frozen_launches || raw_codes!=frozen_codes || period_results!=frozen_periods))
        $fatal(1,"DLL changed during RX deskew scan/payload");
    always @(posedge deskew_commit)begin
        deskew_commits=deskew_commits+1;
        if(!locked || reset0_n || reset90_n || ready || valid)$fatal(1,"Deskew changed outside locked/held capture path");
    end
    always @(negedge raw)begin
        if(deskew_commit)begin deskew_settle_count=12;deskew_settled=0;end
        else if(deskew_settle_count>0)begin
            deskew_settle_count=deskew_settle_count-1;
            if(MODE!=6)begin
                deskew_settled=1;
                deskew_settled_sequence=deskew_settle_count>0 ? deskew_sequence-1 : deskew_sequence;
            end
        end
    end
    integer observed0=0,observed90=0,commands=0;
    always @(posedge clock0 or negedge reset0_n)if(!reset0_n)observed0=0;else observed0=observed0+1;
    always @(posedge clock90 or negedge reset90_n)if(!reset90_n)observed90=0;else observed90=observed90+1;
    always @(posedge dut.training.command_pulse)begin
        commands=commands+1;
        if(!locked || !applied || observed0<256 || observed90<256 || !deskew_settled || deskew_settled_sequence!=deskew_sequence)
            $fatal(1,"RX measured before locked configuration, physical settling and actual warmup");
    end
    always @(negedge clock0)if(valid)begin
        if(data!==2'b01)$fatal(1,"RX payload reordered");
        payload_pairs=payload_pairs+1;
    end
    task expect_failure;
        input [3:0] reason;
        begin
            wait(failed);#0.01;
            if(failure!=reason || ready || valid || reset0_n || reset90_n || busy)
                $fatal(1,"RX failure did not close outputs reason=%d expected=%d",failure,reason);
            if((MODE==6 || MODE==7) && (dut.training.age!=LIMIT-1 || dut.dll.cal_fail ||
                dut.training.transaction.cal_fail || dut.training.scanner.cal_fail))
                $fatal(1,"Timeout did not originate from the single overall deadline");
            repeat(4)@(negedge clk);
            if(!failed || failure!=reason)$fatal(1,"RX failure lost after disabling child stages");
        end
    endtask
    task acquire;
        input integer expected_commits;
        begin
            wait(ready || failed);#0.01;
            if(failed || !ready || deskew!=55 || clearance!=349 || deskew_commits!=expected_commits || commands<expected_commits)
                $fatal(1,"RX acquisition failed reason=%d measurement=%d code=%d clearance=%d commits=%d age=%d",failure,measure_failure,deskew,clearance,deskew_commits,dut.training.age);
            if(valid || busy)$fatal(1,"RX payload valid before end marker");
            $display("RX_READY age=%d time=%g",dut.training.age,$realtime);
        end
    endtask
    initial begin
        #0.001;reset_n=0;#10;reset_n=1;
        repeat(5)@(negedge clk);
        if(busy || ready || valid || locked || commits || deskew_commits)$fatal(1,"RX started without request");
        train=1;
        if((MODE>=1 && MODE<=4) || MODE==10)begin expect_failure(8);end
        else if(MODE==5)begin expect_failure(2);if(locked || deskew_commits)$fatal(1,"RX bypassed missing DLL settling");end
        else if(MODE==6 || MODE==7)begin
            expect_failure(2);
            if(!lock_count || !deskew_commits || (MODE==6 && deskew_commits!=1) || (MODE==7 && (deskew_commits<2 || deskew_commits>=102)))
                $fatal(1,"Deadline fixture missed DLL-to-scan boundary lock=%d commits=%d",lock_count,deskew_commits);
        end else begin
            acquire(102);
            repeat(5)@(negedge clk);
            if(lock_count!=1 || deskew_commits!=102)$fatal(1,"Held request retriggered acquisition");
            train=0;wait(payload_pairs>=64);
            if(MODE==8)begin
                @(negedge clk);train=1;#0.01;
                if(ready || valid || reset0_n || reset90_n || deskew!=55)$fatal(1,"Retrain retained output readiness or cleared deskew word");
                acquire(204);
                if(lock_count!=2 || period_results<128)$fatal(1,"Retrain bypassed fresh DLL calibration");
                @(negedge clk);train=0;wait(payload_pairs>=128);
            end
            @(negedge clock90);
            if(MODE==9)source_running=0;else stop90=1;
            loss_cycles=0;
            while((ready || valid || !failed) && loss_cycles<9)begin @(posedge clk);#0.001;loss_cycles=loss_cycles+1;end
            if(ready || valid || !failed || failure!=1 || loss_cycles>8)$fatal(1,"RX delivered-clock loss escaped budget");
            expect_failure(1);
        end
        $display("PASS v2 RX actual DLL, safe deskew scan, real startup and payload mode=%d",MODE);$finish;
    end
    initial begin #10000000;$fatal(1,"RX composition watchdog DLL=%d RX=%d age=%d",dut.dll.calibration.state,dut.training.scanner.state,dut.training.age);end
endmodule
