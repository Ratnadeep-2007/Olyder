"""Generate current evidence indices from actual artifacts; never infer passes."""
import hashlib
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET


def summarize(path):
    root = ET.parse(path).getroot()
    suites = list(root.iter('testsuite'))
    counts = {key: sum(int(s.get(key, 0)) for s in suites)
              for key in ('tests', 'failures', 'errors', 'skipped')}
    counts['passed'] = counts['tests'] - counts['failures'] - counts['errors'] - counts['skipped']
    cases = []
    for case in root.iter('testcase'):
        outcome = next((key for key in ('failure', 'error', 'skipped') if case.find(key) is not None), None)
        node = case.find(outcome) if outcome else None
        cases.append({'name': case.get('name'), 'class': case.get('classname'),
                      'status': outcome or 'passed',
                      'reason': node.get('message', '') if node is not None else ''})
    return {'artifact': path.as_posix(), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            **counts, 'seconds': sum(float(s.get('time', 0)) for s in suites), 'cases': cases}


def main():
    runs = [summarize(path) for path in sorted(Path('docs/validation').glob('UNIVERSAL_*.xml'))]
    source = hashlib.sha256()
    for path in sorted(Path('src/olyder').glob('*.py')):
        source.update(path.name.encode()); source.update(path.read_bytes())
    ci = Path('docs/validation/UNIVERSAL_CI.json')
    payload = {'schema_version': 1, 'release_gate': 'INCOMPLETE',
               'source_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
               'implementation_sha256': source.hexdigest(), 'runs': runs,
               'live_provider_runs': 0, 'actual_provider_usd': None,
               'development_assistant_billing': 'unknown',
               'local_docker': 'daemon unavailable', 'live_browser': 'not_run',
               'native_ci': json.loads(ci.read_text(encoding='utf-8')) if ci.exists() else 'pending'}
    Path('docs/UNIVERSAL_TEST_RESULTS.json').write_text(json.dumps(payload, indent=2)+'\n', encoding='utf-8')
    print(json.dumps([{k: v for k, v in run.items() if k != 'cases'} for run in runs], indent=2))


if __name__ == '__main__':
    main()
