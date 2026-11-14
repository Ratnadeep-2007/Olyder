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
from .adapters import ExecutableAgent, bind_model, get_agent
from .backends import get_backend
from .config import Spec, load_spec
from .control import Cancelled, ResourceLimit, RunControl, activate, current
from .engine import _independent_review, plan, verify_once
from .execution import ExecutionError, managed_run
from .impact import select_checks
from .models import ModelError
from .policy import RunPolicy, progress
from .privacy import redact
from .quota import Budget, QuotaExceeded
from .report import save_report
from .research import collect
from .state import RunStore
from .workspace import ProtectedWorkspace, WorkspaceViolation, file_modes, tree


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


def _checker_digest():
    digest=hashlib.sha256()
    for name in ('sdk.py','checks.py','contracts.py','engine.py','workspace.py','execution.py'):
        digest.update(name.encode());digest.update(Path(__file__).with_name(name).read_bytes())
    return digest.hexdigest()


def _execute(adapter, backend, workspace, prompt, timeout):
    command = [p.replace('{workspace}', str(workspace)) for p in adapter.command(prompt)]
    if getattr(adapter.capabilities(),'requires_git',False) and not (workspace/'.git').exists():
        with tempfile.TemporaryFile(mode='w+t') as out:
            outcome = managed_run(['git','init','--quiet'], cwd=workspace, stdout=out, timeout=min(5,timeout))
            if outcome.returncode != 0:
                raise ExecutionError('Selected agent requires a Git workspace')
    preparation=getattr(backend,'prepare_detached',None)
    if preparation:
        preparation(workspace,writable=True)
    command = backend.prepare(command, workspace, writable=True)
    with (
        tempfile.TemporaryDirectory(prefix='olyder-private-log-') as logs,
        open(Path(logs)/'agent.log','w+',encoding='utf-8',errors='replace') as out,
        open(Path(logs)/'agent.log',encoding='utf-8',errors='replace') as reader,
    ):
        control=current.get()
        previous_poll=control.poll_output if control else None
        pending=''
        def poll():
            nonlocal pending
            pending+=reader.read(131072)
            while '\n' in pending:
                line,pending=pending.split('\n',1)
                try:
                    event=json.loads(line)
                    kind=event.get('type') if isinstance(event,dict) else None
                    if kind in ('turn.started','turn.completed','turn.failed','step_start','step_finish','result','error','text'):
                        control.emit('agent_event',event_type=kind)
                except (ValueError,TypeError):
                    continue
            if len(pending)>1_000_000:
                pending=''
        if control:
            control.poll_output=poll
        try:
            outcome = managed_run(command,cwd=workspace,stdout=out,timeout=timeout)
            usage = adapter.parse(out)
        finally:
            if control:
                control.poll_output=previous_poll
    usage.update(origin='agent_jsonl', elapsed_seconds=outcome.elapsed_seconds)
    if outcome.timed_out:
        return usage, 'builder_timeout'
    if outcome.returncode != 0 or usage.get('status') == 'failed':
        return usage, 'builder_failed'
    return usage, None


def run(spec_path='olyder.json', *, permissions=None, backend='host', agent=None,
        mode=None, output=None, use_ai=False, docker_image='python:3.13-slim',
        docker_network='none', sink=None, model_provider=None, max_iterations=None,
        apply=True, trace_dir=None, exporters=()) -> dict:
    """Execute a bounded run; return structured uncertainty and artifact paths.

    Custom Python adapters/providers are trusted caller registrations. No plugin
    is discovered from the workspace implicitly. Docker is optional; unsafe host
    execution requires its own explicit grant, including when called from Python.
    """
    spec=load_spec(spec_path)
    permissions=permissions or Permissions()
    if not isinstance(permissions,Permissions) or type(use_ai) is not bool or type(apply) is not bool:
        raise ValueError('SDK permissions and consent flags require explicit typed values')
    if sink is not None and not callable(sink):
        raise ValueError('Event sink must be callable')
    limits=spec.raw.get('limits',{})
    iterations=max_iterations if max_iterations is not None else limits.get('max_iterations',3)
    if type(iterations) is not int or not 1 <= iterations <= 20:
        raise ValueError('max_iterations must be between 1 and 20')
    selected_mode=mode or spec.raw.get('policy',{}).get('mode','balanced')
    policy=RunPolicy(selected_mode)
    (spec.root/'.olyder').mkdir(mode=0o700,exist_ok=True)
    store=RunStore(spec.root/'.olyder'/'runs')
    state=store.create({'spec_sha256':spec.digest,'spec_path':str(spec.path),
                        'checker_sha256':_checker_digest(),
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
    result={'schema_version':2,'goal':spec.goal,'spec_sha256':spec.digest,'run_id':run_id,'status':'blocked',
            'checker_sha256':state['checker_sha256'],
            'checks':[],'history':[],'stop_reason':'initialization_failed',
            'sources':[],'independent_critic_status':'not_requested', 'budget':{}}
    workspace=None
    application_status='not_attempted'
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
            if use_ai and permissions.execute_builder and account.ledger and money_zero(spec.raw.get('budget',{}).get('verifier_reserve_usd','0')):
                raise QuotaExceeded('Requested independent AI review needs a positive verifier reserve')
            control.check()
            workspace=ProtectedWorkspace(spec,run_dir/'workspace')
            contract=run_dir/'contract.json'
            contract.write_bytes(spec.path.read_bytes())
            if _digest(contract) != spec.digest:
                raise WorkspaceViolation('Contract changed during snapshot capture')
            manifest=workspace.evidence()
            checkpoint('ready',manifest_sha256=manifest['manifest_sha256'],contract_sha256=spec.digest,
                       execution_backend=backend,docker_image=docker_image,ai_review_required=use_ai)
            control.check()
            research_started=time.monotonic()
            sources=collect(spec.raw.get('sources',[]),network_allowed=permissions.allow_network)
            research_seconds=time.monotonic()-research_started
            control.check()
            builder=spec.raw.get('builder',{})
            name=agent or builder.get('provider')
            adapter=get_agent(name) if name else ExecutableAgent('generic',builder.get('argv') or ['false'])
            adapter=bind_model(adapter,builder.get('model'))
            feedback='Implement the original goal. Do not create or modify acceptance assets.'
            previous=[]; stagnant=0; previous_tree={}; selections=[]; test_ms=0; executed_count=0
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
                preparation=getattr(control.check_backend,'prepare_detached',None)
                if preparation:
                    preparation(root,writable=False)
                input_before=tree(root)
                modes_before=file_modes(root,input_before)
                trusted_before={n:h for n,h in input_before.items() if workspace.is_protected(n)}
                verification_spec=Spec(contract,root,copy.deepcopy(spec.raw),spec.digest)
                # Preserve relative checks; absolute interpreter argv[0] is allowed.
                for check in verification_spec.checks:
                    if check['type']=='command':
                        for arg in check['argv'][1:]:
                            if Path(arg).is_absolute():
                                raise WorkspaceViolation('Protected checks require relative asset arguments')
                checkpoint('verifying',attempt=number,proposal_digest=tree(workspace.builder))
                critic_ticket=None
                request_critic=False
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
                    test_ms+=item['metrics']['total_check_duration_ms']
                    executed_count+=item['metrics']['executed_checks']
                    if selected is not None and selected!={c['id'] for c in spec.checks} and item['checks'] and all(c['status']=='pass' for c in item['checks']):
                        selections[-1]['final_full_suite']=[c['id'] for c in spec.checks]
                        item=verify_once(verification_spec,allow_exec=permissions.allow_exec,
                            allow_network=permissions.allow_network,budget=token_budget,
                            deadline=deadline,source_evidence=sources,sandbox=backend if backend in ('host','docker') else 'host',
                            docker_image=docker_image)
                        test_ms+=item['metrics']['total_check_duration_ms']
                        executed_count+=item['metrics']['executed_checks']
                    if use_ai and not builder_stop:
                        if item['status']=='passed':
                            try:
                                critic_ticket=account.admit('critic')
                            except QuotaExceeded:
                                item.update(status='needs_review',independent_critic_status='budget_unavailable',
                                    verifier_note='Mandatory tests passed; requested AI review has no admissible budget')
                            else:
                                checkpoint('critic_started',attempt=number)
                                observations_start=len(control.model_observations)
                                try:
                                    note,concerns=_independent_review(verification_spec,item['checks'],token_budget,ai=True)
                                    item.update(verifier_note=note,ai_concerns=concerns,independent_critic_status='completed')
                                    if concerns:
                                        item['status']='needs_review'
                                except (ModelError,QuotaExceeded):
                                    item.update(status='needs_review',independent_critic_status='unavailable',
                                        verifier_note='Requested AI review could not complete')
                        else:
                            item['independent_critic_status']='not_run_incomplete_verification'
                finally:
                    if critic_ticket:
                        observed=control.model_observations[observations_start:]
                        account.settle(critic_ticket,observed[-1] if observed else None)
                control.check()
                if _digest(spec.path)!=spec.digest:
                    raise WorkspaceViolation('Original contract changed during verification')
                workspace.validate()
                input_after=tree(root)
                if trusted_before != {n:h for n,h in input_after.items() if workspace.is_protected(n)}:
                    raise WorkspaceViolation('Trusted acceptance assets changed during verification')
                if any(input_after.get(n)!=h for n,h in input_before.items()):
                    raise WorkspaceViolation('Verifier modified implementation inputs; proposal was not verified unchanged')
                if file_modes(root,input_before)!=modes_before:
                    raise WorkspaceViolation('Verifier modified input file permissions')
                delta=progress(previous,item['checks'])
                delta.update(changed_files=sorted(changed),failure_signature=hashlib.sha256(
                    json.dumps([(c['id'],c['status'],redact(c['details'])) for c in item['checks'] if c['status']!='pass'],sort_keys=True).encode()).hexdigest())
                history=result['history']+[{'number':number,'status':item['status'],
                    'checks':item['checks'],'progress_delta':delta,'code_diff_hash':hashlib.sha256(
                        json.dumps(proposed_tree,sort_keys=True).encode()).hexdigest()}]
                result.update(item,history=history)
                checkpoint('verified',result=result,proposal_digest=tree(workspace.builder))
                if builder_stop:
                    result.update(status='blocked',stop_reason=builder_stop)
                    break
                if item['status']=='passed':
                    if apply and permissions.execute_builder:
                        control.check()
                        application_status='partial_or_failed'
                        workspace.apply()
                        application_status='complete'
                        control.check()
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
                by_check={c['id']:c for c in spec.checks}
                for failure in failed:
                    declared=by_check[failure['check_id']]
                    failure.update(affected_paths=declared.get('paths',[]),
                                   depends_on=declared.get('depends_on',[]))
                feedback=json.dumps({'repair':failed,'rule':'Do not weaken requirements or tests'})
            else:
                result['stop_reason']='iteration_limit'
    except QuotaExceeded as exc:
        result.update(status='budget_exhausted',stop_reason='budget_admission',verifier_note=redact(str(exc)))
    except WorkspaceViolation as exc:
        result.update(status='blocked',stop_reason='integrity_violation',verifier_note=redact(str(exc)))
    except ResourceLimit:
        result.update(status='blocked',stop_reason='resource_limit')
    except (Cancelled,KeyboardInterrupt):
        result.update(status='cancelled',stop_reason='user_cancelled')
    except TimeoutError:
        result.update(status='blocked',stop_reason='deadline_exhausted')
    except (OSError,RuntimeError,ValueError) as exc:
        result.update(status='blocked',stop_reason='execution_blocked',verifier_note=redact(str(exc))[:1000])
    agent_runs=[o for o in account.observations if o['role']=='builder']
    result.update(run_id=run_id,attempts=len(result['history']),accounting=account.snapshot(),
        task_plan=plan(spec),agent_usage={'runs':agent_runs,
            'observed_tokens':sum(o['observed_tokens'] for o in agent_runs) if agent_runs and all(o.get('usage_complete') and o.get('observed_tokens') is not None for o in agent_runs) else None,
            'complete':bool(agent_runs) and all(o.get('usage_complete',False) for o in agent_runs),
            'enforced_provider_quota':False},
        repaired_check_ids=sorted({identifier for attempt in result['history']
            for identifier in attempt.get('progress_delta',{}).get('newly_passing',[])}),
        budget_verdict=account.snapshot()['budget_verdict'],functional_verdict=result['status'],
        wall_seconds=time.monotonic()-started,policy={'mode':selected_mode,'full_final_suite_required':True,
            'selected_by':'explicit_override' if mode else 'spec_policy' if spec.raw.get('policy',{}).get('mode') else 'balanced_default',
            'final_time_reserve_seconds':policy.final_seconds,'enforcement_kind':'local_soft'},
        verification_selection=locals().get('selections',[]),
        resource_usage={'deterministic_check_ms':locals().get('test_ms',0),
                        'executed_checks':locals().get('executed_count',0),
                        'research_seconds':locals().get('research_seconds',0)},
        environment={'python':platform.python_version(),'platform':platform.system()},
        application_status=application_status,verification_target='detached_proposal',
        warnings=['Host execution has no OS containment'] if backend=='host' else [],
        execution_isolation={'mode':backend,'unsafe_host_authorized':permissions.unsafe_host,
                             'protected_assets_detached':workspace is not None,
                             'http_browser_checks':'host','trusted_python_callbacks':'host'})
    if workspace:
        result['acceptance_integrity']=workspace.evidence()
        result['artifact_refs']={'contract':str(run_dir/'contract.json'),
                                'manifest':str(workspace.state/'manifest.json'),
                                'proposal':str(workspace.builder),'harness':str(workspace.verify_root)}
    if control.observer_errors:
        result['warnings'].append('Event observer failures: '+', '.join(control.observer_errors))
    result['paths']={}
    try:
        result['paths']=save_report(result,Path(output) if output else spec.root/'.olyder')
        for name in exporters:
            if not isinstance(name,str) or not name.replace('-','_').isidentifier():
                raise ValueError('Invalid exporter name')
            from .plugins import export
            destination=Path(result['paths']['json']).parent/(name+'.txt')
            destination.write_text(export(name,result),encoding='utf-8')
            result['paths'][name]=str(destination)
        result['artifact_status']='complete'
        if time.monotonic()>=deadline and result['status']=='passed':
            result.update(status='blocked',stop_reason='deadline_exhausted_during_artifacts')
            save_report(result,Path(output) if output else spec.root/'.olyder')
    except Exception as exc:  # noqa: BLE001 -- terminal execution evidence must survive exporter/IO failures
        result.update(artifact_status='failed',artifact_error=type(exc).__name__,
                      status='blocked',execution_stop_reason=result['stop_reason'],stop_reason='artifact_generation_failed')
    finally:
        result['wall_seconds']=time.monotonic()-started
        checkpoint('completed',result=result)
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
    resumed_started=time.monotonic()
    store=RunStore(Path(workspace).resolve()/'.olyder'/'runs')
    state=store.read(run_id)
    if state.get('phase') not in ('completed',) and not (
            recover and state.get('phase') in ('builder_completed','verified','verifying')):
        return {'run_id':run_id,'status':'blocked','stop_reason':'uncertain_inflight_execution',
                'accounting':state.get('accounting'), 'replayed_builder':False}
    contract=store.path(run_id)/'contract.json'
    try:
        if state.get('checker_sha256')!=_checker_digest():
            raise WorkspaceViolation('Verifier implementation changed; start fresh verification')
        if _digest(contract)!=state.get('spec_sha256'):
            raise WorkspaceViolation('Contract digest changed')
        original=Path(state['spec_path'])
        if original.parent.resolve()!=Path(workspace).resolve():
            raise WorkspaceViolation('Saved specification escapes selected workspace')
        if _digest(original)!=state['spec_sha256']:
            raise WorkspaceViolation('Original requirements changed; start a new run')
        saved=ProtectedWorkspace.reopen(store.path(run_id)/'workspace',state['manifest_sha256'])
        if saved.root.resolve()!=Path(workspace).resolve():
            raise WorkspaceViolation('Saved proposal belongs to another workspace')
        if 'proposal_digest' not in state or tree(saved.builder)!=state['proposal_digest']:
            raise WorkspaceViolation('Saved proposal changed')
        root=saved.harness()
        spec=load_spec(contract)
        spec=Spec(contract,root,spec.raw,spec.digest)
        permissions=permissions or Permissions()
        isolation=state.get('execution_backend','host')
        if isolation not in ('host','docker'):
            raise WorkspaceViolation('Custom backend recovery requires explicit integration')
        # Saved paid requests are never resumed or re-settled.
        state=store.update(run_id,state['revision'],{'phase':'resume_started','cancel_requested':False})
        input_before=tree(root)
        modes_before=file_modes(root,input_before)
        before={n:h for n,h in input_before.items() if saved.is_protected(n)}
        control=RunControl(resumed_started+spec.raw.get('limits',{}).get('max_seconds',600),
                           cancelled=lambda:store.read(run_id).get('cancel_requested',False))
        control.check_backend=get_backend('docker',image=state.get('docker_image','python:3.13-slim')) if isolation=='docker' else get_backend('host')
        with activate(control):
            control.check()
            preparation=getattr(control.check_backend,'prepare_detached',None)
            if preparation:
                preparation(root,writable=False)
            item=verify_once(spec,allow_exec=permissions.allow_exec,allow_network=permissions.allow_network,
                             sandbox=isolation,docker_image=state.get('docker_image','python:3.13-slim'),deadline=control.deadline)
            control.check()
        saved.validate()
        input_after=tree(root)
        if before!={n:h for n,h in input_after.items() if saved.is_protected(n)}:
            raise WorkspaceViolation('Verifier changed protected inputs during resume')
        if any(input_after.get(n)!=h for n,h in input_before.items()):
            raise WorkspaceViolation('Verifier modified proposal inputs during resume')
        if file_modes(root,input_before)!=modes_before:
            raise WorkspaceViolation('Verifier modified proposal input permissions during resume')
        item.update(run_id=run_id,resumed_verification_only=True,replayed_builder=False,
                    verification_target='checkpointed_proposal',application_status='not_attempted',
                    accounting=state.get('accounting'),stop_reason='resume_verification')
        if state.get('ai_review_required') and item['status']=='passed':
            item.update(status='needs_review',independent_critic_status='not_replayed_requires_review')
    except (Cancelled,KeyboardInterrupt):
        item={'run_id':run_id,'status':'cancelled','stop_reason':'user_cancelled'}
    except (OSError,ValueError,RuntimeError) as exc:
        item={'run_id':run_id,'status':'blocked','stop_reason':'resume_integrity_or_state',
              'verifier_note':redact(str(exc))[:1000]}
    item['paths']=save_report(item,Path(output) if output else store.path(run_id)/'resume-report')
    latest=store.read(run_id)
    store.update(run_id,latest['revision'],{'phase':'completed','last_resume_result':item})
    return item
