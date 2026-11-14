"""Dollar admission contract: exact Decimal values, atomic tickets, unknown != zero."""
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import pytest
from olyder.ledger import BudgetLedger, MoneyError
from olyder.quota import QuotaExceeded


@pytest.mark.parametrize('value', ['-1', '0', 'NaN', 'Infinity', '-Infinity', 1.0, True, '1e999999', None, 'no'])
def test_invalid_limits(value):
    with pytest.raises(MoneyError):
        BudgetLedger('run', value)


def test_exact_boundary_and_reserve():
    ledger = BudgetLedger('run', '1', verifier_reserve='0.2')
    ledger.reserve('a', '0.8')
    with pytest.raises(QuotaExceeded):
        ledger.reserve('b', '0.0001')


def test_same_size_tickets_settle_independently():
    ledger = BudgetLedger('run', '1')
    ledger.reserve('a', '0.4'); ledger.reserve('b', '0.4')
    ledger.settle('a', '0.2'); ledger.settle('b', '0.3')
    assert ledger.snapshot()['spent_actual'] == '0.5'


def test_idempotent_same_callback_conflict_rejected():
    ledger = BudgetLedger('run', '1')
    ledger.reserve('a', '0.5'); ledger.settle('a', '0.1'); ledger.settle('a', '0.1')
    assert ledger.snapshot()['spent_actual'] == '0.1'
    with pytest.raises(MoneyError):
        ledger.settle('a', '0.2')


def test_foreign_callback_rejected():
    with pytest.raises(MoneyError):
        BudgetLedger('run', '1').settle('alien', '0')


def test_unknown_not_zero_and_strict_blocks():
    ledger = BudgetLedger('run', '1', strict=True)
    ledger.reserve('a', '0.1'); ledger.settle('a', None)
    assert ledger.snapshot()['spent_actual'] is None
    assert ledger.snapshot()['unknown_spend']
    with pytest.raises(QuotaExceeded):
        ledger.reserve('b', '0.1')
    ledger.reconcile('a', '0.2')
    ledger.reserve('b', '0.1')


def test_release_and_reuse_id_rejected():
    ledger = BudgetLedger('run', '1')
    ledger.reserve('a', '1'); ledger.release('a')
    ledger.reserve('b', '1')
    with pytest.raises(MoneyError):
        ledger.reserve('a', '0.1')


def test_concurrent_admission_never_oversubscribes():
    ledger = BudgetLedger('run', '1')
    def reserve(i):
        try:
            ledger.reserve(str(i), '0.1')
            return 1
        except QuotaExceeded:
            return 0
    with ThreadPoolExecutor(max_workers=16) as pool:
        assert sum(pool.map(reserve, range(100))) == 10


def test_overrun_is_reported_and_blocks():
    ledger = BudgetLedger('run', '1')
    ledger.reserve('a', '0.1'); ledger.settle('a', '1.2')
    assert ledger.snapshot()['spent_actual'] == '1.2'
    with pytest.raises(QuotaExceeded):
        ledger.reserve('b', '0.01')


def test_unknown_uses_estimate_for_soft_admission():
    ledger = BudgetLedger('run', '1')
    ledger.reserve('a', '0.8'); ledger.settle('a', None)
    with pytest.raises(QuotaExceeded):
        ledger.reserve('b', '0.3')
    assert ledger.snapshot()['enforcement_kind'] == 'local_soft'


def test_zero_settlement_is_known_zero():
    ledger = BudgetLedger('run', Decimal('1'))
    ledger.reserve('a', '0.1'); ledger.settle('a', '0')
    assert ledger.snapshot()['spent_actual'] == '0'
    assert not ledger.snapshot()['unknown_spend']


def test_conflicting_reservation_rejected():
    ledger = BudgetLedger('run', '1')
    ledger.reserve('a', '0.1')
    with pytest.raises(MoneyError):
        ledger.reserve('a', '0.2')
