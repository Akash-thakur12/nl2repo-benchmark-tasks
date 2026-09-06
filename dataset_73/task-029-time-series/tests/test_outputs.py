import math
import random
import struct

import pytest
from engine.engine import TimeSeriesEngine


@pytest.fixture
def e():
    return TimeSeriesEngine()


def eq(a, b):
    return len(a) == len(b) and all(
        (math.isnan(x) and math.isnan(y)) or x == y for x, y in zip(a, b)
    )


def test_empty(e):
    assert e.compress([]) == struct.pack(">I", 0)
    assert e.decompress(e.compress([])) == []


def test_single_value(e):
    assert eq(e.decompress(e.compress([3.14159])), [3.14159])


def test_roundtrip_repeats_and_drift(e):
    vs = [1.0, 1.0, 1.0, 1.1, 1.1, 1.0, 1.0, 1.0, 1.0, 1.0]
    assert eq(e.decompress(e.compress(vs)), vs)


def test_constant_series_compresses_a_lot(e):
    vs = [42.0] * 50
    blob = e.compress(vs)
    assert len(blob) < len(vs) * 8
    assert len(blob) < 40                     # count header + 64 bits + ~50 zero bits


def test_slow_drift_beats_raw(e):
    vs = [100.0 + i * 0.01 for i in range(200)]
    blob = e.compress(vs)
    assert len(blob) < len(vs) * 8 * 0.85     # meaningfully smaller than raw
    assert eq(e.decompress(blob), vs)


def test_random_series_is_lossless(e):
    rng = random.Random(0)
    vs = [rng.random() * 1000 for _ in range(200)]
    assert eq(e.decompress(e.compress(vs)), vs)


def test_special_values_lossless(e):
    vs = [float("nan"), float("inf"), float("-inf"), -0.0, 0.0, 1e308, -1e-308]
    out = e.decompress(e.compress(vs))
    assert eq(out, vs)
    assert math.copysign(1.0, out[3]) == -1.0     # -0.0 preserved


def test_alternating_pattern(e):
    vs = [1.0, 2.0] * 30
    assert eq(e.decompress(e.compress(vs)), vs)


def test_negative_and_large_magnitudes(e):
    vs = [-12345.678, 12345.678, -0.000123, 9.87e20, -9.87e-20]
    assert eq(e.decompress(e.compress(vs)), vs)


@pytest.mark.parametrize("n", [2, 5, 20, 100, 500])
def test_matrix(e, n):
    vs = [1.0 + i * 0.0001 for i in range(n)]
    assert eq(e.decompress(e.compress(vs)), vs)


def test_reset_and_configure(e):
    vs = [1.0, 1.5, 1.5, 2.0]
    ref = e.compress(vs)
    e.reset()
    assert e.compress(vs) == ref
    e.configure({})
    assert e.compress(vs) == ref
