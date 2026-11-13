"""Render the actual offline paired observations without extrapolating costs."""
import json
from pathlib import Path
import statistics


def main():
    path = Path('docs/validation/UNIVERSAL_BENCHMARK.json')
    data = json.loads(path.read_text(encoding='utf-8'))
    modes = ('v0.4', 'economy', 'balanced', 'thorough')
    lines = [
        '# Offline paired benchmark: measured, cost-inconclusive', '',
        'This pilot executes real Python builders and oracle scripts. Builders are deterministic fixtures, '
        'not paid models or simulated invoices. Baseline source is extracted from the pinned local Git commit. '
        'All variants receive the same source, repair script, acceptance oracle, 30-second run deadline and repetition index.', '',
        f"Baseline: `{data['baseline_commit']}`. Current source digest: `{data['implementation_sha256']}`. "
        f"Python {data['python']}; {data['platform']}; CPU {data['cpu']}.", '',
        'Three repetitions of ten executable tasks across four variants yield 120 executions. '
        'Twelve browser-dependent rows (a separate eleventh scenario) are skipped explicitly. '
        'Pricing/model/image: not applicable to native deterministic Python fixtures; no vendor account, '
        'Docker image or official Harbor/SWE-bench harness was used. Recovery is exercised in the separate state tests, '
        'not timed in this pilot.', '',
        '| Variant | Executions | Expected outcomes | Verified positive solves | Functional/security false PASS | Median total seconds | Actual USD |',
        '|---|---:|---:|---:|---:|---:|---|',
    ]
    for mode in modes:
        item = data['summary'][mode]
        lines.append(f"| {mode} | {item['executed']} | {item['expected_outcomes']} | {item['verified_solved']} | "
                     f"{item['false_passes']} | {item['median_seconds']:.3f} | Unknown / not applicable |")
    lines += ['', 'The six positive tasks have identical observed acceptance success across variants. '
              'Zero functional/security false PASSes were observed on these planted negatives only. '
              'The three baseline mismatches are the small-dollar-budget task: v0.4 has no monetary admission '
              'and reports a functional pass. Those are budget-policy failures and are explicitly excluded '
              'from the narrower functional/security false-PASS metric, not concealed as correct outcomes.', '',
              '## Matched per-task observations', '',
              'Each cell shows observed status, median total seconds, median attempt count and median check milliseconds '
              'over three repetitions. Full individual observations are in the raw JSON. '
              'The compatibility attempts field counts completed verification-history entries, '
              'not billed requests: an integrity-blocked builder turn can have zero entries.', '',
              '| Task | v0.4 | Economy | Balanced | Thorough |', '|---|---|---|---|---|']
    tasks = list(dict.fromkeys(row['task'] for row in data['rows']))
    for task in tasks:
        cells = []
        for mode in modes:
            rows = [row for row in data['rows'] if row['task'] == task and row['mode'] == mode]
            if all(row['status'] == 'skipped' for row in rows):
                cells.append('SKIPPED: no live browser fixture')
                continue
            statuses = ','.join(sorted({row['status'] for row in rows}))
            cells.append(f"{statuses}; {statistics.median(row['seconds'] for row in rows):.3f}s; "
                         f"{statistics.median(row['attempts'] for row in rows):g} attempts; "
                         f"{statistics.median(row['check_ms'] for row in rows):g}ms checks")
        lines.append('| '+task+' | '+' | '.join(cells)+' |')
    lines += ['', '## Interpretation and limits', '',
              'The new engine is slower on these tiny native fixtures. Detached copying, protected verification, '
              'SQLite checkpoints and fresh full checks add overhead. This is an observed tradeoff, not evidence '
              'of throughput or cost improvement. Mode differences mostly affect bounded retry patience; '
              'the pilot does not measure model selection or intelligence.', '',
              'Actual provider dollars and tokens are unavailable/not applicable. No solves-per-dollar ratio '
              'or percentage cost saving is computed. The proposed 15% balanced-cost improvement hypothesis '
              'is INCONCLUSIVE and unvalidated. No positive actual billing exists from which to test it.', '',
              'This small constructed sample has fixed execution order, an uncontrolled shared developer host '
              '(other verification may run concurrently), no hardware affinity and no population sampling. '
              'No inferential confidence interval or general efficiency claim is justified. '
              'A separately authorized live study must pin CLI/model versions, pricing, account receipts, '
              'hardware/image and task classification, randomize paired order, and compare acceptance success '
              'before testing savings. Official harnesses remain NOT RUN.', '',
              'Reproduce from an Olyder Git clone with the baseline commit available:', '',
              '```text', 'olyder bench --repository . --repetitions 3 --output docs/validation/UNIVERSAL_BENCHMARK.json',
              'python scripts/summarize_universal_benchmark.py', '```', '']
    Path('docs/BENCHMARK_V05.md').write_text('\n'.join(lines), encoding='utf-8')


if __name__ == '__main__':
    main()
