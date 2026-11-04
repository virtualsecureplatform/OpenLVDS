// SPDX-License-Identifier: GPL-3.0-only
`default_nettype none
// A single-bit heartbeat aliases at 400 MHz / 25 MHz. Use an eight-bit Gray
// counter, whose wrap period exceeds the eight-management-cycle loss window.
module openlvds_clock_watch_v2 (
    input wire reset_n, input wire observed_clk, input wire mgmt_clk_25,
    output reg clock_present
);
    reg [7:0] count, gray;
    wire [7:0] next_count = count+8'd1;
    (* ASYNC_REG="TRUE" *) reg [7:0] gray_meta, gray_sync;
    reg [7:0] previous;
    reg [3:0] stale;
    always @(posedge observed_clk or negedge reset_n)
        if (!reset_n) begin count<=0; gray<=0; end
        else begin count<=next_count; gray<=next_count ^ (next_count>>1); end
    always @(posedge mgmt_clk_25 or negedge reset_n)
        if (!reset_n) begin
            gray_meta<=0; gray_sync<=0; previous<=0; stale<=0; clock_present<=0;
        end else begin
            gray_meta<=gray; gray_sync<=gray_meta; previous<=gray_sync;
            if (gray_sync!=previous) begin stale<=0; clock_present<=1; end
            else if (stale<8) begin
                stale<=stale+1'b1;
                if (stale==7) clock_present<=0;
            end
        end
endmodule
`default_nettype wire
