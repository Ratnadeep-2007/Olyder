# Olyder Verification Report

**Goal:** Customers receive correct cart totals and invalid pricing inputs are rejected
**Status:** passed
**Spec SHA-256:** `a98968c0d92c2f700e4600456289410f26a83effffd27747f4c39d6a4be0600e`
**Attempts:** 1

## Acceptance checks

- **pricing-module** — PASS (file, 0ms): Text content assertion
- **pricing-cases** — PASS (command, 125ms): Exit 0; output condition not configured; tail: test\_checkout \(test\_pricing\.PricingTests\.test\_checkout\) \.\.\. ok test\_discount \(test\_pricing\.PricingTests\.test\_discount\) \.\.\. ok test\_rejects\_negative\_price \(test\_pricing\.PricingTests\.test\_rejects\_negative\_price\) \.\.\. ok  ---------------------------------------------------------------------- Ran 3 tests in 0\.000s  OK

## Objective metrics

```json
{
  "declared_checks": 2,
  "executed_checks": 2,
  "passed_checks": 2,
  "failed_checks": 0,
  "blocked_checks": 0,
  "execution_coverage_percent": 100.0,
  "pass_rate_of_executed_percent": 100.0,
  "total_check_duration_ms": 125,
  "sources_requested": 0,
  "sources_fetched": 0,
  "sources_unavailable": 0
}
```

## Verification

Independent deterministic checks only; no LLM review requested\.

## Budget

```json
{
  "limit": 4000,
  "spent": 0,
  "calls": 0,
  "remaining_estimated": 4000
}
```

## External evidence


## Limitations

A passing report proves only the declared checks ran and passed in the observed environment. It does not prove that all possible real-world requirements are satisfied.

## Coding-agent telemetry (observed, not enforced)

```json
{
  "runs": [],
  "observed_tokens": null,
  "complete": false,
  "enforced_provider_quota": false
}
```

## Execution isolation

```json
{
  "mode": "host",
  "unsafe_host_authorized": false,
  "protected_assets_detached": true,
  "http_browser_checks": "host",
  "trusted_python_callbacks": "host"
}
```

## Acceptance and policy evidence

```json
{
  "requirement_coverage": {
    "pricing-module": {
      "mandatory": true,
      "check_ids": [
        "pricing-module"
      ],
      "result_ids": [
        "pricing-module"
      ],
      "evidence_refs": [
        "checks/pricing-module"
      ],
      "satisfied": true
    },
    "pricing-cases": {
      "mandatory": true,
      "check_ids": [
        "pricing-cases"
      ],
      "result_ids": [
        "pricing-cases"
      ],
      "evidence_refs": [
        "checks/pricing-cases"
      ],
      "satisfied": true
    }
  },
  "independent_critic_status": "not_requested",
  "selected_checks": [
    "pricing-module",
    "pricing-cases"
  ],
  "full_suite_executed": true,
  "policy": {
    "mode": "balanced",
    "full_final_suite_required": true,
    "selected_by": "balanced_default",
    "final_time_reserve_seconds": 15,
    "enforcement_kind": "local_soft"
  },
  "stop_reason": "acceptance_passed",
  "acceptance_integrity": {
    "trusted_snapshot_sha256": "cf45c47d09d6e1a0ee89be204782b7cc6b6189026be481a528290991d56c4d54",
    "protected_paths": [
      "features",
      "olyder.json",
      "specs",
      "test_pricing.py",
      "tests"
    ],
    "manifest_sha256": "ab246f24297f1fb5316f7878084cfe47679ac17edae8ab8033f42d679b0784e4"
  },
  "run_id": "5611a807060340f996e235d7541a1c6c",
  "functional_verdict": "passed",
  "budget_verdict": "not_applicable",
  "accounting": {
    "ledger": null,
    "ledger_checkpoint": null,
    "observations": [],
    "pending_requests": {},
    "enforcement_kind": "local_soft",
    "budget_verdict": "not_applicable"
  },
  "wall_seconds": 1.8589999999967404,
  "environment": {
    "python": "3.11.15",
    "platform": "Windows"
  },
  "verification_selection": [
    {
      "attempt": 1,
      "selected": [
        "pricing-module",
        "pricing-cases"
      ],
      "reason": "full_suite_default",
      "changed_files": [
        "README.md",
        "pricing.py"
      ]
    }
  ],
  "resource_usage": {
    "deterministic_check_ms": 125,
    "executed_checks": 2,
    "research_seconds": 0.0
  },
  "warnings": [
    "Host execution has no OS containment"
  ],
  "artifact_refs": {
    "contract": "C:\\Users\\ratna\\Olyder\\examples\\demo-app\\.olyder\\runs\\5611a807060340f996e235d7541a1c6c\\contract.json",
    "manifest": "C:\\Users\\ratna\\Olyder\\examples\\demo-app\\.olyder\\runs\\5611a807060340f996e235d7541a1c6c\\workspace\\manifest.json",
    "proposal": "C:\\Users\\ratna\\Olyder\\examples\\demo-app\\.olyder\\runs\\5611a807060340f996e235d7541a1c6c\\workspace\\builder",
    "harness": "C:\\Users\\ratna\\Olyder\\examples\\demo-app\\.olyder\\runs\\5611a807060340f996e235d7541a1c6c\\workspace\\harness"
  },
  "verification_target": "detached_proposal",
  "application_status": "not_attempted",
  "repaired_check_ids": [],
  "checker_sha256": "f5e34962d141522ace7345ac843bc53e1e47bf776272e4f8e3b9b178fd44cd3f"
}
```
