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


def test_live_read_api(tmp_path):
    import os
    import socket
    import subprocess
    import time
    import urllib.request
    import urllib.error
    path=tmp_path/'olyder.json';path.write_text(json.dumps({'goal':'read','checks':[
        {'id':'file','type':'file','path':'olyder.json'}]}))
    with socket.socket() as listener:
        listener.bind(('127.0.0.1',0));port=listener.getsockname()[1]
    token='FAKE_LOCAL_API_TOKEN_123456789'
    script=f'from olyder.api import serve;serve({str(tmp_path)!r},token={token!r},port={port})'
    process=subprocess.Popen([sys.executable,'-c',script],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        deadline=time.monotonic()+5
        while True:
            try:
                request=urllib.request.Request(f'http://127.0.0.1:{port}/v1/verify',headers={'Authorization':'Bearer '+token})
                with urllib.request.urlopen(request,timeout=1) as response:
                    assert json.load(response)['status']=='passed'
                break
            except urllib.error.URLError:
                if time.monotonic()>deadline:
                    raise
                time.sleep(.05)
        with pytest.raises(urllib.error.HTTPError) as denied:
            urllib.request.urlopen(f'http://127.0.0.1:{port}/v1/verify',timeout=1)
        assert denied.value.code==401
    finally:
        process.terminate();process.wait(timeout=5)
