"""Benchmark adapter; certificate generation never sees production J_hat."""
from dataclasses import asdict
from ...optional.certified import certify, assess, _down, _up
from mpmath.ctx_iv import MPIntervalContext


def compare(source_set, q, epsilon2, j_hat, *, tol=.1, **budgets):
    certificate = certify(source_set, q, epsilon2, tol=tol, **budgets)
    iv = MPIntervalContext()
    iv.dps = certificate.dps
    return dict(**asdict(certificate), verdict=assess(j_hat, certificate, tol),
                J_hat=j_hat, comparison_tol_m=tol,
                acceptance_band_m=[_down(iv.mpf(certificate.lower_m)-iv.mpf(tol)),
                                   _up(iv.mpf(certificate.upper_m)+iv.mpf(tol))])
