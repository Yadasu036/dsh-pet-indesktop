"""Persistent Codex stdio client. No per-request application launches."""

import subprocess, selectors, os, json, time, threading, atexit
import shutil
from pathlib import Path


def cli_path():
    """Run the installed CLI in an explicitly background-only macOS bundle.

    The vendor bundle has no LSUIElement/LSBackgroundOnly declaration. Never
    edit it: create a versioned private wrapper containing only the executable.
    No credentials or account data are copied into this bundle.
    """
    import sys
    import plistlib
    import hashlib

    candidate = Path("/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex")
    if sys.platform != "darwin" or not candidate.exists():
        return shutil.which("codex") or "codex"
    stat = candidate.stat()
    version = hashlib.sha256(f"{stat.st_size}:{stat.st_mtime_ns}".encode()).hexdigest()[:16]
    root = Path.home() / "Library/Caches/dsh-pet-codex" / version / "CodexHelper.app/Contents"
    executable = root / "MacOS/codex"
    if not executable.exists():
        executable.parent.mkdir(parents=True, exist_ok=True)
        temporary = executable.with_suffix(".tmp")
        shutil.copy2(candidate, temporary)
        temporary.replace(executable)
        info = {
            "CFBundleExecutable": "codex",
            "CFBundleIdentifier": "local.dsh-pet.codex-helper",
            "CFBundlePackageType": "APPL",
            "LSUIElement": True,
            "LSBackgroundOnly": True,
        }
        (root / "Info.plist").write_bytes(plistlib.dumps(info))
        subprocess.run(["codesign", "--force", "--deep", "--sign", "-", str(root.parent)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return str(executable)


class Client:
    def __init__(self):
        self.lock = threading.RLock()
        self.proc = None
        self.seq = 0
        self.buf = b""
        self.sel = None
        atexit.register(self.close)

    def close(self):
        if self.proc:
            p = self.proc
            self.proc = None
            if p.poll() is None:
                p.terminate()
                try:
                    p.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    p.kill()
                    p.wait()
            if self.sel:
                self.sel.close()

    def send(self, x):
        self.proc.stdin.write((json.dumps(x) + "\n").encode())
        self.proc.stdin.flush()

    def read(self, deadline):
        while b"\n" not in self.buf:
            if time.monotonic() > deadline:
                raise TimeoutError("Codex timeout")
            if self.sel.select(min(1, max(0, deadline - time.monotonic()))):
                b = os.read(self.proc.stdout.fileno(), 65536)
                if not b:
                    raise RuntimeError("Codex disconnected")
                self.buf += b
        line, self.buf = self.buf.split(b"\n", 1)
        return json.loads(line)

    def start(self):
        if self.proc and self.proc.poll() is None:
            return
        self.close()
        self.buf = b""
        self.proc = subprocess.Popen(
            [cli_path(), "app-server", "-c", "features={}", "--listen", "stdio://"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        self.sel = selectors.DefaultSelector()
        self.sel.register(self.proc.stdout, selectors.EVENT_READ)
        self.call("initialize", {"clientInfo": {"name": "desktop_pet_background", "version": "2.0"}}, start=False)
        self.send({"method": "initialized"})

    def call(self, method, params=None, start=True):
        with self.lock:
            if start:
                self.start()
            self.seq += 1
            ident = self.seq
            x = {"id": ident, "method": method}
            if params is not None:
                x["params"] = params
            self.send(x)
            deadline = time.monotonic() + 45
            while True:
                d = self.read(deadline)
                if d.get("id") == ident:
                    if "error" in d:
                        raise RuntimeError("Codex RPC rejected " + method)
                    return d.get("result", {})

    def chat(self, prompt):
        with self.lock:
            try:
                return self._chat(prompt)
            except Exception:
                self.close()
                raise

    def _chat(self, prompt):
        with self.lock:
            t = self.call(
                "thread/start",
                {
                    "model": "gpt-6-luna",
                    "cwd": os.path.dirname(__file__),
                    "ephemeral": True,
                    "approvalPolicy": "never",
                    "sandbox": "read-only",
                    "config": {"model_reasoning_effort": "low"},
                },
            )
            tid = t["thread"]["id"]
            r = self.call("turn/start", {"threadId": tid, "input": [{"type": "text", "text": prompt}]})
            turnid = r["turn"]["id"]
            answers = []
            deadline = time.monotonic() + 150
            while True:
                d = self.read(deadline)
                method = d.get("method")
                p = d.get("params", {})
                if p.get("threadId") != tid:
                    continue
                if method == "item/completed":
                    item = p.get("item", {})
                    if item.get("type") == "agentMessage":
                        answers.append(item.get("text", ""))
                if method == "turn/completed" and p.get("turn", {}).get("id") == turnid:
                    if p["turn"].get("status") != "completed" or not answers:
                        raise RuntimeError("Codex turn failed")
                    return "\n".join(answers)


CLIENT = Client()
