"""Executable offline paired pilot. No model simulation is billed usage.

The baseline source is extracted from a pinned, already-local Git commit. Both
runners execute identical fixture builders and oracle scripts in disposable
directories. These tasks do not represent SWE-bench/Harbor or model quality.
"""
import io
import json
import os
import platform
import statistics
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

BASELINE='99b86067c7e676ca1cecc55ecd83f4ba9fe69109'


def scenarios():
    return [
        {'id': 'calculation','source': 'def add(a,b): return a-b','repair': 'def add(a,b): return a+b','oracle': 'from app import add;assert add(2,3)==5','expected': 'passed'},
        {'id': 'api-input','source': 'def validate(x): return x','repair': "def validate(x):\n if not isinstance(x,int): raise ValueError('invalid')\n return x",'oracle': "from app import validate\ntry: validate('bad')\nexcept ValueError: pass\nelse: raise AssertionError('invalid input accepted')",'expected': 'passed'},
        {'id': 'cli-exception','source': 'def status(): return 1','repair': 'def status(): return 2','oracle': 'from app import status;assert status()==2','expected': 'passed'},
        {'id': 'hidden-regression','source': 'def add(a,b): return a-b','repair': 'def add(a,b): return 5','oracle': 'from app import add;assert add(2,3)==5;assert add(-1,2)==1','expected': 'failed'},
        {'id': 'spec-tamper','source': 'value=0','repair': 'value=1','oracle': 'from app import value;assert value==1','expected': 'blocked','tamper': True},
        {'id': 'stuck-loop','source': 'value=0','repair': 'value=0','oracle': 'from app import value;assert value==1','expected': 'failed'},
        {'id': 'small-budget','source': 'value=0','repair': 'value=1','oracle': 'from app import value;assert value==1','expected': 'budget_exhausted','budget': True},
        {'id': 'missing-usage','source': 'value=0','repair': 'value=1','oracle': 'from app import value;assert value==1','expected': 'passed'},
        {'id': 'browser-dependent','source': 'value=0','repair': 'value=1','oracle': 'assert True','expected': 'blocked','browser': True},
        {'id': 'python-json-integration','source': 'value=0','repair': 'value=42','oracle': "import json;from app import value;assert json.loads(json.dumps({'value':value}))['value']==42",'expected': 'passed'},
        {'id': 'range-boundary','source': 'def values(n): return list(range(n-1))','repair': 'def values(n): return list(range(n))','oracle': 'from app import values;assert values(3)==[0,1,2];assert values(0)==[]','expected': 'passed'},
    ]


def benchmark(output, *, repetitions=3, task_ids=None, repository=None):
    if type(repetitions) is not int or not 1<=repetitions<=10:
        raise ValueError('Pilot repetitions must be between 1 and 10')
    repo=Path(repository or Path.cwd()).resolve()
    current_source=Path(__file__).resolve().parents[1]
    archive=subprocess.run(['git','archive','--format=zip',BASELINE,'src/olyder'],
                           cwd=repo,check=True,capture_output=True,timeout=30).stdout
    rows=[]
    with tempfile.TemporaryDirectory(prefix='olyder-bench-') as temp:
        temp=Path(temp); baseline=temp/'baseline';baseline.mkdir()
        with zipfile.ZipFile(io.BytesIO(archive)) as z:
            for info in z.infolist():
                target=(baseline/info.filename).resolve()
                if not target.is_relative_to(baseline.resolve()):
                    raise ValueError('Unsafe baseline archive')
            z.extractall(baseline)
        for case in scenarios():
            if task_ids is not None and case['id'] not in task_ids:
                continue
            for repetition in range(repetitions):
                for mode in ('v0.4','economy','balanced','thorough'):
                    root=temp/f"{case['id']}-{repetition}-{mode}";root.mkdir()
                    if case.get('browser'):
                        rows.append({'task':case['id'],'repetition':repetition,'mode':mode,
                                     'status':'skipped','reason':'No live browser service fixture; not replaced with a fake browser',
                                     'actual_usd':None})
                        continue
                    (root/'app.py').write_text(case['source'],encoding='utf-8')
                    (root/'acceptance_oracle.py').write_text(case['oracle'],encoding='utf-8')
                    repair="from pathlib import Path;Path('app.py').write_text("+repr(case['repair'])+")"
                    if case.get('tamper'):
                        repair="from pathlib import Path;Path('acceptance_oracle.py').write_text('pass')"
                    config={'goal':case['id'],'checks':[{'id':'oracle','type':'command',
                            'argv':[sys.executable,'acceptance_oracle.py'],'timeout':5}],
                            'builder':{'argv':[sys.executable,'-c',repair]},
                            'limits':{'max_iterations':4,'max_seconds':30}}
                    if case.get('budget'):
                        config['budget']={'max_cost_usd':'0.01','builder_upper_bound_usd':'1'}
                    path=root/'olyder.json';path.write_text(json.dumps(config))
                    if mode=='v0.4':
                        script="from olyder.config import load_spec;from olyder.engine import run_loop;from pathlib import Path;import json;print(json.dumps(run_loop(load_spec('olyder.json'),allow_exec=True,execute_builder=True,use_ai=False,allow_network=False,output=Path('.olyder'))))"
                    else:
                        script="from olyder.sdk import run,Permissions;import json;print(json.dumps(run('olyder.json',permissions=Permissions(allow_exec=True,execute_builder=True,unsafe_host=True),mode="+repr(mode)+")))"
                    env={**os.environ,'PYTHONPATH':str(baseline/'src' if mode=='v0.4' else current_source)}
                    start=time.monotonic()
                    execution=subprocess.run([sys.executable,'-c',script],cwd=root,env=env,check=False,
                        capture_output=True,text=True,timeout=45,encoding='utf-8',errors='replace')
                    data=json.loads(execution.stdout) if execution.returncode==0 else {'status':'execution_error','attempts':0}
                    expected=case['expected']
                    # v0.4 has no monetary admission; keep its unsupported case
                    # visible rather than pretending it supports the new policy.
                    rows.append({'task':case['id'],'mode':mode,'repetition':repetition,
                        'status':data['status'],'expected':expected,'matched':data['status']==expected,
                        'false_pass':data['status']=='passed' and expected in ('failed','blocked'),
                        'seconds':time.monotonic()-start,'attempts':data.get('attempts'),
                        'check_ms':data.get('metrics',{}).get('total_check_duration_ms'),
                        'actual_usd':None,'provider_usage':'not_applicable_fake_agent',
                        'recovery_behavior':'covered_separately_by_checkpoint_tests'})
    summary={}
    for mode in ('v0.4','economy','balanced','thorough'):
        group=[r for r in rows if r['mode']==mode and r['status']!='skipped']
        summary[mode]={'executed':len(group),'expected_outcomes':sum(r['matched'] for r in group),
            'false_passes':sum(r['false_pass'] for r in group),
            'verified_solved':sum(r['status']=='passed' for r in group),
            'median_seconds':statistics.median(r['seconds'] for r in group) if group else None,
            'actual_usd':None,'verified_solves_per_actual_usd':None}
    report={'schema_version':1,'kind':'offline_paired_pilot','baseline_commit':BASELINE,
            'python':platform.python_version(),'platform':platform.platform(),
            'repetitions':repetitions,'deadline_seconds':30,'seed':'deterministic',
            'actual_provider_usd':None,'cost_savings_claim':'inconclusive',
            'live_provider_runs':0,'official_benchmark_harnesses':'not_run',
            'rows':rows,'summary':summary}
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    return report
