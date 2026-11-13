"""Conservative deterministic retry policy; never changes the check suite."""
from dataclasses import dataclass


@dataclass(frozen=True)
class RunPolicy:
    mode: str = 'balanced'
    final_seconds: int = 15

    def __post_init__(self):
        if self.mode not in ('economy', 'balanced', 'thorough'):
            raise ValueError('Unknown policy mode')
        if type(self.final_seconds) is not int or self.final_seconds <= 0:
            raise ValueError('final_seconds must be a positive integer')

    @property
    def no_progress_limit(self):
        return {'economy': 1, 'balanced': 2, 'thorough': 3}[self.mode]

    def admit_builder(self, remaining_seconds):
        return remaining_seconds > self.final_seconds


def progress(previous, current):
    before = {r['id']: r['status'] for r in previous}
    after = {r['id']: r['status'] for r in current}
    newly_passing = sorted(k for k, v in after.items() if v == 'pass' and before.get(k) == 'fail')
    regressions = sorted(k for k, v in before.items() if v == 'pass' and after.get(k) != 'pass')
    return {'newly_passing': newly_passing, 'regressions': regressions,
            'failed': sorted(k for k,v in after.items() if v == 'fail'),
            'blockers': sorted(k for k,v in after.items() if v in ('blocked','needs_review')),
            'improved': bool(newly_passing) and not regressions}
