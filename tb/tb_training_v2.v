// SPDX-License-Identifier: GPL-3.0-only
`timescale 1ns/1ps
module tb_training_v2;
    localparam [255:0] FRAME=256'hffff0000fe041851e459d4fa1c49b5bd8d2ee655fc0830a3c8b3a9f438936b7b;
    reg clk=0,reset_n=0,run=0,scan=0,valid=0,accept_payload=0;
    always #1.25 clk=~clk;
    reg [1:0] pair=0;
    wire done,pass,phase,payload_valid;wire [1:0] payload;
    openlvds_training_rx_v2 rx(.clk_pair(clk),.reset_n(reset_n),.run(run),.scan_start(scan),
        .pair_valid(valid),.pair_data(pair),.accept_payload(accept_payload),
        .scan_done(done),.scan_pass(pass),.marker_pair_phase(phase),
        .payload_data(payload),.payload_valid(payload_valid));
    integer rotation,k,index,seen;
    reg [31:0] end_marker=32'h0000ffff;
    reg [31:0] expected=32'h39a5c168;
    integer output_bit;
    task send;
        input a,b;
        begin @(negedge clk);valid=1;pair={b,a};@(posedge clk);#0.01;end
    endtask
    always @(negedge clk) if(payload_valid) begin
        if(payload!=={expected[30-output_bit],expected[31-output_bit]})
            $fatal(1,"Payload realignment dropped/reordered bits at %d",output_bit);
        output_bit=output_bit+2;
    end
    initial begin
        #10 reset_n=1; run=1;output_bit=0;
        for(rotation=0;rotation<256;rotation=rotation+1) begin
            @(negedge clk);scan=1;valid=0;@(negedge clk);scan=0;
            for(k=0;k<1280;k=k+2) begin
                index=(rotation+k)%256;
                send(FRAME[255-index],FRAME[255-((index+1)%256)]);
                if(k<1022 && done===1'b1) $fatal(1,"Early four-frame pass");
            end
            if(done!==1'b1 || pass!==1'b1 || phase!==(rotation%2))
                $fatal(1,"Training rotation/phase failed %d",rotation);
        end
        // Reset the scan and establish each pair orientation, then switch from
        // training to the end marker to payload at either serial alignment.
        for(rotation=0;rotation<2;rotation=rotation+1) begin
            @(negedge clk);scan=1;valid=0;accept_payload=0;@(negedge clk);scan=0;
            for(k=0;k<1280;k=k+2) begin
                index=(rotation+k)%256;send(FRAME[255-index],FRAME[255-((index+1)%256)]);
            end
            if(pass!==1'b1) $fatal(1,"Training prerequisite");
            accept_payload=1;output_bit=0;
            if(rotation==0) begin
                for(k=0;k<32;k=k+2) send(end_marker[31-k],end_marker[30-k]);
                for(k=0;k<32;k=k+2) send(expected[31-k],expected[30-k]);
            end else begin
                // Finish this frame one bit into the first pair, then marker.
                send(FRAME[255],end_marker[31]);
                for(k=1;k<31;k=k+2) send(end_marker[31-k],end_marker[30-k]);
                send(end_marker[0],expected[31]);
                for(k=1;k<31;k=k+2) send(expected[31-k],expected[30-k]);
                send(expected[0],1'b0);
            end
            @(negedge clk);valid=0;@(negedge clk);
            if(output_bit!=32) $fatal(1,"Payload bit count %d",output_bit);
        end
        $display("PASS v2 all 256 training rotations and both payload pair alignments");$finish;
    end
    initial begin #2000000;$fatal(1,"Training watchdog");end
endmodule
