// SPDX-License-Identifier: GPL-3.0-only
`default_nettype none
// Preserve the v2 calibration and atomic mailbox protocol, translating only
// committed raw-domain legal indices into immutable native programming codes.
// Native table, detector, update timing and physical admission remain required.
module openlvds_dll_control_v3 #(
    parameter CODE_WIDTH=13,RAW_WIDTH=13,CODE_COUNT=2,NATIVE_CODE_COUNT=8192,
    parameter MODEL_ADMITTED=0,TABLE_MODEL_ADMITTED=0,
    parameter [CODE_COUNT*RAW_WIDTH-1:0] RAW_CODES=0,
    parameter CONFIRMATIONS=64,TIMEOUT_CYCLES=2500000,
    parameter VOTES=3,SETTLE_CYCLES=4,TRIAL_TIMEOUT_CYCLES=1024
)(
    input wire mgmt_clk_25,raw_reference,reset_n,enable,train_req,frontend_ready,
    output wire clock_present,cal_busy,dll_locked,cal_fail,
    output wire [3:0] failure_code,measurement_failure_code,
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
    localparam PARAMETERS_VALID=CODE_WIDTH>=1 && CODE_WIDTH<=16 && RAW_WIDTH>=1 && RAW_WIDTH<=16 &&
        CODE_COUNT>=2 && CODE_COUNT<=(2**CODE_WIDTH) &&
        NATIVE_CODE_COUNT>=2 && NATIVE_CODE_COUNT<=(2**RAW_WIDTH) &&
        CONFIRMATIONS>=64 && CONFIRMATIONS<=65535 &&
        TIMEOUT_CYCLES>0 && TIMEOUT_CYCLES<=2500000;
    openlvds_dll_code_map_v2 #(.INDEX_WIDTH(CODE_WIDTH),.RAW_WIDTH(RAW_WIDTH),.CODE_COUNT(CODE_COUNT),
        .NATIVE_CODE_COUNT(NATIVE_CODE_COUNT),.MODEL_ADMITTED(TABLE_MODEL_ADMITTED && PARAMETERS_VALID),.RAW_CODES(RAW_CODES)) native_mapping(
        .indices(raw_indices),.raw_codes(raw_codes),.valid(mapping_valid));
    openlvds_dll_control_v2 #(.CODE_WIDTH(CODE_WIDTH),.LAST_CODE(CODE_COUNT-1),
        .MODEL_ADMITTED(MODEL_ADMITTED && TABLE_MODEL_ADMITTED && PARAMETERS_VALID),
        .CONFIRMATIONS(CONFIRMATIONS),.TIMEOUT_CYCLES(TIMEOUT_CYCLES),.VOTES(VOTES),
        .SETTLE_CYCLES(SETTLE_CYCLES),.TRIAL_TIMEOUT_CYCLES(TRIAL_TIMEOUT_CYCLES)) control(
        .mgmt_clk_25(mgmt_clk_25),.raw_reference(raw_reference),.reset_n(reset_n),.enable(enable),.train_req(train_req),
        .frontend_ready(frontend_ready && mapping_valid),.clock_present(clock_present),.cal_busy(cal_busy),.dll_locked(dll_locked),
        .cal_fail(cal_fail),.failure_code(failure_code),.measurement_failure_code(measurement_failure_code),
        .codes(codes),.raw_codes(raw_indices),.configuration_applied(configuration_applied),
        .raw_separated(raw_separated),.raw_commit(raw_commit),.raw_sequence(raw_sequence),
        .raw_update_allowed(raw_update_allowed),.raw_settled(raw_settled),.raw_settled_sequence(raw_settled_sequence),
        .route_next_period(route_next_period),.route_swap(route_swap),.route_positive_offset(route_positive_offset),
        .route_section_a(route_section_a),.route_section_b(route_section_b),.route_sequence(route_sequence),
        .routes_applied(routes_applied),.routes_sequence(routes_sequence),.arm(arm),.launch_pulse(launch_pulse),
        .reference_pulse(reference_pulse),.observed_a(observed_a),.observed_b(observed_b),.qa(qa),.qb(qb));
endmodule
`default_nettype wire
