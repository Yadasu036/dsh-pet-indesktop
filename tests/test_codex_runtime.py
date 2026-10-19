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
