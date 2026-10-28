// SPDX-License-Identifier: GPL-3.0-only
`timescale 1ns/1ps
`default_nettype none
module tb_link;
    real period_ns=2.5, duty=0.5, skew_ns=0.0, jitter_ns=0.05;
    integer cycles=22000;
    reg clk=0, reset_n=0, enable=0, clock_ready=0, dll_locked=0;
    reg [1:0] tx_data=0;
    wire clk90;
    // Ideal phase source ONLY for RTL verification. Physical DLL has its own gate.
    assign #(period_ns/4.0) clk90=clk;
    wire serial, forwarded, ready;
    reg line_data=0, line_clk=0;
    openlvds_tx_core tx(clk,clk90,reset_n,enable,clock_ready,dll_locked,
                        tx_data,serial,forwarded,ready);
    // Transmission lines transport short pulses; continuous delayed assigns
    // would incorrectly reject pulses narrower than their propagation delay.
    always @(serial) line_data <= #(1.2+skew_ns) serial;
    always @(forwarded) line_clk <= #(1.2) forwarded;
    wire [1:0] rx_data;
    wire rx_valid;
    wire rx_reset_n=reset_n & enable & clock_ready & dll_locked;
    openlvds_ddr_rx rx(line_clk,rx_reset_n,line_data,rx_data,rx_valid);
    reg [31:0] prbs=32'h1274dba9;
    reg [31:0] jitter_rng=32'h13579bdf;
    reg expected_bit=0, expected_first=0, expected_held=0;
    reg expected_line=0;
    always @(expected_bit) expected_line <= #(1.2+skew_ns) expected_bit;
    reg rx_first=0, rx_second=0;
    reg [1:0] previous_pair=0;
    reg [15:0] transitions=0;
    integer checked_bits=0, checked_pairs=0, startup=0;
    real edge_time=0.0, nominal_time=0.0, jitter;

    initial begin
        if ($value$plusargs("PERIOD=%f",period_ns)) begin end
        if ($value$plusargs("DUTY=%f",duty)) begin end
        if ($value$plusargs("SKEW=%f",skew_ns)) begin end
        if ($value$plusargs("CYCLES=%d",cycles)) begin end
        if ($value$plusargs("JITTER=%f",jitter_ns)) begin end
        #0.2;
        forever begin
            jitter_rng={jitter_rng[30:0],jitter_rng[31]^jitter_rng[21]^jitter_rng[1]^jitter_rng[0]};
            jitter=jitter_rng[0] ? jitter_ns : -jitter_ns;
            nominal_time=nominal_time+(clk ? period_ns*duty : period_ns*(1.0-duty));
            #(nominal_time+jitter+0.2-$realtime) clk=~clk;
        end
    end

    always @(negedge clk) begin
        // Change D1 while the current pair is being transmitted: the TX must
        // retain the value captured on the preceding rising edge.
        #0.02;
        prbs={prbs[30:0],prbs[31]^prbs[21]^prbs[1]^prbs[0]};
        prbs={prbs[30:0],prbs[31]^prbs[21]^prbs[1]^prbs[0]};
        tx_data=prbs[1:0];
    end
    always @(posedge clk) begin
        if (tx.data_run) begin expected_first=tx_data[0]; expected_held=tx_data[1]; end
        else begin expected_first=0; expected_held=0; end
    end
    always @(clk90) begin
        edge_time=$realtime;
        if (tx.data_run) begin
            expected_bit=clk90 ? expected_first : expected_held;
            #0.005;
            if (serial !== expected_bit) $fatal(1,"DDR serialization error at %t",$time);
        end else expected_bit=0;
    end
    always @(serial) begin
        if (ready && reset_n && ($realtime-edge_time)>0.002)
            $fatal(1,"Unexpected serial transition between clock edges at %t",$time);
    end
    always @(negedge rx_reset_n) startup=0;
    always @(posedge line_clk) begin
        if (rx_reset_n) begin
            startup=startup+1;
            if (startup>8) begin
                if (line_data !== expected_line) $fatal(1,"First-bit channel error");
                checked_bits=checked_bits+1;
            end
            #0.01;
            if (rx_valid && startup>8) begin
                if (rx_data !== {rx_second,rx_first})
                    $fatal(1,"RX pair error: got %b expected %b at %t",rx_data,{rx_second,rx_first},$time);
                transitions[{previous_pair,rx_data}]=1;
                previous_pair=rx_data;
                checked_pairs=checked_pairs+1;
            end
            rx_first=line_data;
        end
    end
    always @(negedge line_clk) begin
        if (rx_reset_n) begin
            rx_second=line_data;
            if (startup>8) begin
                if (line_data !== expected_line) $fatal(1,"Second-bit channel error");
                checked_bits=checked_bits+1;
            end
        end
    end
    task start_link;
        begin
            reset_n=0; enable=0; clock_ready=0; dll_locked=0;
            repeat(4) @(negedge clk);
            #0.1; reset_n=1; enable=1; clock_ready=1;
            repeat(16) @(negedge clk);
            #0.1; dll_locked=1;
        end
    endtask
    initial begin
        start_link;
        repeat(cycles/2) @(negedge clk);
        if ($test$plusargs("DEBUG")) $display("HALF bits=%0d pairs=%0d startup=%0d ready=%b",checked_bits,checked_pairs,startup,ready);
        #0.1; clock_ready=0;
        #0.01;
        if (ready || rx_valid) $fatal(1,"Readiness was not revoked");
        start_link;
        repeat(cycles/2) @(negedge clk);
        if ($test$plusargs("DEBUG")) $display("END bits=%0d pairs=%0d startup=%0d ready=%b",checked_bits,checked_pairs,startup,ready);
        if (transitions!==16'hffff) $fatal(1,"Missing pair transitions: %h",transitions);
        if (checked_bits<cycles || checked_pairs<cycles/2)
            $fatal(1,"Insufficient checking: bits=%0d pairs=%0d cycles=%0d",checked_bits,checked_pairs,cycles);
        $display("PASS bits=%0d pairs=%0d transitions=%h period=%f duty=%f skew=%f jitter=%f",
                 checked_bits,checked_pairs,transitions,period_ns,duty,skew_ns,jitter_ns);
        $finish;
    end
    initial begin #10000000; $fatal(1,"Watchdog timeout"); end
    initial if ($test$plusargs("TRACE")) begin $dumpfile("build/rtl/link.vcd"); $dumpvars(0,tb_link); end
endmodule
`default_nettype wire
