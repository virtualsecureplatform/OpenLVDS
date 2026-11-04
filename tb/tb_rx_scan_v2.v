// SPDX-License-Identifier: GPL-3.0-only
`timescale 1ns/1ps
module tb_rx_scan_v2;
    localparam COUNT=101;
    reg clk=0,reset_n=0,enable=1,train=0,present=1,locked=1;
    always #20 clk=~clk;
    reg [32:0] rom [0:COUNT-1];
    wire [6:0] index,code;
    wire apply,request,ready,busy,fail;
    wire [3:0] reason;
    wire [15:0] clearance;
    reg applied=0,scan_valid=0,scan_pass=0;
    reg [6:0] committed_code=0;
    integer commits=0,timer=0,mode,expect_code,expect_reason,expect_clearance;
    reg [1023:0] file;
    openlvds_rx_scan_v2 #(.CODE_WIDTH(7),.CODE_COUNT(COUNT),.MODEL_ADMITTED(1),.TIMEOUT_CYCLES(20000)) dut(
        .mgmt_clk_25(clk),.reset_n(reset_n),.enable(enable),.train_req(train),.clock_present(present),
        .dll_locked(locked),.table_ready(1'b1),.table_index(index),.delay_lo_ps(rom[index][15:0]),
        .delay_hi_ps(rom[index][31:16]),.apply_valid(apply),.apply_code(code),.apply_ready(1'b1),.apply_done(applied),
        .scan_request(request),.scan_valid(scan_valid),.scan_pass(scan_pass),.rx_ready(ready),
        .cal_busy(busy),.cal_fail(fail),.failure_code(reason),.selected_clearance_ps(clearance));
    wire default_fail;wire [3:0] default_reason;
    openlvds_rx_scan_v2 #(.CODE_WIDTH(7),.CODE_COUNT(COUNT)) no_model(
        .mgmt_clk_25(clk),.reset_n(reset_n),.enable(enable),.train_req(train),.clock_present(1'b1),
        .dll_locked(1'b1),.table_ready(1'b1),.table_index(),.delay_lo_ps(16'd0),.delay_hi_ps(16'd1),
        .apply_valid(),.apply_code(),.apply_ready(1'b1),.apply_done(1'b0),.scan_request(),
        .scan_valid(1'b0),.scan_pass(1'b0),.rx_ready(),.cal_busy(),.cal_fail(default_fail),
        .failure_code(default_reason),.selected_clearance_ps());
    always @(posedge clk) begin
        applied<=apply;
        if(apply)begin committed_code<=code;commits<=commits+1;end
        scan_valid<=0;
        if(!request)timer<=0;
        else begin
            timer<=timer+1;
            // Absent markers time out at individual codes, not the whole scan.
            if(timer==1 && mode!=4 && rom[committed_code][32])begin
                scan_valid<=1;scan_pass<=!(mode==2 && commits>COUNT);
            end
        end
        if(mode==5 && commits>=3)present<=0;
        if(mode==6 && commits>=3)locked<=0;
    end
    initial begin
        if(!$value$plusargs("ROM=%s",file))$fatal(1,"Missing ROM");
        if(!$value$plusargs("MODE=%d",mode))mode=0;
        if(!$value$plusargs("EXPECT_CODE=%d",expect_code))expect_code=0;
        if(!$value$plusargs("EXPECT_REASON=%d",expect_reason))expect_reason=0;
        if(!$value$plusargs("EXPECT_CLEARANCE=%d",expect_clearance))expect_clearance=0;
        $readmemh(file,rom);
        if(mode==8)locked=0;
        #83 reset_n=1;
        @(negedge clk);train=1;@(negedge clk);train=0;
        wait(ready || fail);@(negedge clk);
        if(default_fail!==1'b1 || default_reason!==8)$fatal(1,"Unadmitted model allowed to run");
        if(expect_reason!=0)begin
            if(fail!==1'b1 || ready!==1'b0 || reason!==expect_reason[3:0])
                $fatal(1,"Wrong scan failure reason=%d expected=%d",reason,expect_reason);
        end else begin
            if(ready!==1'b1 || fail!==1'b0 || code!==expect_code[6:0] || clearance!==expect_clearance[15:0])
                $fatal(1,"Wrong physical selection code=%d clearance=%d expected=%d/%d",code,clearance,expect_code,expect_clearance);
            if(commits!=COUNT+1)$fatal(1,"Missing complete scan/final-code validation commits=%d",commits);
            repeat(5)@(negedge clk);
            if(code!==expect_code[6:0] || apply!==1'b0)$fatal(1,"Payload code not frozen");
            enable=0;@(negedge clk);
            if(ready!==1'b0 || busy!==1'b0)$fatal(1,"Disable did not invalidate RX readiness");
        end
        $display("PASS v2 conservative RX scan mode=%d",mode);$finish;
    end
    initial begin #2000000;$fatal(1,"RX scan test watchdog");end
endmodule
