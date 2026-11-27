"""Workspace-local agent registrations and durable delivery in the run database."""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from .privacy import redact_values
from .state import RunStore


class CommunicationError(RuntimeError):
    pass


_MAX_AGENTS = 256
_MAX_PAYLOAD = 12_000


def _identifier(value, label, *, limit=64):
    if (not isinstance(value, str) or len(value) > limit
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]*", value)):
        raise CommunicationError(f"Invalid {label}")
    return value


def _capabilities(values):
    if not isinstance(values, (list, tuple)) or len(values) > 20:
        raise CommunicationError("Expected at most 20 capabilities")
    return sorted({_identifier(value, "capability") for value in values})


def store_for(workspace):
    return RunStore(Path(workspace).resolve() / ".olyder" / "runs")


def _record(connection, agent_id):
    row = connection.execute("SELECT data FROM agents WHERE id=?", (agent_id,)).fetchone()
    return json.loads(row[0]) if row else None


def register(workspace, agent_id, session, *, role, capabilities=(), provider="external",
             transport="mcp", target=None, available=True):
    """Record an operator-approved binding. Roles never confer execution privileges."""
    _identifier(agent_id, "agent ID")
    if ":" in agent_id:
        raise CommunicationError("Invalid agent ID")
    _identifier(session, "session ID", limit=256)
    _identifier(role, "role")
    _identifier(provider, "provider")
    if transport not in ("mcp", "herdr") or type(available) is not bool:
        raise CommunicationError("Invalid transport or availability")
    if transport == "herdr":
        _identifier(target, "Herdr pane")
    elif target is not None:
        raise CommunicationError("A target applies to Herdr registrations only")
    entry = {"agent_id": agent_id, "session": session, "role": role, "capabilities": _capabilities(capabilities),
             "provider": provider, "transport": transport, "target": target,
             "available": available, "updated_at": time.time()}
    with store_for(workspace).connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        if _record(connection, agent_id) is None:
            count, = connection.execute("SELECT count(*) FROM agents").fetchone()
            if count >= _MAX_AGENTS:
                raise CommunicationError("Workspace agent registry is full")
        connection.execute("INSERT INTO agents VALUES (?, ?) ON CONFLICT(id) DO UPDATE SET data=excluded.data",
                           (agent_id, json.dumps(entry)))
    return entry


def agent(workspace, agent_id):
    with store_for(workspace).connect() as connection:
        return _record(connection, agent_id)


def list_agents(workspace):
    with store_for(workspace).connect() as connection:
        return [json.loads(data) for data, in connection.execute("SELECT data FROM agents ORDER BY id")]


def _edit_agent(workspace, agent_id, changes):
    with store_for(workspace).connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        entry = _record(connection, agent_id)
        if entry is None:
            raise CommunicationError("Agent is not registered")
        entry.update(changes, updated_at=time.time())
        connection.execute("UPDATE agents SET data=? WHERE id=?", (json.dumps(entry), agent_id))
    return entry


def change_role(workspace, agent_id, role):
    return _edit_agent(workspace, agent_id, {"role": _identifier(role, "role")})


def disconnect(workspace, agent_id):
    return _edit_agent(workspace, agent_id, {"available": False})


def route(workspace, capabilities, *, role="builder"):
    required = set(_capabilities(capabilities))
    candidate = next((entry for entry in list_agents(workspace)
                      if entry["available"] and entry["role"] == role and required <= set(entry["capabilities"])), None)
    if candidate is None:
        raise CommunicationError("No available agent matches the role and capabilities")
    return candidate


def _bound(connection, agent_id, session):
    entry = _record(connection, agent_id)
    if entry is None or not entry["available"] or entry["session"] != session:
        raise CommunicationError("Agent session is unavailable or has been replaced")
    return entry


def bound_agent(workspace, agent_id, session):
    with store_for(workspace).connect() as connection:
        return _bound(connection, agent_id, session)


def notification(state, event):
    """Return an optional bounded, redacted message for the task's transaction."""
    session = state.get("agent_session")
    if session is None:
        return None
    message = redact_values({**event, "recipient_agent_id": state["agent_id"]})
    encoded = json.dumps(message)
    if len(encoded) > _MAX_PAYLOAD:
        # Full evidence remains in task status and attempt reports.
        message.pop("findings", None)
        message.pop("goal", None)
        message["details_omitted"] = True
        encoded = json.dumps(message)
    if len(encoded) > _MAX_PAYLOAD:
        raise CommunicationError("Task notification exceeds the delivery bound")
    return event["message_id"], state["agent_id"], session, encoded


def inbox(workspace, agent_id, session):
    with store_for(workspace).connect() as connection:
        _bound(connection, agent_id, session)
        rows = connection.execute(
            """SELECT data, status FROM agent_messages
               WHERE agent_id=? AND session=? AND status!='acknowledged'
               ORDER BY rowid LIMIT 20""", (agent_id, session),
        ).fetchall()
    return [{**json.loads(data), "delivery_status": status} for data, status in rows]


def acknowledge(workspace, agent_id, session, message_id):
    _identifier(message_id, "message ID")
    with store_for(workspace).connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        _bound(connection, agent_id, session)
        updated = connection.execute(
            "UPDATE agent_messages SET status='acknowledged' WHERE id=? AND agent_id=? AND session=?",
            (message_id, agent_id, session),
        )
        if updated.rowcount != 1:
            raise CommunicationError("Message is not assigned to this agent session")
    return {"message_id": message_id, "status": "acknowledged"}


def claim_push(workspace, agent_id, session):
    """Claim one pending message. A crash after claiming never retries it implicitly."""
    with store_for(workspace).connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        _bound(connection, agent_id, session)
        row = connection.execute(
            """SELECT id, data FROM agent_messages WHERE agent_id=? AND session=? AND status='pending'
               ORDER BY rowid LIMIT 1""", (agent_id, session),
        ).fetchone()
        if row is None:
            return None
        connection.execute("UPDATE agent_messages SET status='sending' WHERE id=?", (row[0],))
        return json.loads(row[1])


def finish_push(workspace, message_id, *, accepted):
    with store_for(workspace).connect() as connection:
        status = "sent" if accepted else "uncertain"
        connection.execute("UPDATE agent_messages SET status=? WHERE id=? AND status='sending'",
                           (status, message_id))
        row = connection.execute("SELECT status FROM agent_messages WHERE id=?", (message_id,)).fetchone()
        return row[0] if row else "removed"
