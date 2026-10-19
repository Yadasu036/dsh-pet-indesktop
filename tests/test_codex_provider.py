import threading
from pet.chat.models import ProviderConfig
from pet.chat.providers import OpenAICompatibleProvider
from pet import codex_rpc


def test_auth_chat_uses_persistent_client(monkeypatch):
    calls = []
    monkeypatch.setattr(codex_rpc.CLIENT, "chat", lambda prompt: calls.append(prompt) or "ok")
    config = ProviderConfig("codex")
    config.base_url = "codex://local"
    result = list(OpenAICompatibleProvider().stream([{"role": "user", "content": "hi"}], config, threading.Event()))
    assert result == ["ok"]
    assert len(calls) == 1
