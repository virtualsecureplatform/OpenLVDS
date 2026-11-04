// SPDX-License-Identifier: GPL-3.0-only
`timescale 1ns/1ps
module tb_tag_launch_v2;
    reg mgmt=0,raw=0,reset_n=1,enable=1,present=1,request=0,period_mode=0;
    reg run_clock=1,check_width=1;
    real period=2.5,duty=0.5;
    always #20 mgmt=~mgmt;
    initial forever begin
        if(run_clock)begin
            #(period*(1-duty));raw=1;
            #(period*duty);raw=0;
        end else #0.05;
    end
    wire ready,busy,done,launch,comparison;
    openlvds_tag_launch_v2 dut(.mgmt_clk_25(mgmt),.raw_reference(raw),.reset_n(reset_n),
        .enable(enable),.clock_present(present),.request_valid(request),
        .request_next_period(period_mode),.request_ready(ready),.busy(busy),.done(done),
        .launch_pulse(launch),.reference_pulse(comparison));
    integer epochs=0,launches=0,references=0,launch_epoch=0,reference_epoch=0,done_count=0;
    realtime raw_rise=0,launch_rise=0,reference_rise=0;
    always @(posedge raw)begin epochs=epochs+1;raw_rise=$realtime;end
    always @(posedge launch)begin
        if(raw!==1 || $realtime!=raw_rise)$fatal(1,"Launch did not follow a raw rising edge");
        launches=launches+1;launch_epoch=epochs;launch_rise=$realtime;
    end
    always @(posedge comparison)begin
        if(raw!==1 || $realtime!=raw_rise)$fatal(1,"Comparison did not follow a raw rising edge");
        references=references+1;reference_epoch=epochs;reference_rise=$realtime;
    end
    always @(negedge launch)if(check_width && launches>0 && reset_n && enable && present)
        if($realtime-launch_rise<period*duty-0.002)$fatal(1,"Truncated launch");
    always @(negedge comparison)if(check_width && references>0 && reset_n && enable && present)
        if($realtime-reference_rise<period*duty-0.002)$fatal(1,"Truncated reference");
    always @(posedge mgmt)if(done)done_count=done_count+1;
    task trial;
        input mode;
        input real offset;
        integer before_launch,before_reference,before_done;
        begin
            wait(ready);@(negedge mgmt);#(offset);
            before_launch=launches;before_reference=references;before_done=done_count;
            request=1;period_mode=mode;
            @(posedge mgmt);#0.001;
            if(!busy || ready)$fatal(1,"Missing outstanding-request backpressure");
            // Change the source bus after acceptance: only held command counts.
            request=0;period_mode=~mode;
            while(!done)begin @(negedge mgmt);if(!done && ready)$fatal(1,"Early request readiness");end
            if(launches!=before_launch+1 || references!=before_reference+1)
                $fatal(1,"Missing/repeated isolated tag %d %d",launches-before_launch,references-before_reference);
            if(reference_epoch-launch_epoch!=(mode ? 1 : 0))
                $fatal(1,"Wrong unwrapped reference epoch %d",reference_epoch-launch_epoch);
            @(posedge mgmt);#0.001;
            if(busy || done_count!=before_done+1)$fatal(1,"Missing completion consumption");
            repeat(5)@(posedge raw);
            if(launches!=before_launch+1 || references!=before_reference+1)$fatal(1,"Tag repeated after completion");
        end
    endtask
    integer f,d,o,m;
    initial begin
        #0.001;reset_n=0;#10;reset_n=1;#100;
        for(f=0;f<3;f=f+1)for(d=0;d<3;d=d+1)begin
            @(negedge raw);period=1000.0/(390.0+10*f);duty=0.3+0.2*d;
            for(o=0;o<3;o=o+1)for(m=0;m<2;m=m+1)trial(m!=0,0.17+o*3.11);
        end
        // Cancel an accepted command before it crosses to the launch domain.
        wait(ready);@(negedge mgmt);request=1;
        @(posedge mgmt);#0.001;request=0;enable=0;
        #0.001;if(busy || launch || comparison || done)$fatal(1,"Disable did not invalidate tag");
        #7.13;enable=1;repeat(5)@(posedge mgmt);
        if(launch || comparison || done || busy)$fatal(1,"Canceled command survived reset");
        trial(1,1.37);
        // A stopped raw clock must not retain a stale management transaction.
        @(negedge raw);run_clock=0;present=0;
        #0.001;if(busy || launch || comparison || done)$fatal(1,"Clock loss invalidation failed");
        repeat(3)@(posedge mgmt);present=1;run_clock=1;
        trial(0,0.37);
        $display("PASS v2 isolated tag launch, next-epoch comparison, CDC backpressure and cancellation");$finish;
    end
    initial begin #200000;$fatal(1,"Tag launch watchdog state=%d ready=%b busy=%b done=%b launch=%d reference=%d f=%d d=%d o=%d m=%d",dut.state,ready,busy,done,launches,references,f,d,o,m);end
endmodule
