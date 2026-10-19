"""Codex transcript state and deterministic, balanced pet assignment (no Qt)."""

from __future__ import annotations


def distribute(session_ids, slots):
    slots = sorted(set(slots))
    result = {slot: [] for slot in slots}
    if slots:
        for index, session in enumerate(sorted(set(session_ids))):
            result[slots[index % len(slots)]].append(session)
    return result


def reduce_event(record, prior):
    payload = record.get("payload", {})
    kind = payload.get("type")
    if record.get("type") == "event_msg":
        if kind == "task_started":
            return "thinking"
        if kind in ("task_complete", "task_aborted", "turn_aborted"):
            return "idle"
        if kind in ("turn_failed", "task_failed"):
            return "error"
    if record.get("type") == "response_item" and prior != "idle":
        if kind in ("function_call", "custom_tool_call"):
            return "attention" if "request_user_input" in payload.get("name", "") else "working"
    return prior
