"""Collect an actual GitHub Actions receipt and observed pytest summaries."""
import argparse
import json
from pathlib import Path
import re
import subprocess


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('run_id')
    args = parser.parse_args()
    run = subprocess.run(['gh', 'run', 'view', args.run_id, '--json',
                          'status,conclusion,headSha,url,jobs'], check=True, capture_output=True, text=True)
    receipt = json.loads(run.stdout)
    logs = subprocess.run(['gh', 'run', 'view', args.run_id, '--log'],
                          check=True, capture_output=True, text=True, encoding='utf-8')
    receipt['observed_test_summaries'] = []
    for line in logs.stdout.splitlines():
        match = re.search(r'(?:(\d+) failed, )?(\d+) passed(?:, (\d+) skipped)? in ([\d.]+)s', line)
        if match:
            receipt['observed_test_summaries'].append({
                'job': line.split('\t', 1)[0], 'failed': int(match[1] or 0),
                'passed': int(match[2]), 'skipped': int(match[3] or 0), 'seconds': float(match[4]),
            })
    Path('docs/validation/UNIVERSAL_CI.json').write_text(json.dumps(receipt, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'headSha': receipt['headSha'], 'conclusion': receipt['conclusion'],
                      'tests': receipt['observed_test_summaries']}, indent=2))


if __name__ == '__main__':
    main()
