"""Human and machine-readable reports. Escape all untrusted text in HTML."""
from __future__ import annotations

import html
import json
from pathlib import Path


def save_report(report: dict, output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path, md_path, html_path = (output_dir / n for n in ("report.json", "report.md", "report.html"))
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    checks = report.get("checks", [])
    md = ["# Olyder Verification Report", "", f"**Goal:** {report.get('goal','')}", f"**Status:** {report.get('status','unknown')}", f"**Spec SHA-256:** `{report.get('spec_sha256','')}`", f"**Attempts:** {report.get('attempts',0)}", "", "## Acceptance checks", ""]
    for c in checks:
        md.append(f"- **{c['id']}** — {c['status'].upper()} ({c['type']}, {c['duration_ms']}ms): {c['details'].replace(chr(10), ' ')[:400]}")
    md.extend(["", "## Objective metrics", "", "```json", json.dumps(report.get("metrics", {}), indent=2), "```", "", "## Verification", "", report.get("verifier_note", "Not requested"), "", "## Budget", "", "```json", json.dumps(report.get("budget", {}), indent=2), "```", "", "## External evidence", ""])
    for src in report.get("sources", []):
        md.append(f"- {src['url']} — {src['status']} ({src.get('reason','')})")
    md.extend(["", "## Limitations", "", "A passing report proves only the declared checks ran and passed in the observed environment. It does not prove that all possible real-world requirements are satisfied."])
    if "agent_usage" in report:
        md.extend(["", "## Coding-agent telemetry (observed, not enforced)", "", "```json",
                   json.dumps(report["agent_usage"], indent=2), "```"])
    if "execution_isolation" in report:
        md.extend(["", "## Execution isolation", "", "```json",
                   json.dumps(report["execution_isolation"], indent=2), "```"])
    md_path.write_text("\n".join(md) + "\n", encoding="utf-8")
    e = html.escape
    rows = "\n".join(f"<tr><td>{e(str(c['id']))}</td><td class='{e(c['status'])}'>{e(c['status'])}</td><td>{e(str(c['type']))}</td><td>{e(str(c['duration_ms']))} ms</td><td><pre>{e(str(c['details']))}</pre></td></tr>" for c in checks)
    metrics_text = e(json.dumps(report.get("metrics", {}), indent=2))
    source_rows = "".join(f"<li>{e(s['url'])}: {e(s['status'])}</li>" for s in report.get("sources", []))
    page = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Olyder Verification Report</title><style>
:root{{color-scheme:light dark}} body{{font:15px/1.55 system-ui,-apple-system,sans-serif;max-width:1100px;margin:36px auto;padding:0 20px}} h1{{font-size:1.9rem}}.subtle{{color:gray}}.stat{{display:inline-block;padding:10px 18px;border:1px solid #8886;border-radius:8px;margin-right:8px}}table{{border-collapse:collapse;width:100%;margin-top:18px}}th,td{{border-bottom:1px solid #8885;padding:10px;text-align:left;vertical-align:top}}.pass{{color:#24874e;font-weight:700}}.fail{{color:#bf4236;font-weight:700}}.blocked{{color:#bc8225;font-weight:700}}pre{{white-space:pre-wrap;word-break:break-word;margin:0}}.mono{{font-family:ui-monospace,monospace}}small{{color:gray}}
</style></head><body><h1>Olyder</h1><p class="subtle">Independent, evidence-based verification report</p><h2>{e(report.get('goal',''))}</h2><p><span class="stat">Status: <strong>{e(report.get('status',''))}</strong></span><span class="stat">Attempts: {e(str(report.get('attempts',0)))}</span><span class="stat">Model tokens: {e(str(report.get('budget',{}).get('spent',0)))}</span></p><p><small>Acceptance specification: {e(report.get('spec_sha256',''))}</small></p><h2>Objective metrics</h2><pre>{metrics_text}</pre><h2>Acceptance tests</h2><table><thead><tr><th>Scenario</th><th>Status</th><th>Type</th><th>Duration</th><th>Evidence</th></tr></thead><tbody>{rows}</tbody></table><h2>Independent verifier</h2><p>{e(report.get('verifier_note',''))}</p><h2>Source evidence</h2><ul>{source_rows}</ul><h2>Coding-agent usage (post-hoc, not a provider quota)</h2><pre>{e(json.dumps(report.get("agent_usage", {}), indent=2))}</pre><h2>Execution isolation</h2><pre>{e(json.dumps(report.get("execution_isolation", {}), indent=2))}</pre><h2>Scope</h2><p>Only defined acceptance checks are covered. This report does not establish production security or full real-world correctness.</p></body></html>'''
    html_path.write_text(page, encoding="utf-8")
    return {"json": str(json_path), "markdown": str(md_path), "html": str(html_path)}
