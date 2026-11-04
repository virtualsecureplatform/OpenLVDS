// SPDX-License-Identifier: GPL-3.0-only
`default_nettype none
// Phase-specific release for the two quadrature DCCs. Each release follows
// its OWN raw rising phase, so that phase's current event remains reset and
// the opposite phase is the first event captured half a period later. Both
// delivered rising clocks then follow their own raw phase with +90deg order.
// This gives half-period recovery budget instead of a common quarter-period
// release window. Native CQ/recovery/removal checks remain mandatory.
module openlvds_dcc_release_v2 (
    input wire raw_phase0,raw_phase90,reset_n,enable,clock_present,dll_locked,
    output wire reset0_n,reset90_n
);
    wire allowed=reset_n && enable && clock_present && dll_locked;
    (* ASYNC_REG="TRUE" *) reg first0,second0,first90,second90;
    always @(posedge raw_phase0 or negedge allowed)
        if(!allowed)begin first0<=0;second0<=0;end
        else begin first0<=1;second0<=first0;end
    always @(posedge raw_phase90 or negedge allowed)
        if(!allowed)begin first90<=0;second90<=0;end
        else begin first90<=1;second90<=first90;end
    assign reset0_n=second0;
    assign reset90_n=second90;
endmodule
`default_nettype wire
