// SPDX-License-Identifier: GPL-3.0-only
`timescale 1ns/1ps
// Actual scan/transaction/startup/framing RTL. The eye, settled backend and
// cell delays are explicit protocol fixtures, not native timing evidence.
module tb_rx_training_v3;
    parameter MODE=0;
    localparam COUNT=101;
    localparam LIMIT=MODE==7 ? 2500 : (MODE==1 || MODE==2 || MODE==6 ? 200 : 20000);
    reg mgmt=0,raw=0,raw90=0,reset_n=1,enable=1,train=0,locked=0,dll_failed=0;
    reg source_running=1,stop90=0,table_ready=1;
    always #20 mgmt=~mgmt;
    always #1.25 if(source_running)raw=~raw;else raw=0;
    initial begin #0.625;forever #1.25 raw90=~raw90;end
    wire [6:0] index,deskew;
    wire [15:0] sequence_id,clearance;
    wire commit,ready,busy,failed,valid,dll_enable,dll_train,present,clocks_ready;
    wire reset0_n,reset90_n,clock0,native90;
    wire clock90=native90 && !stop90;
    wire [3:0] failure;
    wire [1:0] tx_pair,rx_data;
    integer settle_count=0,commits=0,commands=0,dll_requests=0;
    wire good_code=MODE!=14 && deskew>=20 && deskew<=90 && !(MODE==13 && commits>COUNT);
    reg settled=0;
    reg [15:0] settled_sequence=0;
    wire [15:0] delay_lo=index*10;
    openlvds_rx_training_v3 #(.CODE_WIDTH(7),.CODE_COUNT(COUNT),.CODE_MODEL_ADMITTED(MODE!=3),
        .DESKEW_MODEL_ADMITTED(MODE!=4),.DCC_MODEL_ADMITTED(MODE!=5),.TIMEOUT_CYCLES(LIMIT)) dut(
        .mgmt_clk_25(mgmt),.source_clk(raw),.raw_phase0(raw),.raw_phase90(raw90),.clock0(clock0),.clock90(clock90),
        .reset_n(reset_n),.enable(enable),.train_req(train),.dll_locked(locked),.dll_failed(dll_failed),
        .dll_failure_code(4'd3),.dll_enable(dll_enable),.dll_train(dll_train),.table_ready(table_ready),
        .table_index(index),.delay_lo_ps(delay_lo),.delay_hi_ps(delay_lo+16'd1),
        .update_allowed(!reset0_n && !reset90_n),.physical_settled(settled),
        .physical_settled_sequence(settled_sequence),.deskew_index(deskew),.deskew_sequence(sequence_id),
        .deskew_commit(commit),.dcc_reset0_n(reset0_n),.dcc_reset90_n(reset90_n),.clocks_ready(clocks_ready),
        .source_clock_present(present),.captured_pair(good_code ? tx_pair : (tx_pair^2'b01)),
        .captured_valid(1'b1),.rx_data(rx_data),.rx_valid(valid),.rx_ready(ready),.cal_busy(busy),
        .cal_fail(failed),.failure_code(failure),.selected_clearance_ps(clearance));
    openlvds_dcc_clock_hold_v2 dcc0(.phase0(raw),.phase180(!raw),.reset_n(reset0_n),.clock_out(clock0));
    openlvds_dcc_clock_hold_v2 dcc90(.phase0(raw90),.phase180(!raw90),.reset_n(reset90_n),.clock_out(native90));
    openlvds_training_tx_v2 tx(.clk_pair(raw),.reset_n(reset_n),.run(1'b1),.train_req(train),
        .payload(2'b01),.pair_data(tx_pair),.payload_active());
    integer observed0=0,observed90=0,warmups=0,payload_pairs=0;
    always @(posedge clock0 or negedge reset0_n)if(!reset0_n)observed0=0;else observed0=observed0+1;
    always @(posedge clock90 or negedge reset90_n)if(!reset90_n)observed90=0;else observed90=observed90+1;
    always @(posedge clocks_ready)begin
        warmups=warmups+1;
        if(observed0<256 || observed90<256)$fatal(1,"Capture readiness skipped actual warmup");
    end
    always @(posedge dll_train)dll_requests=dll_requests+1;
    always @(posedge commit)begin
        commits=commits+1;
        if(reset0_n || reset90_n || !dut.hold_clocks || valid || ready)
            $fatal(1,"RX code changed outside held clock path");
    end
    always @(negedge raw)begin
        if(commit)begin settle_count=12;settled=0;end
        else if(settle_count>0)begin
            settle_count=settle_count-1;
            if(MODE!=1 && !(MODE==9 && commits==6))begin
                settled=1;
                settled_sequence=(settle_count>0 || MODE==2) ? sequence_id-1 : sequence_id;
            end
        end
    end
    always @(posedge dut.command_pulse)begin
        commands=commands+1;
        if(!clocks_ready || observed0<256 || observed90<256 || !settled || settled_sequence!=sequence_id || dut.transaction_busy)
            $fatal(1,"Frame scan started before physical settling and fresh warmup");
    end
    always @(negedge clock0)if(valid)begin
        if(rx_data!==2'b01)$fatal(1,"Payload reordered after end marker");
        payload_pairs=payload_pairs+1;
    end
    task expect_failure;
        input [3:0] reason;
        begin
            wait(failed);#0.01;
            if(failure!=reason || ready || valid || busy || reset0_n || reset90_n)
                $fatal(1,"Wrong failure or released clocks reason=%d expected=%d",failure,reason);
            repeat(4)@(negedge mgmt);
            if(!failed || failure!=reason)$fatal(1,"Original failure did not stay latched");
        end
    endtask
    integer frozen_commits,frozen_commands,loss_cycles;
    initial begin
        #0.001;reset_n=0;#10;reset_n=1;
        repeat(6)@(negedge mgmt);
        if(busy || ready || dll_enable || reset0_n || reset90_n || commits)$fatal(1,"RX started without request");
        train=1;
        // The first acquisition must wait for an actual lock, never bypass it.
        repeat(6)@(negedge mgmt);
        if(ready || commits || reset0_n || reset90_n)$fatal(1,"RX bypassed DLL lock");
        if(MODE!=6)locked=1;
        if(MODE==3 || MODE==4 || MODE==5)begin expect_failure(8);if(commits)$fatal(1,"Unadmitted model published code");end
        else if(MODE==1 || MODE==2 || MODE==6 || MODE==7)begin
            expect_failure(2);
            if(MODE==7 && (commits<2 || commits>=COUNT))$fatal(1,"Deadline did not span multiple successful updates");
        end else if(MODE==8)begin
            wait(commits==1);@(negedge mgmt);source_running=0;loss_cycles=0;
            while(!failed && loss_cycles<9)begin @(posedge mgmt);#0.001;loss_cycles=loss_cycles+1;end
            if(!failed || loss_cycles>8)$fatal(1,"Source loss exceeded eight management cycles");
            expect_failure(1);
        end else if(MODE==10 || MODE==11 || MODE==12)begin
            wait(commits==3);@(negedge mgmt);
            if(MODE==10)locked=0;
            if(MODE==11)dll_failed=1;
            if(MODE==12)table_ready=0;
            expect_failure(MODE==10 ? 4 : (MODE==11 ? 3 : 8));
        end else if(MODE==13 || MODE==14)begin expect_failure(MODE==13 ? 7 : 6);end
        else begin
            if(MODE==9)begin
                wait(commits==6);repeat(3)@(negedge mgmt);train=0;
                @(negedge mgmt);train=1;
                @(negedge mgmt);
                if(deskew!=5 || sequence_id!=6 || ready || valid)$fatal(1,"Retrain cleared physical word or retained readiness");
            end
            wait(ready || failed);#0.01;
            if(failed || !ready || deskew!=55 || clearance!=349 || commits!=(MODE==9 ? COUNT+7 : COUNT+1))
                $fatal(1,"RX scan/final revalidation failed reason=%d code=%d clearance=%d commits=%d",failure,deskew,clearance,commits);
            if(valid || warmups<COUNT+2 || commands<(COUNT+1) || dll_requests!=(MODE==9 ? 2 : 1))
                $fatal(1,"RX skipped warmup/scan/retrain or accepted payload before marker");
            frozen_commits=commits;frozen_commands=commands;
            repeat(5)@(negedge mgmt);
            if(commits!=frozen_commits || dll_requests!=(MODE==9 ? 2 : 1))$fatal(1,"Held train level retriggered scan");
            train=0;wait(payload_pairs>=64);
            if(commits!=frozen_commits || commands!=frozen_commands || deskew!=55)$fatal(1,"Payload deskew code was not frozen");
            @(negedge clock90);stop90=1;loss_cycles=0;
            while((ready || valid || !failed) && loss_cycles<9)begin @(posedge mgmt);#0.001;loss_cycles=loss_cycles+1;end
            if(ready || valid || !failed || failure!=1 || loss_cycles>8)$fatal(1,"Delivered phase loss escaped bound cycles=%d",loss_cycles);
            expect_failure(1);
        end
        $display("PASS v3 RX safe scan, physical settling, DCC warmup, payload and failures mode=%d",MODE);$finish;
    end
    initial begin #3000000;$fatal(1,"RX v3 watchdog state=%d transaction=%d reason=%d",dut.scanner.state,dut.transaction.state,failure);end
endmodule
