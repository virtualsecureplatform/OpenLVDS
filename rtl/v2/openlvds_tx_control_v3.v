// SPDX-License-Identifier: GPL-3.0-only
`default_nettype none
// Mapped TX control: immutable legal/native ROM follows committed DLL indices.
// Switched routes, conditioned
// observers, raw phases and DCC clocks remain explicit backend interfaces.
// This module neither creates an ideal clock nor admits an unqualified model.
module openlvds_tx_control_v3 #(
    parameter CODE_WIDTH=13,RAW_WIDTH=13,CODE_COUNT=2,NATIVE_CODE_COUNT=8192,
    parameter TABLE_MODEL_ADMITTED=0,
    parameter [CODE_COUNT*RAW_WIDTH-1:0] RAW_CODES=0,
    parameter DLL_MODEL_ADMITTED=0,DCC_MODEL_ADMITTED=0,
    parameter CONFIRMATIONS=64,WARMUP_CYCLES=256,TIMEOUT_CYCLES=2500000,
    parameter VOTES=3,SETTLE_CYCLES=4,TRIAL_TIMEOUT_CYCLES=1024
)(
    input wire mgmt_clk_25,raw_reference,raw_phase0,raw_phase90,clock0,clock90,
    input wire reset_n,enable,train_req,frontend_ready,
    input wire [1:0] payload,
    output wire clock_present,dll_locked,clocks_ready,cal_busy,cal_fail,
    output wire [3:0] failure_code,measurement_failure_code,
    output wire [1:0] pair_data,
    output wire pair_valid,payload_active,dcc_reset0_n,dcc_reset90_n,
    output wire [4*CODE_WIDTH-1:0] codes,raw_indices,
    output wire [4*RAW_WIDTH-1:0] raw_codes,
    output wire mapping_valid,
    output wire configuration_applied,raw_separated,raw_commit,
    output wire [15:0] raw_sequence,
    input wire raw_update_allowed,raw_settled,
    input wire [15:0] raw_settled_sequence,
    output wire route_next_period,route_swap,route_positive_offset,
    output wire [1:0] route_section_a,route_section_b,
    output wire [15:0] route_sequence,
    input wire routes_applied,
    input wire [15:0] routes_sequence,
    output wire arm,launch_pulse,reference_pulse,
    input wire observed_a,observed_b,qa,qb
);
    wire bank_enable,start_dll,startup_enable,startup_ready,dll_fail,startup_fail;
    wire [3:0] dll_failure,startup_failure;
    wire [3:0] normalized_dll_failure=measurement_failure_code==8 ? 4'd8 : dll_failure;
    openlvds_clock_sequence_v2 #(.TIMEOUT_CYCLES(TIMEOUT_CYCLES)) sequence_control(
        .mgmt_clk_25(mgmt_clk_25),.reset_n(reset_n),.enable(enable),.train_req(train_req),
        .dll_locked(dll_locked),.dll_fail(dll_fail),.startup_ready(startup_ready),.startup_fail(startup_fail),
        .dll_failure_code(normalized_dll_failure),.startup_failure_code(startup_failure),
        .bank_enable(bank_enable),.start_dll(start_dll),.startup_enable(startup_enable),
        .outputs_valid(clocks_ready),.cal_busy(cal_busy),.cal_fail(cal_fail),.failure_code(failure_code));
    openlvds_dll_control_v3 #(.CODE_WIDTH(CODE_WIDTH),.RAW_WIDTH(RAW_WIDTH),.CODE_COUNT(CODE_COUNT),
        .NATIVE_CODE_COUNT(NATIVE_CODE_COUNT),.TABLE_MODEL_ADMITTED(TABLE_MODEL_ADMITTED),.RAW_CODES(RAW_CODES),
        .MODEL_ADMITTED(DLL_MODEL_ADMITTED),
        .CONFIRMATIONS(CONFIRMATIONS),.TIMEOUT_CYCLES(TIMEOUT_CYCLES),.VOTES(VOTES),
        .SETTLE_CYCLES(SETTLE_CYCLES),.TRIAL_TIMEOUT_CYCLES(TRIAL_TIMEOUT_CYCLES)) dll(
        .mgmt_clk_25(mgmt_clk_25),.raw_reference(raw_reference),.reset_n(reset_n),.enable(bank_enable),
        .train_req(start_dll),.frontend_ready(frontend_ready),.clock_present(clock_present),
        .cal_busy(),.dll_locked(dll_locked),.cal_fail(dll_fail),.failure_code(dll_failure),
        .measurement_failure_code(measurement_failure_code),.codes(codes),.raw_codes(raw_codes),.raw_indices(raw_indices),.mapping_valid(mapping_valid),
        .configuration_applied(configuration_applied),.raw_separated(raw_separated),.raw_commit(raw_commit),.raw_sequence(raw_sequence),
        .raw_update_allowed(raw_update_allowed && !clocks_ready),.raw_settled(raw_settled),.raw_settled_sequence(raw_settled_sequence),
        .route_next_period(route_next_period),.route_swap(route_swap),.route_positive_offset(route_positive_offset),
        .route_section_a(route_section_a),.route_section_b(route_section_b),.route_sequence(route_sequence),
        .routes_applied(routes_applied),.routes_sequence(routes_sequence),.arm(arm),.launch_pulse(launch_pulse),
        .reference_pulse(reference_pulse),.observed_a(observed_a),.observed_b(observed_b),.qa(qa),.qb(qb));
    openlvds_clock_startup_v2 #(.DCC_MODEL_ADMITTED(DCC_MODEL_ADMITTED),.WARMUP_CYCLES(WARMUP_CYCLES),
        .TIMEOUT_CYCLES(TIMEOUT_CYCLES)) startup(
        .mgmt_clk_25(mgmt_clk_25),.raw_phase0(raw_phase0),.raw_phase90(raw_phase90),.clock0(clock0),.clock90(clock90),
        .reset_n(reset_n),.enable(startup_enable),.dll_locked(dll_locked),.source_clock_present(clock_present),
        .dcc_reset0_n(dcc_reset0_n),.dcc_reset90_n(dcc_reset90_n),.clocks_ready(startup_ready),
        .ready0(),.ready90(),.cal_busy(),.cal_fail(startup_fail),.failure_code(startup_failure));
    // The overall coordinator accepts startup on a management edge. Retiming
    // that final grant prevents a mid-cycle assertion of data-domain validity.
    wire pair_reset_n=reset_n && clocks_ready;
    (* ASYNC_REG="TRUE" *) reg run_meta,run_sync;
    always @(posedge clock0 or negedge pair_reset_n)
        if(!pair_reset_n)begin run_meta<=0;run_sync<=0;end
        else begin run_meta<=1;run_sync<=run_meta;end
    (* ASYNC_REG="TRUE" *) reg train_meta,train_sync;
    always @(posedge clock0 or negedge reset_n)
        if(!reset_n)begin train_meta<=1;train_sync<=1;end
        else begin train_meta<=train_req;train_sync<=train_meta;end
    openlvds_training_tx_v2 framing(
        .clk_pair(clock0),.reset_n(reset_n),.run(run_sync),.train_req(train_sync),.payload(payload),
        .pair_data(pair_data),.payload_active(payload_active));
    assign pair_valid=run_sync;
endmodule
`default_nettype wire
