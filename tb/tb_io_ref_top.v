// SPDX-License-Identifier: GPL-3.0-only
`timescale 1ns/1ps
`default_nettype none
module tb_io_ref_top;
    reg clk=0, reset_n=0, enable=0, corrupt=0;
    wire locked, error, tx_p, tx_n, vref, iref_tx, iref_rx;
    // External loopback with an arbitrary non-integer-cycle delay.
    wire #3.7 rx_p=tx_p^corrupt;
    wire #3.7 rx_n=tx_n^corrupt;
    openlvds_io_ref_top dut(.clk(clk),.reset_n(reset_n),.enable(enable),
        .checker_locked(locked),.checker_error(error),.tx_p(tx_p),.tx_n(tx_n),
        .rx_p(rx_p),.rx_n(rx_n),.vref(vref),.iref_tx(iref_tx),.iref_rx(iref_rx));
    always #5 clk=~clk;
    integer ones=0, bits=0;
    always @(posedge clk) if (enable && locked) begin bits=bits+1; ones=ones+dut.tx_bit; end
    initial begin
        #23 reset_n=1; #20 enable=1;
        repeat (40) @(posedge clk);
        if (locked) begin $display("FAIL locked before 64 confirmations"); $finish; end
        repeat (200) @(posedge clk);
        if (!locked || error) begin $display("FAIL lock=%b error=%b",locked,error); $finish; end
        repeat (1270) @(posedge clk);
        if (error) begin $display("FAIL false error"); $finish; end
        // PRBS7 has 64 ones per 127 bits.
        if (bits<1270 || ones*127<bits*62 || ones*127>bits*66) begin $display("FAIL not PRBS7 ones=%0d bits=%0d",ones,bits); $finish; end
        @(negedge clk) corrupt=1; repeat (2) @(posedge clk); @(negedge clk) corrupt=0;
        repeat (20) @(posedge clk);
        if (!error) begin $display("FAIL corrupted bits not detected"); $finish; end
        $display("PASS io_ref_top bits=%0d ones=%0d",bits,ones);
        $finish;
    end
endmodule
`default_nettype wire
