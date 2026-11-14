"""MCP stdio hardening: bounded frames, recovery and credential-safe errors."""
import io
import json
import sys

from olyder import mcp


def _serve(monkeypatch, tmp_path, request_stream):
    output = io.StringIO()
    monkeypatch.setattr(sys, "stdin", request_stream)
    monkeypatch.setattr(sys, "stdout", output)
    assert mcp.serve(tmp_path) == 0
    return [json.loads(line) for line in output.getvalue().splitlines()]


def _ping(identifier=2):
    return json.dumps({"jsonrpc": "2.0", "id": identifier, "method": "ping"}) + "\n"


def test_oversized_valid_json_is_rejected_and_next_message_survives(monkeypatch, tmp_path):
    # Formerly a valid, huge ping request reached dispatch without a size cap.
    oversized = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping",
                             "padding": "x" * (mcp.MAX_MCP_FRAME_BYTES + 100)}) + "\n"
    messages = _serve(monkeypatch, tmp_path, io.StringIO(oversized + _ping()))
    assert len(messages) == 2
    assert messages[0]["error"]["code"] == -32600
    assert messages[0]["id"] is None
    assert messages[1] == {"jsonrpc": "2.0", "id": 2, "result": {}}


def test_unicode_frame_limit_counts_utf8_bytes(monkeypatch, tmp_path):
    # A character limit alone would admit this payload despite a >1MB frame.
    oversized = json.dumps({"jsonrpc": "2.0", "id": 5, "method": "ping",
                             "data": "₹" * (mcp.MAX_MCP_FRAME_BYTES // 3 + 32)},
                            ensure_ascii=False) + "\n"
    messages = _serve(monkeypatch, tmp_path, io.StringIO(oversized + _ping(6)))
    assert messages[0]["error"]["code"] == -32600
    assert messages[1]["id"] == 6
    assert messages[1]["result"] == {}


def test_invalid_utf8_does_not_disconnect_mcp_stdio(monkeypatch, tmp_path):
    stream = io.TextIOWrapper(io.BytesIO(bytes([255, 10]) + _ping(9).encode("utf-8")),
                              encoding="utf-8")
    messages = _serve(monkeypatch, tmp_path, stream)
    assert messages[0]["error"]["code"] == -32700
    assert messages[1] == {"jsonrpc": "2.0", "id": 9, "result": {}}


def test_tool_error_does_not_echo_bearer_secret(monkeypatch, tmp_path):
    def failing_spec(_path):
        raise ValueError("Authorization: Bearer sample-sensitive-key")
    monkeypatch.setattr(mcp, "load_spec", failing_spec)
    message = mcp.process({"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                           "params": {"name": "olyder_plan"}}, tmp_path)
    result = message["result"]
    assert result["isError"] is True
    assert "sample-sensitive-key" not in result["content"][0]["text"]
    assert "[REDACTED]" in result["content"][0]["text"]


def test_mcp_notifications_do_not_emit_responses(monkeypatch, tmp_path):
    raw = json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n"
    assert _serve(monkeypatch, tmp_path, io.StringIO(raw + _ping(3))) == [
        {"jsonrpc": "2.0", "id": 3, "result": {}}
    ]
