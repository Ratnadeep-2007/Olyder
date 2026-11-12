# Realistic scenario examples and measurable outcomes

Olyder does not infer that an idea is good merely because code compiles. Requirements must become observable acceptance checks. These examples require test/staging systems and configured dependencies.

## E-commerce checkout

Criteria: incorrect login is rejected, cart totals are correct, unsuccessful payment does not charge customer, and checkout on a small screen is usable.

Measured evidence:
- Unit assertions for discounts and totals.
- Browser steps with a sandbox payment provider.
- Explicit HTTP status responses, not guesses from UI appearance.
- Test failures and execution duration.

A staging browser scenario:

```json
{
  "id": "checkout-error-screen",
  "type": "browser",
  "url": "http://localhost:3000/checkout",
  "steps": [
    {"action": "fill", "selector": "#email", "value": "tester@example.test"},
    {"action": "click", "selector": "#pay-with-test-card"},
    {"action": "expect_text", "selector": "#payment-status", "text": "Payment declined"}
  ]
}
```

This is an example spec, not a result of a completed checkout test.

## ML market-price forecasts

Criteria: future rows have no data leakage, forecast horizons 7/30 days work, held-out testing beats an agreed baseline, and missing data does not crash predictions.

Measured evidence: MAE/RMSE computed by an external evaluation script, sample count, train/validation date ranges, and data-leakage tests. Olyder runs these scripts as explicit `command` checks; it does not invent or replace evaluation metrics.

## AI-agent workflow

Criteria: the agent asks for consent before a destructive operation, can resume after interruption, does not exceed retry budget, and does not leak credentials to unrelated domains.

Measured evidence: isolated fixture replay, tool-call audit assertions, declared blocked action tests, and duration. Do not run adversarial tests against production systems without authorization.

## Idea validation from external sources

Use only approved HTTPS source URLs in `sources` and `olyder idea --allow-network --ai` with configured provider. Sources supply evidence, not customer demand or proof of viability. A research summary should identify assumptions and propose validation experiments such as interviews and pilots.
