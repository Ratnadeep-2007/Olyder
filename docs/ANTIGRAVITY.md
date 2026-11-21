# Use Olyder as a Google Antigravity skill

Olyder lets Antigravity verify a change against an `olyder.json` file and show
which acceptance checks passed, failed, or were blocked. Start by
[installing the Olyder CLI](../README.md#quick-start) in the environment where
Antigravity runs commands.

From your project's root, install the workspace skill.

```sh
olyder setup antigravity
```

Use `olyder setup antigravity --global` if you want the skill across projects.
The workspace installer writes `.agents/skills/olyder/SKILL.md`. The global
installer uses `~/.gemini/config/skills/olyder/SKILL.md`. These are discovery
locations for Antigravity's App, CLI, and IDE. The skill ID is `olyder`.
[Google Antigravity skill discovery](https://antigravity.google/docs/skills)

## Run the first check

1. Open the workspace in Antigravity. In the CLI, run `/skills reload` or
   start a new session. In the IDE, look under **Customizations** in the agent
   side panel.
2. If you don't have an acceptance spec yet, run `olyder init` in the project
   and edit the generated checks. The [README example](../README.md#verify-your-repository)
   shows a file-only check you can run immediately.
3. Ask Antigravity to use Olyder by name. In the App or CLI, you can also
   explicitly invoke the skill with `/olyder`.

   > Use Olyder to verify the current change against olyder.json. Show the
   > verdict and the report path. Ask before running executable checks.

For a quick CLI check outside the editor, use `olyder demo` first. If the
Antigravity session cannot find `olyder`, provide the executable's absolute
path or start the session in the Python environment where Olyder is
installed. Use the same execution environment for Antigravity and the CLI.

Skill setup is offline. Verification uses the permissions you grant to Olyder.
Run `olyder verify` for file checks. Review a test command before enabling
it with `olyder verify --allow-exec`.
