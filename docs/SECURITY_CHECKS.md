# Verify security controls with Olyder

The repository's security acceptance spec runs defensive regression tests
against synthetic fixtures. Each requirement maps to observed test results in
the Olyder report. Run it from the repository root in a development
environment with the project and pytest installed.

```sh
python -m pip install -e ".[dev]"
python -m olyder plan --spec olyder.security.json
python -m olyder verify --spec olyder.security.json --allow-exec --output .olyder/security-review
```

The spec requires explicit command execution because it runs pytest. Inspect
`.olyder/security-review/report.html` for the checks that ran and
`report.json` for the requirement coverage and spec hash. A failed test or
blocked requirement exits `1`. A pass covers the listed controls under the
conditions recorded in the report.

| Requirement | Evidence |
| --- | --- |
| Local access | An invalid token receives a denial and the listener binds to loopback. |
| Execution permissions | Default MCP verification blocks command checks and plugin manifests must meet the declared contract. |
| Credential isolation | Managed process and browser environments exclude Olyder's credential variables. Known credential files stay outside detached snapshots. |
| Report privacy | Synthetic credential fields are redacted and report content renders as text. |

The Ubuntu Python 3.13 CI job shows the check outcomes in its summary and
saves the verification report.
For a Windows command check, set the first `argv` item to the absolute path
to the Python interpreter that has the development dependencies when the
short `python` command resolves to a different installation.

## Apply the approach to another project

Copy the requirement and check structure from
[`olyder.security.json`](../olyder.security.json). Replace its test paths
with reviewed tests for your project's controls. Use an isolated test
environment and synthetic data. Record the expected result, such as a
denied access decision or a masked report field, in the test. Keep the test
and its pass criteria under maintainer review.

| Risk | Evidence to collect for the project |
| --- | --- |
| Prompt injection and jailbreaking | Policy evaluation results and evidence that sensitive actions require explicit authorization. |
| Data and model poisoning | Dataset and model provenance, approved inputs, and evaluation results for the release. |
| Sensitive data exposure | Tests for credential redaction, tenant boundaries, and retention controls. |
| Excessive agency | Permission checks for tools, confirmation for sensitive actions, and evidence of least privilege. |
| Model theft and extraction | Rate-limit and abuse detection evidence for the model service. |
| LLMjacking | Cloud identity permissions, credential monitoring, and usage alerts. |
| Weak access controls and API flaws | Authentication, role, and resource-ownership checks using known test accounts. |
| Supply chain compromises | Dependency inventory, advisory findings, and verified artifact provenance. |
| Shadow AI | Approved service inventory, data-handling policy evidence, and organization-level audit records. |
| AI-powered social engineering | Evidence for identity and approval controls, staff reporting procedures, and incident response exercises. |

Some rows require evidence from a cloud service, an organization, or a
model operator. Record those controls as unverified until that evidence is
available. Olyder report coverage applies to the checks listed in the
project's spec.

The control mapping draws on published risk and verification guidance.
Sources accessed November 24, 2026. [OWASP GenAI Security Project](https://genai.owasp.org/llm-top-10/) ·
[OWASP Application Security Verification Standard](https://asvs.owasp.org/) ·
[NIST Secure Software Development Framework](https://csrc.nist.gov/pubs/sp/800/218/final)
