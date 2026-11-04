// SPDX-License-Identifier: GPL-3.0-only
`default_nettype none
// Management FSM. Measurement engine must perform a separated four-section
// tournament, then an independent tagged unwrapped period measurement. No
// elapsed-time lock and no analog pulse-area integration are permitted.
// Codes index the characterized common legal sequence, not raw delay controls.
module openlvds_dll_calibrate_v2 #(
    parameter CODE_WIDTH=13, parameter LAST_CODE=8191,
    parameter CONFIRMATIONS=64, parameter TIMEOUT_CYCLES=2500000
)(
    input wire mgmt_clk_25, reset_n, enable, train_req, clock_present,
    input wire codes_applied,
    input wire measure_valid, measure_epoch_valid, measure_balanced,
    input wire [1:0] measure_fastest,
    input wire measure_period_short, measure_period_long,
    input wire measure_detector_valid,
    output wire measure_request, output wire separated_mode,
    output wire [4*CODE_WIDTH-1:0] codes,
    output reg cal_busy, locked, cal_fail,
    output reg [3:0] failure_code
);
    localparam IDLE=0, SEPARATE=1, PERIOD=2, SETTLE=3, LOCKED=4, FAILED=5, PERIOD_GAP=6, WAIT_CLOCK=7;
    reg [2:0] state;
    reg [CODE_WIDTH-1:0] code0, code1, code2, code3;
    reg [1:0] fastest;
    reg balanced, train_seen;
    reg [31:0] age;
    reg [15:0] confirmations;
    assign codes={code3,code2,code1,code0};
    assign separated_mode=state==SEPARATE;
    assign measure_request=enable && clock_present && (state==SEPARATE || state==PERIOD);
    wire saturated = (fastest==0 && code0==LAST_CODE) || (fastest==1 && code1==LAST_CODE)
                  || (fastest==2 && code2==LAST_CODE) || (fastest==3 && code3==LAST_CODE);
    task fail;
        input [3:0] reason;
        begin state<=FAILED; cal_busy<=0; locked<=0; cal_fail<=1; failure_code<=reason; end
    endtask
    always @(posedge mgmt_clk_25 or negedge reset_n)
        if (!reset_n) begin
            state<=IDLE; code0<=0; code1<=0; code2<=0; code3<=0;
            fastest<=0; balanced<=0; train_seen<=0; age<=0; confirmations<=0;
            cal_busy<=0; locked<=0; cal_fail<=0; failure_code<=0;
        end else begin
            train_seen<=train_req;
            if (!enable) begin
                state<=IDLE; locked<=0; cal_busy<=0; cal_fail<=0; failure_code<=0; age<=0; train_seen<=0;
            end else if (train_req && !train_seen) begin
                code0<=0; code1<=0; code2<=0; code3<=0; confirmations<=0; age<=0;
                locked<=0; cal_fail<=0; failure_code<=0; cal_busy<=1; state<=WAIT_CLOCK;
            end else if ((locked || (cal_busy && state!=WAIT_CLOCK)) && !clock_present) fail(4'd1);
            else if (cal_busy && age>=TIMEOUT_CYCLES-1) fail(4'd2);
            else begin
                if (cal_busy) age<=age+1;
                case (state)
                    WAIT_CLOCK: if (clock_present) state<=SETTLE;
                    SETTLE: if (codes_applied) state<=SEPARATE;
                    PERIOD_GAP: state<=PERIOD;
                    SEPARATE: if (measure_valid) begin
                        if (!measure_detector_valid) fail(4'd5);
                        else begin fastest<=measure_fastest; balanced<=measure_balanced; state<=PERIOD_GAP; end
                    end
                    PERIOD: if (measure_valid) begin
                        if (!measure_detector_valid) fail(4'd5);
                        else if (!measure_epoch_valid || (measure_period_short && measure_period_long)) fail(4'd4);
                        else if (measure_period_long) fail(4'd3);
                        else if (!measure_period_short && balanced) begin
                            if (confirmations==CONFIRMATIONS-1) begin
                                locked<=1; cal_busy<=0; state<=LOCKED;
                            end else begin confirmations<=confirmations+1; state<=SETTLE; end
                        end else if (saturated) fail(4'd3);
                        else begin
                            case (fastest)
                                0: code0<=code0+1'b1;
                                1: code1<=code1+1'b1;
                                2: code2<=code2+1'b1;
                                3: code3<=code3+1'b1;
                            endcase
                            confirmations<=0; state<=SETTLE;
                        end
                    end
                    default: begin end
                endcase
            end
        end
endmodule
`default_nettype wire
