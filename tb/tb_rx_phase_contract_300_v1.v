// SPDX-License-Identifier: GPL-3.0-only
`timescale 1ns/1ps
// Stimulus audit only. The child is the exact protocol bench; stop after its
// initial source-clock epochs, before training begins. No electrical claim.
module tb_rx_phase_contract_300_v1;
    parameter MHZ=300,DUTY_PERCENT=50;
    parameter MODEL_MHZ=MHZ,MODEL_DUTY_PERCENT=DUTY_PERCENT,BAD_COMPLEMENT=0;
    localparam real PERIOD=1000.0/MHZ,HIGH=PERIOD*DUTY_PERCENT/100.0;
    tb_rx_training_300_v1 #(.MHZ(MODEL_MHZ),.DUTY_PERCENT(MODEL_DUTY_PERCENT),.MODE(0)) stimulus();
    wire phase180=BAD_COMPLEMENT ? !stimulus.raw : stimulus.raw180;
    real last_rise[0:3],period_seen[0:3],phase_seen[0:3],high_seen[0:3];
    integer rises[0:3];integer k,minimum;
    function real magnitude;input real value;begin magnitude=value<0 ? -value:value;end endfunction
    initial for(k=0;k<4;k=k+1)begin
        last_rise[k]=0;period_seen[k]=0;phase_seen[k]=0;high_seen[k]=0;rises[k]=0;
    end
    task on_rise;
        input integer n;real at;
        begin
            at=$realtime;
            if(n==0 || last_rise[0]>0)begin
                if(rises[n]>0 && rises[n]<33 && magnitude(at-last_rise[n]-PERIOD)>.003)
                    $fatal(1,"CLOCK CONTRACT period phase=%0d actual=%g expected=%g",n,at-last_rise[n],PERIOD);
                if(n>0 && rises[n]<33 && magnitude(at-last_rise[0]-n*PERIOD/4)>.003)
                    $fatal(1,"CLOCK CONTRACT phase phase=%0d actual=%g expected=%g",n,at-last_rise[0],n*PERIOD/4);
                if(rises[n]>0)period_seen[n]=at-last_rise[n];
                if(n>0)phase_seen[n]=at-last_rise[0];
                last_rise[n]=at;rises[n]=rises[n]+1;
            end
        end
    endtask
    task on_fall;
        input integer n;real at;
        begin
            at=$realtime;
            if(rises[n]>0 && rises[n]<=32)begin
                high_seen[n]=at-last_rise[n];
                if(magnitude(high_seen[n]-HIGH)>.003)
                    $fatal(1,"CLOCK CONTRACT duty phase=%0d actual=%g expected=%g",n,high_seen[n],HIGH);
            end
            if(n==0 && rises[0]==32)begin
                minimum=rises[0];for(k=1;k<4;k=k+1)if(rises[k]<minimum)minimum=rises[k];
                if(minimum<31)$fatal(1,"CLOCK CONTRACT missing source phase");
                $display("PASS 300 RX phase contract mhz=%0d duty_percent=%0d root_cycles=32 min_phase_rises=%0d period_ns=%0.6f high_ns=%0.6f phase90_ns=%0.6f phase180_ns=%0.6f phase270_ns=%0.6f",MHZ,DUTY_PERCENT,minimum,period_seen[0],high_seen[0],phase_seen[1],phase_seen[2],phase_seen[3]);
                $finish;
            end
        end
    endtask
    always @(posedge stimulus.raw)on_rise(0);
    always @(posedge stimulus.raw90)on_rise(1);
    always @(posedge phase180)on_rise(2);
    always @(posedge stimulus.raw270)on_rise(3);
    always @(negedge stimulus.raw)on_fall(0);
    always @(negedge stimulus.raw90)on_fall(1);
    always @(negedge phase180)on_fall(2);
    always @(negedge stimulus.raw270)on_fall(3);
    initial begin #1000;$fatal(1,"CLOCK CONTRACT watchdog");end
endmodule
