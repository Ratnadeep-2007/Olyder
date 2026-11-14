# Olyder Verification Report

**Goal:** Customers receive correct cart totals and invalid pricing inputs are rejected
**Status:** passed
**Spec SHA-256:** `a98968c0d92c2f700e4600456289410f26a83effffd27747f4c39d6a4be0600e`
**Attempts:** 1

## Acceptance checks

- **pricing-module** — PASS (file, 0ms): Text content assertion
- **pricing-cases** — PASS (command, 109ms): Exit 0; output condition not configured; tail: test_checkout (test_pricing.PricingTests.test_checkout) ... ok test_discount (test_pricing.PricingTests.test_discount) ... ok test_rejects_negative_price (test_pricing.PricingTests.test_rejects_negative_price) ... ok  ---------------------------------------------------------------------- Ran 3 tests in 0.000s  OK

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
  "total_check_duration_ms": 109,
  "sources_requested": 0,
  "sources_fetched": 0,
  "sources_unavailable": 0
}
```

## Verification

Independent deterministic checks only; no LLM review requested.

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
  "full_suite_executed": true
}
```
