"""3-6-9 Intention Lab: repeatable goal-setting protocol, not a truth or causal engine.

3 recitations/session x 6 self-reported sessions/day x 9 calendar days.
Intention data is intentionally not treated as municipal evidence, legal proof,
forecasting input, or experimental validation of supernatural claims.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from math import isfinite
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .store import Store, now

DAYS = 9
SESSIONS_PER_DAY = 6
REPETITIONS_PER_SESSION = 3
TOTAL_SESSIONS = DAYS * SESSIONS_PER_DAY
TOTAL_REPETITIONS = TOTAL_SESSIONS * REPETITIONS_PER_SESSION


def _str(value: str, name: str, limit: int = 1000, *, empty_ok: bool = False) -> str:
    if not isinstance(value, str) or len(value) > limit or (not empty_ok and not value.strip()):
        raise ValueError(f'{name} must be a {"string" if empty_ok else "nonempty string"} of at most {limit} characters')
    return value.strip()


def _number(value: float, name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f'{name} must be a finite number')
    try:
        n = float(value)
    except (TypeError, ValueError, OverflowError) as e:
        raise ValueError(f'{name} must be a finite number') from e
    if not isfinite(n):
        raise ValueError(f'{name} must be a finite number')
    return n


def local_today(tz: ZoneInfo) -> date:
    return datetime.now(tz).date()


def _zone(name: str) -> ZoneInfo:
    name = _str(name, 'timezone', 80)
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, KeyError) as e:
        raise ValueError('timezone must be an installed IANA timezone, e.g. America/Chicago') from e


class IntentionLab:
    """Source-aware, signed self-report ledger; does not claim outcomes are manifested."""

    def __init__(self, store: Store):
        self.store = store

    def start(self, *, goal: str, affirmation: str, metric: str, baseline: float,
              target: float, start_date: str | None = None,
              timezone_name: str = 'America/Chicago') -> dict[str, Any]:
        goal = _str(goal, 'goal', 300)
        affirmation = _str(affirmation, 'affirmation', 500)
        metric = _str(metric, 'metric', 120)
        baseline = _number(baseline, 'baseline')
        target = _number(target, 'target')
        zone = _zone(timezone_name)
        today = local_today(zone)
        if start_date is None:
            start = today
        else:
            if not isinstance(start_date, str) or len(start_date) != 10:
                raise ValueError('start_date must be YYYY-MM-DD')
            try:
                start = date.fromisoformat(start_date)
            except ValueError as e:
                raise ValueError('start_date must be YYYY-MM-DD') from e
        if start < today:
            raise ValueError('A new practice cannot be backdated; start today or in the future')
        if start > today + timedelta(days=365):
            raise ValueError('Start date cannot exceed one year ahead')
        id_ = str(uuid4())
        with self.store.write() as conn:
            conn.execute('''INSERT INTO intention_campaigns
                (id,goal,affirmation,metric,baseline,target,start_date,timezone,created_at)
                VALUES(?,?,?,?,?,?,?,?,?)''',
                (id_,goal,affirmation,metric,baseline,target,start.isoformat(),timezone_name,now()))
            self.store.append(conn,'369_intention_started',{'id':id_,'goal':goal,
                'affirmation':affirmation,'metric':metric,'baseline':baseline,
                'target':target,'start_date':start.isoformat(),'timezone':timezone_name,
                'protocol':'3 x 6 x 9','epistemic_status':'self-reported intention, not proof'})
        return self.get(id_)

    def get(self, intention_id: str) -> dict[str, Any]:
        with self.store.connect() as conn:
            item = conn.execute('SELECT * FROM intention_campaigns WHERE id=?',(intention_id,)).fetchone()
            if not item:
                raise ValueError('Intention not found')
            sessions = [dict(row) for row in conn.execute('''SELECT id,day_number,session_number,
                repetitions,action_taken,reflection,recorded_at FROM intention_sessions
                WHERE intention_id=? ORDER BY day_number,session_number''',(intention_id,))]
            outcomes = [dict(row) for row in conn.execute('''SELECT id,observed_at,value,source_reference,note
                FROM intention_outcomes WHERE intention_id=? ORDER BY observed_at,id''',(intention_id,))]
        result = dict(item)
        start = date.fromisoformat(result['start_date'])
        today = local_today(_zone(result['timezone']))
        day = (today-start).days+1
        completed_sessions = len(sessions)
        all_done = completed_sessions == TOTAL_SESSIONS
        by_day = {d:0 for d in range(1,DAYS+1)}
        for s in sessions:
            by_day[s['day_number']] += 1
        result.update({
            'protocol':{'repetitions_per_session':REPETITIONS_PER_SESSION,
                        'sessions_per_day':SESSIONS_PER_DAY,'days':DAYS,
                        'total_sessions':TOTAL_SESSIONS,'total_repetitions':TOTAL_REPETITIONS},
            'current_day':day if 1 <= day <= DAYS else None,
            'days':[{ 'day':d,'date':(start+timedelta(days=d-1)).isoformat(),
                    'sessions':by_day[d],'complete':by_day[d]==SESSIONS_PER_DAY}
                    for d in range(1,DAYS+1)],
            'completed_sessions':completed_sessions,
            'completed_repetitions':completed_sessions*REPETITIONS_PER_SESSION,
            'progress_percent':round(100*completed_sessions/TOTAL_SESSIONS,1),
            'practice_complete':all_done,
            'window_closed':day>DAYS,
            'sessions':sessions,
            'outcomes':outcomes,
            'latest_observed_value':outcomes[-1]['value'] if outcomes else None,
            'epistemic_status':'Self-reported practice and observations; not a causal demonstration or municipal finding.'})
        return result

    def list(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.store.connect() as conn:
            rows = conn.execute('SELECT id FROM intention_campaigns ORDER BY created_at DESC,id DESC LIMIT ?',
                                (min(max(limit,1),250),)).fetchall()
        return [self.get(row['id']) for row in rows]

    def session(self, intention_id: str, *, repetitions: int = 3,
                action_taken: str = '', reflection: str = '') -> dict[str, Any]:
        if type(repetitions) is not int or repetitions != REPETITIONS_PER_SESSION:
            raise ValueError('Each recorded session must attest exactly 3 repetitions')
        action_taken = _str(action_taken,'action_taken',1000,empty_ok=True)
        reflection = _str(reflection,'reflection',1000,empty_ok=True)
        session_id = str(uuid4())
        with self.store.write() as conn:
            campaign = conn.execute('SELECT * FROM intention_campaigns WHERE id=?',(intention_id,)).fetchone()
            if not campaign:
                raise ValueError('Intention not found')
            day = (local_today(_zone(campaign['timezone'])) - date.fromisoformat(campaign['start_date'])).days + 1
            if day < 1:
                raise ValueError('Practice has not started yet')
            if day > DAYS:
                raise ValueError('Nine-day practice window has closed; create a new intention to begin again')
            previous = conn.execute('SELECT COUNT(*) AS n FROM intention_sessions WHERE intention_id=? AND day_number=?',
                                    (intention_id,day)).fetchone()['n']
            if previous >= SESSIONS_PER_DAY:
                raise ValueError('Six recorded sessions already exist for today')
            slot = previous+1
            stamp = now()
            conn.execute('''INSERT INTO intention_sessions
                (id,intention_id,day_number,session_number,repetitions,action_taken,reflection,recorded_at)
                VALUES(?,?,?,?,?,?,?,?)''',(session_id,intention_id,day,slot,repetitions,action_taken,reflection,stamp))
            self.store.append(conn,'369_session_self_reported',{'id':session_id,'intention_id':intention_id,
                'day':day,'session':slot,'repetitions':repetitions,
                'action_taken':action_taken,'reflection':reflection,'recorded_at':stamp,
                'verification':'operator self-report; not independently observed'})
        return self.get(intention_id)

    def outcome(self, intention_id: str, *, value: float,
                source_reference: str = '', note: str = '') -> dict[str, Any]:
        value = _number(value,'value')
        source_reference = _str(source_reference,'source_reference',1500,empty_ok=True)
        note = _str(note,'note',1500,empty_ok=True)
        id_ = str(uuid4())
        stamp = now()
        with self.store.write() as conn:
            if not conn.execute('SELECT 1 FROM intention_campaigns WHERE id=?',(intention_id,)).fetchone():
                raise ValueError('Intention not found')
            conn.execute('''INSERT INTO intention_outcomes
                (id,intention_id,observed_at,value,source_reference,note)
                VALUES(?,?,?,?,?,?)''',(id_,intention_id,stamp,value,source_reference,note))
            self.store.append(conn,'369_outcome_self_reported',{'id':id_,'intention_id':intention_id,
                'observed_at':stamp,'value':value,'source_reference':source_reference,
                'note':note,'verification':'not independently verified; correlation not causation'})
        return self.get(intention_id)
