import json
import sys

import pytest

from olyder.cli import main
from olyder.plugins import load_agent_manifest
from olyder.sdk import run


def test_plugin_requires_explicit_grant(tmp_path):
    path=tmp_path/'plugin.json'
    path.write_text(json.dumps({'api_version':1,'kind':'agent','name':'external-fixture',
        'argv':[sys.executable,'-c','print(1)'],'permissions':['execute','write_workspace']}))
    with pytest.raises(PermissionError):
        load_agent_manifest(path,grants=set())
    assert load_agent_manifest(path,grants={'external-fixture'}).name=='external-fixture'


@pytest.mark.parametrize('version,kind', [(2,'agent'),(1,'unsafe-import')])
def test_incompatible_plugin_rejected(tmp_path,version,kind):
    path=tmp_path/'p.json';path.write_text(json.dumps({'api_version':version,'kind':kind,'name':'bad'}))
    with pytest.raises(ValueError):
        load_agent_manifest(path,grants={'bad'})


def test_cli_doctor(capsys):
    assert main(['doctor'])==0
    result=json.loads(capsys.readouterr().out)
    assert 'agents' in result and result['schema_version']==1


def test_cli_status_cancel_report(tmp_path,capsys):
    (tmp_path/'value').write_text('ok')
    path=tmp_path/'olyder.json';path.write_text(json.dumps({'goal':'ok','checks':[
        {'id':'ok','type':'file','path':'value'}]}))
    result=run(path)
    for command in ('status','cancel','report'):
        assert main([command,result['run_id'],'--workspace',str(tmp_path)])==0
        assert json.loads(capsys.readouterr().out)


def test_read_api_rejects_unknown_token(tmp_path):
    from olyder.api import dispatch
    assert dispatch('/v1/plan','wrong','token',tmp_path)[0]==401
    assert dispatch('/v1/not-a-command','token','token',tmp_path)[0]==404


def test_loopback_api_startup_does_not_resolve_dns(tmp_path,monkeypatch):
    import socket
    from olyder.api import create_server
    def forbidden_lookup(*args):
        raise AssertionError('Fixed loopback service must not depend on reverse DNS')
    monkeypatch.setattr(socket,'getfqdn',forbidden_lookup)
    with create_server(tmp_path,token='FAKE_LOCAL_API_TOKEN_123456789',port=0) as server:
        assert server.server_address[0]=='127.0.0.1' and server.server_port>0


@pytest.mark.parametrize('data', [[], {'api_version':1,'kind':'agent','name':'x','permissions':[{}]},
    {'api_version':1,'kind':'agent','name':'x','permissions':['execute','write_workspace'],'argv':['python'],'telemetry':'unsupported'}])
def test_malformed_plugin_contract_is_rejected(tmp_path,data):
    path=tmp_path/'bad.json';path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        load_agent_manifest(path,grants={'x'})


def test_live_read_api(tmp_path):
    import subprocess
    import time
    import urllib.request
    import urllib.error
    path=tmp_path/'olyder.json';path.write_text(json.dumps({'goal':'read','checks':[
        {'id':'file','type':'file','path':'olyder.json'}]}))
    token='FAKE_LOCAL_API_TOKEN_123456789'
    ready=tmp_path/'api.ready'
    script=(f'import sys;print("starting",file=sys.stderr,flush=True);'
            f'from olyder.api import create_server;from pathlib import Path;'
            f'print("imported",file=sys.stderr,flush=True);'
            f'server=create_server({str(tmp_path)!r},token={token!r},port=0);'
            f'Path({str(ready)!r}).write_text(str(server.server_port));server.serve_forever()')
    log=(tmp_path/'api.stderr').open('w+')
    process=subprocess.Popen([sys.executable,'-c',script],stdout=subprocess.DEVNULL,stderr=log)
    try:
        deadline=time.monotonic()+5
        while not ready.exists():
            if process.poll() is not None or time.monotonic()>deadline:
                log.seek(0)
                pytest.fail('API readiness failed: '+log.read())
            time.sleep(.05)
        port=int(ready.read_text())
        while True:
            try:
                request=urllib.request.Request(f'http://127.0.0.1:{port}/v1/verify',headers={'Authorization':'Bearer '+token})
                with urllib.request.urlopen(request,timeout=1) as response:
                    assert json.load(response)['status']=='passed'
                break
            except urllib.error.URLError:
                if process.poll() is not None:
                    log.seek(0)
                    pytest.fail('API process exited: '+log.read())
                if time.monotonic()>deadline:
                    raise
                time.sleep(.05)
        with pytest.raises(urllib.error.HTTPError) as denied:
            urllib.request.urlopen(f'http://127.0.0.1:{port}/v1/verify',timeout=1)
        assert denied.value.code==401
    finally:
        process.terminate();process.wait(timeout=5);log.close()


def test_mcp_run_requires_server_side_grant(tmp_path):
    from olyder.mcp import process
    from olyder.sdk import Permissions
    path=tmp_path/'olyder.json';path.write_text(json.dumps({'goal':'write','builder':{
        'argv':[sys.executable,'-c',"from pathlib import Path;Path('value').write_text('ok')"]},
        'checks':[{'id':'ok','type':'file','path':'value'}]}))
    request={'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':'olyder_run'}}
    assert 'error' in process(request,tmp_path)
    granted=process(request,tmp_path,run_permissions=Permissions(allow_exec=True,execute_builder=True,unsafe_host=True))
    assert json.loads(granted['result']['content'][0]['text'])['status']=='passed'
