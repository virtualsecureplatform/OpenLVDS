# SPDX-License-Identifier: GPL-3.0-only
"""Normalize only analysis views for the strict native parameter inventory."""
import measured_bank_junction_reconstruction_v142 as correction
import measured_bank_native_inventory_v138 as inventory


def verify(reference,reference_top,extracted,extracted_top,profile):
    return inventory.verify(correction.collapse(reference),reference_top,
                            correction.collapse(extracted),extracted_top,profile)
