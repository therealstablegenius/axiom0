# AXIOM0 · 3-6-9 Intention Lab (v0.4)

**Status:** Optional self-report goal-setting feature. Not municipal evidence, not statistical forecasting, and not proof that numbers or affirmations manifest events.

The video introduced a 3-6-9 practice: repeat the same affirmation **three times per session**, **six sessions per day**, for **nine consecutive days**. Thus the maximum recorded total is 54 sessions and 162 repetitions. Its association with Nikola Tesla is not established as a verified historical method, and the claimed ability to cause outcomes has no demonstrated scientific basis. The feature remains useful as a structured reflection and follow-through exercise.

## Workflow

1. Create an intention specifying your goal, affirmation, numeric metric, starting measurement, target, local timezone and optional future start date.
2. Each time you actually repeat the affirmation three times, record *one* completed session (you may record a concrete action and reflection).
3. The engine caps recorded sessions at six per calendar day, for nine days beginning on the configured start date. It does not allow retrospective starts or log sessions outside the period.
4. Log independently observed metric values and sources separately. Values are self-reported and do not prove that an affirmation caused any change.
5. Study whether goals progressed, whether actions were completed, whether there were opposing influences, and whether the baseline/target was sensible.

## Why keep this separate?

Axiom0's **municipal evidence engine** needs externally grounded, citable observations and human verification. The Intention Lab stores private, introspective records in dedicated database tables. Its data is excluded from `occurrences`, `hypotheses`, municipal `signals` and local legal research. It adds `369_*` event types to the signed chain without promoting any intention to a factual finding. The experimental numerical `harmony` score remains unchanged and does not measure truth, fulfillment, or manifestation.

## Browser interface

With AXIOM0 running locally (see `README.md`), open `http://127.0.0.1:8765/`, connect using `AXIOM0_API_KEY` and scroll to **3 · 6 · 9 Intention Lab**. Create a practice and select it to view day-by-day counts and record sessions/outcomes.

## CLI examples

```powershell
python -m axiom0 369-start --goal "Reduce research turnaround" --affirmation "I take clear measurable action each day" --metric "Minutes per request" --baseline 60 --target 30
python -m axiom0 369-list
python -m axiom0 369-show YOUR-UUID-HERE
python -m axiom0 369-session YOUR-UUID-HERE --action "Timed three requests" --reflection "Identified a bottleneck"
python -m axiom0 369-outcome YOUR-UUID-HERE --value 52 --source "local://time-log" --note "Measured today"
python -m axiom0 verify
```

## REST API

Requires normal local `X-AXIOM0-Key` header:

- `GET/POST /v1/369/intentions`
- `GET /v1/369/intentions/{id}`
- `POST /v1/369/intentions/{id}/sessions`
- `POST /v1/369/intentions/{id}/outcomes`

Session API always requires `repetitions=3`; campaign timestamps determine the day and next session slot. An action/reflection is optional. Outcome fields are `value`, `source_reference`, and `note`.

## Privacy and deployments

The v0.4 prototype keeps this information in the same local SQLite database as AXIOM0's other records, in distinct tables. It is **not a multi-user private journal**; anyone holding the current service API secret can view all recorded intentions. Avoid personal secrets, health details, or sensitive resident information. Before deployment to a municipality or multi-user installation, isolate Intention Lab into a separate encrypted data store and add real user identities, permissions, retention/deletion policies, audited access and backup protections. The shared API key used in the prototype does not provide per-user privacy.
