"""MCAℓ five-field atom: Identity, Purpose, Observation, Constraint, Feedback.

This is an operational record definition, NOT an empirical prediction or truth score.
"""
from dataclasses import dataclass, asdict

@dataclass(frozen=True)
class MCAAtom:
    identity: str
    purpose: str
    observation: str
    constraint: str
    feedback: str

    def as_dict(self) -> dict:
        return asdict(self)
