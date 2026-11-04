// SPDX-License-Identifier: GPL-3.0-only
`timescale 1ns/1ps
// Control/CDC integration only. The pass/fail eye mask is synthetic and gives
// no electrical, delay-model, native clock or PHY qualification.
module tb_rx_training_integration_v2;
    reg mgmt=0,raw=0,sample=0,txclk=0,reset_n=0,enable=1,train=1,run_sample=1;
    always #20 mgmt=~mgmt;
    always #1.25 raw=~raw;
    always #1.25 txclk=~txclk;
    initial begin #0.31;forever begin #1.25;if(run_sample)sample=~sample;else sample=0;end end
    wire [6:0] table_index,deskew;
    wire [1:0] tx_pair,data;
    wire commit,valid,ready,busy,fail,tx_payload;
    wire [3:0] reason;
    wire [15:0] clearance;
    reg [1:0] payload=2'b01;
    wire good_code=deskew>=20 && deskew<=90;
    wire [1:0] captured_pair=good_code ? tx_pair:(tx_pair^2'b01);
    openlvds_training_tx_v2 tx(.clk_pair(txclk),.reset_n(reset_n),.run(1'b1),.train_req(train),
        .payload(payload),.pair_data(tx_pair),.payload_active(tx_payload));
    wire [15:0] lo=table_index*10;
    openlvds_rx_training_v2 #(.CODE_WIDTH(7),.CODE_COUNT(101),.MODEL_ADMITTED(1),.TIMEOUT_CYCLES(20000)) rx(
        .mgmt_clk_25(mgmt),.source_clk(raw),.sample_clk(sample),.reset_n(reset_n),.enable(enable),
        .train_req(train),.dll_locked(1'b1),.table_ready(1'b1),.table_index(table_index),
        .delay_lo_ps(lo),.delay_hi_ps(lo+16'd1),.deskew_index(deskew),.deskew_commit(commit),
        .captured_pair(captured_pair),.captured_valid(1'b1),.rx_data(data),.rx_valid(valid),
        .rx_ready(ready),.cal_busy(busy),.cal_fail(fail),.failure_code(reason),.selected_clearance_ps(clearance));
    integer pairs=0;
    always @(negedge sample) if(valid)begin
        if(data!==payload)$fatal(1,"End-marker CDC integration reordered payload %b",data);
        pairs=pairs+1;
    end
    initial begin
        #83 reset_n=1;
        wait(ready || fail);@(negedge mgmt);
        if(fail!==0 || ready!==1 || deskew!==55 || clearance!==349)
            $fatal(1,"RX training integration failed ready=%b fail=%b reason=%d code=%d clearance=%d",ready,fail,reason,deskew,clearance);
        if(valid!==0)$fatal(1,"Payload valid before end marker");
        train=0;
        wait(pairs>=64);
        @(negedge mgmt);run_sample=0;
        repeat(12)@(negedge mgmt);
        if(valid!==0 || ready!==0 || fail!==1 || reason!==1)
            $fatal(1,"Stopped sample clock did not invalidate public RX status");
        $display("PASS v2 RX training CDC, synthetic eye scan, payload boundary and sample-clock loss");$finish;
    end
    initial begin #2000000;$fatal(1,"RX training integration watchdog");end
endmodule
