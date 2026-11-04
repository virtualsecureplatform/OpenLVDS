// SPDX-License-Identifier: GPL-3.0-only
`timescale 1ns/1ps
module tb_dll_configuration_v2;
    reg clk=0,raw=0,reset_n=1,enable=1,train=0,present=1,locked=0,safe=0,settled=0;
    always #20 clk=~clk;
    always #1.31 raw=~raw;
    reg [15:0] codes=16'h3210,settled_sequence=0;
    reg separate=1;
    wire applied,commit,raw_separate;
    wire [15:0] raw_codes,sequence_id;
    integer commits=0,before_count;
    openlvds_dll_configuration_v2 #(.CODE_WIDTH(4)) dut(
        .mgmt_clk_25(clk),.raw_reference(raw),.reset_n(reset_n),.enable(enable),.train_req(train),
        .clock_present(present),.locked(locked),.desired_codes(codes),.desired_separated(separate),
        .configuration_applied(applied),.raw_update_allowed(safe),.raw_codes(raw_codes),
        .raw_separated(raw_separate),.raw_commit(commit),.raw_sequence(sequence_id),
        .raw_settled(settled),.raw_settled_sequence(settled_sequence));
    always @(posedge commit)begin
        commits=commits+1;
        if(!safe || locked)$fatal(1,"Unsafe raw commit");
    end
    task acknowledge;
        begin @(negedge raw);settled_sequence=sequence_id;settled=1;end
    endtask
    task wait_commit;
        input integer previous;
        begin wait(commits>previous);@(negedge raw);end
    endtask
    initial begin
        #0.001;reset_n=0;#9;reset_n=1;
        repeat(12)@(negedge clk);
        if(commits || applied)$fatal(1,"Mailbox bypassed raw safety gate");
        safe=1;wait_commit(0);
        if(raw_codes!==codes || raw_separate!==separate)$fatal(1,"Torn code/mode bundle");
        // Digital mailbox acknowledgement alone must never release measurement.
        repeat(12)@(negedge clk);
        if(applied)$fatal(1,"Digital capture was mistaken for physical settling");
        settled=1;settled_sequence=sequence_id-1;
        repeat(12)@(negedge clk);
        if(applied)$fatal(1,"Stale physical settle generation accepted");
        acknowledge;wait(applied);

        @(negedge clk);before_count=commits;safe=0;settled=0;separate=0;
        repeat(12)@(negedge clk);
        if(applied || commits!=before_count)$fatal(1,"Mode update did not invalidate/wait safely");
        codes=16'h7654;safe=1;wait_commit(before_count);
        // In-flight mode-only command may carry old codes. Its exact reply
        // cannot acknowledge the newer desired bundle.
        acknowledge;repeat(12)@(negedge clk);
        if(applied)$fatal(1,"Old command acknowledged new desired codes");
        wait(raw_codes==codes);acknowledge;wait(applied);

        @(negedge clk);locked=1;before_count=commits;
        repeat(20)@(negedge clk);
        if(commits!=before_count || !applied)$fatal(1,"Locked configuration was not frozen");
        codes=16'hffff;repeat(12)@(negedge clk);
        if(applied || commits!=before_count)$fatal(1,"Locked corruption released or wrote codes");
        locked=0;settled=0;wait_commit(before_count);
        // Retraining invalidates this still-pending generation. Drain it and
        // demand a fresh command even if the desired code happens to match.
        @(negedge clk);train=1;@(negedge clk);train=0;before_count=commits;
        acknowledge;repeat(12)@(negedge clk);
        if(applied)$fatal(1,"Pre-retrain settle acknowledgement reused");
        wait_commit(before_count);acknowledge;wait(applied);

        @(negedge clk);present=0;#1;if(applied)$fatal(1,"Clock loss retained configuration validity");
        repeat(3)@(negedge clk);present=1;settled=0;before_count=commits;
        wait_commit(before_count);acknowledge;wait(applied);
        @(negedge clk);enable=0;#1;if(applied)$fatal(1,"Disable retained validity");
        $display("PASS v2 atomic DLL configuration requires exact fresh physical settling and freezes at lock");$finish;
    end
    initial begin #200000;$fatal(1,"Configuration watchdog commits=%d waiting=%b",commits,dut.waiting);end
endmodule
