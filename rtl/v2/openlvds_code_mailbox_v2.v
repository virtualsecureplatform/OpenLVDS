// SPDX-License-Identifier: GPL-3.0-only
`default_nettype none
// Bundled-data request/acknowledge CDC. Shared asynchronous reset is required.
// The sender holds the bus until the receiver captures it and acknowledges.
module openlvds_code_mailbox_v2 #(parameter WIDTH=32)(
    input wire reset_n,
    input wire source_clk, input wire source_valid,
    input wire [WIDTH-1:0] source_data, output wire source_ready,
    input wire target_clk, input wire target_safe,
    output reg [WIDTH-1:0] target_data, output reg target_valid
);
    reg [WIDTH-1:0] held;
    reg request, acknowledge;
    (* ASYNC_REG="TRUE" *) reg ack_meta, ack_sync;
    (* ASYNC_REG="TRUE" *) reg req_meta, req_sync;
    assign source_ready = request == ack_sync;
    always @(posedge source_clk or negedge reset_n)
        if (!reset_n) begin
            ack_meta<=0; ack_sync<=0; request<=0; held<=0;
        end else begin
            ack_meta<=acknowledge; ack_sync<=ack_meta;
            if (source_valid && source_ready) begin
                held<=source_data; request<=~request;
            end
        end
    always @(posedge target_clk or negedge reset_n)
        if (!reset_n) begin
            req_meta<=0; req_sync<=0; acknowledge<=0;
            target_data<=0; target_valid<=0;
        end else begin
            req_meta<=request; req_sync<=req_meta; target_valid<=0;
            if (target_safe && req_sync!=acknowledge) begin
                target_data<=held;
                target_valid<=1;
                acknowledge<=req_sync;
            end
        end
endmodule
`default_nettype wire
