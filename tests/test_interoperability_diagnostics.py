"""Doctor must distinguish verified protocol paths from proposed interoperability."""
from olyder.diagnostics import doctor
from olyder.mcp import process
from pathlib import Path


def test_doctor_discloses_actual_protocol_support():
    report = doctor()
    support = report["protocol_support"]
    assert support["mcp"]["transport"] == "stdio"
    assert support["mcp"]["protocol_version"] == "2025-03-26"
    assert support["mcp"]["mutation"] == "explicit_server_grant"
    assert support["http_api"]["mutation"] is False
    assert support["acp"]["implemented"] is True
    assert support["acp"]["protocol_version"] == 1
    assert support["acp"]["mode"] == "read_only"
    assert support["acp"]["conformance"] == "official_sdk_stdio_integration"
    assert support["acp"]["full_tck"] == "not_run"
    assert support["acp"]["live_editor"] == "not_run"
    assert support["mcp_2026_07_28"]["implemented"] is False


def test_mcp_advertises_only_the_handshake_revision_it_implements(tmp_path: Path):
    reply = process({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                     "params": {"protocolVersion": "2026-07-28",
                                "capabilities": {}}}, tmp_path)
    assert reply["result"]["protocolVersion"] == "2025-03-26"
    assert reply["result"]["capabilities"] == {"tools": {}}
