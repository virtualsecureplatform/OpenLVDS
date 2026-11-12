// SPDX-License-Identifier: GPL-3.0-only
// Reference integration of the released I/O macros: one transmitter fed by a
// PRBS7 generator and one receiver feeding a self-synchronizing PRBS7 checker.
// It proves that the published LEF, Liberty, Verilog and GDS views place,
// route, connect to a three-rail power grid and pass DRC/LVS in a digital
// flow. It is not a rate or link claim: both ends share one relaxed clock.
`default_nettype none
module openlvds_io_ref_top(
`ifdef USE_POWER_PINS
    inout wire VDDIO, inout wire VDDD, inout wire VSS,
`endif
    input wire clk, input wire reset_n, input wire enable,
    output reg checker_locked, output reg checker_error,
    inout wire tx_p, inout wire tx_n, inout wire rx_p, inout wire rx_n,
    inout wire vref, inout wire iref_tx, inout wire iref_rx
);
    reg [6:0] generator;
    reg tx_bit;
    always @(posedge clk or negedge reset_n)
        if (!reset_n) begin generator<=7'h7f; tx_bit<=1'b0; end
        else if (enable) begin
            generator<={generator[5:0],generator[6]^generator[5]};
            tx_bit<=generator[6]^generator[5];
        end

    wire rx_bit;
    openlvds_io_tx tx_macro(
`ifdef USE_POWER_PINS
        .VDDIO(VDDIO), .VDDD(VDDD), .VSS(VSS),
`endif
        .D(tx_bit), .OUTP(tx_p), .OUTN(tx_n), .VREF(vref), .IREF(iref_tx));
    openlvds_io_rx rx_macro(
`ifdef USE_POWER_PINS
        .VDDIO(VDDIO), .VDDD(VDDD), .VSS(VSS),
`endif
        .INP(rx_p), .INN(rx_n), .Q(rx_bit), .VREF(vref), .IREF(iref_rx));

    // The next PRBS7 bit is a function of the previous seven received bits, so
    // the checker needs no knowledge of the link latency.
    reg [6:0] history;
    reg [6:0] good;
    reg sample;
    wire expected=history[6]^history[5];
    always @(posedge clk or negedge reset_n)
        if (!reset_n) begin
            history<=7'h00; good<=7'd0; sample<=1'b0; checker_locked<=1'b0; checker_error<=1'b0;
        end else if (enable) begin
            sample<=rx_bit;
            history<={history[5:0],sample};
            if (!checker_locked) begin
                // Seven history bits plus 64 consecutive correct predictions.
                if (sample===expected && history!=7'h00) good<=good+7'd1; else good<=7'd0;
                if (good==7'd70) checker_locked<=1'b1;
            end else if (sample!==expected) checker_error<=1'b1;
        end
endmodule
`default_nettype wire
