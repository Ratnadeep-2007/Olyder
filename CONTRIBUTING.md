# Contributing

This project favors reproducible evidence over model judgment. Open an issue with a minimal test fixture and expected/observed behavior. Run `python -m pytest -q` locally before submitting changes.

Safety: never submit real API credentials, private repository data, or generated reports containing secrets. Security bugs should be reported privately to maintainers rather than accompanied by working public exploit payloads. At the first public release, configure a responsible disclosure contact in repository security settings.

New scenario runners should default to non-execution, require explicit user consent for side effects, and be supported by tests on Windows and Linux.
