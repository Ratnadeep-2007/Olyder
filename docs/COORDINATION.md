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

## Register and route agents

The registry lives in the workspace's run database. The operator registers each
agent and the session that can retrieve its task messages. Use a different
agent ID for each instance, including instances of the same provider.

```sh
olyder agent register editor-1 --session session-1 --role builder --capability python
olyder agent role editor-1 --role reviewer
olyder agent role editor-1 --role builder
olyder task open --route --capability python
```

The router chooses the first available registered builder by agent ID whose
declared capabilities match. Roles can change without changing grants.
Capabilities are operator-declared. The registry does not infer editing,
execution or cancellation rights from a provider name. Opening an explicitly
assigned task for an unregistered agent continues to work as before.

For a registered task, use `--session SESSION` when submitting through the CLI.
Acknowledging a message records receipt. The same session can reconnect and
receive up to 20 unacknowledged messages at a time with their original IDs and
current delivery status. Acknowledge messages to advance the inbox. Re-registering a
different session with the same agent ID keeps the old inbox and tasks scoped to
the old session. An operator can reopen work for the new session. A disconnected
agent is ineligible for routing until registered again.

```sh
olyder agent inbox editor-1 --session session-1
olyder agent ack editor-1 MESSAGE_ID --session session-1
```

## Connect through MCP

Start a stdio server for one registered task session. Clients can list their
unacknowledged messages, acknowledge a message, read an assigned task, and
submit an exact proposal revision. The tool arguments carry no role,
permission, controller key, or arbitrary command fields.

```sh
olyder mcp --workspace PROJECT --task-agent editor-1 --task-session session-1
```

The controller can add `--task-auto-verify` and provide the controller key in
the server environment. Add `--allow-exec` only for reviewed command checks.
Network stays disabled on this path. In this mode a submitted revision invokes
Olyder's deterministic verifier. A replay after a lost response retrieves the
existing result for that revision. To retry the same blocked or failed revision
deliberately, use the controller's task CLI. A completed verification still
requires a separate controller approval. The default MCP server continues to
offer its existing file-only verification and planning.

## Use Herdr for delivery

Discover agents in an explicitly selected local Herdr workspace and enroll a
particular pane. The adapter uses Herdr's documented CLI and requires an
observed native session reference. It checks the current pane binding and
readiness before sending a small inbox pointer. [Herdr CLI](https://herdr.dev/tui/docs/cli-reference/)

```sh
olyder agent discover-herdr --herdr-workspace w1
olyder agent enroll-herdr editor-1 --herdr-workspace w1 --pane w1:p2 --role builder --capability python
olyder task open --route --capability python --notify-herdr
olyder agent push-herdr editor-1
```

The controller can also opt into a push after `task verify` or `task complete`
using `--notify-herdr`. Task transitions enqueue their messages in the same
SQLite transaction as the state update. Each explicit push claims one pending
message. If Herdr times out or the controller exits mid-send, the inbox still
offers the message for pull and acknowledgement. Olyder leaves the uncertain
push alone. Herdr's CLI lifecycle response describes session activity. Agent
receipt comes from acknowledgement, and completion authority comes from the
revision-bound gate. The CLI supports a pane preflight check. It does not
provide an atomic session-conditional send.

Keep the run database and controller environment within a trusted OS boundary.
A local CLI identity or session label does not authenticate hostile processes
sharing the same privileges. The optional Herdr path needs an installed local
Herdr client, with `--herdr-bin` available for an explicit executable path.

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
task interface supports CLI, Python, and explicitly bound MCP sessions. ACP
and managed builders use their existing entry points.
