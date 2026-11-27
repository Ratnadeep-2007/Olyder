# Coordinate an existing coding agent

A local task lets an existing agent submit an implementation, receive confirmed
failures, and submit a correction. Olyder freezes the approved acceptance inputs,
checks the detached proposal, and records a revision-specific decision. The same
RunStore and verification engine also serve managed runs.

## Open and submit

Review the specification, its commands, and its protected paths before opening a
task. From a controller shell, set `OLYDER_TASK_CONTROLLER_KEY` to a fresh random
value. For example, `python -c "import secrets; print(secrets.token_urlsafe(32))"`
can generate one. Store it in the controller's environment or secret store.

```sh
olyder task open --spec olyder.json --agent-id builder-1
```

Share the returned `proposal` directory, `run_id`, and approved requirements
with the agent. Keep the controller key private. The agent edits the proposal
directory and calls the following from the original project root. Substitute the
run ID and the `proposal_revision` returned by `task status`.

```sh
olyder task status RUN_ID
olyder task submit RUN_ID --agent-id builder-1 --revision REVISION
```

The assigned identifier is a routing label. It does not establish the caller's
identity or grant execution or approval. A submission records readiness for
verification.

## Verify and approve

In the controller shell, run the reviewed checks. For file-only checks, omit
`--allow-exec`. An external network request also needs `--allow-network`.
Open the task with `--sandbox docker --docker-image IMAGE` if the reviewed image
and Docker daemon are available.

```sh
olyder task verify RUN_ID --allow-exec
```

A failed result includes a `repair.requested` message. Each finding identifies a
check, its requirement IDs, observed evidence, and the relevant report entry.
Send this message to the assigned agent. After repair, the agent reads the new
revision and submits it, and the controller verifies again. Commands that were
blocked remain unresolved. The number of verification attempts is bounded by
`limits.max_iterations`, which defaults to three.

When the controller is satisfied with a verified result, it approves the exact
submitted revision. A separate gate query reads the approval without running
checks or requiring the key.

```sh
olyder task complete RUN_ID --revision REVISION
olyder task gate RUN_ID --revision REVISION
```

`task gate` exits zero and prints `gate: open` for the current, approved
revision. It exits one and prints `gate: closed` when the approval cannot be
used. The approval includes the contract hash, policy version, checker hash,
environment, check IDs, report path and JSON report hash. Use
`olyder report RUN_ID` to read the latest retained result. Attempt reports
are stored separately under the task's run directory.

## Connect an orchestrator

A Herdr script can dispatch implementation work with its public agent commands,
read the response, and then act on Olyder's gate exit code. Herdr's reported state
tells the script about the agent session. Olyder derives its decision from the
captured revision and checks. [Herdr agent automation](https://herdr.dev/tui/docs/agent-automation/)

The gate applies to the detached proposal. The proposal's revision covers the
included files, their modes, and directory paths together with the frozen
acceptance inputs. Olyder uses its existing workspace exclusions for runtime,
version-control, dependency, and known credential paths. An orchestrator
must apply its own revision check when consuming or promoting the proposal.
Olyder records the decision locally and leaves publication and merge control to
the caller. The executor does not own or terminate the external agent process.

The task state, frozen inputs and reports are trusted local data. Give the
agent access to its proposal directory and protect the controller process,
credential and run state using operating-system permissions or an isolated
runner. Host mode cannot contain programs with the controller's OS permissions.
The controller key is excluded from managed workload environments. When an
agent cannot access the run store directly, a trusted integration can relay
its submission through the CLI.

Use `olyder cancel RUN_ID` to invalidate an abandoned task. If the verifier
process was interrupted in flight, stop the old process before opening a new
task. The task interface does not automatically replay uncertain work. This
first interface uses CLI and Python. Existing MCP, ACP, and managed modes
remain available through their own entry points.
