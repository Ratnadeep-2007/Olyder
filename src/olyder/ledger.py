"""In-process Decimal dollar ledger, separate from legacy token accounting.

No provider enforcement or durable crash recovery is claimed. Reserve only
reviewed upper bounds. A provider may exceed them; settlement records overrun.
Callbacks are idempotent for identical data, conflicting replays are rejected.
"""
from decimal import Decimal, InvalidOperation
from threading import RLock

from .quota import QuotaExceeded


class MoneyError(ValueError):
    pass


def money(value, *, positive=False):
    if not isinstance(value, (str, Decimal, int)) or isinstance(value, bool):
        raise MoneyError('Use Decimal or a decimal string, never binary float')
    try:
        amount = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise MoneyError('Invalid money') from exc
    if not amount.is_finite() or amount < 0 or amount > Decimal('1e12'):
        raise MoneyError('Money must be finite and between zero and 1e12')
    if positive and amount == 0:
        raise MoneyError('Limit must be positive')
    if amount.as_tuple().exponent < -12:
        raise MoneyError('Money supports at most 12 decimal places')
    return amount


class BudgetLedger:
    schema_version = 1

    def __init__(self, run_id, limit, *, verifier_reserve='0', strict=False):
        if not isinstance(run_id, str) or not run_id:
            raise MoneyError('run_id required')
        self.run_id = run_id
        self.limit = money(limit, positive=True)
        self.verifier_reserve = money(verifier_reserve)
        if self.verifier_reserve > self.limit:
            raise MoneyError('Verifier reserve exceeds limit')
        self.strict = strict
        self._lock = RLock()
        self._requests = {}

    def reserve(self, request_id, upper_bound):
        amount = money(upper_bound)
        if not isinstance(request_id, str) or not request_id or len(request_id) > 200:
            raise MoneyError('Bounded immutable request_id required')
        with self._lock:
            old = self._requests.get(request_id)
            if old:
                if old['state'] == 'reserved' and old['estimate'] == amount:
                    return
                raise MoneyError('Request ID already used or conflicting')
            if self.strict and any(r['state'] == 'unknown' for r in self._requests.values()):
                raise QuotaExceeded('Unknown spend requires reconciliation')
            allocated = sum((r['actual'] if r['state'] == 'settled' else
                             r['estimate'] if r['state'] in ('reserved', 'unknown') else Decimal(0)
                             for r in self._requests.values()), Decimal(0))
            if allocated + amount + self.verifier_reserve > self.limit:
                raise QuotaExceeded('Admission would spend mandatory verifier reserve or exceed limit')
            self._requests[request_id] = {'estimate': amount, 'actual': None, 'state': 'reserved'}

    def settle(self, request_id, actual):
        amount = None if actual is None else money(actual)
        with self._lock:
            r = self._requests.get(request_id)
            if not r:
                raise MoneyError('Foreign request')
            state = 'unknown' if amount is None else 'settled'
            if r['state'] == state and r['actual'] == amount:
                return
            if r['state'] != 'reserved':
                raise MoneyError('Conflicting settlement')
            r.update(state=state, actual=amount)

    def reserve_verifier(self, request_id, upper_bound):
        """Transfer protected funds into an active verifier reservation atomically."""
        amount = money(upper_bound)
        with self._lock:
            if amount > self.verifier_reserve:
                raise QuotaExceeded('Mandatory verifier reserve unavailable')
            self.verifier_reserve -= amount
            try:
                # Unknown builder billing must not prevent using funds that
                # were protected specifically for mandatory verification.
                strict = self.strict
                self.strict = False
                try:
                    self.reserve(request_id, amount)
                finally:
                    self.strict = strict
            except Exception:
                self.verifier_reserve += amount
                raise

    def release(self, request_id):
        with self._lock:
            r = self._requests.get(request_id)
            if not r or r['state'] not in ('reserved', 'released'):
                raise MoneyError('Cannot release unknown or settled usage')
            r['state'] = 'released'

    def reconcile(self, request_id, actual):
        amount = money(actual)
        with self._lock:
            r = self._requests.get(request_id)
            if not r:
                raise MoneyError('Foreign request')
            if r['state'] == 'settled' and r['actual'] == amount:
                return
            if r['state'] != 'unknown':
                raise MoneyError('Only unknown usage can be reconciled')
            r.update(state='settled', actual=amount)

    def snapshot(self):
        with self._lock:
            unknown = any(r['state'] == 'unknown' for r in self._requests.values())
            actual = sum((r['actual'] for r in self._requests.values() if r['state'] == 'settled'), Decimal(0))
            reserved = sum((r['estimate'] for r in self._requests.values() if r['state'] == 'reserved'), Decimal(0))
            estimates = sum((r['estimate'] for r in self._requests.values() if r['state'] == 'unknown'), Decimal(0))
            return {'schema_version': self.schema_version, 'run_id': self.run_id,
                    'currency': 'USD', 'limit': str(self.limit),
                    'spent_actual': None if unknown else str(actual),
                    'known_actual_subtotal': str(actual), 'spent_estimated': str(estimates),
                    'reserved': str(reserved), 'reserve_remaining': str(self.verifier_reserve),
                    'unknown_spend': unknown, 'enforcement_kind': 'local_soft',
                    'strict_reconciliation': self.strict,
                    'remaining_estimated': str(max(Decimal(0), self.limit-actual-estimates-reserved-self.verifier_reserve))}
