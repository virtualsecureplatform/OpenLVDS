// SPDX-License-Identifier: GPL-3.0-only
`default_nettype none
// Complete RX control composition. source_clk precedes deskew; raw_reference
// is the actual post-deskew DLL reference. Phases, DCC clocks, sampled pairs,
// delay ROMs and physical settling/measurement remain explicit backend ports.
module openlvds_rx_control_v2 #(
    parameter DLL_CODE_WIDTH=13,DLL_LAST_CODE=8191,DESKEW_CODE_WIDTH=13,DESKEW_CODE_COUNT=8192,
    parameter DLL_MODEL_ADMITTED=0,CODE_MODEL_ADMITTED=0,DESKEW_MODEL_ADMITTED=0,DCC_MODEL_ADMITTED=0,
    parameter CONFIRMATIONS=64,WARMUP_CYCLES=256,TIMEOUT_CYCLES=2500000,
    parameter VOTES=3,SETTLE_CYCLES=4,TRIAL_TIMEOUT_CYCLES=1024
)(
    input wire mgmt_clk_25,source_clk,raw_reference,raw_phase0,raw_phase90,clock0,clock90,
    input wire reset_n,enable,train_req,frontend_ready,
    output wire clock_present,dll_reference_present,dll_locked,clocks_ready,cal_busy,cal_fail,
    output wire [3:0] failure_code,measurement_failure_code,
    input wire table_ready,output wire [DESKEW_CODE_WIDTH-1:0] table_index,
    input wire [15:0] delay_lo_ps,delay_hi_ps,
    output wire [DESKEW_CODE_WIDTH-1:0] deskew_index,
    output wire [15:0] deskew_sequence,output wire deskew_commit,
    input wire deskew_update_allowed,deskew_settled,
    input wire [15:0] deskew_settled_sequence,
    input wire [1:0] captured_pair,input wire captured_valid,
    output wire [1:0] rx_data,output wire rx_valid,rx_ready,
    output wire [15:0] selected_clearance_ps,
    output wire dcc_reset0_n,dcc_reset90_n,
    output wire [4*DLL_CODE_WIDTH-1:0] codes,raw_codes,
    output wire configuration_applied,raw_separated,raw_commit,
    output wire [15:0] raw_sequence,
    input wire raw_update_allowed,raw_settled,
    input wire [15:0] raw_settled_sequence,
    output wire route_next_period,route_swap,route_positive_offset,
    output wire [1:0] route_section_a,route_section_b,
    output wire [15:0] route_sequence,
    input wire routes_applied,input wire [15:0] routes_sequence,
    output wire arm,launch_pulse,reference_pulse,
    input wire observed_a,observed_b,qa,qb
);
    localparam PARAMETERS_VALID=DLL_CODE_WIDTH>=1 && DLL_CODE_WIDTH<=16 && DLL_LAST_CODE>=0 &&
        DLL_LAST_CODE<(2**DLL_CODE_WIDTH) && CONFIRMATIONS>=64 && CONFIRMATIONS<=65535 &&
        VOTES>=1 && VOTES<=65535 && VOTES%2==1 && SETTLE_CYCLES>0 && TRIAL_TIMEOUT_CYCLES>0 &&
        TIMEOUT_CYCLES>0 && TIMEOUT_CYCLES<=2500000;
    wire dll_enable,dll_train,dll_failed;
    wire [3:0] dll_failure;
    wire [3:0] normalized_dll_failure=measurement_failure_code==8 ? 4'd8 : dll_failure;
    openlvds_dll_control_v2 #(.CODE_WIDTH(DLL_CODE_WIDTH),.LAST_CODE(DLL_LAST_CODE),
        .MODEL_ADMITTED(DLL_MODEL_ADMITTED),.CONFIRMATIONS(CONFIRMATIONS),.TIMEOUT_CYCLES(TIMEOUT_CYCLES),
        .VOTES(VOTES),.SETTLE_CYCLES(SETTLE_CYCLES),.TRIAL_TIMEOUT_CYCLES(TRIAL_TIMEOUT_CYCLES)) dll(
        .mgmt_clk_25(mgmt_clk_25),.raw_reference(raw_reference),.reset_n(reset_n),.enable(dll_enable),
        .train_req(dll_train),.frontend_ready(frontend_ready),.clock_present(dll_reference_present),
        .cal_busy(),.dll_locked(dll_locked),.cal_fail(dll_failed),.failure_code(dll_failure),
        .measurement_failure_code(measurement_failure_code),.codes(codes),.raw_codes(raw_codes),
        .configuration_applied(configuration_applied),.raw_separated(raw_separated),.raw_commit(raw_commit),
        .raw_sequence(raw_sequence),.raw_update_allowed(raw_update_allowed && !dll_locked && !rx_ready),
        .raw_settled(raw_settled),.raw_settled_sequence(raw_settled_sequence),
        .route_next_period(route_next_period),.route_swap(route_swap),.route_positive_offset(route_positive_offset),
        .route_section_a(route_section_a),.route_section_b(route_section_b),.route_sequence(route_sequence),
        .routes_applied(routes_applied),.routes_sequence(routes_sequence),.arm(arm),.launch_pulse(launch_pulse),
        .reference_pulse(reference_pulse),.observed_a(observed_a),.observed_b(observed_b),.qa(qa),.qb(qb));
    openlvds_rx_training_v3 #(.CODE_WIDTH(DESKEW_CODE_WIDTH),.CODE_COUNT(DESKEW_CODE_COUNT),
        .CODE_MODEL_ADMITTED(CODE_MODEL_ADMITTED && PARAMETERS_VALID),.DESKEW_MODEL_ADMITTED(DESKEW_MODEL_ADMITTED),
        .DCC_MODEL_ADMITTED(DCC_MODEL_ADMITTED),.WARMUP_CYCLES(WARMUP_CYCLES),.TIMEOUT_CYCLES(TIMEOUT_CYCLES)) training(
        .mgmt_clk_25(mgmt_clk_25),.source_clk(source_clk),.raw_phase0(raw_phase0),.raw_phase90(raw_phase90),
        .clock0(clock0),.clock90(clock90),.reset_n(reset_n),.enable(enable),.train_req(train_req),
        .dll_locked(dll_locked),.dll_failed(dll_failed),.dll_failure_code(normalized_dll_failure),
        .dll_enable(dll_enable),.dll_train(dll_train),.table_ready(table_ready),.table_index(table_index),
        .delay_lo_ps(delay_lo_ps),.delay_hi_ps(delay_hi_ps),.update_allowed(deskew_update_allowed),
        .physical_settled(deskew_settled),.physical_settled_sequence(deskew_settled_sequence),
        .deskew_index(deskew_index),.deskew_sequence(deskew_sequence),.deskew_commit(deskew_commit),
        .dcc_reset0_n(dcc_reset0_n),.dcc_reset90_n(dcc_reset90_n),.clocks_ready(clocks_ready),
        .source_clock_present(clock_present),.captured_pair(captured_pair),.captured_valid(captured_valid),
        .rx_data(rx_data),.rx_valid(rx_valid),.rx_ready(rx_ready),.cal_busy(cal_busy),.cal_fail(cal_fail),
        .failure_code(failure_code),.selected_clearance_ps(selected_clearance_ps));
endmodule
`default_nettype wire
