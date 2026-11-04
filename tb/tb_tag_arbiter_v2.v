// SPDX-License-Identifier: GPL-3.0-only
`timescale 1ns/1ps
// Unit gate delays serve logic simulation only; native timing comes from SPICE.
module sky130_fd_sc_hd__mux2_1(input A0,A1,S,output X);assign #0.001 X=S?A1:A0;endmodule
module sky130_fd_sc_hd__buf_1(input A,output X);assign #0.001 X=A;endmodule
module sky130_fd_sc_hd__buf_4(input A,output X);assign #0.001 X=A;endmodule
module sky130_fd_sc_hd__or2_1(input A,B,output X);assign #0.001 X=A|B;endmodule
module sky130_fd_sc_hd__and2_1(input A,B,output X);assign #0.001 X=A&B;endmodule
module sky130_fd_sc_hd__nand2_4(input A,B,output Y);assign #0.001 Y=~(A&B);endmodule
module tb_tag_arbiter_v2;
    reg reference=0,feedback=0,swap=0,arm=0;
    wire qa,qb,ha,hb;
    wire ref_q=swap?qb:qa;
    wire fb_q=swap?qa:qb;
    openlvds_tag_arbiter_v2 dut(.reference(reference),.feedback(feedback),.swap_inputs(swap),
        .cal_arm(arm),.sample_a(qa),.sample_b(qb),.held_a(ha),.held_b(hb));
    integer s,first;
    initial begin
        #0.02;
        for(s=0;s<2;s=s+1)for(first=0;first<2;first=first+1)begin
            arm=0;reference=0;feedback=0;swap=s;#0.02;
            if(ha!==0 || hb!==0 || qa!==1 || qb!==1)$fatal(1,"Tag arbiter clear failed");
            arm=1;#0.02;
            if(first==0)reference=1;else feedback=1;
            #0.02;
            if(first==0)reference=0;else feedback=0;
            // The first pulse ends before the second arrives. Its event must
            // remain latched through readout: no simultaneous-high requirement.
            #0.05;
            if(first==0)feedback=1;else reference=1;
            #0.02;reference=0;feedback=0;#0.05;
            if(ha!==1 || hb!==1)$fatal(1,"Lost isolated event");
            if(first==0 && (ref_q!==0 || fb_q!==1))$fatal(1,"Wrong reference-first race");
            if(first==1 && (ref_q!==1 || fb_q!==0))$fatal(1,"Wrong feedback-first race");
            #0.05;
            if(ha!==1 || hb!==1)$fatal(1,"Event not retained until clear");
        end
        arm=0;#0.02;
        if(ha!==0 || hb!==0)$fatal(1,"Final clear failed");
        $display("PASS v2 tag arbiter both orders/swaps, disjoint pulses, hold and clear");$finish;
    end
    initial begin #100;$fatal(1,"Tag arbiter watchdog");end
endmodule
