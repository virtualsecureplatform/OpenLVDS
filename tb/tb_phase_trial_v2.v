// SPDX-License-Identifier: GPL-3.0-only
`timescale 1ns/1ps
// Synthetic event paths exercise only the measurement protocol. Delays and
// the behavioral winner latch are not native timing or detector admission.
module tb_phase_trial_v2;
    parameter ADMITTED=1;
    reg mgmt=0,raw=0,reset_n=1,enable=1,present=1,frontend=1;
    reg request=0,mode=0,swap=0,result_ready=0;
    reg [1:0] section_a=0,section_b=1;
    reg [15:0] sequence_id=0;
    always #20 mgmt=~mgmt;
    reg run_clock=1;
    always #1.25 if(run_clock)raw=~raw;
    wire ready,busy,route_mode,route_swap,arm,launch,reference,result_valid,epoch_ok,detector_ok,reference_first,feedback_first;
    wire [1:0] route_a,route_b;
    wire [15:0] result_sequence;
    wire [3:0] failure;
    reg a_base=0,b_base=0,extra=0,qa=1,qb=1;
    reg drop_b=0,duplicate_b=0,ambiguous=0,stuck_b=0;
    real delay_a=0.8,delay_b=1.0,loop_delay=2.4;
    wire observed_a=a_base,observed_b=b_base|extra;
    openlvds_phase_trial_v2 #(.MODEL_ADMITTED(ADMITTED),.TIMEOUT_CYCLES(80)) dut (
        .mgmt_clk_25(mgmt),.raw_reference(raw),.reset_n(reset_n),.enable(enable),
        .clock_present(present),.frontend_ready(frontend),.request_valid(request),
        .request_next_period(mode),.request_swap(swap),.request_section_a(section_a),
        .request_section_b(section_b),.request_sequence(sequence_id),.request_ready(ready),.busy(busy),
        .route_next_period(route_mode),.route_swap(route_swap),.route_section_a(route_a),.route_section_b(route_b),
        .arm(arm),.launch_pulse(launch),.reference_pulse(reference),
        .observed_a(observed_a),.observed_b(observed_b),.qa(qa),.qb(qb),
        .result_valid(result_valid),.result_ready(result_ready),.result_sequence(result_sequence),
        .result_epoch_valid(epoch_ok),.result_detector_valid(detector_ok),
        .result_reference_first(reference_first),.result_feedback_first(feedback_first),.failure_code(failure)
    );
    // A period comparison observes the *next-epoch* reference pulse. Separated
    // comparisons instead see two independently delayed copies of launch.
    always @(launch)begin
        if(!route_mode)a_base<=#(delay_a)launch;
        if(!drop_b)begin
            if(launch || !stuck_b)b_base<=#(route_mode ? loop_delay+0.8 : delay_b)launch;
        end
    end
    always @(reference)if(route_mode)a_base<=#0.8 reference;
    always @(posedge launch)if(duplicate_b)begin #5;extra=1;#0.25;extra=0;end
    always @(negedge arm)begin qa=1;qb=1;end
    always @(posedge observed_a)if(arm && !ambiguous && qa && qb)begin
        qa=route_swap ? 1 : 0;qb=route_swap ? 0 : 1;
    end
    always @(posedge observed_b)if(arm && !ambiguous && qa && qb)begin
        qa=route_swap ? 0 : 1;qb=route_swap ? 1 : 0;
    end
    integer launches=0;
    always @(posedge launch)begin
        launches=launches+1;
        if(!arm)$fatal(1,"Tag launched before detector armed");
    end
    task start_trial;
        input next_mode,next_swap;
        begin
            wait(ready);@(negedge mgmt);mode=next_mode;swap=next_swap;
            sequence_id=sequence_id+1;request=1;
            @(posedge mgmt);#0.001;request=0;
            // Mutating the request bundle cannot change the in-flight route.
            mode=~next_mode;swap=~next_swap;section_a=2;section_b=3;
            if(ready || !busy)$fatal(1,"Trial accepted without backpressure");
        end
    endtask
    task read_result;
        input integer reason;
        input expected_reference_first;
        reg [15:0] saved_sequence;
        begin
            wait(result_valid);#0.001;
            if(result_sequence!=sequence_id || failure!=reason)$fatal(1,"Wrong tagged trial result seq=%d reason=%d",result_sequence,failure);
            if(reason==0)begin
                if(!epoch_ok || !detector_ok || reference_first!=expected_reference_first || feedback_first==expected_reference_first)
                    $fatal(1,"Wrong resolved event order or epoch");
            end else if(detector_ok || epoch_ok || reference_first || feedback_first)$fatal(1,"Fault admitted a measurement");
            saved_sequence=result_sequence;
            repeat(3)begin @(negedge mgmt);
                if(!result_valid || ready || result_sequence!=saved_sequence)$fatal(1,"Result changed under backpressure");
            end
            result_ready=1;@(posedge mgmt);#0.001;result_ready=0;
            if(result_valid || busy || arm)$fatal(1,"Consumed result did not clear trial");
            repeat(3)@(posedge mgmt);
        end
    endtask
    integer s,m,before_launch;
    initial begin
        #0.001;reset_n=0;#10;reset_n=1;#100;
        if(!ADMITTED)begin
            start_trial(0,0);read_result(8,0);
            if(launches!=0)$fatal(1,"Unadmitted model launched a pulse");
            $display("PASS v2 unadmitted phase trial remains closed");$finish;
        end
        for(s=0;s<2;s=s+1)begin
            section_a=0;section_b=1;delay_a=0.8;delay_b=1.0;
            start_trial(0,s!=0);read_result(0,1);
            delay_a=1.0;delay_b=0.8;
            start_trial(0,s!=0);read_result(0,0);
            loop_delay=2.4;start_trial(1,s!=0);read_result(0,0);
            loop_delay=2.6;start_trial(1,s!=0);read_result(0,1);
            // An extra whole-period delay must remain LONG, never modulo lock.
            loop_delay=5.1;start_trial(1,s!=0);read_result(0,1);
        end
        duplicate_b=1;start_trial(1,0);read_result(4,0);duplicate_b=0;
        drop_b=1;start_trial(0,0);read_result(4,0);drop_b=0;
        ambiguous=1;start_trial(0,0);read_result(5,0);ambiguous=0;
        stuck_b=1;start_trial(0,0);read_result(4,0);stuck_b=0;b_base=0;
        frontend=0;before_launch=launches;start_trial(0,0);read_result(8,0);
        if(launches!=before_launch)$fatal(1,"Unready frontend launched a trial");frontend=1;
        start_trial(0,0);wait(arm);frontend=0;read_result(8,0);frontend=1;
        start_trial(0,0);wait(result_valid);frontend=0;
        repeat(2)@(posedge mgmt);read_result(8,0);frontend=1;
        // A missing raw clock with a stale presence flag cannot leave a trial
        // pending forever or emit the old command when clocks resume.
        @(negedge raw);run_clock=0;before_launch=launches;
        start_trial(1,0);read_result(2,0);
        if(launches!=before_launch)$fatal(1,"Stopped clock emitted a tag");
        run_clock=1;
        start_trial(1,0);wait(arm);present=0;#0.001;
        if(busy || result_valid || arm || launch || reference)$fatal(1,"Clock loss did not cancel trial");
        repeat(4)@(posedge mgmt);present=1;
        loop_delay=2.6;start_trial(1,1);read_result(0,1);
        $display("PASS v2 phase trial exact events, unwrapped period, swaps, tagged CDC, faults and result backpressure");$finish;
    end
    initial begin #100000;$fatal(1,"Phase trial watchdog state=%d",dut.state);end
endmodule
