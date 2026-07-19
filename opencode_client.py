"""Thin Python client for the opencode serve HTTP API (serve-transport for spectra runners).

One OpencodeServer per pipeline run:
    server = OpencodeServer(REPO_ROOT, required_agents=AGENT_NAMES, required_mcp=("pdf-reader", "tavily-remote"))
    server.start()
    try:
        result = server.run_step(agent="source_processor", model="kimi/kimi-k3",
                                 prompt="Read your task from: ...", slug="rfp-doc",
                                 timeout_s=3600)
    finally:
        server.stop()

Verified against opencode 1.18.3 (see docs/openapi/opencode-1.18.3.json and SPEC_SERVE_API.md §3.9).
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import socket
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx

logger = logging.getLogger("opencode_client")

HEALTH_TIMEOUT_S = 60
SSE_GRACE_S = 1.0


def find_opencode() -> str:
    if os.name == "nt":
        return shutil.which("opencode.cmd") or shutil.which("opencode") or "opencode.cmd"
    return shutil.which("opencode") or "opencode"


def split_model(model: str) -> dict:
    """'kimi/kimi-k3' -> {'providerID': 'kimi', 'modelID': 'kimi-k3'}"""
    provider, _, model_id = model.partition("/")
    return {"providerID": provider, "modelID": model_id}


def extract_text(response_json: dict) -> str:
    """Concatenate final assistant text from POST /message response parts."""
    parts = response_json.get("parts") or []
    return "".join(p.get("text", "") for p in parts if p.get("type") == "text")


@dataclass
class StepResult:
    success: bool
    final_text: str = ""
    error_kind: str = ""          # "", "timeout", "api", "process"
    error: str = ""
    session_id: str = ""
    event_log: str = ""           # raw SSE lines (agent.events.jsonl equivalent)
    tokens: dict = field(default_factory=dict)
    cost: float | None = None


class _SessionEvents:
    """Per-step SSE capture: raw log lines, first fatal error, permission/question dispatch."""

    PROGRESS_TYPES = ("message.part.delta", "message.part.updated", "message.updated")

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.lines: list[str] = []
        self.first_error: dict | None = None        # session.error payload (non-abort)
        self.aborted = threading.Event()
        self.stalled = threading.Event()
        self.permission_requests: list[dict] = []
        self.question_requests: list[dict] = []
        self.last_progress = time.time()

    def feed(self, event: dict) -> None:
        etype = event.get("type", "")
        props = event.get("properties") or {}
        if props.get("sessionID") != self.session_id:
            return
        self.lines.append(json.dumps(event, ensure_ascii=False))
        if etype in self.PROGRESS_TYPES:
            self.last_progress = time.time()
        if etype == "session.error":
            err = props.get("error") or {}
            if err.get("name") == "MessageAbortedError":
                self.aborted.set()
            elif self.first_error is None:
                self.first_error = err
        elif etype in ("permission.asked", "permission.v2.asked"):
            self.permission_requests.append(props)
        elif etype in ("question.asked", "question.v2.asked"):
            self.question_requests.append(props)


class OpencodeServer:
    def __init__(self, repo_root: Path, port: int | None = None,
                 required_agents: tuple[str, ...] = (), required_mcp: tuple[str, ...] = (),
                 client: httpx.Client | None = None):
        self.repo_root = Path(repo_root)
        self.port = port or self._free_port()
        self.base_url = f"http://127.0.0.1:{self.port}"
        self.required_agents = required_agents
        self.required_mcp = required_mcp
        self._client = client                    # injectable for tests
        self._proc: subprocess.Popen | None = None
        self._server_log: list[str] = []
        self.version: str = ""

    # ── lifecycle ────────────────────────────────────────────────────────────
    @staticmethod
    def _free_port() -> int:
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(base_url=self.base_url, timeout=httpx.Timeout(None, connect=10))
        return self._client

    def start(self) -> None:
        logger.info(f"starting opencode serve on port {self.port} (cwd={self.repo_root})")
        self._proc = subprocess.Popen(
            [find_opencode(), "serve", "--port", str(self.port)],
            cwd=str(self.repo_root),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace",
        )
        threading.Thread(target=self._drain_log, daemon=True).start()
        self._wait_health()
        self._sanity_check()

    def _drain_log(self) -> None:
        if self._proc and self._proc.stdout:
            for line in self._proc.stdout:
                self._server_log.append(line.rstrip())

    def _wait_health(self) -> None:
        t0 = time.time()
        while time.time() - t0 < HEALTH_TIMEOUT_S:
            try:
                r = self.client.get("/global/health", timeout=2)
                if r.status_code == 200 and r.json().get("healthy"):
                    self.version = r.json().get("version", "")
                    logger.info(f"server healthy, version {self.version}")
                    return
            except httpx.HTTPError:
                pass
            time.sleep(0.5)
        tail = "\n".join(self._server_log[-20:])
        raise RuntimeError(f"opencode serve did not become healthy in {HEALTH_TIMEOUT_S}s.\n{tail}")

    def _sanity_check(self) -> None:
        if self.required_agents:
            available = {a.get("name") for a in self.client.get("/agent").json()}
            missing = [a for a in self.required_agents if a not in available]
            if missing:
                raise RuntimeError(f"agents not visible to server: {missing}")
        if self.required_mcp:
            status = self.client.get("/mcp").json()
            failed = [m for m in self.required_mcp
                      if status.get(m, {}).get("status") != "connected"]
            if failed:
                raise RuntimeError(f"required MCP servers not connected: {failed} "
                                   f"(statuses: {json.dumps(status)})")

    def stop(self) -> None:
        try:
            self.client.post("/instance/dispose", timeout=5)
        except httpx.HTTPError:
            pass
        if self._client is not None:
            self._client.close()
            self._client = None
        if self._proc:
            if os.name == "nt":
                # The .cmd wrapper respawns the real binary as a grandchild;
                # terminate() alone leaks it — kill the whole tree.
                subprocess.run(["taskkill", "/PID", str(self._proc.pid), "/T", "/F"],
                               capture_output=True)
            else:
                self._proc.terminate()
            try:
                self._proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._proc.kill()

    # ── SSE ──────────────────────────────────────────────────────────────────
    def _sse_listen(self, capture: _SessionEvents, stop: threading.Event,
                    auto_approve: bool, on_event=None) -> None:
        try:
            with httpx.Client(base_url=self.base_url, timeout=None) as c:
                with c.stream("GET", "/event") as r:
                    for line in r.iter_lines():
                        if stop.is_set():
                            return
                        if not line.startswith("data:"):
                            continue
                        try:
                            event = json.loads(line[len("data:"):])
                        except json.JSONDecodeError:
                            continue
                        capture.feed(event)
                        if on_event is not None:
                            try:
                                on_event(event)
                            except Exception:  # noqa: BLE001 — callback must not kill SSE
                                pass
                        if auto_approve and capture.permission_requests:
                            self._approve_pending(capture)
                        if capture.question_requests:
                            self._reject_pending_questions(capture)
        except Exception as exc:  # noqa: BLE001 — SSE is best-effort
            logger.warning(f"SSE listener stopped: {exc!r}")

    def _approve_pending(self, capture: _SessionEvents) -> None:
        while capture.permission_requests:
            props = capture.permission_requests.pop()
            pid = props.get("id")
            try:
                self.client.post(f"/session/{capture.session_id}/permissions/{pid}",
                                 json={"response": "once"}, timeout=10)
                logger.info(f"[{capture.session_id}] permission {pid} approved (once)")
            except httpx.HTTPError as exc:
                logger.warning(f"permission reply failed: {exc!r}")

    def _reject_pending_questions(self, capture: _SessionEvents) -> None:
        """Pipeline agents must not ask the user anything — auto-reject so they proceed."""
        while capture.question_requests:
            props = capture.question_requests.pop()
            qid = props.get("id")
            try:
                self.client.post(f"/question/{qid}/reject", timeout=10)
                logger.info(f"[{capture.session_id}] question {qid} auto-rejected "
                            f"(headless run)")
            except httpx.HTTPError as exc:
                logger.warning(f"question reject failed: {exc!r}")

    def _stall_watchdog(self, capture: _SessionEvents, stop: threading.Event,
                        stall_timeout_s: int, pending: threading.Event) -> None:
        """Abort the step if no message progress events arrive for stall_timeout_s."""
        while not stop.wait(15):
            if not pending.is_set():
                return
            silent = time.time() - capture.last_progress
            if silent > stall_timeout_s:
                logger.error(f"[{capture.session_id}] no progress events for "
                             f"{int(silent)}s — aborting as stalled")
                capture.stalled.set()
                self._abort(capture.session_id)
                return

    # ── main entry ───────────────────────────────────────────────────────────
    def run_step(self, *, agent: str, model: str, prompt: str, slug: str,
                 timeout_s: int, parent_id: str | None = None,
                 auto_approve: bool = True, use_sse: bool = True,
                 stall_timeout_s: int = 420, on_event=None) -> StepResult:
        body_session = {"title": slug}
        if parent_id:
            body_session["parentID"] = parent_id
        try:
            session = self.client.post("/session", json=body_session, timeout=15).json()
        except httpx.HTTPError as exc:
            return StepResult(False, error_kind="process", error=f"session create: {exc!r}")

        sid = session.get("id", "")
        capture = _SessionEvents(sid)
        stop = threading.Event()
        pending = threading.Event()
        pending.set()
        sse_thread = None
        if use_sse:
            sse_thread = threading.Thread(target=self._sse_listen,
                                          args=(capture, stop, auto_approve, on_event),
                                          daemon=True)
            sse_thread.start()
            threading.Thread(target=self._stall_watchdog,
                             args=(capture, stop, stall_timeout_s, pending),
                             daemon=True).start()

        try:
            resp = self.client.post(
                f"/session/{sid}/message",
                json={"agent": agent, "model": split_model(model),
                      "parts": [{"type": "text", "text": prompt}]},
                timeout=httpx.Timeout(timeout_s + 60, connect=15),
            )
        except httpx.TimeoutException:
            self._abort(sid)
            stop.set()
            return StepResult(False, error_kind="timeout",
                              error=f"timeout after {timeout_s}s (aborted)",
                              session_id=sid, event_log="\n".join(capture.lines))
        except httpx.HTTPError as exc:
            stop.set()
            if capture.stalled.is_set():
                return StepResult(False, error_kind="stall",
                                  error=f"no progress events for {stall_timeout_s}s (aborted)",
                                  session_id=sid, event_log="\n".join(capture.lines))
            return StepResult(False, error_kind="process", error=repr(exc),
                              session_id=sid, event_log="\n".join(capture.lines))
        finally:
            pending.clear()
            stop.set()
            if sse_thread:
                sse_thread.join(timeout=SSE_GRACE_S + 2)

        if capture.stalled.is_set():
            return StepResult(False, error_kind="stall",
                              error=f"no progress events for {stall_timeout_s}s (aborted)",
                              session_id=sid, event_log="\n".join(capture.lines))

        if resp.status_code != 200:
            return StepResult(False, error_kind="process",
                              error=f"HTTP {resp.status_code}: {resp.text[:500]}",
                              session_id=sid, event_log="\n".join(capture.lines))

        if capture.first_error is not None:
            err = capture.first_error
            msg = (err.get("data") or {}).get("message") or err.get("name", "unknown")
            return StepResult(False, error_kind="api", error=msg,
                              session_id=sid, event_log="\n".join(capture.lines))

        data = resp.json()
        info = data.get("info") or {}
        return StepResult(True, final_text=extract_text(data), session_id=sid,
                          event_log="\n".join(capture.lines),
                          tokens=info.get("tokens") or {}, cost=info.get("cost"))

    def _abort(self, session_id: str) -> None:
        try:
            self.client.post(f"/session/{session_id}/abort", timeout=10)
        except httpx.HTTPError as exc:
            logger.warning(f"abort failed for {session_id}: {exc!r}")
