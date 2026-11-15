"""Early-Warning indicators: defined, testable, area-level only.

Input: a CSV of service requests with columns date (YYYY-MM-DD), area, category.
Extra columns are ignored. Columns that identify people are refused, because
AXIOM0 forecasts conditions and service risk, never individuals.

Indicator SPIKE (v1): for each (area, category), compare the count in the most
recent window to the counts in the previous `baseline_windows` windows of the
same length. Flag when
    count >= mean + z * stdev   and   count >= min_count
Every flag carries its numbers, so any reviewer can recompute it by hand.
"""

from __future__ import annotations

import csv
import statistics
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import date, timedelta

PERSON_COLUMNS = {"name", "first_name", "last_name", "owner", "owner_name", "resident",
                  "phone", "email", "ssn", "dob", "date_of_birth", "person_id"}


@dataclass
class SpikeRule:
    window_days: int = 30
    baseline_windows: int = 6
    z: float = 2.0
    min_count: int = 5
    name: str = "SPIKE-v1"


@dataclass
class Flag:
    rule: str
    area: str
    category: str
    window_start: str
    window_end: str
    count: int
    baseline_mean: float
    baseline_stdev: float
    threshold: float
    baseline_counts: list


def load_requests(path: str) -> list[tuple[date, str, str]]:
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        cols = {c.strip().lower() for c in (reader.fieldnames or [])}
        bad = cols & PERSON_COLUMNS
        if bad:
            raise ValueError(f"refusing file with person-identifying columns: {sorted(bad)}. "
                             "Remove them; AXIOM0 works at the area level only.")
        missing = {"date", "area", "category"} - cols
        if missing:
            raise ValueError(f"missing required columns: {sorted(missing)}")
        rows = []
        for r in reader:
            r = {k.strip().lower(): (v or "").strip() for k, v in r.items()}
            rows.append((date.fromisoformat(r["date"]), r["area"], r["category"]))
        return rows


def spikes(rows: list[tuple[date, str, str]], rule: SpikeRule = SpikeRule(),
           as_of: date | None = None) -> list[Flag]:
    if not rows:
        return []
    as_of = as_of or max(d for d, _, _ in rows)
    w = timedelta(days=rule.window_days)
    # window 0 is the most recent; window i covers (as_of - (i+1)w, as_of - i*w]
    buckets: Counter = Counter()
    keys = set()
    for d, area, cat in rows:
        if d > as_of:
            continue
        i = (as_of - d).days // rule.window_days
        if i <= rule.baseline_windows:
            buckets[(area, cat, i)] += 1
            keys.add((area, cat))
    flags = []
    for area, cat in sorted(keys):
        count = buckets[(area, cat, 0)]
        base = [buckets[(area, cat, i)] for i in range(1, rule.baseline_windows + 1)]
        mean = statistics.fmean(base)
        sd = statistics.pstdev(base)
        threshold = mean + rule.z * sd
        if count >= rule.min_count and count >= threshold and count > mean:
            flags.append(Flag(rule.name, area, cat, str(as_of - w + timedelta(days=1)), str(as_of),
                              count, round(mean, 2), round(sd, 2), round(threshold, 2), base))
    flags.sort(key=lambda f: -(f.count - f.baseline_mean))
    return flags


def flags_as_dicts(flags: list[Flag]) -> list[dict]:
    return [asdict(f) for f in flags]
