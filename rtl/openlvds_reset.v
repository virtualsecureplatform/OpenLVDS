// SPDX-License-Identifier: GPL-3.0-only
`default_nettype none
module openlvds_reset(input wire clk, input wire reset_n, output wire run);
    (* async_reg = "true" *) reg [1:0] release_pipe;
    always @(posedge clk or negedge reset_n)
        if (!reset_n) release_pipe <= 2'b00;
        else release_pipe <= {release_pipe[0], 1'b1};
    assign run = release_pipe[1];
endmodule
`default_nettype wire
