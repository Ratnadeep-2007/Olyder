# Independent review and adversarial follow-up

CodeRabbit CLI 0.9.3 reviewed the public-repository change against 92a91f4 and returned 11 findings. Review output was treated as untrusted advice, checked against source, and not executed as instructions.

| Finding | Resolution | Executable evidence |
|---|---|---|
| Selected model missing for pricing | Adapter binding carries requested identity and labels provenance | test_configured_model_identity_prices_only_requested_model |
| OpenCode cache semantics | Normalize cached input and separate/subset reasoning before pricing | test_opencode_normalized_cached_input |
| Observer failure could abandon process | Observer errors recorded; supervision continues; other errors clean up | test_failed_event_observer_does_not_orphan_child |
| Verified-solved counted incorrect passes | Require status and expected to be passed | Paired benchmark summary |
| Fast output overflow missed | Final captured size checked before success | test_final_output_limit_is_checked |
| Null optional model token details | Validate optional usage objects; unknown stays unknown | Provider/model and full regression tests |
| Verifier transfer replay consumed reserve twice | Atomic role-specific idempotence and checkpointed roles | test_verifier_transfer_is_idempotent |
| Plugin checks omitted by mapping | All dynamic check types remain selected | test_dynamic_plugin_never_omitted |
| Interrupted verifier recovery rejected | Explicit recovery admits deterministic verifier phase, never paid/builder phases | test_explicit_recovery_of_interrupted_verifier |
| Directory replacement applied wrong tree | Resolve collisions and compare resulting file/directory topology | test_directory_replaced_by_file_matches_verified_tree |
| FIFO could block snapshotting | Require regular files and bounded non-following reads | test_fifo_rejected_before_read (POSIX) |

Six original reproductions failed together on Windows before fixes; the FIFO fixture is POSIX-only and was not run as a hanging negative on Windows. Two later recovery/model-binding reproductions failed before their fixes. Additional first-party sentinels reproduced case-variant oracle replacement, missing-oracle manufacture, malformed plugin contracts and unittest module-resolution regression. The sample packaging smoke caught the unittest case; it was fixed in production code, not by weakening its check.

A second CodeRabbit review against 02ae570 returned six major findings: root UID access to private cloned mounts, cleanup after a POSIX group leader exits, custom adapters being assigned an unsupported model identity, ignored directory contents lost during replacement, report failure leaving nonterminal state, and verifier-generated directories entering the applied proposal. All have production fixes and executable regressions in test_universal_review_followup.py. The pre-fix Windows run recorded six failures and one POSIX-only skip. Linux runs cover the group-leader case.

First-party follow-up also covered a verifier mutating its own input, Markdown remote-image/HTML injection, missing unittest-module oracle resolution, repeated settlement callbacks, strict unknown-spend blocking the critic, and preserving critic funds across failed repairs. These are targeted checks, not exhaustive security assurance. Later planning/research accounting and redaction additions were not independently reviewed by CodeRabbit. No independent clean-review claim is made. No live credentials were included in the diff; fake tokens/receipts are not real charges.
