// SPDX-License-Identifier: GPL-3.0-only
`default_nettype none
// Connect all-pairs/vote sequencing to actual isolated pulse/event trials.
// The physical wrapper applies the exposed route bundle while arm is low and
// acknowledges this exact route_sequence. It implements the characterized
// signed threshold with matched reference/feedback branches. No ideal delays,
// clocks or phase comparisons exist in this integration module.
module openlvds_dll_measurement_v2 #(
    parameter MODEL_ADMITTED=0,parameter VOTES=3,
    parameter SETTLE_CYCLES=4,parameter TRIAL_TIMEOUT_CYCLES=1024
)(
    input wire mgmt_clk_25,raw_reference,reset_n,enable,clock_present,frontend_ready,
    input wire measure_request,separated_mode,
    output wire measure_valid,measure_epoch_valid,measure_detector_valid,measure_balanced,
    output wire [1:0] measure_fastest,
    output wire measure_period_short,measure_period_long,
    output wire [3:0] failure_code,
    output wire route_next_period,route_swap,route_positive_offset,
    output wire [1:0] route_section_a,route_section_b,
    output wire [15:0] route_sequence,
    input wire routes_applied,
    input wire [15:0] routes_sequence,
    output wire arm,launch_pulse,reference_pulse,
    input wire observed_a,observed_b,qa,qb
);
    wire cancel,request_valid,request_ready,result_valid,result_ready;
    wire epoch_valid,detector_valid,reference_first,feedback_first;
    wire [15:0] result_sequence;
    wire [3:0] trial_failure;
    wire route_ok=routes_applied && routes_sequence==route_sequence;
    openlvds_dll_measure_v2 #(.MODEL_ADMITTED(MODEL_ADMITTED),.VOTES(VOTES)) sequence_control(
        .mgmt_clk_25(mgmt_clk_25),.reset_n(reset_n),.enable(enable),.clock_present(clock_present),
        .measure_request(measure_request),.separated_mode(separated_mode),.measure_valid(measure_valid),
        .measure_epoch_valid(measure_epoch_valid),.measure_detector_valid(measure_detector_valid),
        .measure_balanced(measure_balanced),.measure_fastest(measure_fastest),
        .measure_period_short(measure_period_short),.measure_period_long(measure_period_long),.failure_code(failure_code),
        .trial_cancel(cancel),.trial_request_valid(request_valid),.trial_request_ready(request_ready),
        .trial_routes_applied(routes_applied),.trial_routes_sequence(routes_sequence),
        .trial_next_period(route_next_period),.trial_swap(route_swap),.trial_positive_offset(route_positive_offset),
        .trial_section_a(route_section_a),.trial_section_b(route_section_b),.trial_sequence(route_sequence),
        .trial_result_valid(result_valid),.trial_result_ready(result_ready),.trial_result_sequence(result_sequence),
        .trial_epoch_valid(epoch_valid),.trial_detector_valid(detector_valid),
        .trial_reference_first(reference_first),.trial_feedback_first(feedback_first),.trial_failure_code(trial_failure)
    );
    openlvds_phase_trial_v2 #(.MODEL_ADMITTED(MODEL_ADMITTED),.SETTLE_CYCLES(SETTLE_CYCLES),
        .TIMEOUT_CYCLES(TRIAL_TIMEOUT_CYCLES)) trial(
        .mgmt_clk_25(mgmt_clk_25),.raw_reference(raw_reference),.reset_n(reset_n),
        .enable(enable && !cancel),.clock_present(clock_present),.frontend_ready(frontend_ready && route_ok),
        .request_valid(request_valid),.request_next_period(route_next_period),.request_swap(route_swap),
        .request_section_a(route_section_a),.request_section_b(route_section_b),.request_sequence(route_sequence),
        .request_ready(request_ready),.busy(),.route_next_period(),.route_swap(),.route_section_a(),.route_section_b(),
        .arm(arm),.launch_pulse(launch_pulse),.reference_pulse(reference_pulse),
        .observed_a(observed_a),.observed_b(observed_b),.qa(qa),.qb(qb),
        .result_valid(result_valid),.result_ready(result_ready),.result_sequence(result_sequence),
        .result_epoch_valid(epoch_valid),.result_detector_valid(detector_valid),
        .result_reference_first(reference_first),.result_feedback_first(feedback_first),.failure_code(trial_failure)
    );
endmodule
`default_nettype wire
