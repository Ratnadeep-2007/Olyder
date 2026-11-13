# Current development limitations

This is a partial implementation, not completed v0.5.

- Protected verifier assets are still fingerprinted in the builder workspace, not detached from its writable mount. Hashes detect tampering; they do not prevent it.
- Dollar ledger is in-process and not wired into CLI execution; no durable checkpoints, crash replay, paid-provider reservation, price snapshot or gateway enforcement exists.
- Modes affect retry patience and builder time admission only. No empirically supported cost-saving claim, check-selection cache or full global cancellation guarantee exists.
- A mandatory manual criterion stays needs_review without executable coverage. There is no authenticated manual reviewer workflow.
- Windows tests requiring symlink creation fail with WinError 1314 on this host. Tests remain unchanged. Enable the required host capability or run the Linux suite; do not hide the failures.
- Docker Desktop Linux daemon is unavailable. Container enforcement is not live-verified here. HTTP/browser checks remain on the host. Unsafe-host opt-in is not a security boundary.
- No real provider study, actual invoice reconciliation, live browser run or official Harbor/SWE-bench benchmark was done.
- Native hosted Windows/Ubuntu CI must be inspected separately from local Windows/WSL results. Full v0.5 release acceptance is not satisfied.
