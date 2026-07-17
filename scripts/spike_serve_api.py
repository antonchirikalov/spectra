"""Stage-0 spike: verify opencode serve + HTTP API shapes for the serve-transport migration.

Discovers and prints:
  1. /global/health format
  2. /agent list (are spectra's 12 agents visible?)
  3. /mcp statuses
  4. /doc OpenAPI spec (saved to docs/openapi/)
  5. POST /session + POST /session/:id/message — exact request/response shapes
  6. SSE /event stream event types during a run
  7. POST /session/:id/abort behavior

Usage:  .venv\\Scripts\\python scripts\\spike_serve_api.py
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parent.parent
PORT = 4111
BASE = f"http://127.0.0.1:{PORT}"
SPEC_OUT = REPO_ROOT / "docs" / "openapi"

TRIVIAL_PROMPT = "Reply with exactly one word: OK"


def find_opencode() -> str:
    if os.name == "nt":
        return shutil.which("opencode.cmd") or shutil.which("opencode") or "opencode.cmd"
    return shutil.which("opencode") or "opencode"


OPENCODE_EXE = find_opencode()


def load_env() -> None:
    env_file = REPO_ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def wait_health(client: httpx.Client, timeout_s: int = 60) -> dict:
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        try:
            r = client.get("/global/health", timeout=2)
            if r.status_code == 200:
                return r.json()
        except httpx.HTTPError:
            pass
        time.sleep(0.5)
    raise RuntimeError("server did not become healthy")


def sse_listener(stop: threading.Event, events: list[str]) -> None:
    """Collect SSE event types from GET /event until stopped."""
    try:
        with httpx.Client(base_url=BASE, timeout=None) as c:
            with c.stream("GET", "/event") as r:
                for line in r.iter_lines():
                    if stop.is_set():
                        return
                    if not line:
                        continue
                    events.append(line)
    except Exception as exc:  # noqa: BLE001
        events.append(f"[sse error] {exc!r}")


def try_message_variants(client: httpx.Client, session_id: str) -> tuple[str, dict]:
    """Find the working shape for POST /session/:id/message."""
    variants = [
        ("object model {providerID, modelID}", {
            "agent": "build",
            "model": {"providerID": "kimi", "modelID": "kimi-k3"},
            "parts": [{"type": "text", "text": TRIVIAL_PROMPT}],
        }),
        ("string model 'kimi/kimi-k3'", {
            "agent": "build",
            "model": "kimi/kimi-k3",
            "parts": [{"type": "text", "text": TRIVIAL_PROMPT}],
        }),
        ("no model, no agent", {
            "parts": [{"type": "text", "text": TRIVIAL_PROMPT}],
        }),
    ]
    for name, body in variants:
        try:
            r = client.post(f"/session/{session_id}/message", json=body, timeout=180)
            print(f"  variant [{name}] -> HTTP {r.status_code}")
            if r.status_code == 200:
                return name, r.json()
            print(f"    body: {r.text[:300]}")
        except httpx.HTTPError as exc:
            print(f"  variant [{name}] -> exception {exc!r}")
    return "", {}


def main() -> int:
    load_env()
    SPEC_OUT.mkdir(parents=True, exist_ok=True)

    print(f"[1] starting: {OPENCODE_EXE} serve --port {PORT} (cwd={REPO_ROOT})")
    proc = subprocess.Popen(
        [OPENCODE_EXE, "serve", "--port", str(PORT)],
        cwd=str(REPO_ROOT),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace",
    )
    client = httpx.Client(base_url=BASE, timeout=30)
    try:
        health = wait_health(client)
        print(f"[2] health: {health}")

        r = client.get("/agent")
        agents = [a.get("name") for a in r.json()] if r.status_code == 200 else []
        print(f"[3] agents visible ({len(agents)}): {sorted(agents)}")

        r = client.get("/mcp")
        print(f"[4] mcp statuses: {json.dumps(r.json(), ensure_ascii=False)[:600]}")

        r = client.get("/doc")
        ctype = r.headers.get("content-type", "")
        out = SPEC_OUT / f"opencode-{health.get('version', 'unknown')}.json"
        if "json" in ctype:
            out.write_text(json.dumps(r.json(), indent=2), encoding="utf-8")
        else:
            out = out.with_suffix(".html")
            out.write_text(r.text, encoding="utf-8")
        print(f"[5] /doc -> {ctype} ({len(r.content)} bytes) saved to {out}")

        # session + message shapes
        r = client.post("/session", json={"title": "spike"})
        session = r.json()
        sid = session["id"]
        print(f"[6] session created: keys={sorted(session.keys())}")

        stop = threading.Event()
        events: list[str] = []
        t = threading.Thread(target=sse_listener, args=(stop, events), daemon=True)
        t.start()

        print("[7] probing POST /session/:id/message variants ...")
        variant, resp = try_message_variants(client, sid)
        if resp:
            info = resp.get("info", {})
            parts = resp.get("parts", [])
            print(f"    OK via [{variant}]")
            print(f"    info keys: {sorted(info.keys())}")
            print(f"    parts: {[p.get('type') for p in parts]}")
            texts = [p.get("text", "") for p in parts if p.get("type") == "text"]
            print(f"    text: {texts[-1][:120] if texts else '(none)'}")

        # abort test on a fresh session with a long-running prompt
        print("[8] abort test ...")
        r = client.post("/session", json={"title": "spike-abort"})
        sid2 = r.json()["id"]
        client.post(f"/session/{sid2}/prompt_async", json={
            "agent": "build",
            "parts": [{"type": "text", "text": "Count from 1 to 500, one number per line."}],
        }, timeout=10)
        time.sleep(2)
        r = client.post(f"/session/{sid2}/abort", timeout=10)
        print(f"    abort -> HTTP {r.status_code}, body={r.text[:120]}")
        r = client.get("/session/status")
        print(f"    session/status after abort: {json.dumps(r.json())[:300]}")

        stop.set()
        time.sleep(1)
        types = sorted({
            e.split("data:", 1)[-1] and json.loads(e.split("data:", 1)[-1]).get("type", "?")
            for e in events if e.startswith("data:")
        } - {""})
        print(f"[9] SSE events captured: {len(events)} lines; types: {types}")
        (SPEC_OUT / "spike_events.jsonl").write_text("\n".join(events), encoding="utf-8")
        return 0
    finally:
        print("[10] stopping server")
        try:
            client.post("/instance/dispose", timeout=5)
        except httpx.HTTPError:
            pass
        proc.terminate()
        try:
            out, _ = proc.communicate(timeout=10)
            tail = (out or "").strip().splitlines()[-5:]
            print("    server log tail:", *tail, sep="\n      ")
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    sys.exit(main())
