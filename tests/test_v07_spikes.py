"""v0.7: SPIKE-v2 statistics — correct tails, fewer false alarms, seasonality, still finds real spikes."""
import math
import random
from datetime import date, timedelta

import pytest

from axiom0.legacy_v02.warning import SpikeRule, spikes
from axiom0.spikes_v2 import SpikeRuleV2, benjamini_hochberg, negbin_tail, poisson_tail, spikes_v2

AS_OF = date(2026, 11, 1)


def _rows(area, cat, counts_by_window, window=30):
    """counts_by_window[0] is the most recent window."""
    rows = []
    for i, c in enumerate(counts_by_window):
        end = AS_OF - timedelta(days=i * window)
        rows += [(end - timedelta(days=j % window), area, cat) for j in range(c)]
    return rows


def test_tail_probabilities_match_closed_forms():
    expected = 1 - math.exp(-2) * (1 + 2 + 2 + 4 / 3 + 2 / 3)          # P(X>=5), Poisson(2)
    assert poisson_tail(5, 2.0) == pytest.approx(expected, rel=1e-9)
    assert poisson_tail(0, 3.0) == 1.0
    assert poisson_tail(60, 3.0) < 1e-40                                   # far tail, no underflow crash
    # Negative binomial with var > mean is heavier-tailed than Poisson at the same mean.
    assert negbin_tail(15, 6.0, 20.0) > poisson_tail(15, 6.0)


def test_benjamini_hochberg_known_example():
    q = benjamini_hochberg([0.01, 0.04, 0.03, 0.005])
    assert q == pytest.approx([0.02, 0.04, 0.04, 0.02])


def test_clear_spike_on_stable_history_is_flagged():
    flags, summary = spikes_v2(_rows('Area A', 'pothole', [25, 5, 6, 4, 5, 6, 5]), SpikeRuleV2(seasonal=False), AS_OF)
    assert len(flags) == 1 and flags[0].count == 25 and flags[0].distribution == 'poisson'
    assert flags[0].p_value < 1e-6 and summary['pairs_tested'] == 1


def test_v1_overconfident_on_a_steady_looking_short_history():
    # Six windows that happen to look steady (sd ~1.3) make v1 treat 15 as a 4-sigma event.
    # Counts of ~10 naturally vary by about +/-3 (Poisson), so 15 has an ~8% chance: not a spike.
    rows = _rows('Area B', 'sewer backup', [15, 8, 10, 9, 11, 10, 12])
    v1 = spikes(rows, SpikeRule(), AS_OF)
    v2, _ = spikes_v2(rows, SpikeRuleV2(seasonal=False), AS_OF)
    assert len(v1) == 1
    assert v2 == []


def test_overdispersed_pair_uses_negative_binomial():
    rows = _rows('Area B', 'sewer backup', [30, 2, 14, 3, 15, 4, 12])
    flags, _ = spikes_v2(rows, SpikeRuleV2(seasonal=False, alpha=0.5), AS_OF)
    assert flags and flags[0].distribution == 'negative_binomial'
    assert flags[0].p_value > poisson_tail(30, flags[0].expected)   # wider tail = less alarmed


def test_many_quiet_pairs_v1_false_alarms_v2_controls_them():
    rng = random.Random(369)
    rows = []
    for k in range(150):                                  # 150 area/category pairs, nothing changes
        counts = [sum(rng.random() < 0.2 for _ in range(30)) for _ in range(7)]   # ~6 per window
        rows += _rows(f'Area {k}', 'streetlight out', counts)
    v1 = spikes(rows, SpikeRule(), AS_OF)
    v2, summary = spikes_v2(rows, SpikeRuleV2(seasonal=False), AS_OF)
    assert summary['pairs_tested'] == 150
    assert len(v1) >= 3                                   # chance "spikes" under v1
    assert len(v2) == 0                                   # FDR control removes them
    # ...but a genuine spike hidden among them is still found.
    rows += _rows('Area REAL', 'streetlight out', [30, 6, 5, 7, 6, 5, 6])
    v2, _ = spikes_v2(rows, SpikeRuleV2(seasonal=False), AS_OF)
    assert [f.area for f in v2] == ['Area REAL']


def test_seasonal_peak_is_not_a_surprise():
    # Every late autumn this pair jumps to ~20; the rest of the year ~5.
    history = [20] + [5] * 10 + [19, 21, 20] + [5]        # windows 0..14: 11-13 are last year's same period
    rows = _rows('Area C', 'sewer backup', history)
    flagged_without, _ = spikes_v2(rows, SpikeRuleV2(seasonal=False), AS_OF)
    flagged_with, summary = spikes_v2(rows, SpikeRuleV2(seasonal=True), AS_OF)
    assert summary['seasonal_used'] is True
    assert len(flagged_without) == 1 and flagged_with == []
    # A spike well beyond last year's peak is still reported.
    rows2 = _rows('Area C', 'sewer backup', [60] + history[1:])
    flags, _ = spikes_v2(rows2, SpikeRuleV2(seasonal=True), AS_OF)
    assert len(flags) == 1 and flags[0].seasonal_counts == [19, 21, 20]


def test_min_count_and_sample_data_run():
    flags, _ = spikes_v2(_rows('Area D', 'graffiti', [3, 0, 0, 0, 0, 0, 0]), SpikeRuleV2(), AS_OF)
    assert flags == []                                    # below min_count, however unusual
    from axiom0.legacy_v02.warning import load_requests
    rows = load_requests('examples/SIMULATED_service_requests.csv')
    flags, summary = spikes_v2(rows)
    assert summary['pairs_tested'] >= 9 and all(f.q_value <= 0.05 for f in flags)
