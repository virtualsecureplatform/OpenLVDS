# OTA slow-corner acquisition failure

The completed `ota_w4_c8_loop_ss_0` architecture screen fails the original
1200–1500 ns scoring window. Simulation completes normally, clock cadence
passes, and the quarter-cycle delay stays inside 625 ± 100 ps. Feedback error
reaches 128.34 ps against 100 ps, and CTRL spans 87.89 mV against 20 mV.
This is the hybrid architecture bench: schematic controller plus captured
extracted PFD and delay line. It is not the new full-RC physical candidate.

## Measured cause

The waveform shows continued acquisition rather than a large oscillation:

| Interval (ns) | CTRL start/end (V) | CTRL slope (mV/ns) | Maximum feedback error (ps) |
| --- | --- | --- | --- |
| 1200–1300 | 1.3070 / 1.2757 | −0.315 | 128.34 |
| 1300–1400 | 1.2756 / 1.2465 | −0.291 | 121.40 |
| 1400–1500 | 1.2465 / 1.2200 | −0.266 | 114.08 |

The final 10 ns still have approximately 106.8 ps feedback error. After a
linear trend is removed separately from each 100 ns window, CTRL variation is
approximately 1.9 mV peak-to-peak. The scorer's `control_ripple_pp_mv` field
includes drift; the original 87.89 mV value is correct as total variation but
does not establish an 88 mV oscillation. CTRL remains away from the rails and
continues moving in the direction that improves the phase error. This trace
does not establish eventual convergence or phase margin.

The immediate mechanism is limited correction current into the 8 pF nominal
integrator during a long control-voltage excursion. In the scoring window,
UF−DF averages −55 to −46 mV. The standalone SS/0 °C OTA characterization
measures approximately 44 µS transconductance around this operating range.
That input produces correction current on the order of a few microamps.
Using the nominal capacitor alone, the measured slope corresponds to about
2.1–2.5 µA. This is a consistency estimate: parasitic capacitance, signal
nonlinearity and output conductance are not included in that simple equation.

The slow corner starts closer in phase at the 1.8 V precharge setting, but still
needs substantial CTRL movement. Its smaller sustained detector error gives
weaker OTA drive. TT/FF begin with larger errors and larger correction drive;
they reach the steep part of the delay-control characteristic and settle by
the scoring window. The SS trace's improving error versus CTRL also indicates
relatively low delay sensitivity along the early part of its trajectory.
This explanation is inferred from the measured trajectories, not from a
complete loop-gain extraction. A collapsed OTA gm is not supported by the
standalone characterization.

## Comparisons and remaining checks

The same-corner repaired CP passes: 20.15 ps feedback error, 21.81 mV control-copy
error and 6.43 mV CTRL variation. Its control is already near its final value
by approximately 300 ns. This demonstrates a workable operating point in that
screening delay line; it does not qualify the CP across the full matrix.

The ongoing alternatives also show faster acquisition at a common 450–500 ns
window. Their mean CTRL values are 1.5931 V for W4/C8, 1.4655 V for W4/C4,
and 1.5404 V for W8/C8, all at SS/0 °C. These partial comparisons support
reducing the capacitor or increasing OTA input width. They do not establish
passing settled results. The existing W4/C4 and W8/C8 runs should finish before
selecting the repair. A later extended-duration W4/C8 diagnostic could test
eventual convergence, while preserving its failure of the original 1500 ns
test and the original limits.

The earlier OTA component offset failures are a separate issue. At SS/0 °C,
common mode 0.6 V, equivalent input offset grows from 8.08 mV at CTRL 1.1 V
to 11.68 mV at 1.3 V and 13.63 mV at 1.4 V. Its dependence on output voltage
is consistent with finite output resistance and unequal drain voltages in the
current mirrors. This is a systematic-model effect, not measured mismatch.
The offset must be included in the final phase-error budget; it is not by
itself evidence of the slow acquisition mechanism or of instability.

A low BAD signal during the scoring window is compatible with the failure:
the monitor must assert for offsets of at least 150 ps, whereas the loop's
feedback-error requirement is tighter at 100 ps.

Raw input and recomputed interval measurements are retained in
`build/diagnostics/dll_failure_analysis/results.json`, with waveform hashes.
The analysis producer is `build/diagnostics/dll_failure_analysis/analyze.py`.
No circuit, simulator, pass threshold or queued producer was changed.


## Native W8/C4 monitor timing, 2026-10-31

The exact physical candidate `0f0c41cbc75c` passes SS/0 °C 0/+50 ps but misses
both ±150 ps faults through 160 ns. The ±300 ps cases eventually assert BAD,
but fail the unchanged requirement for valid fault coverage across the
120–160 ns window. Reanalysis of their completed waveforms finds:

| Offset | BAD falls after startup | BAD next rises | Filtered UF−DF mean, 120–160 ns |
| --- | --- | --- | --- |
| +150 ps | 80.552 ns | none through 160 ns | +89.34 mV |
| −150 ps | 80.190 ns | none through 160 ns | −91.80 mV |
| +300 ps | 79.421 ns | 147.595 ns | +160.83 mV |
| −300 ps | 79.019 ns | 137.510 ns | −158.93 mV |

TT/25 °C +150 ps also stays quiet after 89.361 ns despite a 90.71 mV filtered
difference. The startup high is not evidence of sustained fault detection.
`monitor_fault_timing_diagnosis.json` under qualification `d4d687cf4e0b5e1e`
binds these crossing measurements to the completed waveform and report hashes.

These failures justify measuring the divider and comparator nodes rather than
changing the fault window. A loaded/unloaded schematic control and a stronger
monitor are being compared with captured coupling capacitances. The repair's
new GDS passes DRC/LVS/extraction/audit, but its electrical response has not yet
been established. The old coordinator is draining submitted work without new
dispatch; the RX characterization remains intact.


The loaded-baseline SS/0 °C +150 ps control now reproduces the missed fault:
BAD stays below 4.5 µV in 120–160 ns while UF−DF averages 89.51 mV. Its
comparator O rises from about 0.55 V at 120 ns to 0.69 V at 160 ns without
asserting POS. This makes captured capacitance a demonstrated contributor;
it does not exclude further native resistance or junction effects.

With monitor resistor lengths divided by four, averaging capacitance multiplied
by four and comparator branch widths multiplied by four, the same loaded
+150 ps test passes. BAD reasserts at 88.271 ns and stays near 1.8 V throughout
the original scoring window. Comparator O averages 1.127 V instead of 0.643 V.
The repaired filtered difference is 85.86 mV. This is one proxy condition,
not native signoff: quiet ±50 ps, both fault polarities, the remaining corners,
source-specific loop screening and fresh extracted qualification remain required.


The matched unloaded +150 ps control passes, with BAD rising at 28.794 ns and
comparator O averaging 1.505 V. Its loaded counterpart has a similar filtered
error (89.51 versus 90.03 mV) but O averages 0.643 V and BAD never reasserts.
The repaired loaded case restores a passing response at 88.271 ns. These controls
hold the PFD/bias and analog device definitions constant while adding the captured
capacitance, establishing a causal loading effect within the proxy.

The +300 ps loaded control instead passes its reference-cycle scoring, with BAD
rising at 121.023 ns, versus 22.119 ns unloaded. The original native result remains
a failure at 147.595 ns. The missing distributed resistance and extracted device
junction geometry remain candidates for the remaining timing difference; they
have not been isolated. The negative-control expectation is preserved as a
mismatch. Full native qualification remains necessary.


## Repaired physical monitor: native failure

Qualification `0cc06862af2fae63`, case `phase_ss_0_150ps`, completes normally
but fails electrically. BAD falls at 52.100 ns and never reasserts through
160 ns; its maximum during 120–160 ns is 7.655 µV. Filtered UF−DF averages
85.287 mV versus 85.863 mV for the passing repaired loaded proxy. The full-RC
waveform SHA-256 is
`81089b51decf8029d1a0ff80fada0243db8840a4a3b1a775ebf563d748f9d232`.

The repair therefore has not solved the physical failure. Its positive comparator
output has 396.3 fF incident extracted external capacitance, compared with
222.7 fF in the proxy's old layout. Native junction geometry and distributed
resistance are also absent from that proxy. These remain possible explanations,
not isolated causes.

The next diagnostic probes every actual PA/PB and comparator O/OB/L/T terminal,
the positive tail's PC gate and local VDDD contacts. A separate native DC
diagnostic adds three test ports to clamp UF/DF/CTRL to the measured fault-case
means without replacing any extracted device or R/C. A high DC BAD with a
failed transient would support a settling problem; a low DC BAD requires
examining comparator input difference, gain, bias and readout headroom first.
Neither result changes the original phase test or releases the candidate.


The clamped native DC diagnostic `monitor_native/0fcf74f7d7868e78/dc` completes
with BAD = 1.800000 V and POS = 1.799995 V. PA/PB are 0.381484/0.372850 V
(8.634 mV difference), comparator O = 1.456808 V, L = 0.711481 V, and
T = 1.562139 V. The local positive-tail VDDD terminals span
1.799555–1.800000 V and PC = 0.612602 V. This shows that the native comparator
can detect the measured positive fault at equilibrium. It supports a dynamic
settling explanation; it does not prove which capacitance or resistance dominates,
or establish the response with pulsed inputs. The waveform and native library
hashes are retained in that diagnostic's manifest and summary.

A source-identical local comparator layout passes DRC/LVS. Keeping O/OB/L/T
inside small comparator islands avoids their long drops through the passive
bank. Its extracted capacitance and native response must improve before this
physical change is selected. The failed 160 ns trace remains unchanged.


The first local layout reduces O/OB/L/T incident external capacitances to
93.272/41.225/94.846/143.083 fF, from 396.255/199.656/339.985/570.225 fF.
Its long child-port escapes instead increase PA/PB and activity-reference
loading. `monitor_capacitance_comparison.json` under layout `0a4253d72e392de9`
records both netlist/GDS hashes and the node sums. A fresh local-port variant
passes DRC/LVS and is being extracted before native selection. No transient
improvement has yet been demonstrated by either layout.


## Source-specific acquisition failure

The new source-specific SS/0 °C screen completes 1500 ns but settles at the
high CTRL rail instead of lock: CTRL = 1.783719 V, feedback error = 845.001 ps,
quarter delay about 223.6 ps, UF−DF = +159.381 mV, and BAD high. At 90–120 ns
CTRL already averages 1.782274 V and stays near that value. This is not merely
a late monitor assertion or a small CTRL-ripple failure.

At 1200 ns, PH0 rises at 1200.087699 ns, PH180 at 1200.521840 ns and PD_REF
at 1201.366732 ns. Thus the PFD feedback edge precedes its reference by about
845 ps, while raw UP/DN means across 1200–1500 ns are 0.886011/0.690257 V.
The positive area imbalance drives the OTA toward higher CTRL, rather than
correcting this leading-feedback condition. This makes wide-range detector
capture/reset timing a priority for diagnosis; a reduced precharge voltage is
another experiment, not an established fix. Matched ±850 ps input controls and
a reset coincidence taken before the UP/DN output buffers can test that hypothesis.

The old passing W8/C4 screen is not a matched control: it retains an extracted
standalone delay line and the preceding captured PFD, while the new screen uses
fully native-finger schematic analog/delay devices and the 8-port PFD. Common
non-monitor analog device rows are unchanged, but the delay implementation and
PFD view differ. Do not attribute the new failure solely to monitor scaling or
reuse the old success as qualification of the repaired source. The completed
new summary binds waveform
`dbb036ab1be26613944e759c5e7aa7a1918f96d0b6b73ddc5d77eb9653bc0874`
and raw trace
`045ef5b90e21ca5fe7b2aae9bb88e88c8c96d106f8407d7ab2fa8e52a26025ca`.
