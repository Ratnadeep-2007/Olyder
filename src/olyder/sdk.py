"""Version-1 local Python SDK and vendor-neutral protected orchestration.

No paid calls occur unless use_ai or an executable builder is explicitly enabled.
The legacy engine functions remain import-compatible; new integrations use this
module to get detached verification, permission checks and durable run metadata.
"""
from __future__ import annotations

import copy
import hashlib
import json
import platform
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from .accounting import RuntimeAccounting
from .adapters import ExecutableAgent, get_agent
from .backends import get_backend
from .config import Spec, load_spec
from .control import Cancelled, RunControl, activate
from .engine import plan, verify_once
from .execution import ExecutionError, managed_run
from .policy import RunPolicy, progress
from .privacy import redact
from .quota import Budget, QuotaExceeded
from .report import save_report
from .research import collect
from .state import RunStore
from .workspace import ProtectedWorkspace, WorkspaceViolation, tree
from .impact import select_checks


@dataclass(frozen=True)
class Permissions:
    allow_exec: bool = False
    execute_builder: bool = False
    allow_network: bool = False
    unsafe_host: bool = False

    def __post_init__(self):
        if any(type(v) is not bool for v in asdict(self).values()):
            raise ValueError('Permissions require explicit booleans')


def _digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _execute(adapter, backend, workspace, prompt, timeout):
    command = [p.replace('{workspace}', str(workspace)) for p in adapter.command(prompt)]
    if adapter.name == 'codex':
        with tempfile.TemporaryFile(mode='w+t') as out:
            outcome = managed_run(['git','init','--quiet'], cwd=workspace, stdout=out, timeout=min(5,timeout))
            if outcome.returncode != 0:
                raise ExecutionError('Codex adapter requires a Git workspace')
    if backend.name == 'docker':
        command = [p.replace(str(workspace),'/workspace') for p in command]
    command = backend.prepare(command, workspace, writable=True)
    with tempfile.TemporaryFile(mode='w+t',encoding='utf-8',errors='replace') as out:
        outcome = managed_run(command,cwd=workspace,stdout=out,timeout=timeout)
        usage = adapter.parse(out)
    usage.update(origin='agent_jsonl', elapsed_seconds=outcome.elapsed_seconds)
    if outcome.timed_out:
        return usage, 'builder_timeout'
    if outcome.returncode != 0 or usage.get('status') == 'failed':
        return usage, 'builder_failed'
    return usage, None


def run(spec_path='olyder.json', *, permissions=None, backend='host', agent=None,
        mode=None, output=None, use_ai=False, docker_image='python:3.13-slim',
        docker_network='none', sink=None, model_provider=None, max_iterations=None,
        apply=True, trace_dir=None) -> dict:
    """Execute a bounded run; return structured uncertainty and artifact paths.

    Custom Python adapters/providers are trusted caller registrations. No plugin
    is discovered from the workspace implicitly. Docker is optional; unsafe host
    execution requires its own explicit grant, including when called from Python.
    """
    spec=load_spec(spec_path)
    permissions=permissions or Permissions()
    limits=spec.raw.get('limits',{})
    iterations=max_iterations if max_iterations is not None else limits.get('max_iterations',3)
    if type(iterations) is not int or not 1 <= iterations <= 20:
        raise ValueError('max_iterations must be between 1 and 20')
    selected_mode=mode or spec.raw.get('policy',{}).get('mode','balanced')
    policy=RunPolicy(selected_mode)
    store=RunStore(spec.root/'.olyder'/'runs')
    state=store.create({'spec_sha256':spec.digest,'spec_path':str(spec.path),
                        'phase':'initializing','cancel_requested':False})
    run_id=state['run_id']; run_dir=store.path(run_id)
    account=RuntimeAccounting(run_id,spec.raw.get('budget'))
    started=time.monotonic()
    deadline=started+limits.get('max_seconds',600)
    events=[]
    def emit(event):
        if len(events)<1000:
            events.append(event)
        if sink:
            sink(event)
    control=RunControl(deadline, cancelled=lambda: store.read(run_id).get('cancel_requested',False),
                       sink=emit, model_provider=model_provider)
    result={'goal':spec.goal,'spec_sha256':spec.digest,'run_id':run_id,'status':'blocked',
            'checks':[],'history':[],'stop_reason':'initialization_failed',
            'sources':[],'independent_critic_status':'not_requested', 'budget':{}}
    workspace=None
    def checkpoint(phase, **data):
        nonlocal state
        latest=store.read(run_id)
        state=store.update(run_id,latest['revision'],{'phase':phase,
            'accounting':account.snapshot(),'events':events,**data})
    try:
        with activate(control):
            if permissions.execute_builder and not permissions.allow_exec:
                raise PermissionError('Builder execution requires allow_exec')
            if docker_network != 'none' and not permissions.allow_network:
                raise PermissionError('Docker networking requires explicit network grant')
            if backend == 'host':
                execution=get_backend(backend,unsafe_authorized=permissions.unsafe_host)
            elif backend == 'docker':
                execution=get_backend(backend,image=docker_image,network=docker_network,
                    env_names=tuple(spec.raw.get('builder',{}).get('env',[])))
            else:
                execution=get_backend(backend)
            control.check_backend = get_backend('docker',image=docker_image) if backend == 'docker' else execution
            if permissions.execute_builder and not execution.capabilities().isolated and not permissions.unsafe_host:
                raise PermissionError('Unisolated builder requires explicit unsafe_host grant')
            if use_ai and account.ledger and money_zero(spec.raw.get('budget',{}).get('verifier_reserve_usd','0')):
                raise QuotaExceeded('Requested independent AI review needs a positive verifier reserve')
            control.check()
            workspace=ProtectedWorkspace(spec,run_dir/'workspace')
            contract=run_dir/'contract.json'
            contract.write_bytes(spec.path.read_bytes())
            if _digest(contract) != spec.digest:
                raise WorkspaceViolation('Contract changed during snapshot capture')
            manifest=workspace.evidence()
            checkpoint('ready',manifest_sha256=manifest['manifest_sha256'],contract_sha256=spec.digest,
                       execution_backend=backend,docker_image=docker_image)
            control.check()
            sources=collect(spec.raw.get('sources',[]),network_allowed=permissions.allow_network)
            control.check()
            builder=spec.raw.get('builder',{})
            name=agent or builder.get('provider')
            adapter=get_agent(name) if name else ExecutableAgent('generic',builder.get('argv') or ['false'])
            feedback='Implement the original goal. Do not create or modify acceptance assets.'
            previous=[]; stagnant=0; previous_tree={}; selections=[]
            token_budget=Budget(limits.get('max_tokens',30000))
            for number in range(1,iterations+1):
                control.check()
                if _digest(spec.path) != spec.digest:
                    raise WorkspaceViolation('Original contract changed')
                builder_stop=None
                reserve_only=permissions.execute_builder and not policy.admit_builder(deadline-time.monotonic())
                if permissions.execute_builder and not reserve_only:
                    ticket=account.admit('builder')
                    checkpoint('builder_started',attempt=number)
                    prompt=json.dumps({'goal':spec.goal,'tasks':plan(spec)['tasks'],
                        'feedback_untrusted':redact(feedback)[:8000],
                        'rules':'Implementation files only. Verifier assets are detached.'},ensure_ascii=False)
                    usage=None
                    try:
                        usage,builder_stop=_execute(adapter,execution,workspace.builder,prompt,
                            max(.01,min(180,deadline-time.monotonic()-policy.final_seconds)))
                    finally:
                        account.settle(ticket,usage)
                        checkpoint('builder_completed',proposal_digest=tree(workspace.builder))
                    cap=limits.get('max_agent_tokens')
                    if cap is not None and (not usage or not usage.get('usage_complete') or
                        sum(o.get('observed_tokens') or 0 for o in account.observations if o['role']=='builder')>cap):
                        builder_stop='agent_token_soft_cap'
                root=workspace.harness()
                trusted_before={n:h for n,h in tree(root).items() if workspace.is_protected(n)}
                verification_spec=Spec(contract,root,copy.deepcopy(spec.raw),spec.digest)
                # Preserve relative checks; absolute interpreter argv[0] is allowed.
                for check in verification_spec.checks:
                    if check['type']=='command':
                        for arg in check['argv'][1:]:
                            if Path(arg).is_absolute():
                                raise WorkspaceViolation('Protected checks require relative asset arguments')
                checkpoint('verifying',attempt=number)
                critic_ticket=None
                request_critic=use_ai and not builder_stop
                if request_critic:
                    critic_ticket=account.admit('critic')
                    checkpoint('critic_started',attempt=number)
                observations_start=len(control.model_observations)
                try:
                    proposed_tree=tree(workspace.builder)
                    changed={n for n in proposed_tree.keys()|previous_tree.keys() if proposed_tree.get(n)!=previous_tree.get(n)}
                    selected=None; selection_reason='full_suite_default'
                    if spec.raw.get('incremental') is True and number>1 and not request_critic:
                        selected,selection_reason=select_checks(spec.checks,changed,
                            {c['id'] for c in previous if c['status']!='pass'})
                    selections.append({'attempt':number,'selected':sorted(selected) if selected is not None else [c['id'] for c in spec.checks],
                                       'reason':selection_reason,'changed_files':sorted(changed)})
                    item=verify_once(verification_spec,allow_exec=permissions.allow_exec,
                        allow_network=permissions.allow_network,use_ai=request_critic,
                        budget=token_budget,deadline=deadline,source_evidence=sources,
                        only=selected,
                        sandbox=backend if backend in ('host','docker') else 'host',docker_image=docker_image,
                        trace_dir=Path(trace_dir) if trace_dir else None)
                    if selected is not None and item['checks'] and all(c['status']=='pass' for c in item['checks']):
                        selections[-1]['final_full_suite']=[c['id'] for c in spec.checks]
                        item=verify_once(verification_spec,allow_exec=permissions.allow_exec,
                            allow_network=permissions.allow_network,budget=token_budget,
                            deadline=deadline,source_evidence=sources,sandbox=backend if backend in ('host','docker') else 'host',
                            docker_image=docker_image)
                finally:
                    if critic_ticket:
                        observed=control.model_observations[observations_start:]
                        account.settle(critic_ticket,observed[-1] if observed else None)
                control.check()
                workspace.validate()
                if trusted_before != {n:h for n,h in tree(root).items() if workspace.is_protected(n)}:
                    raise WorkspaceViolation('Trusted acceptance assets changed during verification')
                delta=progress(previous,item['checks'])
                history=result['history']+[{'number':number,'status':item['status'],
                    'checks':item['checks'],'progress_delta':delta,'proposal_digest':tree(workspace.builder)}]
                result.update(item,history=history)
                checkpoint('verified',result=result,proposal_digest=tree(workspace.builder))
                if builder_stop:
                    result.update(status='blocked',stop_reason=builder_stop)
                    break
                if item['status']=='passed':
                    if apply and permissions.execute_builder:
                        workspace.apply()
                    result['stop_reason']='acceptance_passed'
                    break
                if reserve_only:
                    result['stop_reason']='final_verification_reserve';break
                if not permissions.execute_builder:
                    result['stop_reason']='verification_only';break
                if item['status'] in ('blocked','needs_review') or delta['regressions']:
                    result['stop_reason']='unresolved_verification';break
                stagnant=0 if delta['improved'] else stagnant+1
                if stagnant>policy.no_progress_limit:
                    result['stop_reason']='no_progress';break
                previous=item['checks']
                previous_tree=proposed_tree
                failed=[{'check_id':c['id'],'status':c['status'],'evidence':c['details'][:1200]}
                    for c in item['checks'] if c['status']!='pass']
                feedback=json.dumps({'repair':failed,'rule':'Do not weaken requirements or tests'})
            else:
                result['stop_reason']='iteration_limit'
    except QuotaExceeded as exc:
        result.update(status='budget_exhausted',stop_reason='budget_admission',verifier_note=redact(str(exc)))
    except WorkspaceViolation as exc:
        result.update(status='blocked',stop_reason='integrity_violation',verifier_note=redact(str(exc)))
    except (Cancelled,KeyboardInterrupt):
        result.update(status='cancelled',stop_reason='user_cancelled')
    except (OSError,RuntimeError,ValueError) as exc:
        result.update(status='blocked',stop_reason='execution_blocked',verifier_note=redact(str(exc))[:1000])
    result.update(run_id=run_id,attempts=len(result['history']),accounting=account.snapshot(),
        budget_verdict=account.snapshot()['budget_verdict'],functional_verdict=result['status'],
        wall_seconds=time.monotonic()-started,policy={'mode':selected_mode,'full_final_suite_required':True},
        verification_selection=locals().get('selections',[]),
        environment={'python':platform.python_version(),'platform':platform.system()},
        execution_isolation={'mode':backend,'unsafe_host_authorized':permissions.unsafe_host,
                             'protected_assets_detached':workspace is not None})
    if workspace:
        result['acceptance_integrity']=workspace.evidence()
    checkpoint('completed',result=result)
    result['paths']=save_report(result,Path(output) if output else spec.root/'.olyder')
    return result


def money_zero(value):
    from .ledger import money
    return money(value)==0


def resume(run_id, workspace='.', *, permissions=None, output=None, recover=False):
    """Reverify a durable proposal; never replay a builder or a paid model call.

    In-flight builder/critic requests require external billing/process
    reconciliation and are deliberately not automatically resumed. Explicit
    recover permits a saved, completed proposal after an interrupted verifier.
    """
    store=RunStore(Path(workspace).resolve()/'.olyder'/'runs')
    state=store.read(run_id)
    if state.get('phase') not in ('completed',) and not (
            recover and state.get('phase') in ('builder_completed','verified')):
        return {'run_id':run_id,'status':'blocked','stop_reason':'uncertain_inflight_execution',
                'accounting':state.get('accounting'), 'replayed_builder':False}
    contract=store.path(run_id)/'contract.json'
    try:
        if _digest(contract)!=state.get('spec_sha256'):
            raise WorkspaceViolation('Contract digest changed')
        original=Path(state['spec_path'])
        if _digest(original)!=state['spec_sha256']:
            raise WorkspaceViolation('Original requirements changed; start a new run')
        saved=ProtectedWorkspace.reopen(store.path(run_id)/'workspace',state['manifest_sha256'])
        if tree(saved.builder)!=state.get('proposal_digest',tree(saved.builder)):
            raise WorkspaceViolation('Saved proposal changed')
        root=saved.harness()
        spec=load_spec(contract)
        spec=Spec(contract,root,spec.raw,spec.digest)
        permissions=permissions or Permissions()
        isolation=state.get('execution_backend','host')
        if isolation not in ('host','docker'):
            raise WorkspaceViolation('Custom backend recovery requires explicit integration')
        # Saved paid requests are never resumed or re-settled.
        state=store.update(run_id,state['revision'],{'phase':'resume_started'})
        before={n:h for n,h in tree(root).items() if saved.is_protected(n)}
        item=verify_once(spec,allow_exec=permissions.allow_exec,allow_network=permissions.allow_network,
                         sandbox=isolation,docker_image=state.get('docker_image','python:3.13-slim'),
                         deadline=time.monotonic()+spec.raw.get('limits',{}).get('max_seconds',600))
        saved.validate()
        if before!={n:h for n,h in tree(root).items() if saved.is_protected(n)}:
            raise WorkspaceViolation('Verifier changed protected inputs during resume')
        item.update(run_id=run_id,resumed_verification_only=True,replayed_builder=False,
                    accounting=state.get('accounting'),stop_reason='resume_verification')
    except (OSError,ValueError,RuntimeError) as exc:
        item={'run_id':run_id,'status':'blocked','stop_reason':'resume_integrity_or_state',
              'verifier_note':redact(str(exc))[:1000]}
    item['paths']=save_report(item,Path(output) if output else store.path(run_id)/'resume-report')
    latest=store.read(run_id)
    store.update(run_id,latest['revision'],{'phase':'completed','last_resume_result':item})
    return item
