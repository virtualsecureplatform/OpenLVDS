// SPDX-License-Identifier: GPL-3.0-only
`timescale 1ns/1ps
module tb_training_tx_v2;
    reg clk=0,reset_n=0,run=0,train=1;
    always #1.25 clk=~clk;
    wire [1:0] pair;wire payload_active;
    integer count=0;
    openlvds_training_tx_v2 tx(.clk_pair(clk),.reset_n(reset_n),.run(run),.train_req(train),
        .payload(2'b01),.pair_data(pair),.payload_active(payload_active));
    initial begin #10 reset_n=1;run=1;end
    always @(posedge clk) if(run) begin
        $display("PAIR %d %b%b %b",count,pair[0],pair[1],payload_active);
        if(count==349)train<=0;
        if(count==431)begin $display("PASS v2 training TX stream");$finish;end
        count=count+1;
    end
endmodule
