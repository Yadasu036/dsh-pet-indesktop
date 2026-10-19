"""In-process Codex session polling; queued Qt delivery never activates a window."""

from __future__ import annotations
import json
import logging
import os
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from PySide6.QtCore import QObject, Signal, Qt
from .codex_sessions import distribute, reduce_event


class CodexRuntime(QObject):
    updated = Signal(object)

    def __init__(self, shell):
        super().__init__()
        self.shell = shell
        self.stopped = threading.Event()
        self.worker = None
        self.updated.connect(self.present, Qt.QueuedConnection)
        self.last = {}
        self.active_sessions = set()
        self.notice_until = {}

    def start(self):
        if not self.shell.config.get("agent_link", {}).get("codex", False):
            return
        if self.worker is not None:
            return
        self.worker = threading.Thread(target=self.poll, name="CodexSessionMonitor", daemon=True)
        self.worker.start()
        self.quota_worker = threading.Thread(target=self.poll_quota, name="CodexQuota", daemon=True)
        self.quota_worker.start()

    def stop(self):
        self.stopped.set()
        if self.worker:
            self.worker.join(timeout=2)

    def poll_quota(self):
        from .codex_rpc import CLIENT

        while not self.stopped.is_set():
            try:
                result = CLIENT.call("account/rateLimits/read")
                data = result.get("rateLimitsByLimitId", {}).get("codex") or result.get("rateLimits") or {}
                payload = {"updated_at": time.time(), "ok": True, "primary": data.get("primary"), "secondary": data.get("secondary")}
            except Exception:
                CLIENT.close()
                payload = {"updated_at": time.time(), "ok": False}
            try:
                path = Path(self.shell.config.dir) / "codex-quota.json"
                temp = path.with_suffix(".tmp")
                temp.write_text(json.dumps(payload))
                temp.replace(path)
            except OSError:
                pass
            self.stopped.wait(180)

    def poll(self):
        root = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))) / "sessions"
        offsets, states, excluded = {}, {}, set()
        while not self.stopped.is_set():
            try:
                for day in (datetime.now() - timedelta(days=n) for n in range(3)):
                    for path in (root / day.strftime("%Y/%m/%d")).glob("*.jsonl"):
                        if path in excluded:
                            continue
                        stat = path.stat()
                        old = offsets.get(path)
                        offset = old[1] if old and old[0] == stat.st_ino and old[1] <= stat.st_size else 0
                        state = states.get(str(path), "idle")
                        with path.open("rb") as stream:
                            stream.seek(offset)
                            while True:
                                pos = stream.tell()
                                # Images/tool output can make a JSONL record exceed 1 MiB.
                                # Read through its newline so later completion events remain reachable.
                                line = stream.readline()
                                if not line:
                                    break
                                if not line.endswith(b"\n"):
                                    stream.seek(pos)
                                    break
                                try:
                                    record = json.loads(line)
                                    if record.get("type") == "session_meta":
                                        source = record.get("payload", {}).get("source")
                                        if isinstance(source, dict) and "subagent" in source:
                                            excluded.add(path)
                                            state = "idle"
                                            break
                                    state = reduce_event(record, state)
                                except (ValueError, AttributeError, TypeError):
                                    pass
                            offsets[path] = (stat.st_ino, stream.tell())
                        states[str(path)] = state
                self.updated.emit(dict(states))
            except OSError:
                pass
            self.stopped.wait(.5)

    def present(self, states):
        overlay = getattr(self.shell, "_overlay_shell", None)
        if overlay is None:
            return
        sprites = {overlay._spawned_slots.get(s, 0): s for s in overlay._all_sprites() if overlay._sprite_visible(s)}
        # Only active turns occupy pets. Finished historical conversations do not
        # inflate the assignment count; one pet receives all live turns.
        active = {key: value for key, value in states.items() if value != "idle"}
        added = set(active) - self.active_sessions
        self.active_sessions = set(active)
        groups = distribute(active, sprites)
        for slot, sessions in groups.items():
            state = next((x for x in ("attention", "error", "working", "thinking") if any(active[s] == x for s in sessions)), "idle")
            snapshot = (state, tuple(sessions))
            sprite = sprites[slot]
            host = overlay.host_for_sprite(sprite)
            previous = self.last.get(slot)
            ended = [session for session in previous[1] if states.get(session) == "idle"] if previous else []
            received = [session for session in sessions if session in added]
            lifecycle_changed = bool(received or ended)
            changed = previous != snapshot
            if not changed and state not in ("thinking", "working"):
                continue
            self.last[slot] = snapshot
            label = {"attention": "等待查看", "error": "异常", "working": "工作中", "thinking": "思考中", "idle": "已完成"}[state]
            if changed and (lifecycle_changed or time.monotonic() >= self.notice_until.get(slot, 0) or state in ("attention", "error")):
                logging.info("Codex session routing: slot=%s state=%s sessions=%s", slot, state, len(sessions))
                message = f"Codex · {label} · {len(sessions)}个会话"
                if received:
                    message = f"Codex · 新增{len(received)}个会话 · 当前{len(sessions)}个会话"
                if ended:
                    message = f"Codex · {len(ended)}个会话已结束 · 剩余{len(sessions)}个会话"
                    if received:
                        message = f"Codex · 新增{len(received)}个会话 · {len(ended)}个会话已结束 · 剩余{len(sessions)}个会话"
                    if not sessions:
                        message += " · 已完成"
                overlay._show_bubble_text_for(sprite, message, 4500)
                if lifecycle_changed:
                    self.notice_until[slot] = time.monotonic() + 4.5
            if state in ("thinking", "working"):
                categories = host.behavior._categories(sprite.library)
                acts = categories.get("acts", [])
                preferred = [a for a in acts if any(word in str(a) for word in ("写代码", "吃Token", "工作"))]
                if acts and host.behavior.state_of(sprite) == "idle":
                    host.behavior.play_once(sprite, str((preferred or acts)[0]))
        self.last = {key: value for key, value in self.last.items() if key in sprites}
        self.notice_until = {key: value for key, value in self.notice_until.items() if key in sprites}
