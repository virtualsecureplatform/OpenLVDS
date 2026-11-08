#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Full two-bank metrics with an independently checked known PWL input."""
import bank_entry_waveform_300_v1 as reference
import two_bank_native_measure_300_v1 as original
import two_bank_independent_measure_300_v1 as independent
from native_binary_raw_v2 import validate

VERSION='two-bank-known-entry-reference-metrology-300-v1'


def measure(folder,observations,s,*,next_coarse,next_fine,independent_reader=False):
    reader=independent if independent_reader else original
    result=reader.measure(folder,observations,s,next_coarse=next_coarse,next_fine=next_fine)
    names,w=validate(folder/'bench.raw',{'v(in)'},40e-9)
    return reference.apply_reference(result,w[:,names.index('time')]*1e12,w[:,names.index('v(in)')],s,
                                     independent=independent_reader)
