// SPDX-License-Identifier: GPL-3.0-only
`timescale 1ns/1ps
module tb_phy;
    reg clk=0,reset_n=0,enable=0,clock_ready=0;
    reg [1:0] tx_data=0;
    reg [31:0] lfsr=32'h1234abcd;
    wire ready,locked,dp,dn,cp,cn;
    reg rdp=0,rdn=1,rcp=0,rcn=1;
    wire [1:0] rx_data;
    wire rx_clk,valid;
    supply1 vd,va,vr;
    supply0 ground;
    tri itx,irx;
    openlvds_tx tx(clk,reset_n,enable,clock_ready,tx_data,dp,dn,cp,cn,
                   ready,locked,vr,itx,va,vd,ground);
    openlvds_rx rx(rdp,rdn,rcp,rcn,reset_n,enable,rx_data,rx_clk,valid,
                  vr,irx,va,vd,ground);
    always #1.25 clk=~clk;
    always @(dp) rdp<=#1.2 dp;
    always @(dn) rdn<=#1.2 dn;
    always @(cp) rcp<=#1.2 cp;
    always @(cn) rcn<=#1.2 cn;
    reg [1:0] queue [0:8191];
    real due [0:8191];
    integer wr=0,rd=0,checked=0;
    always @(negedge reset_n) begin wr=0;rd=0;end
    always @(negedge clk) begin
        #0.1;
        repeat(2) lfsr={lfsr[30:0],lfsr[31]^lfsr[21]^lfsr[1]^lfsr[0]};
        tx_data=lfsr[1:0];
    end
    always @(posedge clk) if (reset_n && ready) begin
        queue[wr]=tx_data;
        // Fixture latency: one pair-assembly cycle + half-cycle sampling
        // phase + 50ps model clock buffer + 2*200ps I/O + 1.2ns channel.
        due[wr]=$realtime+5.400;
        wr=wr+1;
    end
    always @(posedge rx_clk) begin
        #0.01;
        if (reset_n && rd<wr && $realtime>=due[rd]-0.005) begin
            if (!valid || rx_data!==queue[rd])
                $fatal(1,"PHY ordering error at %t: got %b expected %b valid=%b",$time,rx_data,queue[rd],valid);
            if ($realtime>due[rd]+0.02) $fatal(1,"Missing/duplicated PHY pair");
            checked=checked+2;rd=rd+1;
        end
    end
    initial begin
        #10;reset_n=1;enable=1;clock_ready=1;
        repeat(1800) @(negedge clk);
        #0.1;reset_n=0;clock_ready=0;
        #10;reset_n=1;clock_ready=1;
        repeat(1800) @(negedge clk);
        if (checked<5000) $fatal(1,"Insufficient PHY traffic: %d",checked);
        $display("PASS complete PHY functional assembly bits=%0d",checked);$finish;
    end
    initial begin #20000;$fatal(1,"Timeout");end
endmodule
