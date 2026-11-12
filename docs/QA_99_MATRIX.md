# 99-scenario expected vs observed matrix

**Baseline:** 84 passed, 15 mismatches. **Final:** 99 passed, zero mismatches.

Each case asserts the expected outcome, including correct failures/blocks for negative scenarios. Browser action tests in level 5 use a **deterministic simulated Playwright adapter**; actual Chromium navigation remains unverified in this hosted environment (`ERR_BLOCKED_BY_ADMINISTRATOR`).

| Level | Scenario | Expected | Observed | Before fix | Mode |
|---:|---|---|---|---|---|
| 1 | `minimal_valid` | accepted | matched expected | passed | local check / fixture |
| 1 | `non_ascii_goal` | accepted | matched expected | passed | local check / fixture |
| 1 | `empty_goal` | rejected | matched expected | passed | local check / fixture |
| 1 | `missing_check_list` | rejected | matched expected | passed | local check / fixture |
| 1 | `duplicate_check_ids` | rejected | matched expected | passed | local check / fixture |
| 1 | `bool_command_timeout` | rejected | matched expected | passed | local check / fixture |
| 1 | `invalid_http_scheme` | rejected | matched expected | passed | local check / fixture |
| 1 | `embedded_credentials` | rejected | matched expected | passed | local check / fixture |
| 1 | `missing_file_path` | rejected | matched expected | passed | local check / fixture |
| 1 | `insecure_research_source` | rejected | matched expected | passed | local check / fixture |
| 1 | `empty_builder_argument` | rejected | matched expected | failed | local check / fixture |
| 2 | `existing_file` | pass | matched expected | passed | local check / fixture |
| 2 | `absent_file_expected_absent` | pass | matched expected | passed | local check / fixture |
| 2 | `missing_file_fails` | fail | matched expected | passed | local check / fixture |
| 2 | `contains_match` | pass | matched expected | passed | local check / fixture |
| 2 | `contains_mismatch` | fail | matched expected | passed | local check / fixture |
| 2 | `unicode_contains` | pass | matched expected | passed | local check / fixture |
| 2 | `nested_file` | pass | matched expected | passed | local check / fixture |
| 2 | `traversal_rejected` | fail | matched expected | passed | local check / fixture |
| 2 | `symlink_escape_rejected` | fail | matched expected | passed | local check / fixture |
| 2 | `directory_not_regular_text_file` | fail | matched expected | passed | local check / fixture |
| 2 | `content_limited_to_first_megabyte` | fail | matched expected | passed | local check / fixture |
| 3 | `blocked_without_consent` | blocked | matched expected | passed | local check / fixture |
| 3 | `simple_success` | pass | matched expected | passed | local check / fixture |
| 3 | `failure_nonzero` | fail | matched expected | passed | local check / fixture |
| 3 | `expected_nonzero` | pass | matched expected | passed | local check / fixture |
| 3 | `stdout_contains_true` | pass | matched expected | passed | local check / fixture |
| 3 | `stdout_contains_false` | fail | matched expected | failed | local check / fixture |
| 3 | `stderr_captured` | pass | matched expected | passed | local check / fixture |
| 3 | `cwd_workspace` | pass | matched expected | passed | local check / fixture |
| 3 | `secret_redacted` | pass | matched expected | passed | local check / fixture |
| 3 | `timeout_observed` | fail | matched expected | passed | local check / fixture |
| 3 | `no_shell_injection` | pass | matched expected | passed | local check / fixture |
| 4 | `success_200` | pass | matched expected | passed | local check / fixture |
| 4 | `created_201` | pass | matched expected | passed | local check / fixture |
| 4 | `expected_404` | pass | matched expected | passed | local check / fixture |
| 4 | `expected_500` | pass | matched expected | passed | local check / fixture |
| 4 | `unexpected_404` | fail | matched expected | passed | local check / fixture |
| 4 | `content_found` | pass | matched expected | passed | local check / fixture |
| 4 | `content_missing` | fail | matched expected | passed | local check / fixture |
| 4 | `redirect_not_followed` | pass | matched expected | passed | local check / fixture |
| 4 | `http_requires_opt_in` | blocked | matched expected | passed | local check / fixture |
| 4 | `nonlocal_http_without_network_opt_in` | blocked | matched expected | failed | local check / fixture |
| 4 | `unicode_utf8_content` | pass | matched expected | passed | local check / fixture |
| 5 | `browser_requires_opt_in` | blocked | matched expected | passed | local check / fixture |
| 5 | `load_real_page` | pass | matched expected | failed | simulated browser adapter |
| 5 | `click_button_changes_dom` | pass | matched expected | failed | simulated browser adapter |
| 5 | `fill_form_field` | pass | matched expected | failed | simulated browser adapter |
| 5 | `missing_text_fails` | fail | matched expected | passed | simulated browser adapter |
| 5 | `current_url_regex` | pass | matched expected | failed | simulated browser adapter |
| 5 | `wrong_url_regex` | fail | matched expected | passed | simulated browser adapter |
| 5 | `navigation_to_next_page` | pass | matched expected | failed | simulated browser adapter |
| 5 | `click_link_navigation` | pass | matched expected | failed | simulated browser adapter |
| 5 | `invalid_browser_selector_fails` | fail | matched expected | passed | simulated browser adapter |
| 5 | `browser_external_without_network_consent` | blocked | matched expected | failed | local check / fixture |
| 6 | `reserve_settle_actual` | quota/model behavior asserted | matched expected | passed | local check / fixture |
| 6 | `estimate_blocks_overspend` | quota/model behavior asserted | matched expected | passed | local check / fixture |
| 6 | `reserve_exact_boundary` | quota/model behavior asserted | matched expected | passed | local check / fixture |
| 6 | `unicode_estimation` | quota/model behavior asserted | matched expected | passed | local check / fixture |
| 6 | `settle_unknown_charges_reserved` | quota/model behavior asserted | matched expected | passed | local check / fixture |
| 6 | `actual_usage_can_exceed_reservation` | quota/model behavior asserted | matched expected | passed | local check / fixture |
| 6 | `release_restores_budget` | quota/model behavior asserted | matched expected | passed | local check / fixture |
| 6 | `reject_negative_output` | quota/model behavior asserted | matched expected | failed | local check / fixture |
| 6 | `reject_negative_limit` | quota/model behavior asserted | matched expected | failed | local check / fixture |
| 6 | `missing_model_configuration` | quota/model behavior asserted | matched expected | passed | local check / fixture |
| 6 | `network_failure_settles_reservation` | quota/model behavior asserted | matched expected | failed | local check / fixture |
| 7 | `deterministic_no_ai` | passed | matched expected | passed | local check / fixture |
| 7 | `clean_ai_assessment` | passed | matched expected | passed | local check / fixture |
| 7 | `ai_concern_forces_review` | needs_review | matched expected | passed | local check / fixture |
| 7 | `non_json_response` | needs_review | matched expected | passed | local check / fixture |
| 7 | `markdown_fenced_json` | passed | matched expected | passed | local check / fixture |
| 7 | `non_string_concern` | needs_review | matched expected | passed | local check / fixture |
| 7 | `json_array_instead_object` | needs_review | matched expected | passed | local check / fixture |
| 7 | `ai_cannot_override_failed` | failed | matched expected | passed | local check / fixture |
| 7 | `blocked_takes_priority` | blocked | matched expected | passed | local check / fixture |
| 7 | `select_none_does_not_pass` | failed | matched expected | passed | local check / fixture |
| 7 | `no_builder_history_shared` | passed | matched expected | passed | local check / fixture |
| 8 | `verify_only_no_builder` | failed | matched expected | passed | local check / fixture |
| 8 | `builder_creates_output` | passed | matched expected | passed | local check / fixture |
| 8 | `builder_modifies_spec_blocked` | blocked | matched expected | passed | local check / fixture |
| 8 | `builder_not_found_blocked` | blocked | matched expected | passed | local check / fixture |
| 8 | `builder_fails_nonzero_blocked` | blocked | matched expected | passed | local check / fixture |
| 8 | `failure_then_repair` | passed | matched expected | passed | local check / fixture |
| 8 | `no_progress_terminates` | failed | matched expected | passed | local check / fixture |
| 8 | `max_iterations_stops` | failed | matched expected | passed | local check / fixture |
| 8 | `report_files_created` | passed | matched expected | passed | local check / fixture |
| 8 | `negative_iteration_rejected` | input rejected | matched expected | failed | local check / fixture |
| 8 | `deadline_exceeded_status` | blocked | matched expected | failed | local check / fixture |
| 9 | `cli_init` | integration behavior asserted | matched expected | passed | local check / fixture |
| 9 | `cli_init_refuses_overwrite` | integration behavior asserted | matched expected | passed | local check / fixture |
| 9 | `skill_installs` | integration behavior asserted | matched expected | passed | local check / fixture |
| 9 | `cli_plan` | integration behavior asserted | matched expected | passed | local check / fixture |
| 9 | `mcp_list_tools` | integration behavior asserted | matched expected | passed | local check / fixture |
| 9 | `mcp_verify_read_only` | integration behavior asserted | matched expected | passed | local check / fixture |
| 9 | `mcp_unknown_tool` | integration behavior asserted | matched expected | passed | local check / fixture |
| 9 | `mcp_invalid_params` | integration behavior asserted | matched expected | passed | local check / fixture |
| 9 | `mcp_notification_no_reply` | integration behavior asserted | matched expected | passed | local check / fixture |
| 9 | `html_escapes_payload` | integration behavior asserted | matched expected | passed | local check / fixture |
| 9 | `network_sources_blocked` | integration behavior asserted | matched expected | passed | local check / fixture |
