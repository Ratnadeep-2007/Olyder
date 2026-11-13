"""Record a real installed-wheel CLI/demo/MCP smoke without model calls."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--python', required=True, help='Interpreter with the built wheel installed')
    args = parser.parse_args()
    commands = [
        [args.python, '-m', 'olyder', '--help'],
        [args.python, '-m', 'olyder', 'doctor'],
        [args.python, '-m', 'olyder', 'verify', '--spec', 'examples/demo-app/olyder.json',
         '--allow-exec', '--output', 'docs/examples/universal'],
        [args.python, '-m', 'olyder', 'mcp', '--workspace', 'examples/demo-app'],
    ]
    results = []
    for command in commands:
        request = '\n'.join(json.dumps(item) for item in (
            {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {}},
            {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list', 'params': {}},
        ))+'\n' if 'mcp' in command else ''
        process = subprocess.run(command, input=request, capture_output=True, text=True,
                                 encoding='utf-8', timeout=60, check=False)
        results.append({'argv': command, 'returncode': process.returncode,
                        'stdout': process.stdout, 'stderr': process.stderr})
    demo = json.loads(results[2]['stdout'])
    handshake = [json.loads(line) for line in results[3]['stdout'].splitlines() if line.strip()]
    valid = (all(item['returncode'] == 0 for item in results) and demo['status'] == 'passed'
             and len(handshake) == 2 and all('result' in item for item in handshake)
             and len(handshake[1]['result']['tools']) == 2)
    wheel = Path('dist/olyder_agent-0.4.0-py3-none-any.whl')
    result = {'schema_version': 1, 'passed': valid, 'commands': results,
              'wheel': str(wheel), 'wheel_sha256': hashlib.sha256(wheel.read_bytes()).hexdigest()}
    Path('docs/validation/UNIVERSAL_INSTALL.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'passed': valid, 'demo_run_id': demo['run_id'], 'mcp_responses': len(handshake)}))
    return 0 if valid else 1


if __name__ == '__main__':
    raise SystemExit(main())
