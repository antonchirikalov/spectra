#!/usr/bin/env python3
"""
spectra — solution_design_runner.py

Phase 0: Read requirements document, create output directory, initialise ledger.
Phase 1: Run solution_designer agent for each model in parallel.
Phase 2: Run solution_design_selector — picks the best candidate as _solution_design.md.
Phase 3: Critic loop (max MAX_CRITIC_ROUNDS) — review, revise on REVISE, stop on APPROVED.
Phase 4: Print final output summary.

Usage:
    python3 solution_design_runner.py run <path_to/_requirements.md> [--models MODEL ...]
    python3 solution_design_runner.py status <output_dir>
    python3 solution_design_runner.py resume <output_dir> [--retry-failed] [--force-step STEP_ID]

Step IDs (for --force-step):
    designer-<model-slug>
    selector
    critic:r1  critic:r2  critic:r3
    revision:r1  revision:r2
"""

import argparse
import atexit
import json
import os
import re
import shutil
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger


def _load_dotenv(env_path: Path) -> None:
    """Load .env into os.environ so subprocesses (opencode) inherit the vars."""
    if not env_path.exists():
        return
    with env_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = val


_load_dotenv(Path(__file__).resolve().parent / ".env")

# ── Constants ──────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parent
AGENT_TIMEOUT_S = 3600
MAX_CRITIC_ROUNDS = 3
MIN_OUTPUT_BYTES = 200

import model_config as _mc

_MODEL_CFG = _mc.load_model_config(REPO_ROOT)
try:
    DEFAULT_MODEL = _mc.default_model(_MODEL_CFG)
    DESIGNER_MODELS = _mc.designer_models(_MODEL_CFG)
except _mc.ModelConfigError:
    DEFAULT_MODEL = None  # run/resume re-validate at startup and refuse to start
    DESIGNER_MODELS = []


def _find_opencode() -> str:
    import shutil
    if sys.platform == "win32":
        return shutil.which("opencode.cmd") or shutil.which("opencode") or "opencode.cmd"
    return shutil.which("opencode") or "opencode"


OPENCODE_EXE = _find_opencode()

# ── Serve transport (opencode serve + HTTP API; see docs/SPEC_SERVE_API.md) ────
_TRANSPORT = "serve"                # "subprocess" | "serve" (CLI --transport); serve is default
_SERVER = None
_SERVER_LOCK = threading.Lock()
_ROOT_SESSION = None

_SD_AGENTS = ("solution_designer", "solution_design_selector", "solution_design_critic")


def _serve_server():
    """Lazily start the shared opencode server and root session for this run."""
    global _SERVER, _ROOT_SESSION
    if _SERVER is not None:
        return _SERVER
    with _SERVER_LOCK:
        if _SERVER is not None:
            return _SERVER
        from opencode_client import OpencodeServer
        _SERVER = OpencodeServer(REPO_ROOT, required_agents=_SD_AGENTS,
                                 required_mcp=("tavily-remote",))
        _SERVER.start()
        root = _SERVER.client.post(
            "/session", json={"title": f"sd-{datetime.now():%Y%m%d-%H%M%S}"},
            timeout=15).json()
        _ROOT_SESSION = root.get("id")
        atexit.register(_shutdown_serve)
        logger.info(f"serve transport ready (root session {_ROOT_SESSION})")
    return _SERVER


def _shutdown_serve():
    global _SERVER, _ROOT_SESSION
    if _SERVER is not None:
        _SERVER.stop()
        _SERVER = None
        _ROOT_SESSION = None


def _run_step_serve(agent_name: str, prompt_file: Path, slug: str, model: str):
    """One agent step via serve transport. Returns StepResult."""
    import time as _time

    server = _serve_server()
    last_event = {"type": None}
    t0 = _time.time()

    def _on_event(ev):
        props = ev.get("properties") or {}
        if props.get("sessionID"):
            last_event["type"] = ev.get("type")

    def _watch():
        while not done.is_set():
            if done.wait(30):
                return
            el = int(_time.time() - t0)
            print(f"[{datetime.now():%H:%M:%S}] [{slug}] running... {el}s elapsed"
                  f" (last event: {last_event['type']})", flush=True)

    done = threading.Event()
    watcher = threading.Thread(target=_watch, daemon=True)
    print(f"[{datetime.now():%H:%M:%S}] [{slug}] start", flush=True)
    watcher.start()
    try:
        return server.run_step(
            agent=agent_name, model=model,
            prompt=f"Read your task from: {prompt_file}",
            slug=slug, timeout_s=AGENT_TIMEOUT_S, parent_id=_ROOT_SESSION,
            on_event=_on_event)
    finally:
        done.set()
        watcher.join(timeout=2)

logger.remove()


# ── Validation gates ───────────────────────────────────────────────────────────
def gate_design_file(path: Path) -> tuple[bool, str]:
    if not path.exists():
        return False, "file not found"
    size = path.stat().st_size
    if size < MIN_OUTPUT_BYTES:
        return False, f"too small ({size} bytes)"
    return True, "ok"


def gate_verdict_file(path: Path) -> tuple[bool, str]:
    if not path.exists():
        return False, "file not found"
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return False, "empty file"
    first_line = text.splitlines()[0]
    if first_line.startswith(("VERDICT: APPROVED", "VERDICT: REVISE")):
        return True, "ok"
    return False, f"unexpected first line: {first_line!r}"


# ── Ledger ─────────────────────────────────────────────────────────────────────
class Ledger:
    """Crash-safe state tracker — state.json is the single source of truth."""

    SCHEMA_VERSION = 1

    def __init__(self, path: Path) -> None:
        self._path = path
        self._state: dict = {}
        self._lock = threading.Lock()

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _save(self) -> None:
        self._state["updated_at"] = self._now()
        tmp = self._path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self._state, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self._path)

    @classmethod
    def create(cls, path: Path, run_id: str, requirements_path: Path,
               designer_models: list[str]) -> "Ledger":
        l = cls(path)
        l._state = {
            "schema_version": cls.SCHEMA_VERSION,
            "run_id": run_id,
            "requirements_path": str(requirements_path),
            "designer_models": designer_models,
            "created_at": l._now(),
            "updated_at": l._now(),
            "steps": {},
            "loops": {
                "critic": {
                    "round": 0,
                    "max_rounds": MAX_CRITIC_ROUNDS,
                    "last_verdict": None,
                    "complete": False,
                }
            },
            "winning_model": None,
        }
        l._save()
        return l

    @classmethod
    def load(cls, path: Path) -> "Ledger":
        l = cls(path)
        l._state = json.loads(path.read_text(encoding="utf-8"))
        for sid, step in l._state.get("steps", {}).items():
            if step.get("status") == "running":
                logger.warning(f"[ledger] '{sid}' was running at crash → reset to pending")
                step["status"] = "pending"
        l._save()
        return l

    @property
    def run_id(self) -> str:
        return self._state["run_id"]

    @property
    def requirements_path(self) -> Path:
        return Path(self._state["requirements_path"])

    @property
    def designer_models(self) -> list[str]:
        return self._state.get("designer_models", DESIGNER_MODELS)

    @property
    def winning_model(self) -> str | None:
        return self._state.get("winning_model")

    @winning_model.setter
    def winning_model(self, value: str) -> None:
        with self._lock:
            self._state["winning_model"] = value
            self._save()

    @property
    def raw_state(self) -> dict:
        return self._state

    @property
    def critic_loop_state(self) -> dict:
        return self._state["loops"]["critic"]

    def get_critic_round(self) -> int:
        return self._state["loops"]["critic"]["round"]

    def get_last_critic_verdict(self) -> str | None:
        return self._state["loops"]["critic"].get("last_verdict")

    def is_critic_complete(self) -> bool:
        return self._state["loops"]["critic"]["complete"]

    def update_critic_loop(self, round_num: int, last_verdict: str) -> None:
        with self._lock:
            self._state["loops"]["critic"]["round"] = round_num
            self._state["loops"]["critic"]["last_verdict"] = last_verdict
            self._save()

    def set_critic_complete(self, last_verdict: str) -> None:
        with self._lock:
            self._state["loops"]["critic"]["complete"] = True
            self._state["loops"]["critic"]["last_verdict"] = last_verdict
            self._save()

    def is_done(self, step_id: str, artifact_path: Path, gate_fn) -> bool:
        with self._lock:
            step = self._state.get("steps", {}).get(step_id, {})
            if step.get("status") != "done":
                return False
        ok, _ = gate_fn(artifact_path)
        return ok

    def mark_running(self, step_id: str) -> None:
        with self._lock:
            step = self._state.setdefault("steps", {}).setdefault(step_id, {})
            step["status"] = "running"
            step["started_at"] = self._now()
            step["attempts"] = step.get("attempts", 0) + 1
            self._save()

    def mark_done(self, step_id: str, artifact_path: Path, wall_s: float) -> None:
        with self._lock:
            self._state.setdefault("steps", {})[step_id] = {
                "status": "done",
                "artifact": str(artifact_path),
                "wall_s": round(wall_s, 1),
                "done_at": self._now(),
            }
            self._save()

    def mark_failed(self, step_id: str, error: str, wall_s: float) -> None:
        with self._lock:
            step = self._state.setdefault("steps", {}).setdefault(step_id, {})
            step.update({
                "status": "failed",
                "error": error,
                "wall_s": round(wall_s, 1),
                "failed_at": self._now(),
            })
            self._save()

    def reset_failed_steps(self) -> int:
        with self._lock:
            count = 0
            has_failed_critic = False
            for sid, step in self._state["steps"].items():
                if step.get("status") == "failed":
                    step["status"] = "pending"
                    count += 1
                    if sid.startswith(("critic:", "revision:")):
                        has_failed_critic = True
            if has_failed_critic and self._state["loops"]["critic"].get("complete"):
                self._state["loops"]["critic"]["complete"] = False
            if count:
                self._save()
            return count

    def reset_step(self, step_id: str) -> bool:
        with self._lock:
            step = self._state["steps"].get(step_id)
            if step is None:
                return False
            step["status"] = "pending"
            if step_id.startswith(("critic:", "revision:")):
                self._state["loops"]["critic"]["complete"] = False
            self._save()
            return True


# ── Heartbeat ──────────────────────────────────────────────────────────────────
def _run_with_heartbeat(cmd: list, slug: str, timeout: int) -> subprocess.CompletedProcess:
    stop = threading.Event()

    def _beat():
        t0 = datetime.now()
        while not stop.wait(10):
            elapsed = int((datetime.now() - t0).total_seconds())
            print(f"[{datetime.now():%H:%M:%S}] [{slug}] running... "
                  f"{elapsed}s elapsed, timeout in {timeout - elapsed}s", flush=True)

    threading.Thread(target=_beat, daemon=True).start()
    try:
        return subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, cwd=str(REPO_ROOT),
            encoding="utf-8", errors="replace"
        )
    finally:
        stop.set()


# ── Agent runner ───────────────────────────────────────────────────────────────
@dataclass
class AgentRun:
    slug: str
    success: bool
    error: str = ""
    event_log: str = ""


def run_agent_write(
    agent_name: str,
    prompt_file: Path,
    slug: str,
    output_path: Path,
    model: str = None,
    logs_dir: Path = None,
) -> AgentRun:
    """Run agent; agent writes output to output_path via write tool."""
    if _TRANSPORT == "serve":
        m = model or DEFAULT_MODEL
        logger.info(f"[{slug}] Starting agent via serve ({m}) → {output_path.name}")
        res = _run_step_serve(agent_name, prompt_file, slug, m)
        if logs_dir:
            logs_dir.mkdir(parents=True, exist_ok=True)
            if res.event_log:
                (logs_dir / f"{slug}.events.jsonl").write_text(res.event_log, encoding="utf-8")
        if not res.success:
            if res.error_kind == "stall" and output_path.exists() \
                    and output_path.stat().st_size > 0:
                logger.warning(f"[{slug}] step stalled after writing output — accepting")
                return AgentRun(slug=slug, success=True, event_log=res.event_log)
            logger.error(f"[{slug}] serve step failed ({res.error_kind}): {res.error}")
            return AgentRun(slug=slug, success=False, error=res.error or res.error_kind,
                            event_log=res.event_log)
        ok = output_path.exists() and output_path.stat().st_size > 0
        if not ok:
            logger.warning(f"[{slug}] serve step done but output missing: {output_path}")
        else:
            logger.info(f"[{slug}] Done; {output_path.stat().st_size} bytes")
        return AgentRun(slug=slug, success=ok,
                        error="" if ok else "output not written",
                        event_log=res.event_log)
    m = model or DEFAULT_MODEL
    cmd = [
        OPENCODE_EXE, "run",
        "--agent", agent_name,
        "--model", m,
        "--format", "json",
        "--dangerously-skip-permissions",
        f"Read your task from: {prompt_file}",
    ]
    logger.info(f"[{slug}] Starting agent ({m}) → {output_path.name}")
    logger.debug(f"[{slug}] cmd: {' '.join(cmd)}")
    print(f"[{datetime.now():%H:%M:%S}] [{slug}] start", flush=True)

    try:
        proc = _run_with_heartbeat(cmd, slug, AGENT_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        logger.error(f"[{slug}] Timed out after {AGENT_TIMEOUT_S}s")
        return AgentRun(slug=slug, success=False, error="timeout")

    if logs_dir:
        logs_dir.mkdir(parents=True, exist_ok=True)
        if proc.stdout:
            (logs_dir / f"{slug}.events.jsonl").write_text(proc.stdout, encoding="utf-8")
        if proc.stderr:
            (logs_dir / f"{slug}.stderr.txt").write_text(proc.stderr, encoding="utf-8")

    logger.debug(f"[{slug}] exit {proc.returncode}, stdout {len(proc.stdout)} chars")
    if proc.returncode != 0:
        err = proc.stderr.strip() or f"exit code {proc.returncode}"
        logger.error(f"[{slug}] Failed: {err}")
        return AgentRun(slug=slug, success=False, error=err, event_log=proc.stdout)

    ok = output_path.exists() and output_path.stat().st_size > 0
    if not ok:
        logger.warning(f"[{slug}] Exit 0 but output missing: {output_path}")
    else:
        logger.info(f"[{slug}] Done; {output_path.stat().st_size} bytes")

    return AgentRun(slug=slug, success=ok,
                    error="" if ok else "output not written",
                    event_log=proc.stdout)


# ── Step runner with idempotency ───────────────────────────────────────────────
def run_step(step_id: str, ledger: Ledger, gate_fn, artifact_path: Path, run_fn) -> bool:
    if ledger.is_done(step_id, artifact_path, gate_fn):
        print(f"[SKIP] {step_id} (already done)", flush=True)
        return True
    ledger.mark_running(step_id)
    t0 = datetime.now()
    result: AgentRun = run_fn()
    wall_s = (datetime.now() - t0).total_seconds()
    passed, detail = gate_fn(artifact_path)
    if result.success and passed:
        ledger.mark_done(step_id, artifact_path, wall_s)
        return True
    err = result.error or f"gate failed: {detail}"
    ledger.mark_failed(step_id, err, wall_s)
    return False


# ── Prompt writers ─────────────────────────────────────────────────────────────
def _safe_model_slug(model: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "_", model)


def write_designer_prompt(prompt_file: Path, requirements_path: Path,
                           output_file: Path, revision_instructions: str = "") -> None:
    lines = [
        f"Requirements document: {requirements_path}",
        f"Output file: {output_file}",
    ]
    if revision_instructions:
        lines.append(f"Revision instructions: {revision_instructions}")
    prompt_file.write_text("\n".join(lines), encoding="utf-8")


def write_selector_prompt(prompt_file: Path,
                           candidates: list[tuple[str, str, Path]],
                           output_path: Path, report_path: Path) -> None:
    lines = [f"Candidate {label} ({model}): {path}" for label, model, path in candidates]
    lines += [f"Output file: {output_path}", f"Selection report: {report_path}"]
    prompt_file.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_critic_prompt(prompt_file: Path, design_path: Path, verdict_path: Path) -> None:
    prompt_file.write_text(
        f"Solution design document: {design_path}\n"
        f"Verdict output: {verdict_path}\n",
        encoding="utf-8",
    )


def write_revision_prompt(prompt_file: Path, requirements_path: Path,
                           output_file: Path, verdict_path: Path) -> None:
    verdict_text = verdict_path.read_text(encoding="utf-8") if verdict_path.exists() else ""
    issues_match = re.search(r"## Issues\n(.+?)(?=\n## |\Z)", verdict_text, re.DOTALL)
    issues_text = issues_match.group(1).strip() if issues_match else verdict_text.strip()
    prompt_file.write_text(
        f"Requirements document: {requirements_path}\n"
        f"Output file: {output_file}\n"
        f"Revision instructions: Address the following issues from the critic review:\n"
        f"{issues_text}\n",
        encoding="utf-8",
    )


# ── Verdict parser ─────────────────────────────────────────────────────────────
def parse_verdict(verdict_path: Path) -> str:
    if not verdict_path.exists():
        return "REVISE"
    return "APPROVED" if "VERDICT: APPROVED" in verdict_path.read_text(encoding="utf-8") else "REVISE"


def parse_winning_model(report_path: Path, designer_models: list[str]) -> str:
    fallback = designer_models[0]
    if not report_path.exists():
        return fallback
    m = re.search(r"WINNING_MODEL:\s*(.+)", report_path.read_text(encoding="utf-8"))
    return m.group(1).strip() if m else fallback


# ── Status display ─────────────────────────────────────────────────────────────
_STATUS_ICON = {"done": "✓", "failed": "✗", "running": "⟳", "pending": "○"}


def _print_run_state(ledger: Ledger, out_dir: Path) -> None:
    st = ledger.raw_state
    critic = ledger.critic_loop_state
    print(f"\n{'─' * 70}", flush=True)
    print(f"  Run:      {st['run_id']}", flush=True)
    print(f"  Created:  {st['created_at']}", flush=True)
    print(f"  Updated:  {st['updated_at']}", flush=True)
    print(f"  Models:   {', '.join(st.get('designer_models', []))}", flush=True)
    if st.get("winning_model"):
        print(f"  Winner:   {st['winning_model']}", flush=True)
    print(f"  Critic:   round {critic.get('round', 0)}/{critic.get('max_rounds', MAX_CRITIC_ROUNDS)}"
          f"  verdict={critic.get('last_verdict') or 'N/A'}"
          f"  complete={critic.get('complete', False)}", flush=True)
    print(flush=True)
    steps = st.get("steps", {})
    if not steps:
        print("  (no steps recorded yet)", flush=True)
    else:
        print(f"  {'Step':<32} {'Status':<10} {'Elapsed':>8}  {'Tries':>5}  Info", flush=True)
        print(f"  {'─' * 66}", flush=True)
        for sid, s in steps.items():
            icon = _STATUS_ICON.get(s.get("status", ""), "?")
            wall = f"{s['wall_s']:.0f}s" if s.get("wall_s") else "  -"
            tries = s.get("attempts", 1)
            info = s.get("error") or (Path(s["artifact"]).name if s.get("artifact") else "")
            print(f"  {icon} {sid:<31} {s.get('status','?'):<10} {wall:>8}  {tries:>5}  {info}",
                  flush=True)
    print(f"{'─' * 70}\n", flush=True)


# ── Pipeline ───────────────────────────────────────────────────────────────────
def _execute_pipeline(out_dir: Path, requirements_path: Path,
                       ledger: Ledger, designer_models: list[str]) -> int:
    prompts_dir = out_dir / "prompts"
    prompts_dir.mkdir(exist_ok=True)
    logs_dir = out_dir / "logs"
    logs_dir.mkdir(exist_ok=True)

    print(f"[PHASE:0] Output dir:      {out_dir}", flush=True)
    print(f"[PHASE:0] Requirements:    {requirements_path}", flush=True)
    print(f"[PHASE:0] Designer models: {', '.join(designer_models)}", flush=True)

    design_paths = {
        model: out_dir / f"_design_{_safe_model_slug(model)}.md"
        for model in designer_models
    }

    # ── Phase 1: parallel design generation ───────────────────────────────────
    print("\n[PHASE:1] Generating solution design(s)...", flush=True)
    tasks = []
    for model in designer_models:
        step_id = f"designer-{_safe_model_slug(model)}"
        artifact = design_paths[model]
        if ledger.is_done(step_id, artifact, gate_design_file):
            print(f"[SKIP] {step_id} (already done)", flush=True)
            continue
        prompt_file = prompts_dir / f"designer_{_safe_model_slug(model)}_prompt.txt"
        write_designer_prompt(prompt_file, requirements_path, artifact)
        tasks.append({"step_id": step_id, "model": model,
                       "prompt_file": prompt_file, "artifact": artifact})

    if tasks:
        with ThreadPoolExecutor(max_workers=len(tasks)) as pool:
            future_to_task = {
                pool.submit(
                    run_step,
                    t["step_id"], ledger, gate_design_file, t["artifact"],
                    lambda _t=t: run_agent_write(
                        "solution_designer", _t["prompt_file"], _t["step_id"],
                        _t["artifact"], model=_t["model"], logs_dir=logs_dir,
                    ),
                ): t
                for t in tasks
            }
            for future in as_completed(future_to_task):
                t = future_to_task[future]
                try:
                    ok = future.result()
                    print(f"[PHASE:1] {t['model']}: {'ok' if ok else 'FAILED'}", flush=True)
                except Exception as exc:
                    logger.error(f"[{t['step_id']}] Exception: {exc}")
                    ledger.mark_failed(t["step_id"], str(exc), 0.0)
                    print(f"[PHASE:1] {t['model']}: FAILED (exception)", flush=True)

    successful_models = [
        m for m in designer_models
        if ledger.is_done(f"designer-{_safe_model_slug(m)}", design_paths[m], gate_design_file)
    ]
    if not successful_models:
        print("[ERROR] No successful design candidates. Aborting.", file=sys.stderr)
        return 1

    # ── Phase 2: selection ─────────────────────────────────────────────────────
    print("\n[PHASE:2] Selecting best design...", flush=True)
    final_design_path = out_dir / "_solution_design.md"
    selection_report_path = out_dir / "_selection_report.md"

    if not ledger.is_done("selector", final_design_path, gate_design_file):
        if len(successful_models) == 1:
            winning_model = successful_models[0]
            shutil.copy2(design_paths[winning_model], final_design_path)
            selection_report_path.write_text(
                f"WINNING_MODEL: {winning_model}\n\n"
                f"## Selection Rationale\n\nOnly one candidate succeeded in Phase 1.\n"
            )
            ledger.mark_done("selector", final_design_path, 0.0)
            print(f"[PHASE:2] One candidate; selected: {winning_model}", flush=True)
        else:
            candidates = [(chr(65 + i), m, design_paths[m])
                          for i, m in enumerate(successful_models)]
            selector_prompt = prompts_dir / "selector_prompt.txt"
            write_selector_prompt(selector_prompt, candidates,
                                   final_design_path, selection_report_path)
            ok = run_step(
                "selector", ledger, gate_design_file, final_design_path,
                lambda: run_agent_write(
                    "solution_design_selector", selector_prompt, "selector",
                    final_design_path, model=_mc.sd_role_model("selector", _MODEL_CFG),
                    logs_dir=logs_dir,
                ),
            )
            if not ok:
                print("[WARNING] Selector failed; falling back to first candidate.", flush=True)
                shutil.copy2(design_paths[successful_models[0]], final_design_path)
                selection_report_path.write_text(f"WINNING_MODEL: {successful_models[0]}\n", encoding="utf-8")
                ledger.mark_done("selector", final_design_path, 0.0)
    else:
        print("[SKIP] selector (already done)", flush=True)

    winning_model = ledger.winning_model or parse_winning_model(selection_report_path, designer_models)
    if not ledger.winning_model:
        ledger.winning_model = winning_model
    print(f"[PHASE:2] Winning model: {winning_model}", flush=True)

    # ── Phase 3: critic loop ───────────────────────────────────────────────────
    print("\n[PHASE:3] Critic review loop...", flush=True)
    final_verdict = ledger.get_last_critic_verdict() or "REVISE"
    final_round = ledger.get_critic_round()

    if ledger.is_critic_complete():
        print(f"[SKIP] Critic loop (complete: {final_verdict})", flush=True)
    else:
        for round_num in range(1, MAX_CRITIC_ROUNDS + 1):
            print(f"[PHASE:3] Round {round_num}/{MAX_CRITIC_ROUNDS}", flush=True)
            final_round = round_num

            verdict_path = out_dir / f"_verdict_round{round_num}.md"
            critic_prompt = prompts_dir / f"critic_prompt_r{round_num}.txt"
            write_critic_prompt(critic_prompt, final_design_path, verdict_path)

            ok = run_step(
                f"critic:r{round_num}", ledger, gate_verdict_file, verdict_path,
                lambda rn=round_num: run_agent_write(
                    "solution_design_critic",
                    prompts_dir / f"critic_prompt_r{rn}.txt",
                    f"critic-r{rn}",
                    out_dir / f"_verdict_round{rn}.md",
                    model=_mc.sd_role_model("critic", _MODEL_CFG),
                    logs_dir=logs_dir,
                ),
            )
            final_verdict = parse_verdict(verdict_path) if ok else "REVISE"
            if not ok:
                print(f"[PHASE:3] Round {round_num}: critic failed → treating as REVISE", flush=True)
            else:
                print(f"[PHASE:3] Round {round_num}: verdict = {final_verdict}", flush=True)

            ledger.update_critic_loop(round_num, final_verdict)

            if final_verdict == "APPROVED":
                ledger.set_critic_complete("APPROVED")
                break

            if round_num < MAX_CRITIC_ROUNDS:
                revised_output = out_dir / f"_design_revised_r{round_num}.md"
                revision_prompt = prompts_dir / f"revision_prompt_r{round_num}.txt"
                write_revision_prompt(revision_prompt, requirements_path,
                                       revised_output, verdict_path)
                rev_ok = run_step(
                    f"revision:r{round_num}", ledger, gate_design_file, revised_output,
                    lambda rn=round_num: run_agent_write(
                        "solution_designer",
                        prompts_dir / f"revision_prompt_r{rn}.txt",
                        f"revision-r{rn}",
                        out_dir / f"_design_revised_r{rn}.md",
                        model=winning_model,
                        logs_dir=logs_dir,
                    ),
                )
                if rev_ok:
                    shutil.copy2(revised_output, final_design_path)
                    print(f"[PHASE:3] Revised design → {final_design_path.name}", flush=True)
                else:
                    print("[PHASE:3] Revision failed; keeping current design", flush=True)
            else:
                ledger.set_critic_complete(final_verdict)
                print(f"[PHASE:3] Max rounds reached with verdict {final_verdict}", flush=True)

    # ── Phase 4: summary ───────────────────────────────────────────────────────
    print("\n[PHASE:4] Pipeline complete.", flush=True)
    print(f"[DONE] Output dir:       {out_dir}", flush=True)
    print(f"[DONE] Final design:     {final_design_path}", flush=True)
    print(f"[DONE] Selection report: {selection_report_path}", flush=True)
    print(f"[DONE] Winning model:    {winning_model}", flush=True)
    print(f"[DONE] Critic verdict:   {final_verdict} (after {final_round} round(s))", flush=True)
    if final_design_path.exists():
        n = final_design_path.read_text(encoding="utf-8").count("<!-- ILLUSTRATION:")
        print(f"[DONE] Illustration placeholders: {n}", flush=True)

    return 0 if final_verdict == "APPROVED" else 1


# ── Commands ───────────────────────────────────────────────────────────────────
def cmd_run(requirements_path: Path, designer_models: list[str] | None) -> int:
    if not requirements_path.exists():
        print(f"[ERROR] Requirements file not found: {requirements_path}", file=sys.stderr)
        return 1
    designer_models = _mc.designer_models(_MODEL_CFG, designer_models)
    run_id = datetime.now().strftime("solution_design_%Y%m%d_%H%M%S")
    out_dir = requirements_path.parent.parent / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    ledger = Ledger.create(out_dir / "state.json", run_id, requirements_path, designer_models)
    return _execute_pipeline(out_dir, requirements_path, ledger, designer_models)


def cmd_status(output_dir: Path) -> int:
    state_path = output_dir / "state.json"
    if not state_path.exists():
        print(f"[ERROR] No state.json found in {output_dir}", file=sys.stderr)
        return 1
    ledger = Ledger.load(state_path)
    _print_run_state(ledger, output_dir)
    return 0


def cmd_resume(output_dir: Path, retry_failed: bool = False,
               force_step: str | None = None) -> int:
    state_path = output_dir / "state.json"
    if not state_path.exists():
        print(f"[ERROR] No state.json found in {output_dir}", file=sys.stderr)
        return 1

    ledger = Ledger.load(state_path)

    if retry_failed:
        n = ledger.reset_failed_steps()
        print(f"[RESUME] Reset {n} failed step(s) to pending" if n else
              "[RESUME] No failed steps to reset", flush=True)

    if force_step:
        if ledger.reset_step(force_step):
            print(f"[RESUME] Force-reset step '{force_step}' to pending", flush=True)
        else:
            print(f"[WARNING] Step '{force_step}' not found in ledger", flush=True)

    print(f"[RESUME] Resuming run: {ledger.run_id}", flush=True)
    _print_run_state(ledger, output_dir)

    requirements_path = ledger.requirements_path
    if not requirements_path.exists():
        print(f"[ERROR] Requirements file not found: {requirements_path}", file=sys.stderr)
        return 1

    designer_models = ledger.designer_models
    print(f"[RESUME] Designer models: {', '.join(designer_models)}", flush=True)
    return _execute_pipeline(output_dir, requirements_path, ledger, designer_models)


# ── Entry point ────────────────────────────────────────────────────────────────
def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        prog="solution_design_runner",
        description="spectra solution design pipeline",
    )
    sub = parser.add_subparsers(dest="command")

    run_p = sub.add_parser("run", help="Generate solution design from requirements document")
    run_p.add_argument("requirements_path", type=Path)
    run_p.add_argument(
        "--models", nargs="+", default=None, metavar="MODEL",
        help="Models for parallel generation (default: designer_models from "
             "models.yaml, one entry = one candidate).",
    )
    run_p.add_argument("--verbose", "-v", action="store_true")
    run_p.add_argument(
        "--transport", choices=["subprocess", "serve"], default="serve",
        help="Agent call transport: one shared 'opencode serve' server + "
             "HTTP API (serve, default) or one 'opencode run' process per "
             "step (subprocess, legacy fallback).",
    )

    res_p = sub.add_parser("resume", help="Resume an interrupted run")
    res_p.add_argument("output_dir", type=Path)
    res_p.add_argument("--retry-failed", action="store_true")
    res_p.add_argument("--force-step", metavar="STEP_ID")
    res_p.add_argument("--verbose", "-v", action="store_true")
    res_p.add_argument(
        "--transport", choices=["subprocess", "serve"], default="serve",
        help="Agent call transport on resume (see 'run --transport').",
    )

    sta_p = sub.add_parser("status", help="Show run state")
    sta_p.add_argument("output_dir", type=Path)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    global _TRANSPORT
    _TRANSPORT = getattr(args, "transport", "serve")
    if _TRANSPORT == "serve":
        print("[INFO] Using serve transport (opencode serve + HTTP API)")
    else:
        print("[INFO] Using legacy subprocess transport (one opencode run per step)")

    if args.command in ("run", "resume"):
        try:
            _mc.require_model_config(REPO_ROOT, _MODEL_CFG)
        except _mc.ModelConfigError as e:
            print(f"[ERROR] {e}", file=sys.stderr)
            sys.exit(1)

    log_level = "DEBUG" if getattr(args, "verbose", False) else "INFO"
    logger.add(sys.stderr, level=log_level, colorize=True,
               format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | {message}")

    if args.command == "run":
        sys.exit(cmd_run(args.requirements_path.resolve(), args.models))
    elif args.command == "resume":
        sys.exit(cmd_resume(args.output_dir.resolve(),
                             retry_failed=args.retry_failed,
                             force_step=args.force_step))
    elif args.command == "status":
        sys.exit(cmd_status(args.output_dir.resolve()))


if __name__ == "__main__":
    main()
