"""Regenerate factual test summaries from pytest JUnit artifacts."""
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

runs = []
for filename in ('baseline.xml', 'v05-red.xml', 'ledger-red.xml', 'policy-red.xml', 'review-red.xml', 'timeout-red.xml',
                 'v05-foundations.xml', 'final-windows.xml', 'final-linux.xml'):
    path = Path('docs/validation') / filename
    if not path.exists():
        continue
    root = ET.parse(path).getroot()
    suites = list(root.iter('testsuite'))
    counts = {k: sum(int(s.get(k, 0)) for s in suites)
              for k in ('tests', 'failures', 'errors', 'skipped')}
    counts['passed'] = counts['tests']-counts['failures']-counts['errors']-counts['skipped']
    runs.append({'artifact': path.as_posix(), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                 **counts, 'seconds': sum(float(s.get('time',0)) for s in suites),
                 'cases': [{'name': c.get('name'), 'class': c.get('classname'),
                            'status': 'failed' if c.find('failure') is not None else
                            'error' if c.find('error') is not None else
                            'skipped' if c.find('skipped') is not None else 'passed'}
                           for c in root.iter('testcase')]})
Path('docs/TEST_RESULTS_V05.json').write_text(json.dumps({
    'schema_version': 1, 'release_gate': 'INCOMPLETE', 'runs': runs,
    'live_provider': 'NOT_RUN', 'provider_dollars': None,
    'docker_live': 'BLOCKED: Docker Desktop Linux daemon pipe unavailable',
    'native_github_ci': 'PENDING',
}, indent=2)+'\n')
print(json.dumps([{k:v for k,v in r.items() if k != 'cases'} for r in runs], indent=2))
