// SPDX-License-Identifier: GPL-3.0-only
`default_nettype none
// Atomic legal-code/mode transfer, followed by an independent physical-settle
// acknowledgement. A mailbox capture is NOT an analog settling certificate.
// The raw backend acknowledges this exact sequence only after the ROM outputs,
// code switches and separated/cascaded route have settled with outputs invalid.
module openlvds_dll_configuration_v2 #(parameter CODE_WIDTH=13)(
    input wire mgmt_clk_25,raw_reference,reset_n,enable,train_req,clock_present,locked,
    input wire [4*CODE_WIDTH-1:0] desired_codes,
    input wire desired_separated,
    output wire configuration_applied,
    input wire raw_update_allowed,
    output wire [4*CODE_WIDTH-1:0] raw_codes,
    output wire raw_separated,raw_commit,
    output wire [15:0] raw_sequence,
    input wire raw_settled,
    input wire [15:0] raw_settled_sequence
);
    localparam CONFIG_WIDTH=4*CODE_WIDTH+1,PACKET_WIDTH=CONFIG_WIDTH+16;
    wire [CONFIG_WIDTH-1:0] desired={desired_separated,desired_codes};
    reg [CONFIG_WIDTH-1:0] acknowledged;
    reg [PACKET_WIDTH-1:0] expected;
    reg [15:0] generation;
    reg waiting,have_ack,superseded,train_seen;
    wire restart=train_req && !train_seen;
    wire command_ready,reply_valid;
    wire [PACKET_WIDTH-1:0] reply,raw_packet;
    wire send=enable && clock_present && !locked && !restart && !waiting &&
        (!have_ack || desired!=acknowledged) && command_ready;
    assign configuration_applied=enable && clock_present && !restart && !waiting && have_ack && desired==acknowledged;
    always @(posedge mgmt_clk_25 or negedge reset_n)
        if(!reset_n)begin
            acknowledged<=0;expected<=0;generation<=0;waiting<=0;
            have_ack<=0;superseded<=0;train_seen<=0;
        end else begin
            train_seen<=train_req;
            // Keep an old mailbox transaction intact until it drains. Its
            // eventual reply cannot acknowledge a new training generation.
            if(!enable || !clock_present || restart)begin
                have_ack<=0;
                if(waiting)superseded<=1;
            end
            if(send)begin
                generation<=generation+16'd1;
                expected<={generation+16'd1,desired};waiting<=1;superseded<=0;
            end
            if(reply_valid && waiting && reply==expected)begin
                waiting<=0;
                if(!superseded && enable && clock_present && !restart)begin
                    acknowledged<=reply[CONFIG_WIDTH-1:0];have_ack<=1;
                end
            end
        end
    (* ASYNC_REG="TRUE" *) reg enable_meta,enable_sync;
    always @(posedge raw_reference or negedge reset_n)
        if(!reset_n)begin enable_meta<=0;enable_sync<=0;end
        else begin enable_meta<=enable;enable_sync<=enable_meta;end
    openlvds_code_mailbox_v2 #(.WIDTH(PACKET_WIDTH)) command_mailbox(
        .reset_n(reset_n),.source_clk(mgmt_clk_25),.source_valid(send),
        .source_data({generation+16'd1,desired}),.source_ready(command_ready),
        .target_clk(raw_reference),.target_safe(enable_sync && raw_update_allowed),
        .target_data(raw_packet),.target_valid(raw_commit));
    assign raw_codes=raw_packet[4*CODE_WIDTH-1:0];
    assign raw_separated=raw_packet[CONFIG_WIDTH-1];
    assign raw_sequence=raw_packet[PACKET_WIDTH-1:CONFIG_WIDTH];
    reg raw_pending;
    wire reply_ready;
    wire acknowledge=raw_pending && raw_settled && raw_settled_sequence==raw_sequence;
    always @(posedge raw_reference or negedge reset_n)
        if(!reset_n)raw_pending<=0;
        else if(raw_commit)raw_pending<=1;
        else if(acknowledge && reply_ready)raw_pending<=0;
    openlvds_code_mailbox_v2 #(.WIDTH(PACKET_WIDTH)) settled_mailbox(
        .reset_n(reset_n),.source_clk(raw_reference),.source_valid(acknowledge),
        .source_data(raw_packet),.source_ready(reply_ready),
        .target_clk(mgmt_clk_25),.target_safe(1'b1),.target_data(reply),.target_valid(reply_valid));
endmodule
`default_nettype wire
