"""Replaceable CLI adapters. Templates never imply permission auto-approval."""
from __future__ import annotations

import json
from decimal import Decimal

from .agents import agent_argv, parse_agent_log
from .interfaces import API_VERSION, AgentAdapter, Capabilities


class ExecutableAgent:
    api_version = API_VERSION

    def __init__(self, name: str, argv: list[str], telemetry: str = 'unknown'):
        if not name or not argv or not all(isinstance(a, str) and a and '\0' not in a for a in argv):
            raise ValueError('Agent requires a name and explicit nonempty argv')
        if telemetry not in ('unknown','codex','opencode','claude'):
            raise ValueError('Unsupported agent telemetry format')
        self.name, self.argv, self.telemetry = name, list(argv), telemetry

    def command(self, prompt):
        return [a.replace('{prompt}', prompt) for a in self.argv]

    def capabilities(self):
        return Capabilities(structured_usage=self.telemetry != 'unknown',
                            streaming=True, notes='Live event metadata only; usage is post-hoc; no provider hard limit')

    def parse(self, stream):
        if self.telemetry in ('codex', 'opencode'):
            usage=parse_agent_log(stream, self.telemetry).snapshot()
            if not usage['usage_events']:
                for key in ('input_tokens','output_tokens','cached_tokens','reasoning_tokens'):
                    usage[key]=None
            if self.telemetry=='opencode' and usage['usage_complete']:
                usage['input_tokens']+=usage['cached_tokens']
                base=usage['input_tokens']+usage['output_tokens']
                if usage['observed_tokens']==base+usage['reasoning_tokens']:
                    usage['output_tokens']+=usage['reasoning_tokens']
                    usage['reasoning_accounting']='separate_output'
                elif usage['observed_tokens']==base:
                    usage['reasoning_accounting']='included_in_output'
                else:
                    usage['usage_complete']=False
                    usage['reasoning_accounting']='unknown'
            return usage
        result = {'provider': self.name, 'observed_tokens': None,
                  'input_tokens': None, 'output_tokens': None,
                  'cached_tokens': None, 'usage_complete': False,
                  'estimated_cost_usd': None, 'billed_cost_usd': None,
                  'status': 'incomplete', 'origin': 'agent_jsonl'}
        stream.seek(0)
        for i in range(10000):
            line = stream.readline(1_000_001)
            if not line:
                break
            if len(line) > 1_000_000:
                break
            try:
                e = json.loads(line)
                if not isinstance(e, dict):
                    continue
                if self.telemetry == 'claude' and e.get('type') == 'result':
                    result['status'] = 'failed' if e.get('is_error') else 'completed'
                    usage = e.get('usage', {})
                    inp, out = usage.get('input_tokens'), usage.get('output_tokens')
                    if type(inp) is int and inp >= 0 and type(out) is int and out >= 0:
                        cached = usage.get('cache_read_input_tokens', 0)
                        written = usage.get('cache_creation_input_tokens', 0)
                        if type(cached) is not int or cached < 0 or type(written) is not int or written < 0:
                            continue
                        result.update(input_tokens=inp+cached+written, output_tokens=out,
                                      cached_tokens=cached, observed_tokens=inp+cached+written+out,
                                      usage_complete=not e.get('is_error'))
                    cost = e.get('total_cost_usd')
                    if isinstance(cost, (int, float, str)) and not isinstance(cost, bool):
                        amount = Decimal(str(cost))
                        if amount.is_finite() and amount >= 0:
                            result['estimated_cost_usd'] = str(amount)
            except (ValueError, TypeError, AttributeError, ArithmeticError):
                continue
        return result


class BuiltinAgent(ExecutableAgent):
    def capabilities(self):
        from dataclasses import replace
        return replace(super().capabilities(),requires_git=self.name=='codex')

    def command(self, prompt):
        return agent_argv(self.name, prompt)


_agents: dict[str, AgentAdapter] = {
    n: BuiltinAgent(n, [n], n) for n in ('codex', 'opencode')
}
_agents['claude'] = ExecutableAgent('claude', [
    'claude', '--bare', '-p', '--output-format', 'stream-json', '--verbose', '{prompt}'
], 'claude')


def register_agent(adapter: AgentAdapter):
    if not isinstance(adapter, AgentAdapter) or adapter.api_version != API_VERSION:
        raise ValueError('Unsupported agent protocol version')
    if adapter.name in _agents:
        raise ValueError('Agent name already registered')
    _agents[adapter.name] = adapter


def get_agent(name: str) -> AgentAdapter:
    try:
        return _agents[name]
    except KeyError as exc:
        raise ValueError(f'Unknown agent: {name}; explicitly register an adapter first') from exc


def bind_model(adapter, model):
    if model is None:
        return adapter
    if not isinstance(model,str) or not model or len(model)>512 or '\0' in model:
        raise ValueError('Invalid selected model')
    if adapter.name not in ('codex','opencode','claude'):
        raise ValueError('Custom adapters must implement their own model selection and provenance')
    class ConfiguredAgent:
        name=adapter.name
        api_version=API_VERSION
        def command(self,prompt):
            argv=adapter.command(prompt)
            if self.name in ('codex','opencode','claude'):
                return [*argv[:-1],'--model='+model,argv[-1]]
            return argv
        def parse(self,stream):
            usage=adapter.parse(stream)
            usage.update(model=model,model_origin='requested_configuration')
            return usage
        def capabilities(self):
            return adapter.capabilities()
    return ConfiguredAgent()


def agent_capabilities():
    from dataclasses import asdict
    return {n: asdict(a.capabilities()) for n, a in _agents.items()}
