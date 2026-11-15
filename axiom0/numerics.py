"""Axiom0 Number System reference implementation v0.1.0."""
from __future__ import annotations
import math
from typing import Iterable, Sequence

SPEC_VERSION = "0.1.0"
GENESIS = (1, 2, 8, 7, 5)
SOUL = (5, 12, 5, 12, 5)
CANONICAL_UNSIGNED = frozenset(range(10)) | {12}
CANONICAL_SIGNED = frozenset({0, 12, -12, *range(1, 10), *range(-9, 0)})

class Axiom0Error(ValueError):
    pass

class InvalidScalarError(Axiom0Error):
    pass

class InvalidVectorError(Axiom0Error):
    pass

class NonIntegralDivisionError(Axiom0Error):
    pass

def _require_int(n: int) -> int:
    if isinstance(n, bool) or not isinstance(n, int):
        raise InvalidScalarError("Axiom0 scalar inputs must be integers")
    return n

def _digit_sum(n: int) -> int:
    return sum(int(ch) for ch in str(n))

def reduce(n: int) -> int:
    """Protected reduction rho."""
    n = _require_int(n)
    if n == 0:
        return 0
    sign = -1 if n < 0 else 1
    m = abs(n)
    if m == 12:
        return sign * 12
    while True:
        m = _digit_sum(m)
        if m == 12:
            return sign * 12
        if m <= 9:
            return sign * m

def add(a: int, b: int) -> int:
    return reduce(_require_int(a) + _require_int(b))

def sub(a: int, b: int) -> int:
    return reduce(_require_int(a) - _require_int(b))

def mul(a: int, b: int) -> int:
    return reduce(_require_int(a) * _require_int(b))

def div(a: int, b: int) -> int:
    a, b = _require_int(a), _require_int(b)
    if b == 0 or a % b != 0:
        raise NonIntegralDivisionError("Protected division requires a nonzero exact integer divisor")
    return reduce(a // b)

def normalize(v: Sequence[int]) -> tuple[int, int, int, int, int]:
    if not isinstance(v, Sequence) or isinstance(v, (str, bytes)) or len(v) != 5:
        raise InvalidVectorError("Axiom0 states must contain exactly five integers")
    return tuple(reduce(x) for x in v)  # type: ignore[return-value]

def upgrade_5_12_scalar(x: int) -> int:
    x = _require_int(x)
    if x not in CANONICAL_SIGNED:
        raise InvalidScalarError("5→12 upgrade accepts canonical symbols only; reduce first")
    return 12 if x == 5 else x

def upgrade_5_12(v: Sequence[int]) -> tuple[int, int, int, int, int]:
    nv = normalize(v)
    return tuple(upgrade_5_12_scalar(x) for x in nv)  # type: ignore[return-value]

def scalar_resonance(a: int, b: int) -> float:
    a, b = _require_int(a), _require_int(b)
    if a not in CANONICAL_SIGNED or b not in CANONICAL_SIGNED:
        raise InvalidScalarError("Resonance requires canonical symbols")
    return max(0.0, 1.0 - abs(a - b) / 24.0)

def resonance(a: Sequence[int], b: Sequence[int]) -> float:
    aa, bb = normalize(a), normalize(b)
    return sum(scalar_resonance(x, y) for x, y in zip(aa, bb)) / 5.0

def harmony(x: Sequence[int]) -> float:
    xx = normalize(x)
    return math.sqrt(resonance(xx, GENESIS) * resonance(xx, SOUL))

def annotate(n: int) -> str | None:
    labels = {
        1: "Unity", 2: "Duality", 3: "Creation", 5: "Transformation / Physical Manifestation",
        6: "Balance", 7: "Wisdom", 8: "Infinity", 9: "Completion", 12: "Cosmic Completion"
    }
    return labels.get(reduce(n))
