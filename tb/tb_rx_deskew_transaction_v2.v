// SPDX-License-Identifier: GPL-3.0-only
`timescale 1ns/1ps
// Protocol evidence using real startup and DCC topology with test cell delays.
// This bench does not qualify native electrical timing.
module tb_rx_deskew_transaction_v2;
    parameter MODE=0;
    reg mgmt=0,raw=0,raw90=0,reset_n=1,enable=1,present=1;
    always #20 mgmt=~mgmt;
    always #1.25 raw=~raw;
    initial begin #0.625;forever #1.25 raw90=~raw90;end
    reg valid=0,grant=1,settled=0;
    reg [12:0] code=0;
    reg [15:0] settled_sequence=0;
    wire ready,done,hold_clocks,busy,failed,commit;
    wire [3:0] failure;
    wire [12:0] physical_code;
    wire [15:0] sequence_id;
    wire reset0_n,reset90_n,clock0,clock90,clocks_ready,start_failed;
    wire [3:0] start_failure;
    wire startup_ready=MODE==8 ? 1'b1 : clocks_ready;
    openlvds_rx_deskew_transaction_v2 #(.MODEL_ADMITTED(MODE!=6),.TIMEOUT_CYCLES(100)) dut(
        .mgmt_clk_25(mgmt),.source_clk(raw),.reset_n(reset_n),.enable(enable),.source_clock_present(present),
        .apply_valid(valid),.apply_code(code),.apply_ready(ready),.apply_done(done),
        .update_allowed(grant && !reset0_n && !reset90_n),.physical_settled(settled),
        .physical_settled_sequence(settled_sequence),.deskew_code(physical_code),
        .deskew_sequence(sequence_id),.deskew_commit(commit),.hold_clocks(hold_clocks),.busy(busy),
        .clocks_ready(startup_ready),.clocks_failed(start_failed),.clocks_failure_code(start_failure),
        .cal_fail(failed),.failure_code(failure));
    openlvds_clock_startup_v2 #(.DCC_MODEL_ADMITTED(MODE!=5),.TIMEOUT_CYCLES(90)) startup(
        .mgmt_clk_25(mgmt),.raw_phase0(raw),.raw_phase90(raw90),.clock0(clock0),.clock90(clock90),
        .reset_n(reset_n),.enable(enable && !hold_clocks),.dll_locked(1'b1),.source_clock_present(present),
        .dcc_reset0_n(reset0_n),.dcc_reset90_n(reset90_n),.clocks_ready(clocks_ready),
        .ready0(),.ready90(),.cal_busy(),.cal_fail(start_failed),.failure_code(start_failure));
    openlvds_dcc_clock_hold_v2 dcc0(.phase0(raw),.phase180(!raw),.reset_n(reset0_n),.clock_out(clock0));
    openlvds_dcc_clock_hold_v2 dcc90(.phase0(raw90),.phase180(!raw90),.reset_n(reset90_n),.clock_out(clock90));
    integer edges0=0,edges90=0,commits=0,completions=0;
    always @(posedge clock0 or negedge reset0_n)if(!reset0_n)edges0=0;else edges0=edges0+1;
    always @(posedge clock90 or negedge reset90_n)if(!reset90_n)edges90=0;else edges90=edges90+1;
    always @(posedge commit)begin
        commits=commits+1;
        if(!hold_clocks || reset0_n || reset90_n || physical_code!=code)
            $fatal(1,"Code published outside safe hold");
    end
    always @(posedge done)begin
        completions=completions+1;
        if(edges0<256 || edges90<256 || !clocks_ready || !settled || settled_sequence!=sequence_id || failed)
            $fatal(1,"Completion before physical settling and both actual warmups");
    end
    task request;
        input [12:0] value;
        begin
            wait(ready);@(negedge mgmt);code=value;valid=1;
            @(negedge mgmt);valid=0;
        end
    endtask
    task acknowledge;
        begin
            wait(commit);@(negedge raw);settled_sequence=sequence_id;settled=0;
            repeat(8)@(negedge raw);settled=1;
        end
    endtask
    task expect_failure;
        input [3:0] reason;
        begin
            wait(failed);#0.01;
            if(failure!=reason || done || !hold_clocks || completions!=0)
                $fatal(1,"Failure did not hold closed reason=%d expected=%d",failure,reason);
        end
    endtask
    reg [15:0] previous_sequence;
    initial begin
        #0.001;reset_n=0;#10;reset_n=1;
        if(MODE==6)begin expect_failure(8);if(commits || ready)$fatal(1,"Default admitted an update");end
        else begin
            if(MODE==1 || MODE==7)grant=0;
            if(MODE==3)begin settled=1;settled_sequence=1;end
            request(13'h123);
            if(MODE==1 || MODE==8)begin expect_failure(2);if(commits)$fatal(1,"Unsafe commit");end
            else if(MODE==9)begin wait(commit);expect_failure(2);end
            else if(MODE==10)begin
                wait(commit);@(negedge mgmt);enable=0;
                repeat(4)@(negedge mgmt);
                if(physical_code!=13'h123 || sequence_id!=1 || completions!=0)
                    $fatal(1,"Cancellation after physical commit lost word or falsely completed");
                enable=1;request(13'h456);acknowledge;wait(done);#0.01;
                if(sequence_id!=2 || commits!=2 || completions!=1)
                    $fatal(1,"Canceled physical commit replayed or reused generation");
            end
            else if(MODE==4)begin wait(commit);@(negedge mgmt);present=0;expect_failure(1);end
            else if(MODE==2)begin
                wait(commit);@(negedge raw);settled_sequence=sequence_id+1;settled=1;
                expect_failure(2);
            end else if(MODE==3 || MODE==11)begin
                if(MODE==11)begin
                    wait(dut.hold_sync);@(negedge raw);
                    settled_sequence=1;settled=1;
                end
                wait(commit);repeat(8)@(negedge mgmt);
                if(!hold_clocks || done || !busy)$fatal(1,"Stale matching high qualified settling");
                @(negedge raw);settled=0;repeat(8)@(negedge raw);settled=1;
                wait(done);#0.01;
            end else if(MODE==5)begin acknowledge;expect_failure(8);end
            else if(MODE==7)begin
                repeat(6)@(negedge mgmt);enable=0;grant=1;
                repeat(4)@(negedge mgmt);
                if(commits || physical_code!=0)$fatal(1,"Canceled request reached the physical word");
                enable=1;request(13'h456);acknowledge;wait(done);#0.01;
                if(sequence_id!=2)$fatal(1,"Canceled generation reused");
                @(negedge mgmt);enable=0;repeat(3)@(negedge mgmt);
                if(physical_code!=13'h456 || sequence_id!=2)$fatal(1,"Disable cleared committed physical word");
                enable=1;repeat(8)@(negedge mgmt);
                if(commits!=1 || completions!=1)$fatal(1,"Canceled transport replayed");
            end else begin
                acknowledge;wait(done);#0.01;previous_sequence=sequence_id;
                @(negedge mgmt);settled=0;
                request(13'h654);acknowledge;wait(done);#0.01;
                if(sequence_id!=previous_sequence+1 || commits!=2 || completions!=2)
                    $fatal(1,"Second transaction skipped fresh commit/warmup");
            end
        end
        $display("PASS v2 RX held commit, fresh tagged settling and real DCC warmup mode=%d",MODE);$finish;
    end
    initial begin #30000;$fatal(1,"RX transaction watchdog state=%d failure=%d",dut.state,failure);end
endmodule
