import json
import sys
import tempfile
import time

import pytest

from olyder.accounting import RuntimeAccounting
from olyder.control import RunControl, Cancelled, activate
from olyder.execution import managed_run
from olyder.quota import QuotaExceeded
from olyder.state import RunStore, StateError


def test_runtime_budget_unknown_strict_blocks_next():
    accounting=RuntimeAccounting('run', {'max_cost_usd':'1','builder_upper_bound_usd':'0.4',
                                        'verifier_reserve_usd':'0.3','strict':True})
    ticket=accounting.admit('builder')
    accounting.settle(ticket, {'observed_tokens':10,'usage_complete':True})
    assert accounting.snapshot()['ledger']['spent_actual'] is None
    with pytest.raises(QuotaExceeded):
        accounting.admit('builder')


def test_reserve_protects_critic_and_records_estimate():
    accounting=RuntimeAccounting('run', {'max_cost_usd':'1','builder_upper_bound_usd':'0.8',
                                        'verifier_reserve_usd':'0.3'})
    with pytest.raises(QuotaExceeded):
        accounting.admit('builder')
    ticket=accounting.admit('critic')
    accounting.settle(ticket, {'estimated_cost_usd':'0.1','origin':'fixture'})
    assert accounting.snapshot()['observations'][0]['estimated_cost_usd'] == '0.1'
    assert accounting.snapshot()['ledger']['spent_actual'] is None


def test_atomic_checkpoint_and_conflicting_writer(tmp_path):
    store=RunStore(tmp_path)
    state=store.create({'spec_sha256':'abc','phase':'ready'})
    first=store.read(state['run_id'])
    store.update(first['run_id'], first['revision'], {'phase':'builder_started'})
    with pytest.raises(StateError):
        store.update(first['run_id'], first['revision'], {'phase':'passed'})
    assert store.read(first['run_id'])['phase'] == 'builder_started'


@pytest.mark.parametrize('identifier', ['../escape','/tmp/evil','wrong','a'*100])
def test_store_rejects_bad_run_ids(tmp_path, identifier):
    with pytest.raises(StateError):
        RunStore(tmp_path).read(identifier)


def test_cancellation_kills_process(tmp_path):
    started=time.monotonic()
    control=RunControl(deadline=started+10, cancelled=lambda: time.monotonic()-started > .15)
    with activate(control), tempfile.TemporaryFile(mode='w+t') as output:
        with pytest.raises(Cancelled):
            managed_run([sys.executable,'-c','import time;time.sleep(8)'],
                        cwd=tmp_path,stdout=output,timeout=5)
    assert time.monotonic()-started < 3
