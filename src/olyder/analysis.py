"""Budgeted, checkpointed planning/research jobs. No builder is executed."""
import hashlib
import time

from .accounting import RuntimeAccounting
from .config import load_spec
from .control import Cancelled, RunControl, activate
from .engine import plan
from .idea import evaluate_idea
from .models import ModelError
from .privacy import redact
from .quota import Budget, QuotaExceeded
from .state import RunStore


def run_analysis(kind, spec_path='olyder.json', *, use_ai=False, allow_network=False, model_provider=None):
    if kind not in ('plan','idea') or type(use_ai) is not bool or type(allow_network) is not bool:
        raise ValueError('Invalid analysis workflow or consent flags')
    spec=load_spec(spec_path)
    (spec.root/'.olyder').mkdir(mode=0o700,exist_ok=True)
    store=RunStore(spec.root/'.olyder'/'runs')
    state=store.create({'phase':'analysis_ready','spec_sha256':spec.digest,'job_type':kind})
    run_id=state['run_id']
    account=RuntimeAccounting(run_id,spec.raw.get('budget'))
    started=time.monotonic()
    budget=Budget(spec.raw.get('limits',{}).get('max_tokens',30000))
    def checkpoint(phase):
        nonlocal state
        latest=store.read(run_id)
        state=store.update(run_id,latest['revision'],{'phase':phase,'accounting':account.snapshot()})
    control=RunControl(started+spec.raw.get('limits',{}).get('max_seconds',600),
        cancelled=lambda:store.read(run_id).get('cancel_requested',False),
        model_provider=model_provider,model_accounting=account,
        model_role='planner' if kind=='plan' else 'research',model_checkpoint=checkpoint)
    result={'goal':spec.goal,'status':'blocked','run_id':run_id,'job_type':kind,'spec_sha256':spec.digest}
    try:
        with activate(control):
            control.check()
            if kind=='plan':
                result.update(plan(spec,budget,use_ai=use_ai),status='planned_not_verified')
            else:
                result.update(evaluate_idea(spec,network_allowed=allow_network,use_ai=use_ai,budget=budget))
            control.check()
            if hashlib.sha256(spec.path.read_bytes()).hexdigest()!=spec.digest:
                raise ValueError('Original requirements changed during analysis')
    except QuotaExceeded:
        result.update(status='budget_exhausted',stop_reason='analysis_budget_admission')
    except (Cancelled,KeyboardInterrupt):
        result.update(status='cancelled',stop_reason='user_cancelled')
    except (ModelError,OSError,ValueError,RuntimeError) as exc:
        result.update(status='blocked',stop_reason='analysis_unavailable',reason=redact(str(exc))[:500])
    result.update(run_id=run_id,budget=budget.snapshot(),accounting=account.snapshot(),
                  budget_verdict=account.snapshot()['budget_verdict'],wall_seconds=time.monotonic()-started,
                  verification_performed=False)
    latest=store.read(run_id)
    store.update(run_id,latest['revision'],{'phase':'completed','result':result,'accounting':account.snapshot()})
    return result
