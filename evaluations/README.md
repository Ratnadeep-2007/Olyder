# Paired evaluation of Olyder

This study measures whether the same coding agent produces better solutions with
Olyder. The first fixture set covers checkout totals, tenant-scoped authorization,
attendance requirements, inventory API behavior, and an existing name-normalization
module. These are small Python applications with a `solve(input)` interface.

## Reproduce the offline pilot

From an installed source checkout, run:

```sh
python -m olyder.evals offline .olyder/eval-checkout --task checkout
python -m olyder.evals offline .olyder/eval-all
```

Each task defaults to three pairs. Both arms receive byte-identical starter
files, instructions, and public tests. Pair order alternates. A uses a
conventional public test command. B uses Olyder's detached verifier and
revision-bound completion gate. Each arm receives the same scripted candidate
sequence. One script returns the public example's answer for every input, so
the pilot exercises detection of a false completion signal. The offline study
exercises the framework with zero model calls. It provides no estimate of
how an AI agent's performance changes.

`plan.json` records fixture identity, limits and initial file hashes.
`records/` stores frozen source digests, public outcomes and trial observations.
`report.json` contains every paired result, held-out check outcome and per-pair
public-check time delta. Use a fresh output directory for each run. CI runs the
full fixture set on Linux and uploads these three artifacts.

## Run a separately authorized live study

1. Have an independent evaluator create a private oracle in the format shown in
   `offline-oracles-v1.json`. Give each case an ID, category, input and expected
   JSON output. Set `preserve_input: true` where mutation is a defect. Label
   existing behavior `regression` and permission cases `access_control`. Keep
   the file outside the study directory and precommit its SHA-256 before running
   any agent. The public offline oracle is suitable for smoke tests.
2. Use a preloaded Docker image ID and a pinned agent and model version. Choose
   equal time, total attempt and token budgets. The first attempt counts toward
   the total even when no repair is requested. Prepare the workspaces:

```sh
python -m olyder.evals prepare-live .olyder/live-study --allow-live \
  --task checkout --agent AGENT --model PROVIDER/MODEL@VERSION \
  --oracle-sha256 HASH --image sha256:IMAGE_ID --token-budget 8000
```

3. Run fresh sessions through the authorized provider separately. Give each
   session access only to its designated trial directory and use exactly its
   `PROMPT.md` as the development instruction. Keep evaluator code, scripts,
   oracles, records, other trials and controller state outside the agent's
   OS access. Group A uses normal tools. Group B can request Olyder public
   verification through the controller:

```sh
python -m olyder.evals public-check .olyder/live-study checkout-1-B --image sha256:IMAGE_ID
```

4. Stop development before recording. Put the final `app.py` into the
   prepared workspace. Have the controller record each trial with a JSON
   receipt. Required fields are `agent`, `model`, `claimed_completion` (boolean),
   `development_seconds` and `repair_attempts`. Optional fields include
   `human_interventions`, `observed_tokens`, `actual_usd`, `peak_rss_kib`, and
   `no_submission` (true for a trial with no artifact). Costs describe
   reconciled observations only. Missing metrics stay null.

```sh
python -m olyder.evals record .olyder/live-study checkout-1-A RECEIPT.json --image sha256:IMAGE_ID
python -m olyder.evals score .olyder/live-study PRIVATE_ORACLE.json --image sha256:IMAGE_ID
```

The live runner prepares and scores trials. The operator supplies and budgets
external agent sessions. Preparation performs no provider calls. Score
requires every trial receipt and rejects changed submissions. The oracle is
loaded only at scoring. Submitted code receives individual JSON inputs in a
separate environment without receiving the expected outputs or the oracle file.
The Docker verifier uses the same preregistered local image for both groups.

## Interpret the results

- Completion requires all holdout checks and compliance with observed limits.
  Hidden acceptance rate uses all scheduled checks. Errors and missing
  submissions remain visible in the raw rows.
- A false completion signal means a claim in A or an actual public gate
  approval in B followed by a failed held-out assertion. Public coverage misses
  and infrastructure errors are reported separately.
- Public-check deltas measure Olyder overhead for these fixtures. Live agent
  wall time, usage and intervention counts depend on controller receipts.
  Linux runner peak RSS covers the scorer process, excluding Docker containers
  and model hosts.
- The inventory fixture exercises the API's state-change function. HTTP,
  database concurrency and full-stack behavior need separate fixtures.
  Three pairs establish that the harness works. Broader performance claims
  require more live trials across tasks, models and realistic repositories.

The separation of development and scoring follows the independent verifier
pattern described by Harbor. This runner is a local Olyder study.
[Harbor task environment documentation](https://github.com/harbor-framework/harbor/blob/main/docs-mintlify/tasks/environment.mdx)
