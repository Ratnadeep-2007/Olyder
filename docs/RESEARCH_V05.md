# Research record

Access date: 2026-11-13. Sources below were opened through the web tool. They are mutable documentation, not pinned commits or validation of product claims. No source snapshots or content hashes were retained; documentation-level conclusions are not integration evidence. No remote MCP change is proposed, so the conditional MCP authorization source was not evaluated.

| Source | Finding / implication | Assumption and falsification |
|---|---|---|
| https://learn.chatgpt.com/docs/non-interactive-mode | Noninteractive JSONL is documented; retain structured adapter | Check local help and replay usage fixtures; paid run NOT done |
| https://opencode.ai/docs/cli/commands | JSON run output documented | Local help must match installed version |
| https://cheatsheetseries.owasp.org/cheatsheets/Secure_Coding_with_AI_Cheat_Sheet.html | AI coding security guidance supports independent validation | Plant a defect and challenge acceptance |
| https://owasp.github.io/DevSecOpsGuideline/2-Process/2-2-Develop/2-2-5-AI-Agent-and-MCP-Security/ | Agent/MCP boundaries need explicit permissions | Command and network probes must fail without grants |
| https://docs.docker.com/engine/security/ | Daemon/runtime privileges remain in threat boundary | Execute mount/egress adversarial tests on live Docker |
| https://docs.docker.com/engine/security/rootless/ | Rootless reduces daemon privilege exposure | Not equivalent to containment certification |
| https://docs.litellm.ai/docs/proxy/users | Budget controls are an optional proxy capability | Require DB, routing and billing probe before enforcement claim |
| https://docs.litellm.ai/docs/proxy/cost_tracking | Spend tracking needs separate provenance | Reconcile against provider billing, not fabricated prices |
| https://github.com/Aider-AI/aider | Terminal coding assistant alternative | Auto-tests alone do not establish independent oracle |
| https://github.com/OpenHands/docs/blob/main/openhands/usage/sandboxes/docker.mdx | Supplied page opened; useful sandbox body not established from returned page | Treat exact sandbox implementation as unverified |
| https://github.com/harbor-framework/harbor | Evaluation framework alternative | Official harness not executed here |
| https://www.swebench.com/verified | Human-validated 500-instance benchmark subset | Local fixture results cannot imply SWE-bench performance |

Local executable evidence: codex-cli 0.169.0 help confirms --json and workspace-write sandbox; --skip-git-repo-check permits non-repositories and is removed from the default template. OpenCode help confirms --auto auto-approves permissions not denied; removed by default. No paid provider inference was invoked. Docker info failed because the Docker Desktop Linux daemon pipe is absent. Installed executable presence is not live integration verification.
