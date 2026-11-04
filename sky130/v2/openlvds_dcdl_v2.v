// SPDX-License-Identifier: GPL-3.0-only
`default_nettype none
// Source topology candidate, inspired by the NAND mirror lattice and enabled
// inverter loads in the pinned Apache-2.0 OpenPLL experiments. No pinned source
// is modified. Thermometer controls must be committed only while invalid.
// Increasing fine code is NOT assumed to increase delay until characterized.
module openlvds_dcdl_v2 #(parameter COARSE_COUNT=16, FINE_COUNT=32)(
    input wire clock_in,
    input wire [COARSE_COUNT-2:0] coarse_therm,
    input wire [FINE_COUNT-2:0] fine_therm,
    output wire clock_out
);
    wire [COARSE_COUNT-1:0] forward_path, return_path, turn_n;
    wire [COARSE_COUNT-2:0] pass_n;
    (* keep="true", dont_touch="true" *) wire [FINE_COUNT-2:0] load_dummy;
    (* keep="true", dont_touch="true" *)
    sky130_fd_sc_hd__buf_4 input_drive(.A(clock_in),.X(forward_path[0]));
    genvar i;
    generate for(i=0;i<COARSE_COUNT;i=i+1) begin: coarse
        if(i<COARSE_COUNT-1) begin: controlled
            (* keep="true", dont_touch="true" *)
            sky130_fd_sc_hd__nand2_4 forward_gate(.A(forward_path[i]),.B(coarse_therm[i]),.Y(forward_path[i+1]));
            (* keep="true", dont_touch="true" *)
            sky130_fd_sc_hd__nand2b_4 turn_gate(.A_N(coarse_therm[i]),.B(forward_path[i]),.Y(turn_n[i]));
            (* keep="true", dont_touch="true" *)
            sky130_fd_sc_hd__nand2b_4 return_gate(.A_N(return_path[i+1]),.B(coarse_therm[i]),.Y(pass_n[i]));
            (* keep="true", dont_touch="true" *)
            sky130_fd_sc_hd__nand2_4 merge_gate(.A(turn_n[i]),.B(pass_n[i]),.Y(return_path[i]));
        end else begin: terminal
            (* keep="true", dont_touch="true" *)
            sky130_fd_sc_hd__nand2b_4 turn_gate(.A_N(1'b0),.B(forward_path[i]),.Y(turn_n[i]));
            (* keep="true", dont_touch="true" *)
            sky130_fd_sc_hd__nand2_4 merge_gate(.A(turn_n[i]),.B(1'b1),.Y(return_path[i]));
        end
    end
    for(i=0;i<FINE_COUNT-1;i=i+1) begin: fine
        if(i%2==0) begin: on_input
            (* keep="true", dont_touch="true" *)
            sky130_fd_sc_hd__einvp_1 load_cell(.A(forward_path[0]),.TE(fine_therm[i]),.Z(load_dummy[i]));
        end else begin: on_return
            (* keep="true", dont_touch="true" *)
            sky130_fd_sc_hd__einvp_1 load_cell(.A(return_path[0]),.TE(fine_therm[i]),.Z(load_dummy[i]));
        end
    end endgenerate
    (* keep="true", dont_touch="true" *)
    sky130_fd_sc_hd__buf_4 output_drive(.A(return_path[0]),.X(clock_out));
endmodule
`default_nettype wire
