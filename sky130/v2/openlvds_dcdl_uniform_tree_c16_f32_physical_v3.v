// SPDX-License-Identifier: GPL-3.0-only
// Native structural experiment; no timing or PHY admission.
`default_nettype none
module openlvds_dcdl_uniform_tree_c16_f32_physical_v3 (
    input wire IN,
    output wire OUT,
    input wire S0,
    input wire S1,
    input wire S2,
    input wire S3,
    input wire E0,
    input wire E1,
    input wire E2,
    input wire E3,
    input wire E4,
    input wire E5,
    input wire E6,
    input wire E7,
    input wire E8,
    input wire E9,
    input wire E10,
    input wire E11,
    input wire E12,
    input wire E13,
    input wire E14,
    input wire E15,
    input wire E16,
    input wire E17,
    input wire E18,
    input wire E19,
    input wire E20,
    input wire E21,
    input wire E22,
    input wire E23,
    input wire E24,
    input wire E25,
    input wire E26,
    input wire E27,
    input wire E28,
    input wire E29,
    input wire E30,
    inout wire VPWR,
    inout wire VGND
);
    (* keep = 1 *) wire fine0;
    (* keep = 1 *) wire fine1;
    (* keep = 1 *) wire fine10;
    (* keep = 1 *) wire fine11;
    (* keep = 1 *) wire fine12;
    (* keep = 1 *) wire fine13;
    (* keep = 1 *) wire fine14;
    (* keep = 1 *) wire fine15;
    (* keep = 1 *) wire fine16;
    (* keep = 1 *) wire fine17;
    (* keep = 1 *) wire fine18;
    (* keep = 1 *) wire fine19;
    (* keep = 1 *) wire fine2;
    (* keep = 1 *) wire fine20;
    (* keep = 1 *) wire fine21;
    (* keep = 1 *) wire fine22;
    (* keep = 1 *) wire fine23;
    (* keep = 1 *) wire fine24;
    (* keep = 1 *) wire fine25;
    (* keep = 1 *) wire fine26;
    (* keep = 1 *) wire fine27;
    (* keep = 1 *) wire fine28;
    (* keep = 1 *) wire fine29;
    (* keep = 1 *) wire fine3;
    (* keep = 1 *) wire fine30;
    (* keep = 1 *) wire fine4;
    (* keep = 1 *) wire fine5;
    (* keep = 1 *) wire fine6;
    (* keep = 1 *) wire fine7;
    (* keep = 1 *) wire fine8;
    (* keep = 1 *) wire fine9;
    (* keep = 1 *) wire fine_b0;
    (* keep = 1 *) wire fine_b1;
    (* keep = 1 *) wire fine_b10;
    (* keep = 1 *) wire fine_b11;
    (* keep = 1 *) wire fine_b12;
    (* keep = 1 *) wire fine_b13;
    (* keep = 1 *) wire fine_b14;
    (* keep = 1 *) wire fine_b15;
    (* keep = 1 *) wire fine_b16;
    (* keep = 1 *) wire fine_b17;
    (* keep = 1 *) wire fine_b18;
    (* keep = 1 *) wire fine_b19;
    (* keep = 1 *) wire fine_b2;
    (* keep = 1 *) wire fine_b20;
    (* keep = 1 *) wire fine_b21;
    (* keep = 1 *) wire fine_b22;
    (* keep = 1 *) wire fine_b23;
    (* keep = 1 *) wire fine_b24;
    (* keep = 1 *) wire fine_b25;
    (* keep = 1 *) wire fine_b26;
    (* keep = 1 *) wire fine_b27;
    (* keep = 1 *) wire fine_b28;
    (* keep = 1 *) wire fine_b29;
    (* keep = 1 *) wire fine_b3;
    (* keep = 1 *) wire fine_b30;
    (* keep = 1 *) wire fine_b4;
    (* keep = 1 *) wire fine_b5;
    (* keep = 1 *) wire fine_b6;
    (* keep = 1 *) wire fine_b7;
    (* keep = 1 *) wire fine_b8;
    (* keep = 1 *) wire fine_b9;
    (* keep = 1 *) wire select0;
    (* keep = 1 *) wire select1;
    (* keep = 1 *) wire select2;
    (* keep = 1 *) wire select3;
    (* keep = 1 *) wire selected;
    (* keep = 1 *) wire tap0;
    (* keep = 1 *) wire tap1;
    (* keep = 1 *) wire tap10;
    (* keep = 1 *) wire tap11;
    (* keep = 1 *) wire tap12;
    (* keep = 1 *) wire tap13;
    (* keep = 1 *) wire tap14;
    (* keep = 1 *) wire tap15;
    (* keep = 1 *) wire tap2;
    (* keep = 1 *) wire tap3;
    (* keep = 1 *) wire tap4;
    (* keep = 1 *) wire tap5;
    (* keep = 1 *) wire tap6;
    (* keep = 1 *) wire tap7;
    (* keep = 1 *) wire tap8;
    (* keep = 1 *) wire tap9;
    (* keep = 1 *) wire tree0_0;
    (* keep = 1 *) wire tree0_1;
    (* keep = 1 *) wire tree0_2;
    (* keep = 1 *) wire tree0_3;
    (* keep = 1 *) wire unused_tail;
    (* keep = 1, dont_touch = 1 *) openlvds_buf_8_o4_shunted_v2 u_input (.A(IN), .X(tap0), .VGND(VGND), .VPWR(VPWR));
    (* keep = 1, dont_touch = 1 *) openlvds_buf_8_o4_shunted_v2 u_delay1 (.A(tap0), .X(tap1), .VGND(VGND), .VPWR(VPWR));
    (* keep = 1, dont_touch = 1 *) openlvds_buf_8_o4_shunted_v2 u_delay2 (.A(tap1), .X(tap2), .VGND(VGND), .VPWR(VPWR));
    (* keep = 1, dont_touch = 1 *) openlvds_buf_8_o4_shunted_v2 u_delay3 (.A(tap2), .X(tap3), .VGND(VGND), .VPWR(VPWR));
    (* keep = 1, dont_touch = 1 *) openlvds_buf_8_o4_shunted_v2 u_delay4 (.A(tap3), .X(tap4), .VGND(VGND), .VPWR(VPWR));
    (* keep = 1, dont_touch = 1 *) openlvds_buf_8_o4_shunted_v2 u_delay5 (.A(tap4), .X(tap5), .VGND(VGND), .VPWR(VPWR));
    (* keep = 1, dont_touch = 1 *) openlvds_buf_8_o4_shunted_v2 u_delay6 (.A(tap5), .X(tap6), .VGND(VGND), .VPWR(VPWR));
    (* keep = 1, dont_touch = 1 *) openlvds_buf_8_o4_shunted_v2 u_delay7 (.A(tap6), .X(tap7), .VGND(VGND), .VPWR(VPWR));
    (* keep = 1, dont_touch = 1 *) openlvds_buf_8_o4_shunted_v2 u_delay8 (.A(tap7), .X(tap8), .VGND(VGND), .VPWR(VPWR));
    (* keep = 1, dont_touch = 1 *) openlvds_buf_8_o4_shunted_v2 u_delay9 (.A(tap8), .X(tap9), .VGND(VGND), .VPWR(VPWR));
    (* keep = 1, dont_touch = 1 *) openlvds_buf_8_o4_shunted_v2 u_delay10 (.A(tap9), .X(tap10), .VGND(VGND), .VPWR(VPWR));
    (* keep = 1, dont_touch = 1 *) openlvds_buf_8_o4_shunted_v2 u_delay11 (.A(tap10), .X(tap11), .VGND(VGND), .VPWR(VPWR));
    (* keep = 1, dont_touch = 1 *) openlvds_buf_8_o4_shunted_v2 u_delay12 (.A(tap11), .X(tap12), .VGND(VGND), .VPWR(VPWR));
    (* keep = 1, dont_touch = 1 *) openlvds_buf_8_o4_shunted_v2 u_delay13 (.A(tap12), .X(tap13), .VGND(VGND), .VPWR(VPWR));
    (* keep = 1, dont_touch = 1 *) openlvds_buf_8_o4_shunted_v2 u_delay14 (.A(tap13), .X(tap14), .VGND(VGND), .VPWR(VPWR));
    (* keep = 1, dont_touch = 1 *) openlvds_buf_8_o4_shunted_v2 u_delay15 (.A(tap14), .X(tap15), .VGND(VGND), .VPWR(VPWR));
    (* keep = 1, dont_touch = 1 *) openlvds_buf_8_o4_shunted_v2 u_tail_load (.A(tap15), .X(unused_tail), .VGND(VGND), .VPWR(VPWR));
    (* keep = 1, dont_touch = 1 *) sky130_fd_sc_hd__buf_4 u_select_buffer0 (.A(S0), .VGND(VGND), .VNB(VGND), .VPB(VPWR), .VPWR(VPWR), .X(select0));
    (* keep = 1, dont_touch = 1 *) sky130_fd_sc_hd__buf_4 u_select_buffer1 (.A(S1), .VGND(VGND), .VNB(VGND), .VPB(VPWR), .VPWR(VPWR), .X(select1));
    (* keep = 1, dont_touch = 1 *) sky130_fd_sc_hd__buf_4 u_select_buffer2 (.A(S2), .VGND(VGND), .VNB(VGND), .VPB(VPWR), .VPWR(VPWR), .X(select2));
    (* keep = 1, dont_touch = 1 *) sky130_fd_sc_hd__buf_4 u_select_buffer3 (.A(S3), .VGND(VGND), .VNB(VGND), .VPB(VPWR), .VPWR(VPWR), .X(select3));
    (* keep = 1, dont_touch = 1 *) sky130_fd_sc_hd__mux4_4 u_mux0_0 (.A0(tap0), .A1(tap1), .A2(tap2), .A3(tap3), .S0(select0), .S1(select1), .VGND(VGND), .VNB(VGND), .VPB(VPWR), .VPWR(VPWR), .X(tree0_0));
    (* keep = 1, dont_touch = 1 *) sky130_fd_sc_hd__mux4_4 u_mux0_1 (.A0(tap4), .A1(tap5), .A2(tap6), .A3(tap7), .S0(select0), .S1(select1), .VGND(VGND), .VNB(VGND), .VPB(VPWR), .VPWR(VPWR), .X(tree0_1));
    (* keep = 1, dont_touch = 1 *) sky130_fd_sc_hd__mux4_4 u_mux0_2 (.A0(tap8), .A1(tap9), .A2(tap10), .A3(tap11), .S0(select0), .S1(select1), .VGND(VGND), .VNB(VGND), .VPB(VPWR), .VPWR(VPWR), .X(tree0_2));
    (* keep = 1, dont_touch = 1 *) sky130_fd_sc_hd__mux4_4 u_mux0_3 (.A0(tap12), .A1(tap13), .A2(tap14), .A3(tap15), .S0(select0), .S1(select1), .VGND(VGND), .VNB(VGND), .VPB(VPWR), .VPWR(VPWR), .X(tree0_3));
    (* keep = 1, dont_touch = 1 *) sky130_fd_sc_hd__mux4_4 u_mux1_0 (.A0(tree0_0), .A1(tree0_1), .A2(tree0_2), .A3(tree0_3), .S0(select2), .S1(select3), .VGND(VGND), .VNB(VGND), .VPB(VPWR), .VPWR(VPWR), .X(selected));
    (* keep = 1, dont_touch = 1 *) sky130_fd_sc_hd__buf_1 u_fine_buffer0 (.A(E0), .VGND(VGND), .VNB(VGND), .VPB(VPWR), .VPWR(VPWR), .X(fine0));
    (* keep = 1, dont_touch = 1 *) sky130_fd_sc_hd__inv_1 u_fine_inverse0 (.A(fine0), .VGND(VGND), .VNB(VGND), .VPB(VPWR), .VPWR(VPWR), .Y(fine_b0));
    (* keep = 1, dont_touch = 1 *) openlvds_mim_switch_2x3_v2 u_fine_unit0 (.NODE(selected), .EN(fine0), .ENB(fine_b0), .VDD(VPWR), .VSS(VGND));
    (* keep = 1, dont_touch = 1 *) sky130_fd_sc_hd__buf_1 u_fine_buffer1 (.A(E1), .VGND(VGND), .VNB(VGND), .VPB(VPWR), .VPWR(VPWR), .X(fine1));
    (* keep = 1, dont_touch = 1 *) sky130_fd_sc_hd__inv_1 u_fine_inverse1 (.A(fine1), .VGND(VGND), .VNB(VGND), .VPB(VPWR), .VPWR(VPWR), .Y(fine_b1));
    (* keep = 1, dont_touch = 1 *) openlvds_mim_switch_2x3_v2 u_fine_unit1 (.NODE(selected), .EN(fine1), .ENB(fine_b1), .VDD(VPWR), .VSS(VGND));
    (* keep = 1, dont_touch = 1 *) sky130_fd_sc_hd__buf_1 u_fine_buffer2 (.A(E2), .VGND(VGND), .VNB(VGND), .VPB(VPWR), .VPWR(VPWR), .X(fine2));
    (* keep = 1, dont_touch = 1 *) sky130_fd_sc_hd__inv_1 u_fine_inverse2 (.A(fine2), .VGND(VGND), .VNB(VGND), .VPB(VPWR), .VPWR(VPWR), .Y(fine_b2));
    (* keep = 1, dont_touch = 1 *) openlvds_mim_switch_2x3_v2 u_fine_unit2 (.NODE(selected), .EN(fine2), .ENB(fine_b2), .VDD(VPWR), .VSS(VGND));
    (* keep = 1, dont_touch = 1 *) sky130_fd_sc_hd__buf_1 u_fine_buffer3 (.A(E3), .VGND(VGND), .VNB(VGND), .VPB(VPWR), .VPWR(VPWR), .X(fine3));
    (* keep = 1, dont_touch = 1 *) sky130_fd_sc_hd__inv_1 u_fine_inverse3 (.A(fine3), .VGND(VGND), .VNB(VGND), .VPB(VPWR), .VPWR(VPWR), .Y(fine_b3));
    (* keep = 1, dont_touch = 1 *) openlvds_mim_switch_2x3_v2 u_fine_unit3 (.NODE(selected), .EN(fine3), .ENB(fine_b3), .VDD(VPWR), .VSS(VGND));
    (* keep = 1, dont_touch = 1 *) sky130_fd_sc_hd__buf_1 u_fine_buffer4 (.A(E4), .VGND(VGND), .VNB(VGND), .VPB(VPWR), .VPWR(VPWR), .X(fine4));
    (* keep = 1, dont_touch = 1 *) sky130_fd_sc_hd__inv_1 u_fine_inverse4 (.A(fine4), .VGND(VGND), .VNB(VGND), .VPB(VPWR), .VPWR(VPWR), .Y(fine_b4));
    (* keep = 1, dont_touch = 1 *) openlvds_mim_switch_2x3_v2 u_fine_unit4 (.NODE(selected), .EN(fine4), .ENB(fine_b4), .VDD(VPWR), .VSS(VGND));
    (* keep = 1, dont_touch = 1 *) sky130_fd_sc_hd__buf_1 u_fine_buffer5 (.A(E5), .VGND(VGND), .VNB(VGND), .VPB(VPWR), .VPWR(VPWR), .X(fine5));
    (* keep = 1, dont_touch = 1 *) sky130_fd_sc_hd__inv_1 u_fine_inverse5 (.A(fine5), .VGND(VGND), .VNB(VGND), .VPB(VPWR), .VPWR(VPWR), .Y(fine_b5));
    (* keep = 1, dont_touch = 1 *) openlvds_mim_switch_2x3_v2 u_fine_unit5 (.NODE(selected), .EN(fine5), .ENB(fine_b5), .VDD(VPWR), .VSS(VGND));
    (* keep = 1, dont_touch = 1 *) sky130_fd_sc_hd__buf_1 u_fine_buffer6 (.A(E6), .VGND(VGND), .VNB(VGND), .VPB(VPWR), .VPWR(VPWR), .X(fine6));
    (* keep = 1, dont_touch = 1 *) sky130_fd_sc_hd__inv_1 u_fine_inverse6 (.A(fine6), .VGND(VGND), .VNB(VGND), .VPB(VPWR), .VPWR(VPWR), .Y(fine_b6));
    (* keep = 1, dont_touch = 1 *) openlvds_mim_switch_2x3_v2 u_fine_unit6 (.NODE(selected), .EN(fine6), .ENB(fine_b6), .VDD(VPWR), .VSS(VGND));
    (* keep = 1, dont_touch = 1 *) sky130_fd_sc_hd__buf_1 u_fine_buffer7 (.A(E7), .VGND(VGND), .VNB(VGND), .VPB(VPWR), .VPWR(VPWR), .X(fine7));
    (* keep = 1, dont_touch = 1 *) sky130_fd_sc_hd__inv_1 u_fine_inverse7 (.A(fine7), .VGND(VGND), .VNB(VGND), .VPB(VPWR), .VPWR(VPWR), .Y(fine_b7));
    (* keep = 1, dont_touch = 1 *) openlvds_mim_switch_2x3_v2 u_fine_unit7 (.NODE(selected), .EN(fine7), .ENB(fine_b7), .VDD(VPWR), .VSS(VGND));
    (* keep = 1, dont_touch = 1 *) sky130_fd_sc_hd__buf_1 u_fine_buffer8 (.A(E8), .VGND(VGND), .VNB(VGND), .VPB(VPWR), .VPWR(VPWR), .X(fine8));
    (* keep = 1, dont_touch = 1 *) sky130_fd_sc_hd__inv_1 u_fine_inverse8 (.A(fine8), .VGND(VGND), .VNB(VGND), .VPB(VPWR), .VPWR(VPWR), .Y(fine_b8));
    (* keep = 1, dont_touch = 1 *) openlvds_mim_switch_2x3_v2 u_fine_unit8 (.NODE(selected), .EN(fine8), .ENB(fine_b8), .VDD(VPWR), .VSS(VGND));
    (* keep = 1, dont_touch = 1 *) sky130_fd_sc_hd__buf_1 u_fine_buffer9 (.A(E9), .VGND(VGND), .VNB(VGND), .VPB(VPWR), .VPWR(VPWR), .X(fine9));
    (* keep = 1, dont_touch = 1 *) sky130_fd_sc_hd__inv_1 u_fine_inverse9 (.A(fine9), .VGND(VGND), .VNB(VGND), .VPB(VPWR), .VPWR(VPWR), .Y(fine_b9));
    (* keep = 1, dont_touch = 1 *) openlvds_mim_switch_2x3_v2 u_fine_unit9 (.NODE(selected), .EN(fine9), .ENB(fine_b9), .VDD(VPWR), .VSS(VGND));
    (* keep = 1, dont_touch = 1 *) sky130_fd_sc_hd__buf_1 u_fine_buffer10 (.A(E10), .VGND(VGND), .VNB(VGND), .VPB(VPWR), .VPWR(VPWR), .X(fine10));
    (* keep = 1, dont_touch = 1 *) sky130_fd_sc_hd__inv_1 u_fine_inverse10 (.A(fine10), .VGND(VGND), .VNB(VGND), .VPB(VPWR), .VPWR(VPWR), .Y(fine_b10));
    (* keep = 1, dont_touch = 1 *) openlvds_mim_switch_2x3_v2 u_fine_unit10 (.NODE(selected), .EN(fine10), .ENB(fine_b10), .VDD(VPWR), .VSS(VGND));
    (* keep = 1, dont_touch = 1 *) sky130_fd_sc_hd__buf_1 u_fine_buffer11 (.A(E11), .VGND(VGND), .VNB(VGND), .VPB(VPWR), .VPWR(VPWR), .X(fine11));
    (* keep = 1, dont_touch = 1 *) sky130_fd_sc_hd__inv_1 u_fine_inverse11 (.A(fine11), .VGND(VGND), .VNB(VGND), .VPB(VPWR), .VPWR(VPWR), .Y(fine_b11));
    (* keep = 1, dont_touch = 1 *) openlvds_mim_switch_2x3_v2 u_fine_unit11 (.NODE(selected), .EN(fine11), .ENB(fine_b11), .VDD(VPWR), .VSS(VGND));
    (* keep = 1, dont_touch = 1 *) sky130_fd_sc_hd__buf_1 u_fine_buffer12 (.A(E12), .VGND(VGND), .VNB(VGND), .VPB(VPWR), .VPWR(VPWR), .X(fine12));
    (* keep = 1, dont_touch = 1 *) sky130_fd_sc_hd__inv_1 u_fine_inverse12 (.A(fine12), .VGND(VGND), .VNB(VGND), .VPB(VPWR), .VPWR(VPWR), .Y(fine_b12));
    (* keep = 1, dont_touch = 1 *) openlvds_mim_switch_2x3_v2 u_fine_unit12 (.NODE(selected), .EN(fine12), .ENB(fine_b12), .VDD(VPWR), .VSS(VGND));
    (* keep = 1, dont_touch = 1 *) sky130_fd_sc_hd__buf_1 u_fine_buffer13 (.A(E13), .VGND(VGND), .VNB(VGND), .VPB(VPWR), .VPWR(VPWR), .X(fine13));
    (* keep = 1, dont_touch = 1 *) sky130_fd_sc_hd__inv_1 u_fine_inverse13 (.A(fine13), .VGND(VGND), .VNB(VGND), .VPB(VPWR), .VPWR(VPWR), .Y(fine_b13));
    (* keep = 1, dont_touch = 1 *) openlvds_mim_switch_2x3_v2 u_fine_unit13 (.NODE(selected), .EN(fine13), .ENB(fine_b13), .VDD(VPWR), .VSS(VGND));
    (* keep = 1, dont_touch = 1 *) sky130_fd_sc_hd__buf_1 u_fine_buffer14 (.A(E14), .VGND(VGND), .VNB(VGND), .VPB(VPWR), .VPWR(VPWR), .X(fine14));
    (* keep = 1, dont_touch = 1 *) sky130_fd_sc_hd__inv_1 u_fine_inverse14 (.A(fine14), .VGND(VGND), .VNB(VGND), .VPB(VPWR), .VPWR(VPWR), .Y(fine_b14));
    (* keep = 1, dont_touch = 1 *) openlvds_mim_switch_2x3_v2 u_fine_unit14 (.NODE(selected), .EN(fine14), .ENB(fine_b14), .VDD(VPWR), .VSS(VGND));
    (* keep = 1, dont_touch = 1 *) sky130_fd_sc_hd__buf_1 u_fine_buffer15 (.A(E15), .VGND(VGND), .VNB(VGND), .VPB(VPWR), .VPWR(VPWR), .X(fine15));
    (* keep = 1, dont_touch = 1 *) sky130_fd_sc_hd__inv_1 u_fine_inverse15 (.A(fine15), .VGND(VGND), .VNB(VGND), .VPB(VPWR), .VPWR(VPWR), .Y(fine_b15));
    (* keep = 1, dont_touch = 1 *) openlvds_mim_switch_2x3_v2 u_fine_unit15 (.NODE(selected), .EN(fine15), .ENB(fine_b15), .VDD(VPWR), .VSS(VGND));
    (* keep = 1, dont_touch = 1 *) sky130_fd_sc_hd__buf_1 u_fine_buffer16 (.A(E16), .VGND(VGND), .VNB(VGND), .VPB(VPWR), .VPWR(VPWR), .X(fine16));
    (* keep = 1, dont_touch = 1 *) sky130_fd_sc_hd__inv_1 u_fine_inverse16 (.A(fine16), .VGND(VGND), .VNB(VGND), .VPB(VPWR), .VPWR(VPWR), .Y(fine_b16));
    (* keep = 1, dont_touch = 1 *) openlvds_mim_switch_2x3_v2 u_fine_unit16 (.NODE(selected), .EN(fine16), .ENB(fine_b16), .VDD(VPWR), .VSS(VGND));
    (* keep = 1, dont_touch = 1 *) sky130_fd_sc_hd__buf_1 u_fine_buffer17 (.A(E17), .VGND(VGND), .VNB(VGND), .VPB(VPWR), .VPWR(VPWR), .X(fine17));
    (* keep = 1, dont_touch = 1 *) sky130_fd_sc_hd__inv_1 u_fine_inverse17 (.A(fine17), .VGND(VGND), .VNB(VGND), .VPB(VPWR), .VPWR(VPWR), .Y(fine_b17));
    (* keep = 1, dont_touch = 1 *) openlvds_mim_switch_2x3_v2 u_fine_unit17 (.NODE(selected), .EN(fine17), .ENB(fine_b17), .VDD(VPWR), .VSS(VGND));
    (* keep = 1, dont_touch = 1 *) sky130_fd_sc_hd__buf_1 u_fine_buffer18 (.A(E18), .VGND(VGND), .VNB(VGND), .VPB(VPWR), .VPWR(VPWR), .X(fine18));
    (* keep = 1, dont_touch = 1 *) sky130_fd_sc_hd__inv_1 u_fine_inverse18 (.A(fine18), .VGND(VGND), .VNB(VGND), .VPB(VPWR), .VPWR(VPWR), .Y(fine_b18));
    (* keep = 1, dont_touch = 1 *) openlvds_mim_switch_2x3_v2 u_fine_unit18 (.NODE(selected), .EN(fine18), .ENB(fine_b18), .VDD(VPWR), .VSS(VGND));
    (* keep = 1, dont_touch = 1 *) sky130_fd_sc_hd__buf_1 u_fine_buffer19 (.A(E19), .VGND(VGND), .VNB(VGND), .VPB(VPWR), .VPWR(VPWR), .X(fine19));
    (* keep = 1, dont_touch = 1 *) sky130_fd_sc_hd__inv_1 u_fine_inverse19 (.A(fine19), .VGND(VGND), .VNB(VGND), .VPB(VPWR), .VPWR(VPWR), .Y(fine_b19));
    (* keep = 1, dont_touch = 1 *) openlvds_mim_switch_2x3_v2 u_fine_unit19 (.NODE(selected), .EN(fine19), .ENB(fine_b19), .VDD(VPWR), .VSS(VGND));
    (* keep = 1, dont_touch = 1 *) sky130_fd_sc_hd__buf_1 u_fine_buffer20 (.A(E20), .VGND(VGND), .VNB(VGND), .VPB(VPWR), .VPWR(VPWR), .X(fine20));
    (* keep = 1, dont_touch = 1 *) sky130_fd_sc_hd__inv_1 u_fine_inverse20 (.A(fine20), .VGND(VGND), .VNB(VGND), .VPB(VPWR), .VPWR(VPWR), .Y(fine_b20));
    (* keep = 1, dont_touch = 1 *) openlvds_mim_switch_2x3_v2 u_fine_unit20 (.NODE(selected), .EN(fine20), .ENB(fine_b20), .VDD(VPWR), .VSS(VGND));
    (* keep = 1, dont_touch = 1 *) sky130_fd_sc_hd__buf_1 u_fine_buffer21 (.A(E21), .VGND(VGND), .VNB(VGND), .VPB(VPWR), .VPWR(VPWR), .X(fine21));
    (* keep = 1, dont_touch = 1 *) sky130_fd_sc_hd__inv_1 u_fine_inverse21 (.A(fine21), .VGND(VGND), .VNB(VGND), .VPB(VPWR), .VPWR(VPWR), .Y(fine_b21));
    (* keep = 1, dont_touch = 1 *) openlvds_mim_switch_2x3_v2 u_fine_unit21 (.NODE(selected), .EN(fine21), .ENB(fine_b21), .VDD(VPWR), .VSS(VGND));
    (* keep = 1, dont_touch = 1 *) sky130_fd_sc_hd__buf_1 u_fine_buffer22 (.A(E22), .VGND(VGND), .VNB(VGND), .VPB(VPWR), .VPWR(VPWR), .X(fine22));
    (* keep = 1, dont_touch = 1 *) sky130_fd_sc_hd__inv_1 u_fine_inverse22 (.A(fine22), .VGND(VGND), .VNB(VGND), .VPB(VPWR), .VPWR(VPWR), .Y(fine_b22));
    (* keep = 1, dont_touch = 1 *) openlvds_mim_switch_2x3_v2 u_fine_unit22 (.NODE(selected), .EN(fine22), .ENB(fine_b22), .VDD(VPWR), .VSS(VGND));
    (* keep = 1, dont_touch = 1 *) sky130_fd_sc_hd__buf_1 u_fine_buffer23 (.A(E23), .VGND(VGND), .VNB(VGND), .VPB(VPWR), .VPWR(VPWR), .X(fine23));
    (* keep = 1, dont_touch = 1 *) sky130_fd_sc_hd__inv_1 u_fine_inverse23 (.A(fine23), .VGND(VGND), .VNB(VGND), .VPB(VPWR), .VPWR(VPWR), .Y(fine_b23));
    (* keep = 1, dont_touch = 1 *) openlvds_mim_switch_2x3_v2 u_fine_unit23 (.NODE(selected), .EN(fine23), .ENB(fine_b23), .VDD(VPWR), .VSS(VGND));
    (* keep = 1, dont_touch = 1 *) sky130_fd_sc_hd__buf_1 u_fine_buffer24 (.A(E24), .VGND(VGND), .VNB(VGND), .VPB(VPWR), .VPWR(VPWR), .X(fine24));
    (* keep = 1, dont_touch = 1 *) sky130_fd_sc_hd__inv_1 u_fine_inverse24 (.A(fine24), .VGND(VGND), .VNB(VGND), .VPB(VPWR), .VPWR(VPWR), .Y(fine_b24));
    (* keep = 1, dont_touch = 1 *) openlvds_mim_switch_2x3_v2 u_fine_unit24 (.NODE(selected), .EN(fine24), .ENB(fine_b24), .VDD(VPWR), .VSS(VGND));
    (* keep = 1, dont_touch = 1 *) sky130_fd_sc_hd__buf_1 u_fine_buffer25 (.A(E25), .VGND(VGND), .VNB(VGND), .VPB(VPWR), .VPWR(VPWR), .X(fine25));
    (* keep = 1, dont_touch = 1 *) sky130_fd_sc_hd__inv_1 u_fine_inverse25 (.A(fine25), .VGND(VGND), .VNB(VGND), .VPB(VPWR), .VPWR(VPWR), .Y(fine_b25));
    (* keep = 1, dont_touch = 1 *) openlvds_mim_switch_2x3_v2 u_fine_unit25 (.NODE(selected), .EN(fine25), .ENB(fine_b25), .VDD(VPWR), .VSS(VGND));
    (* keep = 1, dont_touch = 1 *) sky130_fd_sc_hd__buf_1 u_fine_buffer26 (.A(E26), .VGND(VGND), .VNB(VGND), .VPB(VPWR), .VPWR(VPWR), .X(fine26));
    (* keep = 1, dont_touch = 1 *) sky130_fd_sc_hd__inv_1 u_fine_inverse26 (.A(fine26), .VGND(VGND), .VNB(VGND), .VPB(VPWR), .VPWR(VPWR), .Y(fine_b26));
    (* keep = 1, dont_touch = 1 *) openlvds_mim_switch_2x3_v2 u_fine_unit26 (.NODE(selected), .EN(fine26), .ENB(fine_b26), .VDD(VPWR), .VSS(VGND));
    (* keep = 1, dont_touch = 1 *) sky130_fd_sc_hd__buf_1 u_fine_buffer27 (.A(E27), .VGND(VGND), .VNB(VGND), .VPB(VPWR), .VPWR(VPWR), .X(fine27));
    (* keep = 1, dont_touch = 1 *) sky130_fd_sc_hd__inv_1 u_fine_inverse27 (.A(fine27), .VGND(VGND), .VNB(VGND), .VPB(VPWR), .VPWR(VPWR), .Y(fine_b27));
    (* keep = 1, dont_touch = 1 *) openlvds_mim_switch_2x3_v2 u_fine_unit27 (.NODE(selected), .EN(fine27), .ENB(fine_b27), .VDD(VPWR), .VSS(VGND));
    (* keep = 1, dont_touch = 1 *) sky130_fd_sc_hd__buf_1 u_fine_buffer28 (.A(E28), .VGND(VGND), .VNB(VGND), .VPB(VPWR), .VPWR(VPWR), .X(fine28));
    (* keep = 1, dont_touch = 1 *) sky130_fd_sc_hd__inv_1 u_fine_inverse28 (.A(fine28), .VGND(VGND), .VNB(VGND), .VPB(VPWR), .VPWR(VPWR), .Y(fine_b28));
    (* keep = 1, dont_touch = 1 *) openlvds_mim_switch_2x3_v2 u_fine_unit28 (.NODE(selected), .EN(fine28), .ENB(fine_b28), .VDD(VPWR), .VSS(VGND));
    (* keep = 1, dont_touch = 1 *) sky130_fd_sc_hd__buf_1 u_fine_buffer29 (.A(E29), .VGND(VGND), .VNB(VGND), .VPB(VPWR), .VPWR(VPWR), .X(fine29));
    (* keep = 1, dont_touch = 1 *) sky130_fd_sc_hd__inv_1 u_fine_inverse29 (.A(fine29), .VGND(VGND), .VNB(VGND), .VPB(VPWR), .VPWR(VPWR), .Y(fine_b29));
    (* keep = 1, dont_touch = 1 *) openlvds_mim_switch_2x3_v2 u_fine_unit29 (.NODE(selected), .EN(fine29), .ENB(fine_b29), .VDD(VPWR), .VSS(VGND));
    (* keep = 1, dont_touch = 1 *) sky130_fd_sc_hd__buf_1 u_fine_buffer30 (.A(E30), .VGND(VGND), .VNB(VGND), .VPB(VPWR), .VPWR(VPWR), .X(fine30));
    (* keep = 1, dont_touch = 1 *) sky130_fd_sc_hd__inv_1 u_fine_inverse30 (.A(fine30), .VGND(VGND), .VNB(VGND), .VPB(VPWR), .VPWR(VPWR), .Y(fine_b30));
    (* keep = 1, dont_touch = 1 *) openlvds_mim_switch_2x3_v2 u_fine_unit30 (.NODE(selected), .EN(fine30), .ENB(fine_b30), .VDD(VPWR), .VSS(VGND));
    (* keep = 1, dont_touch = 1 *) openlvds_buf_8_o4_shunted_v2 u_output (.A(selected), .X(OUT), .VGND(VGND), .VPWR(VPWR));
endmodule
`default_nettype wire
