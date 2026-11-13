# Offline paired benchmark: measured, cost-inconclusive

This pilot executes real Python builders and oracle scripts. Builders are deterministic fixtures, not paid models or simulated invoices. Baseline source is extracted from the pinned local Git commit. All variants receive the same source, repair script, acceptance oracle, 30-second run deadline and repetition index.

Baseline: `99b86067c7e676ca1cecc55ecd83f4ba9fe69109`. Current source digest: `c4216eb1f5a159868c8c84c7d63b6d9e4805c16c1b0ec252cb4ee5a7264900bc`. Python 3.11.15; Windows-10-10.0.26200-SP0; CPU Intel64 Family 6 Model 183 Stepping 1, GenuineIntel.

Three repetitions of ten executable tasks across four variants yield 120 executions. Twelve browser-dependent rows (a separate eleventh scenario) are skipped explicitly. Pricing/model/image: not applicable to native deterministic Python fixtures; no vendor account, Docker image or official Harbor/SWE-bench harness was used. Recovery is exercised in the separate state tests, not timed in this pilot.

| Variant | Executions | Expected outcomes | Verified positive solves | Functional/security false PASS | Median total seconds | Actual USD |
|---|---:|---:|---:|---:|---:|---|
| v0.4 | 30 | 27 | 18 | 0 | 0.398 | Unknown / not applicable |
| economy | 30 | 30 | 18 | 0 | 1.852 | Unknown / not applicable |
| balanced | 30 | 30 | 18 | 0 | 1.891 | Unknown / not applicable |
| thorough | 30 | 30 | 18 | 0 | 1.866 | Unknown / not applicable |

The six positive tasks have identical observed acceptance success across variants. Zero functional/security false PASSes were observed on these planted negatives only. The three baseline mismatches are the small-dollar-budget task: v0.4 has no monetary admission and reports a functional pass. Those are budget-policy failures and are explicitly excluded from the narrower functional/security false-PASS metric, not concealed as correct outcomes.

## Matched per-task observations

Each cell shows observed status, median total seconds, median attempt count and median check milliseconds over three repetitions. Full individual observations are in the raw JSON. The compatibility attempts field counts completed verification-history entries, not billed requests: an integrity-blocked builder turn can have zero entries.

| Task | v0.4 | Economy | Balanced | Thorough |
|---|---|---|---|---|
| calculation | passed; 0.375s; 1 attempts; 79ms checks | passed; 1.891s; 1 attempts; 78ms checks | passed; 1.937s; 1 attempts; 78ms checks | passed; 1.922s; 1 attempts; 78ms checks |
| api-input | passed; 0.391s; 1 attempts; 93ms checks | passed; 1.969s; 1 attempts; 94ms checks | passed; 2.047s; 1 attempts; 94ms checks | passed; 2.032s; 1 attempts; 94ms checks |
| cli-exception | passed; 0.422s; 1 attempts; 94ms checks | passed; 2.078s; 1 attempts; 94ms checks | passed; 2.016s; 1 attempts; 94ms checks | passed; 2.031s; 1 attempts; 78ms checks |
| hidden-regression | failed; 0.750s; 3 attempts; 236ms checks | failed; 2.547s; 2 attempts; 171ms checks | failed; 3.532s; 3 attempts; 251ms checks | failed; 5.562s; 4 attempts; 344ms checks |
| spec-tamper | blocked; 0.282s; 0 attempts; 0ms checks | blocked; 0.938s; 0 attempts; 0ms checks | blocked; 0.968s; 0 attempts; 0ms checks | blocked; 0.938s; 0 attempts; 0ms checks |
| stuck-loop | failed; 0.781s; 3 attempts; 250ms checks | failed; 2.125s; 2 attempts; 173ms checks | failed; 2.953s; 3 attempts; 250ms checks | failed; 4.296s; 4 attempts; 329ms checks |
| small-budget | passed; 0.390s; 1 attempts; 94ms checks | budget_exhausted; 0.641s; 0 attempts; 0ms checks | budget_exhausted; 0.640s; 0 attempts; 0ms checks | budget_exhausted; 0.640s; 0 attempts; 0ms checks |
| missing-usage | passed; 0.375s; 1 attempts; 78ms checks | passed; 1.688s; 1 attempts; 78ms checks | passed; 1.703s; 1 attempts; 78ms checks | passed; 1.719s; 1 attempts; 78ms checks |
| browser-dependent | SKIPPED: no live browser fixture | SKIPPED: no live browser fixture | SKIPPED: no live browser fixture | SKIPPED: no live browser fixture |
| python-http-integration | passed; 0.516s; 1 attempts; 203ms checks | passed; 1.828s; 1 attempts; 203ms checks | passed; 1.875s; 1 attempts; 204ms checks | passed; 1.843s; 1 attempts; 203ms checks |
| range-boundary | passed; 0.375s; 1 attempts; 94ms checks | passed; 1.703s; 1 attempts; 94ms checks | passed; 1.688s; 1 attempts; 78ms checks | passed; 1.719s; 1 attempts; 78ms checks |

## Interpretation and limits

The new engine is slower on these tiny native fixtures. Detached copying, protected verification, SQLite checkpoints and fresh full checks add overhead. This is an observed tradeoff, not evidence of throughput or cost improvement. Mode differences mostly affect bounded retry patience; the pilot does not measure model selection or intelligence.

Actual provider dollars and tokens are unavailable/not applicable. No solves-per-dollar ratio or percentage cost saving is computed. The proposed 15% balanced-cost improvement hypothesis is INCONCLUSIVE and unvalidated. No positive actual billing exists from which to test it.

This small constructed sample has fixed execution order, an uncontrolled shared developer host (other verification may run concurrently), no hardware affinity and no population sampling. No inferential confidence interval or general efficiency claim is justified. A separately authorized live study must pin CLI/model versions, pricing, account receipts, hardware/image and task classification, randomize paired order, and compare acceptance success before testing savings. Official harnesses remain NOT RUN.

Reproduce from an Olyder Git clone with the baseline commit available:

```text
olyder bench --repository . --repetitions 3 --output docs/validation/UNIVERSAL_BENCHMARK.json
python scripts/summarize_universal_benchmark.py
```
