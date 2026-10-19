from pet.codex_sessions import distribute, reduce_event


def test_balanced_stable_session_assignment():
    assert distribute(["c", "a", "b"], [1, 4]) == {1: ["a", "c"], 4: ["b"]}
    assert distribute(["c", "a", "b"], [4]) == {4: ["a", "b", "c"]}
    assert distribute([], [4]) == {4: []}


def test_completion_and_tool_state():
    assert reduce_event({"type": "event_msg", "payload": {"type": "task_started"}}, "idle") == "thinking"
    assert reduce_event({"type": "event_msg", "payload": {"type": "task_complete"}}, "working") == "idle"
    assert reduce_event({"type": "response_item", "payload": {"type": "custom_tool_call", "name": "exec"}}, "thinking") == "working"
