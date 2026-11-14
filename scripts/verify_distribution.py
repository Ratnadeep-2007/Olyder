"""Offline validation of Olyder PyPI source and wheel archives.

Never extracts archives or executes embedded files. Intended for CI gates
before any release is authorized.
"""
from __future__ import annotations

import configparser
import email
import os
from pathlib import Path
import tarfile
import tomllib
import zipfile


def _assert_no_sensitive_entries(names: set[str]) -> None:
    forbidden = {".env", "id_rsa", "id_ed25519"}
    for entry in names:
        path = Path(entry)
        if (any(part in forbidden or part.startswith(".git") for part in path.parts) or
                path.suffix.lower() in {".pem", ".p12", ".pfx", ".key"}):
            raise AssertionError(f"Unexpected sensitive/private artifact: {entry}")


def verify() -> None:
    project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))["project"]
    name, version = project["name"], project["version"]
    assert name == "olyder", f"Unexpected distribution name: {name}"
    tag = os.environ.get("RELEASE_TAG")
    if tag:
        assert tag == f"v{version}", f"Release tag {tag!r} does not match package version {version!r}"

    folder = Path("dist")
    wheel = list(folder.glob("olyder-*.whl"))
    sdist = list(folder.glob("olyder-*.tar.gz"))
    assert len(wheel) == len(sdist) == 1, "Expected exactly one wheel and one source archive"
    assert wheel[0].name == f"olyder-{version}-py3-none-any.whl", wheel[0]
    assert sdist[0].name == f"olyder-{version}.tar.gz", sdist[0]

    with zipfile.ZipFile(wheel[0]) as z:
        entries = set(z.namelist())
        _assert_no_sensitive_entries(entries)
        skill = "olyder/data/SKILL.md"
        assert skill in entries, "Packaged wheel is missing the Olyder skill"
        assert "name: olyder" in z.read(skill).decode("utf-8")
        assert "description:" in z.read(skill).decode("utf-8").split("---", 2)[1]
        assert "olyder/__main__.py" in entries
        assert "olyder/skill_install.py" in entries

        meta = f"olyder-{version}.dist-info/METADATA"
        assert meta in entries, "Missing wheel metadata"
        parsed = email.message_from_bytes(z.read(meta))
        assert parsed.get("Name") == name
        assert parsed.get("Version") == version
        assert parsed.get("Requires-Python") == ">=3.11"
        entry_file = f"olyder-{version}.dist-info/entry_points.txt"
        assert entry_file in entries, "Missing console entry point"
        parser = configparser.ConfigParser()
        parser.read_string(z.read(entry_file).decode("utf-8"))
        assert parser["console_scripts"]["olyder"] == "olyder.cli:main"

    with tarfile.open(sdist[0], "r:gz") as tar:
        entries = set(tar.getnames())
        _assert_no_sensitive_entries(entries)
        prefix = f"olyder-{version}/"
        assert all(x.startswith(prefix) for x in entries), "Unexpected source archive layout"
        for file in ("README.md", "LICENSE", "pyproject.toml", "src/olyder/data/SKILL.md"):
            assert prefix + file in entries, f"Missing source artifact: {file}"
        meta_entry = tar.extractfile(prefix + "PKG-INFO")
        assert meta_entry is not None
        parsed = email.message_from_bytes(meta_entry.read())
        assert parsed.get("Name") == name
        assert parsed.get("Version") == version
    print(f"Verified distribution archives: {name} {version}, console CLI and embedded skill")


if __name__ == "__main__":
    verify()
