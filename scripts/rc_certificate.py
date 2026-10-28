# SPDX-License-Identifier: GPL-3.0-only
"""Shared fail-closed qualification contract for approximate RC consumers."""
import hashlib
from pathlib import Path
from spice_engine import engine,provenance
import rc_trace

REQUIRED={'driver','receiver','dll','delay','tx','rx'}
MODEL_SCOPES=dict(driver={'openlvds_driver_core','lvds_bias'},receiver={'openlvds_receiver_core','lvds_bias'},
    dll={'openlvds_dll_analog','lvds_bias','lvds_pfd'},delay={'openlvds_delay_line'},
    tx={'openlvds_tx_core'},rx={'openlvds_ddr_rx'})
TOPS=dict(driver='openlvds_driver',receiver='openlvds_receiver',dll='openlvds_dll',
    delay='openlvds_delay_line',tx='openlvds_tx_core',rx='openlvds_ddr_rx')
ROOT=Path(__file__).resolve().parents[1]

def traces_current(certificate):
    try:
        for kind,case in certificate['cases'].items():
            for key,inputs_key in [('reference','reference_inputs'),('approximation','fast_inputs')]:
                reference=case[key];folder=(ROOT/reference['artifact']).resolve()
                if not folder.is_relative_to((ROOT/'build/rc_validation').resolve()):return False
                evidence=rc_trace.verified(folder,engine(),provenance(),certificate['requirements_sha256'],
                    reference['trace_evidence_sha256'])
                if not evidence or evidence['top']!=TOPS[kind] or set(evidence['inputs'])!=MODEL_SCOPES[kind]:return False
                if evidence['scope_sha256']!=reference['scope_sha256']:return False
                if any(certificate[inputs_key].get(name)!=value for name,value in evidence['inputs'].items()):return False
        return True
    except (OSError,ValueError,KeyError,TypeError):return False

def valid(certificate,inputs,subset=False):
    cases=certificate.get('cases',{})
    runner=Path(__file__).with_name('validate_fast.py')
    if not (certificate.get('passed') and certificate.get('complete_suite') and
            set(cases)==REQUIRED and all(v.get('passed') for v in cases.values()) and
            certificate.get('runner_sha256')==hashlib.sha256(runner.read_bytes()).hexdigest() and
            certificate.get('simulator')==engine() and certificate.get('simulator_provenance')==provenance() and
            certificate.get('requirements_sha256')==hashlib.sha256((ROOT/'requirements.json').read_bytes()).hexdigest() and
            certificate.get('trace_policy_sha256')==hashlib.sha256(Path(rc_trace.__file__).read_bytes()).hexdigest() and
            traces_current(certificate)):return False
    expected=certificate.get('fast_inputs',{})
    return all(expected.get(k)==v for k,v in inputs.items()) if subset else expected==inputs
