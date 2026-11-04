// SPDX-License-Identifier: GPL-3.0-only
`default_nettype none
// Complete DLL management/measurement/atomic-configuration control path.
// Physical delay ROMs, switches, signed thresholds and analog observers remain
// explicit interfaces. No behavioral delay or ideal timing oracle is present.
module openlvds_dll_control_v2 #(
    parameter CODE_WIDTH=13,LAST_CODE=8191,MODEL_ADMITTED=0,
    parameter CONFIRMATIONS=64,TIMEOUT_CYCLES=2500000,
    parameter VOTES=3,SETTLE_CYCLES=4,TRIAL_TIMEOUT_CYCLES=1024
)(
    input wire mgmt_clk_25,raw_reference,reset_n,enable,train_req,frontend_ready,
    output wire clock_present,cal_busy,dll_locked,cal_fail,
    output wire [3:0] failure_code,measurement_failure_code,
    output wire [4*CODE_WIDTH-1:0] codes,raw_codes,
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
    wire locked,request,separated;
    wire measure_valid,epoch_valid,detector_valid,balanced,period_short,period_long;
    wire [1:0] fastest;
    openlvds_clock_watch_v2 reference_watch(
        .reset_n(reset_n),.observed_clk(raw_reference),.mgmt_clk_25(mgmt_clk_25),.clock_present(clock_present));
    openlvds_dll_calibrate_v2 #(.CODE_WIDTH(CODE_WIDTH),.LAST_CODE(LAST_CODE),
        .CONFIRMATIONS(CONFIRMATIONS),.TIMEOUT_CYCLES(TIMEOUT_CYCLES)) calibration(
        .mgmt_clk_25(mgmt_clk_25),.reset_n(reset_n),.enable(enable),.train_req(train_req),.clock_present(clock_present),
        .codes_applied(configuration_applied),.measure_valid(measure_valid),.measure_epoch_valid(epoch_valid),
        .measure_balanced(balanced),.measure_fastest(fastest),.measure_period_short(period_short),
        .measure_period_long(period_long),.measure_detector_valid(detector_valid),
        .measure_request(request),.separated_mode(separated),.codes(codes),.cal_busy(cal_busy),
        .locked(locked),.cal_fail(cal_fail),.failure_code(failure_code));
    openlvds_dll_configuration_v2 #(.CODE_WIDTH(CODE_WIDTH)) configuration(
        .mgmt_clk_25(mgmt_clk_25),.raw_reference(raw_reference),.reset_n(reset_n),
        .enable(enable && (cal_busy || locked)),.train_req(train_req),.clock_present(clock_present),.locked(locked),
        .desired_codes(codes),.desired_separated(separated),.configuration_applied(configuration_applied),
        .raw_update_allowed(raw_update_allowed),.raw_codes(raw_codes),.raw_separated(raw_separated),
        .raw_commit(raw_commit),.raw_sequence(raw_sequence),.raw_settled(raw_settled),.raw_settled_sequence(raw_settled_sequence));
    openlvds_dll_measurement_v2 #(.MODEL_ADMITTED(MODEL_ADMITTED),.VOTES(VOTES),
        .SETTLE_CYCLES(SETTLE_CYCLES),.TRIAL_TIMEOUT_CYCLES(TRIAL_TIMEOUT_CYCLES)) measurement(
        .mgmt_clk_25(mgmt_clk_25),.raw_reference(raw_reference),.reset_n(reset_n),.enable(enable),
        .clock_present(clock_present),.frontend_ready(frontend_ready),
        .measure_request(request && configuration_applied),.separated_mode(separated),
        .measure_valid(measure_valid),.measure_epoch_valid(epoch_valid),.measure_detector_valid(detector_valid),
        .measure_balanced(balanced),.measure_fastest(fastest),.measure_period_short(period_short),
        .measure_period_long(period_long),.failure_code(measurement_failure_code),
        .route_next_period(route_next_period),.route_swap(route_swap),.route_positive_offset(route_positive_offset),
        .route_section_a(route_section_a),.route_section_b(route_section_b),.route_sequence(route_sequence),
        .routes_applied(routes_applied),.routes_sequence(routes_sequence),.arm(arm),
        .launch_pulse(launch_pulse),.reference_pulse(reference_pulse),
        .observed_a(observed_a),.observed_b(observed_b),.qa(qa),.qb(qb));
    // DLL lock alone is not DCC/warmup/training readiness.
    assign dll_locked=locked && configuration_applied && enable && clock_present && !cal_fail;
endmodule
`default_nettype wire
