// SPDX-License-Identifier: GPL-3.0-only
`default_nettype none
// Unqualified edge-sampled detector candidate. Exchange inputs between trials
// to expose path/device bias; measure its dead zone rather than assuming that
// digital control removes slew-dependent offset. Results need a settled CDC
// snapshot and epoch qualification before the management FSM may consume them.
module openlvds_bbpd_v2 #(parameter INPUT_DRIVE=4)(
    input wire reference,feedback,swap_inputs,output wire sample_a,sample_b
);
    wire r0,f0,a,b;
    (* keep="true", dont_touch="true" *)
    sky130_fd_sc_hd__mux2_1 select_a(.A0(reference),.A1(feedback),.S(swap_inputs),.X(r0));
    (* keep="true", dont_touch="true" *)
    sky130_fd_sc_hd__mux2_1 select_b(.A0(feedback),.A1(reference),.S(swap_inputs),.X(f0));
    generate if(INPUT_DRIVE==1)begin: small
        (* keep="true", dont_touch="true" *) sky130_fd_sc_hd__buf_1 first(.A(r0),.X(a));
        (* keep="true", dont_touch="true" *) sky130_fd_sc_hd__buf_1 second(.A(f0),.X(b));
    end else begin: large
        (* keep="true", dont_touch="true" *) sky130_fd_sc_hd__buf_4 first(.A(r0),.X(a));
        (* keep="true", dont_touch="true" *) sky130_fd_sc_hd__buf_4 second(.A(f0),.X(b));
    end endgenerate
    (* keep="true", dont_touch="true" *)
    sky130_fd_sc_hd__dfxtp_1 first_sample(.CLK(a),.D(b),.Q(sample_a));
    (* keep="true", dont_touch="true" *)
    sky130_fd_sc_hd__dfxtp_1 second_sample(.CLK(b),.D(a),.Q(sample_b));
endmodule
`default_nettype wire
