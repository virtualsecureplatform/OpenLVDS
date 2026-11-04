// SPDX-License-Identifier: GPL-3.0-only
`default_nettype none
// Regenerative candidate with input conditioning BEFORE the swap mux.
// This isolates input-slew bias in the conditioning and selection paths.
// Regenerative tagged-event candidate. Arm only after both selected input
// pulses are LOW; hold until the result crosses into management, then clear.
// Unlike a CLK/D sampler, the race has no flip-flop setup aperture. Native
// offset, metastability, reset, pulse transport and physical proofs remain
// mandatory. No numerical tolerance or DLL lock criterion is relaxed.
module openlvds_preconditioned_arbiter_v2 #(parameter INPUT_DRIVE=4)(
    input wire reference,feedback,swap_inputs,cal_arm,
    output wire sample_a,sample_b,held_a,held_b
);
    wire r0,f0,a,b,or_a,or_b;
    (* keep="true", dont_touch="true" *)
    sky130_fd_sc_hd__mux2_1 select_a(.A0(r0),.A1(f0),.S(swap_inputs),.X(a));
    (* keep="true", dont_touch="true" *)
    sky130_fd_sc_hd__mux2_1 select_b(.A0(f0),.A1(r0),.S(swap_inputs),.X(b));
    generate if(INPUT_DRIVE==1)begin: input_drive_one
        (* keep="true", dont_touch="true" *) sky130_fd_sc_hd__buf_1 first(.A(reference),.X(r0));
        (* keep="true", dont_touch="true" *) sky130_fd_sc_hd__buf_1 second(.A(feedback),.X(f0));
    end else begin: input_drive_four
        (* keep="true", dont_touch="true" *) sky130_fd_sc_hd__buf_4 first(.A(reference),.X(r0));
        (* keep="true", dont_touch="true" *) sky130_fd_sc_hd__buf_4 second(.A(feedback),.X(f0));
    end endgenerate
    (* keep="true", dont_touch="true" *)
    sky130_fd_sc_hd__or2_1 event_a(.A(a),.B(held_a),.X(or_a));
    (* keep="true", dont_touch="true" *)
    sky130_fd_sc_hd__or2_1 event_b(.A(b),.B(held_b),.X(or_b));
    (* keep="true", dont_touch="true" *)
    sky130_fd_sc_hd__and2_1 hold_a(.A(or_a),.B(cal_arm),.X(held_a));
    (* keep="true", dont_touch="true" *)
    sky130_fd_sc_hd__and2_1 hold_b(.A(or_b),.B(cal_arm),.X(held_b));
    (* keep="true", dont_touch="true" *)
    sky130_fd_sc_hd__nand2_4 arbitrate_a(.A(held_a),.B(sample_b),.Y(sample_a));
    (* keep="true", dont_touch="true" *)
    sky130_fd_sc_hd__nand2_4 arbitrate_b(.A(held_b),.B(sample_a),.Y(sample_b));
endmodule
`default_nettype wire
