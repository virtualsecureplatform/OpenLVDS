// SPDX-License-Identifier: GPL-3.0-only
`default_nettype none
// Pair order follows openlvds_ddr_tx: bit 0 first, bit 1 second. Caller holds
// train_req until RX ready and preloads payload before deasserting train_req.
// Deassertion is synchronized externally and takes effect at a frame boundary.
module openlvds_training_tx_v2 (
    input wire clk_pair, reset_n, run, train_req,
    input wire [1:0] payload,
    output reg [1:0] pair_data, output wire payload_active
);
    localparam TRAIN=0, END=1, PAYLOAD=2;
    reg [1:0] state;
    reg [7:0] position;
    reg [6:0] prbs;
    reg [15:0] warmup;
    wire [31:0] marker=32'hffff0000, end_marker=32'h0000ffff;
    wire first_prbs=prbs[6], second_prbs=prbs[5];
    wire [6:0] after_one={prbs[5:0],prbs[6]^prbs[5]};
    wire [6:0] after_two={after_one[5:0],after_one[6]^after_one[5]};
    assign payload_active=run && state==PAYLOAD;
    always @* begin
        pair_data=2'b00;
        if (run) begin
            if (state==PAYLOAD) pair_data=payload;
            else if (state==END) pair_data={end_marker[30-position],end_marker[31-position]};
            else if (position<32) pair_data={marker[30-position],marker[31-position]};
            else pair_data={second_prbs,first_prbs};
        end
    end
    always @(posedge clk_pair or negedge reset_n)
        if (!reset_n) begin state<=TRAIN; position<=0; prbs<=7'h7f; warmup<=0; end
        else if (!run) begin state<=TRAIN; position<=0; prbs<=7'h7f; warmup<=0; end
        else begin
            if (warmup<256) warmup<=warmup+1'b1;
            if (state==TRAIN) begin
                if (position==254) begin
                    position<=0; prbs<=7'h7f;
                    if (!train_req && warmup>=256) state<=END;
                end else begin
                    position<=position+2;
                    if (position>=32) prbs<=after_two;
                end
            end else if (state==END) begin
                if (position==30) begin state<=PAYLOAD; position<=0; end
                else position<=position+2;
            end else if (train_req) begin state<=TRAIN; position<=0; prbs<=7'h7f; warmup<=0; end
        end
endmodule
`default_nettype wire
