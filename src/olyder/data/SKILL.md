---
name: olyder
summary: Verify delivered code against acceptance criteria using independent, evidence-based tests and bounded correction loops.
---

# Olyder agent skill

Use this skill when a user asks to implement, verify, challenge, or repair code with measurable outcomes. Olyder is a CLI executable, not a promise that a model's judgment alone proves correctness.

1. Confirm the user's goal, workspace and realistic acceptance criteria. Create or review `olyder.json` using `olyder init` as a starting point. Do not silently change acceptance criteria during a task.
2. Run `olyder plan --spec olyder.json` to get deterministic task breakdown. Research with `olyder idea --allow-network` ONLY after the user authorizes source retrieval and the HTTPS URLs are explicitly recorded in the spec.
3. Before running project test commands, read the spec and obtain permission for `--allow-exec`; commands can execute arbitrary tools. Use an external OS sandbox for untrusted workspaces.
4. Run `olyder verify --spec olyder.json --allow-exec` where authorized. Inspect `.olyder/report.json` for factual test evidence. Treat 'blocked' and untested cases as unresolved.
5. To enable bounded automatic corrections, configure a builder CLI in `olyder.json` and run `olyder run --allow-exec --execute-builder --sandbox docker --docker-image YOUR_REVIEWED_AGENT_IMAGE` (or `--unsafe-host` only for fully trusted local work). This allows the coding agent to edit files; get approval before running. Never use unattended execution on a sensitive machine without sandboxing.
6. Optional `--ai` triggers a **fresh, independent model request** with only acceptance criteria and observed test evidence. Set OLYDER_MODEL, OLYDER_API_KEY, and optionally OLYDER_BASE_URL. Never claim the independent verifier saw the builder's internal reasoning. Never present an LLM opinion as proof of correctness.
7. Summarize verified and unverified items, failures with reproduction evidence, quota usage, research sources, and the stopping reason. Do not claim completion if any critical acceptance check is not verified.

## Integration

- Claude Code: copy this skill directory to `.claude/skills/olyder/`.
- Codex or OpenCode (where supported): copy this directory to `.agents/skills/olyder/`.
- Other IDEs: use `olyder` CLI in their integrated terminal; use `olyder mcp --workspace PATH` for read-only-by-default planning and file verification.

This repository does not implement OS-level sandboxing, autonomous open-web research, mobile controls, or cross-provider remaining-quota discovery in v0.1.


## v0.5 development branch (incomplete)

- `olyder run --mode economy|balanced|thorough` changes retry patience, never acceptance checks. Every attempt executes the full suite.
- Existing specs retain the legacy policy. Newly initialized specs use schema 2 and balanced. Explicit schema-2 requirements map `acceptance_check_ids`; uncovered mandatory requirements require review.
- A selected subset cannot establish full acceptance. Requested AI review that cannot complete remains unresolved.
- OpenCode no longer receives `--auto`; approve permissions through its own reviewed configuration. Codex now requires a Git workspace.
- Dollar ledger is a library foundation only: no CLI dollar cap, provider-enforced quota, or durable recovery is implemented. Do not describe this branch as a completed v0.5 release.
