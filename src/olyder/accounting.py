"""Runtime monetary admission; CLI/client estimates never become invoices."""
from dataclasses import dataclass
from decimal import Decimal
from uuid import uuid4

from .ledger import BudgetLedger, money
from .quota import QuotaExceeded


@dataclass(frozen=True)
class PricingSnapshot:
    provider: str
    model: str
    date: str
    input_per_million_usd: str
    output_per_million_usd: str
    cached_per_million_usd: str | None = None
    schema_version: int = 1

    def __post_init__(self):
        from datetime import date
        date.fromisoformat(self.date)
        if any(not isinstance(v,str) or not v for v in (self.provider,self.model)):
            raise ValueError('Pricing provider and model must be explicit names')
        if self.schema_version!=1:
            raise ValueError('Unsupported pricing schema')
        money(self.input_per_million_usd);money(self.output_per_million_usd)
        if self.cached_per_million_usd is not None:
            money(self.cached_per_million_usd)

    def estimate(self, usage):
        inp, out = usage.get('input_tokens'), usage.get('output_tokens')
        cached = usage.get('cached_tokens')
        if not usage.get('usage_complete') or any(type(x) is not int or x < 0 for x in (inp,out,cached)) or cached > inp:
            return None
        if cached and self.cached_per_million_usd is None:
            return None
        cost = ((inp-cached)*money(self.input_per_million_usd) +
                out*money(self.output_per_million_usd) +
                cached*money(self.cached_per_million_usd or '0')) / Decimal(1000000)
        return str(cost)


class RuntimeAccounting:
    def __init__(self, run_id, config=None):
        self.config = config or {}
        c = self.config
        self.ledger = BudgetLedger(run_id, c['max_cost_usd'],
            verifier_reserve=c.get('verifier_reserve_usd','0'), strict=c.get('strict',False)) if c.get('max_cost_usd') is not None else None
        self.observations = []
        self.pending = {}

    def admit(self, role):
        request_id = str(uuid4())
        upper = self.config.get('builder_upper_bound_usd') if role == 'builder' else self.config.get('verifier_reserve_usd')
        if self.ledger:
            if upper is None or money(upper) == 0:
                raise QuotaExceeded(f'No positive reviewed upper bound for {role}; spend cannot be bounded')
            if role == 'critic':
                self.ledger.reserve_verifier(request_id, upper)
            else:
                self.ledger.reserve(request_id, upper)
        self.pending[request_id] = role
        return request_id

    def settle(self, request_id, usage=None):
        role = self.pending.pop(request_id)
        allowed={'provider','model','model_origin','input_tokens','output_tokens','cached_tokens',
                 'reasoning_tokens','observed_tokens','usage_complete','estimated_cost_usd',
                 'origin','elapsed_seconds','status','usage_events','malformed_events','reasoning_accounting'}
        observation = {k:v for k,v in (usage or {}).items() if k in allowed}
        from .privacy import redact
        for key,value in list(observation.items()):
            if isinstance(value,str):
                observation[key]=redact(value)[:500]
        estimate=observation.get('estimated_cost_usd')
        if estimate is not None:
            try:
                observation['estimated_cost_usd']=str(money(estimate))
            except ValueError:
                observation['estimated_cost_usd']=None
        # No trusted billing channel is implemented by CLI agents. Even their
        # self-reported cost is observed/estimated, never a reconciled invoice.
        observation.update(request_id=request_id, role=role, billed_cost_usd=None)
        observation.setdefault('origin','unavailable')
        observation.setdefault('usage_complete',False)
        observation.setdefault('observed_tokens',None)
        observation.setdefault('estimated_cost_usd',None)
        pricing = self.config.get('pricing')
        if pricing and observation.get('provider') == pricing.get('provider') and observation.get('model') == pricing.get('model'):
            observation['estimated_cost_usd'] = PricingSnapshot(**pricing).estimate(observation)
            observation['pricing_snapshot'] = dict(pricing)
        self.observations.append(observation)
        if self.ledger:
            self.ledger.settle(request_id, None)

    def snapshot(self):
        return {'ledger':self.ledger.snapshot() if self.ledger else None,
                'ledger_checkpoint':self.ledger.checkpoint() if self.ledger else None,
                'observations':list(self.observations), 'pending_requests':dict(self.pending),
                'enforcement_kind':'local_soft',
                'budget_verdict':'unknown' if any(o['billed_cost_usd'] is None for o in self.observations) else 'not_applicable'}
