"""Replay the reviewed cart-pricing example using the installed Olyder CLI."""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def verify_case(project: Path, output: Path, expected_status: str, exit_code: int) -> dict:
    env = os.environ.copy()
    env["PATH"] = os.pathsep.join([str(Path(sys.executable).parent), env.get("PATH", os.defpath)])
    outcome = subprocess.run(
        [sys.executable, "-m", "olyder", "verify", "--allow-exec", "--output", str(output)],
        cwd=project, env=env, capture_output=True, text=True, timeout=45,
    )
    if outcome.returncode != exit_code:
        raise SystemExit(f"Expected {expected_status} (exit {exit_code}).\n"
                         f"{outcome.stdout}{outcome.stderr}")
    result = json.loads(outcome.stdout)
    if (result["status"] != expected_status or result["budget"]["calls"] != 0
            or result["artifact_status"] != "complete"):
        raise SystemExit(f"Unexpected result for {output.name}: {outcome.stdout}")
    report = json.loads((output / "report.json").read_text(encoding="utf-8"))
    print(f"{report['status']}: {output / 'report.html'}")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(".olyder/pricing-proof"),
                        help="Directory for the two reports (default: .olyder/pricing-proof)")
    output = parser.parse_args().output.resolve()
    example = Path(__file__).resolve().parent

    with tempfile.TemporaryDirectory(prefix="olyder-cart-") as temporary:
        project = Path(temporary)
        for name in ("olyder.json", "pricing.py", "test_pricing.py"):
            shutil.copyfile(example / name, project / name)
        implementation = project / "pricing.py"
        original = implementation.read_text(encoding="utf-8")
        discount = "(1 - discount_percent / 100)"
        if discount not in original:
            raise SystemExit("The example no longer contains the reviewed discount calculation.")
        implementation.write_text(original.replace(discount, "1", 1), encoding="utf-8")
        failed = verify_case(project, output / "discount-regression", "failed", 1)
        failure = next(check for check in failed["checks"] if check["id"] == "pricing-cases")
        if failure["status"] != "fail" or "FAIL: test_discount" not in failure["details"]:
            raise SystemExit("The replay did not observe the expected discount test failure.")

        shutil.copyfile(example / "pricing.py", implementation)
        passed = verify_case(project, output / "discount-fixed", "passed", 0)
        if passed["spec_sha256"] != failed["spec_sha256"]:
            raise SystemExit("The acceptance spec changed between runs.")


if __name__ == "__main__":
    main()
