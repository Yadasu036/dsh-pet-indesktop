from types import SimpleNamespace
import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


from pet.codex_runtime import CodexRuntime


class Behavior:
    def __init__(self):
        self.played = []

    def _categories(self, lib):
        return {"acts": ["写代码"]}

    def state_of(self, sprite):
        return "idle"

    def play_once(self, sprite, clip):
        self.played.append((sprite, clip))


class Sprite:
    library = None


def test_single_surviving_child_receives_all_sessions(qapp):
    sprite = Sprite()
    behavior = Behavior()
    bubbles = []
    overlay = SimpleNamespace(
        _spawned_slots={sprite: 1},
        _all_sprites=lambda: [sprite],
        _sprite_visible=lambda s: True,
        host_for_sprite=lambda s: SimpleNamespace(behavior=behavior),
        _show_bubble_text_for=lambda *args: bubbles.append(args),
    )
    runtime = CodexRuntime(SimpleNamespace(_overlay_shell=overlay))
    runtime.updated.emit({"a": "working", "b": "thinking"})
    qapp.processEvents()
    assert "2个会话" in bubbles[0][1]
    assert behavior.played == [(sprite, "写代码")]
    runtime.updated.emit({"a": "idle", "b": "idle"})
    qapp.processEvents()
    assert "已完成" in bubbles[-1][1]


def test_native_polling_does_not_write_application_config(tmp_path, qapp):
    runtime = CodexRuntime(SimpleNamespace(config={"agent_link": {"codex": False}}))
    runtime.start()
    assert runtime.worker is None
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("terminal", ["task_complete", "task_aborted"])
def test_large_transcript_record_does_not_hide_completed_sessions(tmp_path, monkeypatch, qapp, terminal):
    import json
    from datetime import datetime
    from PySide6.QtCore import Qt

    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    day = tmp_path / "sessions" / datetime.now().strftime("%Y/%m/%d")
    day.mkdir(parents=True)
    started = {"type": "event_msg", "payload": {"type": "task_started"}}
    large = {"type": "response_item", "payload": {"type": "function_call_output", "output": "x" * (2 * 1024 * 1024)}}
    for index in range(4):
        records = [started, large]
        if index < 2:
            records.append({"type": "event_msg", "payload": {"type": terminal}})
        (day / f"session-{index}.jsonl").write_text("".join(json.dumps(record) + "\n" for record in records))
    runtime = CodexRuntime(SimpleNamespace())
    snapshots = []
    runtime.updated.connect(snapshots.append, Qt.DirectConnection)
    monkeypatch.setattr(runtime.stopped, "wait", lambda _: runtime.stopped.set())
    runtime.poll()
    states = snapshots[-1]
    assert sum(state != "idle" for state in states.values()) == 2
    assert states[str(day / "session-0.jsonl")] == "idle"
    assert states[str(day / "session-1.jsonl")] == "idle"


def test_partial_large_record_is_retried_until_newline_then_completion(tmp_path, monkeypatch, qapp):
    import json
    from datetime import datetime
    from PySide6.QtCore import Qt

    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    day = tmp_path / "sessions" / datetime.now().strftime("%Y/%m/%d")
    day.mkdir(parents=True)
    path = day / "partial.jsonl"
    started = json.dumps({"type": "event_msg", "payload": {"type": "task_started"}}) + "\n"
    large = json.dumps({"type": "response_item", "payload": {"type": "function_call_output", "output": "x" * (2 * 1024 * 1024)}})
    path.write_text(started + large[:-10])
    runtime = CodexRuntime(SimpleNamespace())
    snapshots = []
    runtime.updated.connect(snapshots.append, Qt.DirectConnection)

    def next_cycle(_):
        if len(snapshots) == 1:
            with path.open("a") as stream:
                stream.write(large[-10:] + "\n")
                stream.write(json.dumps({"type": "event_msg", "payload": {"type": "task_complete"}}) + "\n")
        else:
            runtime.stopped.set()

    monkeypatch.setattr(runtime.stopped, "wait", next_cycle)
    runtime.poll()
    assert snapshots == [{str(path): "thinking"}, {str(path): "idle"}]


@pytest.mark.parametrize("slots", [[1], [1, 4]])
def test_finished_session_notifies_its_previous_pet_once(qapp, slots):
    sprites = {slot: Sprite() for slot in slots}
    bubbles = []
    behavior = Behavior()
    overlay = SimpleNamespace(
        _spawned_slots={sprite: slot for slot, sprite in sprites.items()},
        _all_sprites=lambda: list(sprites.values()),
        _sprite_visible=lambda s: True,
        host_for_sprite=lambda s: SimpleNamespace(behavior=behavior),
        _show_bubble_text_for=lambda *args: bubbles.append(args),
    )
    runtime = CodexRuntime(SimpleNamespace(_overlay_shell=overlay))
    runtime.updated.emit({"a": "working", "b": "working", "c": "thinking"})
    qapp.processEvents()
    bubbles.clear()
    runtime.updated.emit({"a": "idle", "b": "working", "c": "thinking"})
    qapp.processEvents()
    finished = [entry for entry in bubbles if "会话已结束" in entry[1]]
    assert len(finished) == 1
    assert finished[0][0] is sprites[1]
    assert "1个会话已结束" in finished[0][1]
    assert f"剩余{2 if len(slots) == 1 else 1}个会话" in finished[0][1]
    before = len(bubbles)
    runtime.updated.emit({"a": "idle", "b": "working", "c": "thinking"})
    qapp.processEvents()
    assert len(bubbles) == before
    runtime.updated.emit({"a": "idle", "b": "idle", "c": "idle"})
    qapp.processEvents()
    assert "剩余0个会话" in bubbles[-1][1]


@pytest.mark.parametrize("slots", [[1], [1, 4]])
def test_new_session_notice_survives_work_phase_changes(qapp, monkeypatch, slots):
    now = [100.0]
    monkeypatch.setattr("pet.codex_runtime.time.monotonic", lambda: now[0])
    sprites = {slot: Sprite() for slot in slots}
    bubbles = []
    behavior = Behavior()
    overlay = SimpleNamespace(
        _spawned_slots={sprite: slot for slot, sprite in sprites.items()},
        _all_sprites=lambda: list(sprites.values()),
        _sprite_visible=lambda s: True,
        host_for_sprite=lambda s: SimpleNamespace(behavior=behavior),
        _show_bubble_text_for=lambda *args: bubbles.append(args),
    )
    runtime = CodexRuntime(SimpleNamespace(_overlay_shell=overlay))
    runtime.updated.emit({"a": "thinking", "b": "thinking"})
    qapp.processEvents()
    bubbles.clear()
    runtime.updated.emit({"a": "thinking", "b": "thinking", "c": "thinking"})
    qapp.processEvents()
    notices = [entry for entry in bubbles if "新增1个会话" in entry[1]]
    assert len(notices) == 1
    assert notices[0][0] is sprites[1]
    before = len(bubbles)
    now[0] += .5
    runtime.updated.emit({"a": "working", "b": "working", "c": "working"})
    qapp.processEvents()
    assert len(bubbles) == before
    # Action-required state may interrupt a passive lifecycle notice.
    runtime.updated.emit({"a": "attention", "b": "working", "c": "working"})
    qapp.processEvents()
    assert "等待查看" in bubbles[-1][1]
    now[0] += 5
    runtime.updated.emit({"a": "working", "b": "working", "c": "working"})
    qapp.processEvents()
    assert "工作中" in bubbles[-1][1]


def test_new_session_is_picked_up_on_next_half_second_poll(tmp_path, monkeypatch, qapp):
    import json
    from datetime import datetime
    from PySide6.QtCore import Qt

    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    day = tmp_path / "sessions" / datetime.now().strftime("%Y/%m/%d")
    day.mkdir(parents=True)
    record = json.dumps({"type": "event_msg", "payload": {"type": "task_started"}}) + "\n"
    (day / "first.jsonl").write_text(record)
    runtime = CodexRuntime(SimpleNamespace())
    snapshots, waits = [], []
    runtime.updated.connect(snapshots.append, Qt.DirectConnection)

    def next_cycle(interval):
        waits.append(interval)
        if len(snapshots) == 1:
            (day / "new.jsonl").write_text(record)
        else:
            runtime.stopped.set()

    monkeypatch.setattr(runtime.stopped, "wait", next_cycle)
    runtime.poll()
    assert [len(snapshot) for snapshot in snapshots] == [1, 2]
    assert waits == [.5, .5]


def test_recently_resumed_old_session_is_discovered(tmp_path, monkeypatch, qapp):
    import json
    from datetime import datetime, timedelta
    from PySide6.QtCore import Qt

    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    old_day = tmp_path / "sessions" / (datetime.now() - timedelta(days=30)).strftime("%Y/%m/%d")
    old_day.mkdir(parents=True)
    runtime = CodexRuntime(SimpleNamespace())
    snapshots = []
    runtime.updated.connect(snapshots.append, Qt.DirectConnection)

    def next_cycle(_):
        if len(snapshots) == 1:
            (old_day / "resumed.jsonl").write_text(json.dumps({"type": "event_msg", "payload": {"type": "task_started"}}) + "\n")
        else:
            runtime.stopped.set()

    monkeypatch.setattr(runtime.stopped, "wait", next_cycle)
    runtime.poll()
    assert snapshots == [{}, {str(old_day / "resumed.jsonl"): "thinking"}]


def test_known_active_session_survives_age_cutoff_and_disappears_on_archive(tmp_path, monkeypatch, qapp):
    import json
    import os
    import time
    from datetime import datetime
    from PySide6.QtCore import Qt

    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    day = tmp_path / "sessions" / datetime.now().strftime("%Y/%m/%d")
    day.mkdir(parents=True)
    path = day / "active.jsonl"
    path.write_text(json.dumps({"type": "event_msg", "payload": {"type": "task_started"}}) + "\n")
    runtime = CodexRuntime(SimpleNamespace())
    snapshots = []
    runtime.updated.connect(snapshots.append, Qt.DirectConnection)

    def next_cycle(_):
        if len(snapshots) == 1:
            stale = time.time() - 10 * 86400
            os.utime(path, (stale, stale))
        elif len(snapshots) == 2:
            path.unlink()
        else:
            runtime.stopped.set()

    monkeypatch.setattr(runtime.stopped, "wait", next_cycle)
    runtime.poll()
    assert snapshots == [{str(path): "thinking"}, {str(path): "thinking"}, {}]


def test_discovery_does_not_count_stale_history_or_subagents(tmp_path, monkeypatch, qapp):
    import json
    import os
    import time
    from PySide6.QtCore import Qt

    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    day = tmp_path / "sessions" / "2020/01/01"
    day.mkdir(parents=True)
    started = {"type": "event_msg", "payload": {"type": "task_started"}}
    stale = day / "stale.jsonl"
    stale.write_text(json.dumps(started) + "\n")
    old = time.time() - 10 * 86400
    os.utime(stale, (old, old))
    subagent = {"type": "session_meta", "payload": {"source": {"subagent": {"parent_thread_id": "parent"}}}}
    (day / "subagent.jsonl").write_text(json.dumps(subagent) + "\n" + json.dumps(started) + "\n")
    runtime = CodexRuntime(SimpleNamespace())
    snapshots = []
    runtime.updated.connect(snapshots.append, Qt.DirectConnection)
    monkeypatch.setattr(runtime.stopped, "wait", lambda _: runtime.stopped.set())
    runtime.poll()
    assert not any(value != "idle" for value in snapshots[-1].values())
    assert str(stale) not in snapshots[-1]
