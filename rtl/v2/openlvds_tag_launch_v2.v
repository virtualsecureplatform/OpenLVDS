// SPDX-License-Identifier: GPL-3.0-only
`default_nettype none
// One outstanding isolated calibration tag. Source and comparison-reference
// enables change only on falling raw-reference edges. A period trial launches
// the comparison pulse on the NEXT rising edge, giving an unwrapped one-period
// reference rather than a modulo-phase comparison. Separated trials launch
// both pulses together. The caller arms/routes the detector before requesting
// and waits for actual detector settling after done (done means launch ended).
// Native gated-pulse width/CQ/recovery and physical implementation are required.
module openlvds_tag_launch_v2 (
    input wire mgmt_clk_25,raw_reference,reset_n,enable,clock_present,
    input wire request_valid,request_next_period,
    output wire request_ready,
    output reg busy,
    output wire done,launch_pulse,reference_pulse
);
    wire allowed=reset_n && enable && clock_present;
    wire falling_reference=~raw_reference;
    wire command_ready,command_valid,command_next_period;
    wire complete_ready,complete_valid,complete_data;
    reg launch_enable,reference_enable,next_period;
    reg [1:0] state;
    localparam IDLE=0,LAUNCH=1,REFERENCE=2,COMPLETE=3;
    assign request_ready=allowed && !busy && command_ready;
    openlvds_code_mailbox_v2 #(.WIDTH(1)) command (
        .reset_n(allowed),.source_clk(mgmt_clk_25),
        .source_valid(request_valid && request_ready),.source_data(request_next_period),
        .source_ready(command_ready),.target_clk(falling_reference),.target_safe(state==IDLE),
        .target_data(command_next_period),.target_valid(command_valid)
    );
    openlvds_code_mailbox_v2 #(.WIDTH(1)) completion (
        .reset_n(allowed),.source_clk(falling_reference),
        .source_valid(state==COMPLETE),.source_data(1'b1),.source_ready(complete_ready),
        .target_clk(mgmt_clk_25),.target_safe(1'b1),
        .target_data(complete_data),.target_valid(complete_valid)
    );
    assign launch_pulse=allowed && raw_reference && launch_enable;
    assign reference_pulse=allowed && raw_reference && reference_enable;
    assign done=allowed && complete_valid && complete_data;
    always @(posedge mgmt_clk_25 or negedge allowed)
        if(!allowed)busy<=0;
        else if(request_valid && request_ready)busy<=1;
        else if(done)busy<=0;
    always @(negedge raw_reference or negedge allowed)
        if(!allowed)begin
            state<=IDLE;launch_enable<=0;reference_enable<=0;next_period<=0;
        end else case(state)
            IDLE:if(command_valid)begin
                launch_enable<=1;reference_enable<=!command_next_period;
                next_period<=command_next_period;state<=LAUNCH;
            end
            LAUNCH:begin
                launch_enable<=0;reference_enable<=next_period;
                state<=next_period ? REFERENCE : COMPLETE;
            end
            REFERENCE:begin reference_enable<=0;state<=COMPLETE;end
            COMPLETE:if(complete_ready)state<=IDLE;
            default:begin state<=IDLE;launch_enable<=0;reference_enable<=0;end
        endcase
endmodule
`default_nettype wire
