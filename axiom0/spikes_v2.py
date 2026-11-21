"""SPIKE-v2: area-level service-request spike detection with honest statistics.

What changed from SPIKE-v1 (mean + 2 x population stdev over 6 windows):

1. Count model. Request counts are counts, often more variable than a Poisson
   process. v2 measures each pair's own variability (sample variance of its
   baseline windows). If the counts vary more than their mean, it uses a negative
   binomial model fitted to that variance; otherwise Poisson. The output is a
   p-value: the chance of seeing at least this many requests if nothing changed.
2. Seasonality. When the data covers it, the expected count is the higher of
   the recent baseline and the same period last year (three windows around the
   one-year mark). A spike must be unusual against BOTH, so recurring seasonal
   peaks (e.g. winter sewer backups) are not reported as surprises.
3. Multiple testing. Checking many area/category pairs guarantees some chance
   "spikes". v2 applies the Benjamini-Hochberg procedure across every pair
   tested, so the expected share of false flags among reported flags is <= alpha.

Every flag carries the numbers needed to recompute it. Flags are statistical
signals for human investigation, never predictions about people, and are not
validated against ground truth.
"""
from __future__ import annotations
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, timedelta
import math
import statistics


@dataclass
class SpikeRuleV2:
    window_days: int = 30
    baseline_windows: int = 6
    seasonal: bool = True
    alpha: float = 0.05           # false discovery rate across all pairs tested
    min_count: int = 5
    name: str = 'SPIKE-v2'


@dataclass
class FlagV2:
    rule: str
    area: str
    category: str
    window_start: str
    window_end: str
    count: int
    expected: float
    baseline_counts: list
    baseline_mean: float
    baseline_variance: float
    seasonal_counts: list | None
    seasonal_mean: float | None
    distribution: str
    p_value: float
    q_value: float
    pairs_tested: int
    alpha: float
    meaning: str = field(default='Unusual against recent and seasonal baselines after multiple-testing '
                                 'correction; investigate, not a prediction or a finding')


def poisson_tail(k: int, mu: float) -> float:
    """P(X >= k) for X ~ Poisson(mu)."""
    if k <= 0:
        return 1.0
    logpmf = lambda i: -mu + i * math.log(mu) - math.lgamma(i + 1)
    return _tail(k, mu, logpmf)


def negbin_tail(k: int, mu: float, var: float) -> float:
    """P(X >= k) for a negative binomial with mean mu and variance var (> mu)."""
    if k <= 0:
        return 1.0
    r = mu * mu / (var - mu)
    p = r / (r + mu)
    logpmf = lambda i: (math.lgamma(i + r) - math.lgamma(r) - math.lgamma(i + 1)
                        + r * math.log(p) + i * math.log1p(-p))
    return _tail(k, mu, logpmf)


def _tail(k: int, mu: float, logpmf) -> float:
    if k <= mu:                                    # left of the mode: complement of the CDF is accurate
        return max(0.0, min(1.0, 1.0 - sum(math.exp(logpmf(i)) for i in range(k))))
    total, i = 0.0, k                              # right tail: sum directly (terms shrink)
    while True:
        term = math.exp(logpmf(i))
        total += term
        if term < 1e-17 * max(total, 1e-300) or i - k > 100_000:
            return min(1.0, total)
        i += 1


def benjamini_hochberg(pvalues: list[float]) -> list[float]:
    """Adjusted q-values, same order as input."""
    m = len(pvalues)
    order = sorted(range(m), key=lambda i: pvalues[i])
    q = [0.0] * m
    running = 1.0
    for rank in range(m, 0, -1):
        i = order[rank - 1]
        running = min(running, pvalues[i] * m / rank)
        q[i] = running
    return q


def spikes_v2(rows: list[tuple[date, str, str]], rule: SpikeRuleV2 = SpikeRuleV2(),
              as_of: date | None = None) -> tuple[list[FlagV2], dict]:
    """Return (flags, summary). Window 0 is (as_of - window, as_of]."""
    if not rows:
        return [], {'pairs_tested': 0, 'seasonal_used': False}
    as_of = as_of or max(d for d, _, _ in rows)
    earliest = min(d for d, _, _ in rows)
    wd = rule.window_days
    year_k = round(365 / wd)
    seasonal_idx = [year_k - 1, year_k, year_k + 1]
    # Seasonal windows are usable only if the data reaches back past the oldest of them.
    seasonal_ok = rule.seasonal and (as_of - earliest).days >= (max(seasonal_idx) + 1) * wd - 1
    max_idx = max(seasonal_idx) if seasonal_ok else rule.baseline_windows
    buckets: Counter = Counter()
    keys = set()
    for d, area, cat in rows:
        if d > as_of:
            continue
        i = (as_of - d).days // wd
        if i <= max_idx:
            buckets[(area, cat, i)] += 1
            keys.add((area, cat))

    tested = []
    for area, cat in sorted(keys):
        count = buckets[(area, cat, 0)]
        base = [buckets[(area, cat, i)] for i in range(1, rule.baseline_windows + 1)]
        n = len(base)
        mean = statistics.fmean(base)
        variance = statistics.variance(base) if n > 1 else mean
        # Half-count continuity floor: a pair with an all-zero history is not "infinitely" surprising.
        expected = max(mean, 0.5 / n)
        season = None
        season_mean = None
        if seasonal_ok:
            season = [buckets[(area, cat, i)] for i in seasonal_idx]
            season_mean = statistics.fmean(season)
            expected = max(expected, season_mean)
        if variance > expected * 1.05:
            dist = 'negative_binomial'
            p = negbin_tail(count, expected, max(variance, expected * 1.05))
        else:
            dist = 'poisson'
            p = poisson_tail(count, expected)
        tested.append((area, cat, count, expected, base, mean, variance, season, season_mean, dist, p))

    qvals = benjamini_hochberg([t[-1] for t in tested])
    flags = []
    for t, q in zip(tested, qvals):
        area, cat, count, expected, base, mean, variance, season, season_mean, dist, p = t
        if count >= rule.min_count and count > expected and q <= rule.alpha:
            flags.append(FlagV2(rule.name, area, cat, str(as_of - timedelta(days=wd - 1)), str(as_of),
                                count, round(expected, 3), base, round(mean, 3), round(variance, 3),
                                season, None if season_mean is None else round(season_mean, 3),
                                dist, float(f'{p:.6g}'), float(f'{q:.6g}'), len(tested), rule.alpha))
    flags.sort(key=lambda f: (f.q_value, -f.count))
    summary = {'rule': rule.name, 'as_of': str(as_of), 'pairs_tested': len(tested),
               'seasonal_used': seasonal_ok, 'alpha_fdr': rule.alpha, 'flags': len(flags)}
    return flags, summary
