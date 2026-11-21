"""A small offline example that exercises the same verifier as the CLI."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from .config import load_spec
from .engine import verify_once
from .report import save_report


def run_demo(*, fail: bool, output: Path) -> dict:
    with tempfile.TemporaryDirectory(prefix="olyder-demo-") as directory:
        project = Path(directory)
        (project / "release.txt").write_text(
            "channel=beta\n" if fail else "channel=stable\n", encoding="utf-8", newline="\n"
        )
        spec = project / "olyder.json"
        spec.write_text(json.dumps({
            "goal": "The sample release declares a stable channel.",
            "checks": [
                {"id": "release-file", "type": "file", "path": "release.txt"},
                {
                    "id": "stable-channel", "type": "file", "path": "release.txt",
                    "contains": "channel=stable\n",
                },
            ],
        }), encoding="utf-8")
        result = verify_once(load_spec(spec))
    result["attempts"] = 1
    result["verification_target"] = "built_in_demo"
    result["paths"] = save_report(result, output)
    return result
