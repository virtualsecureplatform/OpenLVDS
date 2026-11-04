// SPDX-License-Identifier: GPL-3.0-only
`timescale 1ns/1ps
module tb_code_mailbox_v2;
    reg src=0,dst=0,reset_n=0,valid=0,safe=0;
    always #20 src=~src;
    always #1.27 dst=~dst;
    reg [31:0] data=0;
    wire ready,received; wire [31:0] result;
    openlvds_code_mailbox_v2 dut(.reset_n(reset_n),.source_clk(src),.source_valid(valid),
        .source_data(data),.source_ready(ready),.target_clk(dst),.target_safe(safe),
        .target_data(result),.target_valid(received));
    integer i, count=0;
    always @(negedge dst) if(received) count=count+1;
    initial begin
        #83 reset_n=1;
        for(i=0;i<32;i=i+1) begin
            @(negedge src); valid=1;data=32'h12345678 ^ (32'hf010a0e0*i);
            @(negedge src);valid=0;
            if(ready) $fatal(1,"Premature acknowledgement");
            repeat(3) @(negedge src);
            if (received || ready) $fatal(1,"Unsafe code commit");
            safe=1;wait(received);#0.1;
            if(result!==data) $fatal(1,"Torn multi-bit code");
            @(negedge src);safe=0;
            wait(ready);
        end
        repeat(3) @(negedge src);
        if(count!=32) $fatal(1,"Duplicate or lost mailbox commit");
        $display("PASS v2 atomic mailbox backpressure and 32 asynchronous commits");$finish;
    end
    initial begin #100000; $fatal(1,"Testbench watchdog");end
endmodule
