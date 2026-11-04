// SPDX-License-Identifier: GPL-3.0-only
`default_nettype none
// Capture-domain training/end-marker detector and one-bit pair realigner.
// scan_start is a pulse after a safe code commit and physical settling. A scan
// passes only after four complete frames. Its result crosses via a mailbox.
module openlvds_training_rx_v2 (
    input wire clk_pair, reset_n, run, scan_start,
    input wire pair_valid, input wire [1:0] pair_data,
    input wire accept_payload,
    output reg scan_done, scan_pass, marker_pair_phase,
    output reg [1:0] payload_data, output reg payload_valid
);
    localparam [255:0] FRAME=256'hffff0000fe041851e459d4fa1c49b5bd8d2ee655fc0830a3c8b3a9f438936b7b;
    reg [31:0] shift, next_shift;
    reg acquired, next_acquired, payload_mode, next_payload_mode;
    reg [7:0] position, next_position;
    reg [10:0] matched, next_matched;
    reg pending, next_pending, pending_bit, next_pending_bit;
    reg next_done, next_pass, next_phase;
    reg [1:0] next_data;
    reg next_valid;
    integer j;
    always @* begin
        next_shift=shift;next_acquired=acquired;next_position=position;next_matched=matched;
        next_payload_mode=payload_mode;next_pending=pending;next_pending_bit=pending_bit;
        next_done=scan_done;next_pass=scan_pass;next_phase=marker_pair_phase;
        next_data=payload_data;next_valid=0;
        if(pair_valid) for(j=0;j<2;j=j+1) begin
            next_shift={next_shift[30:0],pair_data[j]};
            if(next_payload_mode) begin
                if(next_pending) begin
                    next_data={pair_data[j],next_pending_bit};next_valid=1;next_pending=0;
                end else begin next_pending_bit=pair_data[j];next_pending=1;end
            end else if(accept_payload && scan_pass && next_shift==32'h0000ffff) begin
                next_payload_mode=1;next_pending=0;
            end else if(!next_done) begin
                if(!next_acquired) begin
                    if(next_shift==32'hffff0000) begin
                        next_acquired=1;next_position=32;next_matched=32;next_phase=(j==0);
                    end
                end else if(pair_data[j]!==FRAME[255-next_position]) begin
                    next_done=1;next_pass=0;
                end else begin
                    next_position=next_position+1'b1;
                    if(next_matched==1023) begin next_done=1;next_pass=1;end
                    else next_matched=next_matched+1'b1;
                end
            end
        end
    end
    always @(posedge clk_pair or negedge reset_n)
        if(!reset_n) begin
            shift<=0;acquired<=0;position<=0;matched<=0;payload_mode<=0;
            pending<=0;pending_bit<=0;scan_done<=0;scan_pass<=0;marker_pair_phase<=0;
            payload_data<=0;payload_valid<=0;
        end else if(!run || scan_start) begin
            shift<=0;acquired<=0;position<=0;matched<=0;payload_mode<=0;
            pending<=0;pending_bit<=0;scan_done<=0;scan_pass<=0;marker_pair_phase<=0;
            payload_data<=0;payload_valid<=0;
        end else begin
            shift<=next_shift;acquired<=next_acquired;position<=next_position;matched<=next_matched;
            payload_mode<=next_payload_mode;pending<=next_pending;pending_bit<=next_pending_bit;
            scan_done<=next_done;scan_pass<=next_pass;marker_pair_phase<=next_phase;
            payload_data<=next_data;payload_valid<=next_valid;
        end
endmodule
`default_nettype wire
