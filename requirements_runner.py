#!/usr/bin/env python3
"""
spectra — requirements_runner.py

Phase 0: scan project directory, build manifest.
Phase 1: run source_processor agents in parallel (one per source file).
Phase 2: run requirements_writer agent → _requirements.md
Phase 3: requirements_critic loop (up to MAX_CRITIC_ROUNDS).
Discovery mode: Phase 1 → arch_probe → arch_critic → discovery_report.md

Usage:
    python3 requirements_runner.py run <project_dir> [--mode extract|discovery]
    python3 requirements_runner.py status <output_dir>
    python3 requirements_runner.py resume <output_dir> [--retry-failed] [--force-step STEP_ID]

Step IDs (for --force-step):
    extract:<slug>
    phase2:requirements_writer
    critic:r1  critic:r2  ...
    revision:r1  revision:r2  ...
"""

import argparse
import json
import os
import re
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger

# ── Constants ──────────────────────────────────────────────────────────────────
VERSION = "1.0.0"
REPO_ROOT = Path(__file__).resolve().parent
AGENT_TIMEOUT_S = 3600          # 60 min per agent — large PDFs can take 8-10 min
MAX_CRITIC_ROUNDS = 5
MIN_OUTPUT_BYTES = 200
DEFAULT_MODEL = "kimi/kimi-k2.6"

SUPPORTED_EXT = {".md", ".txt", ".docx", ".xlsx", ".pptx",
                 ".pdf", ".png", ".jpg", ".jpeg", ".webp"}
EXCLUDED_DIRS = {"plan", ".git", ".github", "__pycache__", ".venv", "outputs"}

logger.remove()


# ── Data classes ───────────────────────────────────────────────────────────────
@dataclass
class AgentResult:
    slug: str
    success: bool
    raw_text: str
    parsed_json: dict
    error: str = ""
    event_log: str = ""


@dataclass
class ClarifyRequest:
    slug: str
    source_file: str
    question: str


# ── Ledger: crash-safe checkpoint ──────────────────────────────────────────────
class Ledger:
    """Thread-safe run-state ledger stored as state.json in the output directory."""

    SCHEMA_VERSION = 1

    def __init__(self, path: Path):
        self._path = path
        self._state: dict = {}
        self._lock = threading.Lock()

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _save(self):
        self._state["updated_at"] = self._now()
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._state, ensure_ascii=False, indent=2))
        os.replace(tmp, self._path)

    @classmethod
    def create(cls, path: Path, run_id: str, project_dir: Path, output_dir: Path) -> "Ledger":
        led = cls(path)
        led._state = {
            "schema_version": cls.SCHEMA_VERSION,
            "run_id": run_id,
            "project_dir": str(project_dir),
            "output_dir": str(output_dir),
            "created_at": led._now(),
            "critic_round": 0,
            "critic_complete": False,
            "last_verdict": None,
            "steps": {},
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        led._save()
        return led

    @classmethod
    def load(cls, path: Path) -> "Ledger":
        led = cls(path)
        led._state = json.loads(path.read_text())
        for step in led._state.get("steps", {}).values():
            if step.get("state") == "running":
                step["state"] = "pending"
        led._save()
        return led

    @property
    def run_id(self) -> str:
        return self._state["run_id"]

    @property
    def project_dir(self) -> Path:
        return Path(self._state["project_dir"])

    @property
    def output_dir(self) -> Path:
        return Path(self._state["output_dir"])

    @property
    def raw_state(self) -> dict:
        return self._state

    def get_critic_round(self) -> int:
        return self._state.get("critic_round", 0)

    def is_critic_complete(self) -> bool:
        return self._state.get("critic_complete", False)

    def update_critic_loop(self, round_num: int, last_verdict: str) -> None:
        with self._lock:
            self._state["critic_round"] = round_num
            self._state["last_verdict"] = last_verdict
            self._save()

    def set_critic_complete(self, last_verdict: str) -> None:
        with self._lock:
            self._state["critic_complete"] = True
            self._state["last_verdict"] = last_verdict
            self._save()

    def is_done(self, step_id: str, artifact_path: Path, gate_fn) -> bool:
        with self._lock:
            step = self._state.get("steps", {}).get(step_id, {})
            if step.get("state") != "done":
                return False
        ok, _ = gate_fn(artifact_path)
        return ok

    def mark_running(self, step_id: str) -> None:
        with self._lock:
            step = self._state.setdefault("steps", {}).setdefault(step_id, {})
            step["state"] = "running"
            step["started_at"] = self._now()
            step["attempts"] = step.get("attempts", 0) + 1
            self._save()

    def mark_done(self, step_id: str, artifact_path: Path, wall_s: float) -> None:
        with self._lock:
            self._state.setdefault("steps", {})[step_id] = {
                "state": "done",
                "artifact": str(artifact_path),
                "wall_s": round(wall_s, 1),
                "done_at": self._now(),
            }
            self._save()

    def mark_failed(self, step_id: str, error: str, wall_s: float) -> None:
        with self._lock:
            step = self._state.setdefault("steps", {}).setdefault(step_id, {})
            step.update({
                "state": "failed",
                "error": error,
                "wall_s": round(wall_s, 1),
                "failed_at": self._now(),
            })
            self._save()

    def reset_failed_steps(self) -> int:
        with self._lock:
            count = 0
            has_failed_critic = False
            for sid, step in self._state.get("steps", {}).items():
                if step.get("state") == "failed":
                    step["state"] = "pending"
                    count += 1
                    if sid.startswith(("critic:", "revision:")):
                        has_failed_critic = True
            if has_failed_critic and self._state.get("critic_complete"):
                self._state["critic_complete"] = False
            if count:
                self._save()
            return count

    def reset_step(self, step_id: str) -> bool:
        with self._lock:
            step = self._state.get("steps", {}).get(step_id)
            if step is None:
                return False
            step["state"] = "pending"
            if step_id.startswith(("critic:", "revision:")):
                self._state["critic_complete"] = False
            self._save()
            return True


# ── Gate functions ─────────────────────────────────────────────────────────────
def gate_extract_file(path: Path) -> tuple[bool, str]:
    if not path.exists():
        return False, f"missing: {path.name}"
    if path.stat().st_size < 50:
        return False, f"too small: {path.stat().st_size} bytes"
    return True, ""


def gate_requirements_file(path: Path) -> tuple[bool, str]:
    if not path.exists():
        return False, f"missing: {path.name}"
    if path.stat().st_size < MIN_OUTPUT_BYTES:
        return False, f"too small: {path.stat().st_size} bytes"
    return True, ""


def gate_verdict_file(path: Path) -> tuple[bool, str]:
    if not path.exists():
        return False, f"missing: {path.name}"
    try:
        first_line = path.read_text(encoding="utf-8").strip().splitlines()[0]
    except Exception:
        return False, "unreadable"
    if not re.match(r"VERDICT:\s*(APPROVED|REVISE)", first_line):
        return False, f"unexpected first line: {first_line[:60]!r}"
    return True, ""


# ── Pre-flight ─────────────────────────────────────────────────────────────────
def check_opencode_cli() -> bool:
    try:
        result = subprocess.run(
            ["opencode", "--version"], capture_output=True, text=True, timeout=10
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def check_mcp_pdf_reader() -> bool:
    config_paths = [
        Path.home() / ".config" / "opencode" / "opencode.json",
        Path.home() / "Library" / "Application Support" / "Code" / "User" / "mcp.json",
        Path.home() / ".config" / "Code" / "User" / "mcp.json",
    ]
    for p in config_paths:
        if p.exists():
            try:
                cfg = json.loads(p.read_text())
                mcp = cfg.get("mcp", cfg.get("servers", {}))
                if "pdf-reader" in mcp:
                    return True
            except Exception:
                pass
    return False


# ── Slug helpers ───────────────────────────────────────────────────────────────
def slugify(name: str) -> str:
    stem = Path(name).stem if "." in name else name
    slug = re.sub(r"[^\w\-]", "_", stem)
    slug = re.sub(r"_+", "_", slug).strip("_").lower()
    return slug or "unnamed"


def unique_slug(name: str, existing: set) -> str:
    base = slugify(name)
    if base not in existing:
        existing.add(base)
        return base
    counter = 2
    while f"{base}_{counter}" in existing:
        counter += 1
    slug = f"{base}_{counter}"
    existing.add(slug)
    return slug


# ── Phase 0: Scan ──────────────────────────────────────────────────────────────
def detect_read_tool(ext: str) -> str:
    if ext == ".pdf":
        return "mcp_pdf-reader"
    if ext in {".png", ".jpg", ".jpeg", ".webp"}:
        return "vision"
    return "read"


def scan_project(project_dir: Path) -> list:
    entries = []
    seen_slugs: set = set()

    for item in sorted(project_dir.iterdir()):
        if item.name.startswith("."):
            continue
        if item.is_dir():
            if item.name in EXCLUDED_DIRS:
                continue
            sub_files = [
                f for f in sorted(item.rglob("*"))
                if f.is_file() and f.suffix.lower() in SUPPORTED_EXT
            ]
            if sub_files:
                slug = unique_slug(item.name, seen_slugs)
                entries.append({
                    "kind": "subfolder",
                    "slug": slug,
                    "path": str(item),
                    "files": [
                        {"path": str(f), "read_tool": detect_read_tool(f.suffix.lower())}
                        for f in sub_files
                    ],
                    "read_tool": "read",
                })
        elif item.is_file() and item.suffix.lower() in SUPPORTED_EXT:
            slug = unique_slug(item.name, seen_slugs)
            entries.append({
                "kind": "file",
                "slug": slug,
                "path": str(item),
                "read_tool": detect_read_tool(item.suffix.lower()),
            })

    return entries


def build_manifest(project_dir: Path, entries: list) -> dict:
    return {
        "runner_version": VERSION,
        "project_dir": str(project_dir),
        "entries": entries,
    }


# ── stdout parser: opencode JSON event stream ──────────────────────────────────
def extract_assistant_text(event_output: str) -> str:
    """Extract assistant text from opencode --format json event stream."""
    text_parts = []
    for line in event_output.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            t = obj.get("type", "")
            if t == "text" and "text" in obj:
                text_parts.append(obj["text"])
            elif t == "assistant":
                content = obj.get("content", "")
                if isinstance(content, str):
                    text_parts.append(content)
                elif isinstance(content, list):
                    for part in content:
                        if isinstance(part, dict) and part.get("type") == "text":
                            text_parts.append(part.get("text", ""))
            elif t == "content_block_delta":
                delta = obj.get("delta", {})
                if delta.get("type") == "text_delta":
                    text_parts.append(delta.get("text", ""))
        except json.JSONDecodeError:
            pass
    return "".join(text_parts) or event_output.strip()


def parse_json_from_text(text: str) -> dict:
    """Extract first JSON object from agent response text."""
    decoder = json.JSONDecoder()
    m = re.search(r"```json\s*(\{.*?)\s*```", text, re.DOTALL)
    if m:
        try:
            obj, _ = decoder.raw_decode(m.group(1))
            return obj
        except json.JSONDecodeError:
            pass
    start = text.find("{")
    if start == -1:
        return {}
    try:
        obj, _ = decoder.raw_decode(text, start)
        return obj
    except json.JSONDecodeError:
        return {}


# ── params.yaml ────────────────────────────────────────────────────────────────
DEFAULT_PARAMS_YAML = """\
industry: unknown
project_type: software
domain_tags: []

# Per-agent model overrides — format: provider/model-id
# Leave empty to use DEFAULT_MODEL (kimi/kimi-k2.6) for all agents
models: {}

trust_policy:
  auto_resolve: true
  escalate_on: [scope, budget, architecture, security]
"""


def create_default_params(plan_dir: Path):
    params_path = plan_dir / "params.yaml"
    if not params_path.exists():
        plan_dir.mkdir(parents=True, exist_ok=True)
        params_path.write_text(DEFAULT_PARAMS_YAML, encoding="utf-8")
        print(f"[INFO] Created {params_path}")


def load_params(plan_dir: Path) -> dict:
    try:
        import yaml
        params_path = plan_dir / "params.yaml"
        if params_path.exists():
            return yaml.safe_load(params_path.read_text()) or {}
    except ImportError:
        pass
    return {}


def model_for(agent_name: str, params: dict) -> str:
    return (params.get("models") or {}).get(agent_name, DEFAULT_MODEL)


# ── Heartbeat ──────────────────────────────────────────────────────────────────
def _run_with_heartbeat(cmd: list, slug: str, cwd: str, timeout: int) -> subprocess.CompletedProcess:
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
            cmd, capture_output=True, text=True, timeout=timeout, cwd=cwd
        )
    finally:
        stop.set()


# ── Agent runners ──────────────────────────────────────────────────────────────
def run_agent(agent_name: str, prompt_file: Path, slug: str,
              model: str = None, project_dir: Path = None) -> AgentResult:
    """Run agent and parse JSON from its stdout (used for source_processor)."""
    m = model or DEFAULT_MODEL
    cmd = [
        "opencode", "run",
        "--agent", agent_name,
        "--model", m,
        "--format", "json",
        "--dangerously-skip-permissions",
        f"Read your task from: {prompt_file}",
    ]
    cwd = str(project_dir or REPO_ROOT)
    logger.info(f"[{slug}] Starting agent ({m})")
    logger.debug(f"[{slug}] cmd: {' '.join(cmd)}")
    print(f"[{datetime.now():%H:%M:%S}] [{slug}] start", flush=True)

    try:
        proc = _run_with_heartbeat(cmd, slug, cwd, AGENT_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        logger.error(f"[{slug}] Timed out after {AGENT_TIMEOUT_S}s")
        return AgentResult(slug=slug, success=False, raw_text="",
                           parsed_json={}, error="timeout")

    logger.debug(f"[{slug}] exit {proc.returncode}, stdout {len(proc.stdout)} chars")
    if proc.returncode != 0:
        err = proc.stderr.strip() or f"exit code {proc.returncode}"
        logger.error(f"[{slug}] Agent failed: {err}")
        return AgentResult(slug=slug, success=False, raw_text=proc.stdout,
                           parsed_json={}, error=err, event_log=proc.stdout)

    raw = extract_assistant_text(proc.stdout)
    parsed = parse_json_from_text(raw)
    logger.info(f"[{slug}] Done; JSON found: {bool(parsed)}")
    return AgentResult(
        slug=slug,
        success=bool(parsed),
        raw_text=raw,
        parsed_json=parsed,
        error="" if parsed else "no valid JSON in response",
        event_log=proc.stdout,
    )


def run_agent_write(agent_name: str, prompt_file: Path, slug: str,
                    output_path: Path, model: str = None,
                    project_dir: Path = None) -> tuple[bool, str]:
    """Run agent; agent writes output to output_path via write tool.
    Returns (success, event_log)."""
    m = model or DEFAULT_MODEL
    cmd = [
        "opencode", "run",
        "--agent", agent_name,
        "--model", m,
        "--format", "json",
        "--dangerously-skip-permissions",
        f"Read your task from: {prompt_file}",
    ]
    cwd = str(project_dir or REPO_ROOT)
    logger.info(f"[{slug}] Starting agent write-mode ({m}) → {output_path.name}")
    logger.debug(f"[{slug}] cmd: {' '.join(cmd)}")
    print(f"[{datetime.now():%H:%M:%S}] [{slug}] start", flush=True)

    try:
        proc = _run_with_heartbeat(cmd, slug, cwd, AGENT_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        logger.error(f"[{slug}] Timed out after {AGENT_TIMEOUT_S}s")
        return False, ""

    logger.debug(f"[{slug}] exit {proc.returncode}")
    if proc.returncode != 0:
        err = proc.stderr.strip() or f"exit code {proc.returncode}"
        logger.error(f"[{slug}] Agent failed: {err}")
        return False, proc.stdout

    logger.info(f"[{slug}] Agent process finished")
    return True, proc.stdout


# ── Phase 1: Prompt rendering ──────────────────────────────────────────────────
PROMPT_TEMPLATE = """\
# Source Extraction Task

## Source Document

{document_instruction}
{assets_block}
## Manifest Entry

```json
{manifest_entry_json}
```
{clarification_block}
## Output Schema

Read: `prompts/source_processor/output_schema.md`

## Strategies

Read: `prompts/source_processor/strategies/`
"""


def render_prompt(entry: dict, clarification: str = "") -> str:
    ext = Path(entry.get("path", "")).suffix.lower()
    read_tool = entry.get("read_tool", "read")

    if entry["kind"] == "subfolder":
        document_instruction = (
            f"This entry is a subfolder: `{entry['path']}`\n"
            f"Read its files listed in the manifest entry below."
        )
        assets_block = ""
    elif read_tool == "mcp_pdf-reader":
        document_instruction = f"Read `{entry['path']}` using the `pdf-reader` MCP tool."
        assets_block = ""
    elif read_tool == "vision":
        document_instruction = f"Read image `{entry['path']}` using your vision capability."
        assets_block = ""
    else:
        document_instruction = f"Read `{entry['path']}` using the `read` tool."
        assets_block = ""

    assets = entry.get("assets", [])
    if assets:
        asset_lines = "\n".join(f"- `{a['path']}`" for a in assets)
        assets_block = f"\n## Additional Assets\n\n{asset_lines}\n"

    clarification_block = ""
    if clarification:
        clarification_block = f"\n## User Clarification\n\n{clarification}\n"

    return PROMPT_TEMPLATE.format(
        document_instruction=document_instruction,
        assets_block=assets_block,
        manifest_entry_json=json.dumps(entry, indent=2, ensure_ascii=False),
        clarification_block=clarification_block,
    )


# ── Phase 1: Parallel extraction ───────────────────────────────────────────────
def _run_agents_parallel(tasks: list, project_dir: Path) -> list:
    results = []
    with ThreadPoolExecutor(max_workers=max(1, len(tasks))) as pool:
        future_to_task = {
            pool.submit(
                run_agent,
                t["agent"], t["prompt_file"], t["slug"],
                model=t.get("model"), project_dir=project_dir,
            ): t
            for t in tasks
        }
        for future in as_completed(future_to_task):
            task = future_to_task[future]
            try:
                result = future.result()
                results.append(result)
                status = "ok" if result.success else f"failed ({result.error})"
                print(f"[PHASE:1] {result.slug}: {status}")
            except Exception as e:
                slug = task["slug"]
                logger.error(f"[{slug}] Unexpected exception: {e}")
                results.append(AgentResult(slug=slug, success=False, raw_text="",
                                           parsed_json={}, error=str(e)))
                print(f"[PHASE:1] {slug}: failed (exception)")
    return results


def _save_extract(result: AgentResult, artifacts_dir: Path):
    extract_dir = artifacts_dir / "extracts" / result.slug
    extract_dir.mkdir(parents=True, exist_ok=True)
    if result.success and result.parsed_json:
        (extract_dir / "extract.json").write_text(
            json.dumps(result.parsed_json, ensure_ascii=False, indent=2)
        )
    else:
        (extract_dir / "extract.error.json").write_text(
            json.dumps({"error": result.error, "partial_raw": result.raw_text[:2000]},
                       ensure_ascii=False, indent=2)
        )
    (extract_dir / "raw.txt").write_text(result.raw_text or "")
    if result.event_log:
        (extract_dir / "agent.events.jsonl").write_text(result.event_log)


def _collect_clarifications(results: list) -> list:
    return [
        ClarifyRequest(
            slug=r.slug,
            source_file=r.parsed_json.get("source_file", r.slug),
            question=r.parsed_json.get("clarification_request", "No details provided"),
        )
        for r in results
        if r.parsed_json.get("needs_clarification")
    ]


def _hitl_clarify(flagged: list, interactive: bool) -> dict:
    if not flagged:
        return {}
    if not interactive:
        for r in flagged:
            logger.info(f"[HITL] Skipping clarification for {r.slug}: {r.question}")
        return {}
    answers = {}
    print("\n" + "─" * 60)
    print(f"[HITL] Agent requests clarification ({len(flagged)} item(s))")
    print("─" * 60)
    for r in flagged:
        print(f"\nFile: {r.source_file}")
        print(f"Question: {r.question}")
        try:
            answer = input("Your answer (Enter to skip): ").strip()
        except EOFError:
            break
        if answer:
            answers[r.slug] = answer
    print("─" * 60 + "\n")
    return answers


def run_phase1(entries: list, project_dir: Path, artifacts_dir: Path,
               params: dict, interactive: bool, ledger: Ledger = None) -> list:
    prompts_dir = artifacts_dir / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)

    already_done: list = []
    tasks = []
    for entry in entries:
        slug = entry["slug"]
        artifact_path = artifacts_dir / "extracts" / slug / "extract.json"
        if ledger and ledger.is_done(f"extract:{slug}", artifact_path, gate_extract_file):
            print(f"[PHASE:1] [{slug}] skipping — already done")
            try:
                parsed_json = json.loads(artifact_path.read_text())
            except Exception:
                parsed_json = {}
            already_done.append(AgentResult(slug=slug, success=True, raw_text="",
                                             parsed_json=parsed_json))
            continue
        prompt_content = render_prompt(entry)
        prompt_file = prompts_dir / f"{slug}.md"
        prompt_file.write_text(prompt_content, encoding="utf-8")
        tasks.append({
            "agent": "source_processor",
            "slug": slug,
            "prompt_file": prompt_file,
            "model": model_for("source_processor", params),
        })

    if tasks:
        suffix = f" ({len(already_done)} already done)" if already_done else ""
        print(f"[PHASE:1] Running {len(tasks)} agent(s) in parallel{suffix}")
        if ledger:
            for t in tasks:
                ledger.mark_running(f"extract:{t['slug']}")
        new_results = _run_agents_parallel(tasks, project_dir)
        for r in new_results:
            _save_extract(r, artifacts_dir)
            if ledger:
                artifact = artifacts_dir / "extracts" / r.slug / "extract.json"
                if r.success:
                    ledger.mark_done(f"extract:{r.slug}", artifact, 0.0)
                else:
                    ledger.mark_failed(f"extract:{r.slug}", r.error, 0.0)
    else:
        print(f"[PHASE:1] All {len(already_done)} extract(s) already done — skipping")
        new_results = []

    results = already_done + new_results

    # HITL:clarify — up to 2 rounds
    for round_num in range(1, 3):
        flagged = _collect_clarifications(results)
        if not flagged:
            break
        print(f"[PHASE:1] {len(flagged)} agent(s) need clarification (round {round_num}/2)")
        answers = _hitl_clarify(flagged, interactive)
        if not answers:
            break
        retry_tasks = []
        for slug, answer in answers.items():
            entry = next((e for e in entries if e["slug"] == slug), None)
            if not entry:
                continue
            prompt_content = render_prompt(entry, clarification=answer)
            prompt_file = prompts_dir / f"{slug}_retry{round_num}.md"
            prompt_file.write_text(prompt_content, encoding="utf-8")
            retry_tasks.append({
                "agent": "source_processor",
                "slug": slug,
                "prompt_file": prompt_file,
                "model": model_for("source_processor", params),
            })
        if retry_tasks:
            retry_results = _run_agents_parallel(retry_tasks, project_dir)
            for rr in retry_results:
                _save_extract(rr, artifacts_dir)
            result_map = {r.slug: r for r in results}
            for rr in retry_results:
                result_map[rr.slug] = rr
            results = list(result_map.values())

    return results


# ── Phase 2: Requirements Writer ───────────────────────────────────────────────
PHASE2_PROMPT_TEMPLATE = """\
# Requirements Writing Task

**Project directory:** `{project_dir}`
**Sources analysed:** {source_count}

## Extract Files

{extract_list}

## Output File

`{output_path}`
"""

PHASE2_REVISION_TEMPLATE = """\
# Requirements Writing Task — Revision Round {round_num}

**Project directory:** `{project_dir}`
**Sources analysed:** {source_count}

## Extract Files

{extract_list}

## Output File

`{output_path}`

## Critic Feedback (must be fully addressed in this revision)

{verdict_content}
"""


def run_phase2(results: list, artifacts_dir: Path, project_dir: Path,
               params: dict, output_dir: Path, ledger: Ledger = None) -> bool:
    successful = [r for r in results if r.success]
    if not successful:
        print("[PHASE:2] Skipped — no successful extracts from Phase 1")
        return False

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "_requirements.md"

    if ledger and ledger.is_done("phase2:requirements_writer", output_path, gate_requirements_file):
        print("[PHASE:2] Skipping — already done")
        return True

    print(f"[PHASE:2] Synthesising {len(successful)} extract(s) into _requirements.md ...")

    extracts_dir = artifacts_dir / "extracts"
    prompts_dir = artifacts_dir / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)

    extract_paths = [extracts_dir / r.slug / "extract.json" for r in successful
                     if (extracts_dir / r.slug / "extract.json").exists()]
    extract_list = "\n".join(f"- `{p}`" for p in extract_paths)

    prompt_content = PHASE2_PROMPT_TEMPLATE.format(
        project_dir=project_dir,
        source_count=len(extract_paths),
        extract_list=extract_list,
        output_path=output_path,
    )
    prompt_file = prompts_dir / "_requirements_writer.md"
    prompt_file.write_text(prompt_content, encoding="utf-8")

    if ledger:
        ledger.mark_running("phase2:requirements_writer")

    ok, event_log = run_agent_write(
        "requirements_writer", prompt_file, "_requirements_writer",
        output_path=output_path,
        model=model_for("requirements_writer", params),
        project_dir=project_dir,
    )

    log_dir = artifacts_dir / "extracts" / "_requirements_writer"
    log_dir.mkdir(parents=True, exist_ok=True)
    if event_log:
        (log_dir / "agent.events.jsonl").write_text(event_log)

    if not ok:
        print("[PHASE:2] FAILED — agent process error")
        if ledger:
            ledger.mark_failed("phase2:requirements_writer", "agent process error", 0.0)
        return False

    if not output_path.exists() or output_path.stat().st_size < MIN_OUTPUT_BYTES:
        print("[PHASE:2] FAILED — agent did not write output file")
        if ledger:
            ledger.mark_failed("phase2:requirements_writer", "output missing/too small", 0.0)
        return False

    if ledger:
        ledger.mark_done("phase2:requirements_writer", output_path, 0.0)

    text = output_path.read_text(encoding="utf-8")
    fr = text.count("| FR-")
    nfr = text.count("| NFR-")
    br = text.count("| BR-")
    print(f"[PHASE:2] Done → {output_path.name} ({fr} FR, {nfr} NFR, {br} BR)")
    return True


# ── Phase 3: Requirements Critic loop ─────────────────────────────────────────
CRITIC_PROMPT_TEMPLATE = """\
# Requirements Critic Task

**Requirements document:** `{requirements_path}`
**Extracts directory:** `{extracts_dir}`
**Verdict output file:** `{verdict_path}`

Read the requirements document, load the output schema and conflict rules, \
cross-check against the source extracts, then write your verdict to the verdict output file.
"""


def run_phase3_critic_loop(
    requirements_path: Path,
    extracts_dir: Path,
    artifacts_dir: Path,
    project_dir: Path,
    params: dict,
    output_dir: Path,
    results: list,
    max_rounds: int = MAX_CRITIC_ROUNDS,
    ledger: Ledger = None,
) -> bool:
    if ledger and ledger.is_critic_complete():
        print("[PHASE:3] Skipping — critic loop already complete")
        return True

    prompts_dir = artifacts_dir / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)

    successful = [r for r in results if r.success]
    extract_paths = [extracts_dir / r.slug / "extract.json" for r in successful
                     if (extracts_dir / r.slug / "extract.json").exists()]
    extract_list = "\n".join(f"- `{p}`" for p in extract_paths)

    start_round = (ledger.get_critic_round() if ledger else 0) + 1

    for round_num in range(start_round, max_rounds + 1):
        verdict_path = artifacts_dir / "extracts" / f"_requirements_critic_r{round_num}" / "verdict.md"
        verdict_path.parent.mkdir(parents=True, exist_ok=True)

        if ledger and ledger.is_done(f"critic:r{round_num}", verdict_path, gate_verdict_file):
            print(f"[PHASE:3] Round {round_num} critic — skipping (already done)")
            verdict_text = verdict_path.read_text(encoding="utf-8").strip()
        else:
            critic_prompt = CRITIC_PROMPT_TEMPLATE.format(
                requirements_path=requirements_path,
                extracts_dir=extracts_dir,
                verdict_path=verdict_path,
            )
            critic_prompt_file = prompts_dir / f"_requirements_critic_r{round_num}.md"
            critic_prompt_file.write_text(critic_prompt, encoding="utf-8")

            print(f"[PHASE:3] Round {round_num}/{max_rounds} — running requirements_critic ...")
            if ledger:
                ledger.mark_running(f"critic:r{round_num}")

            ok, event_log = run_agent_write(
                "requirements_critic", critic_prompt_file,
                f"_requirements_critic_r{round_num}",
                output_path=verdict_path,
                model=model_for("requirements_critic", params),
                project_dir=project_dir,
            )
            if event_log:
                (verdict_path.parent / "agent.events.jsonl").write_text(event_log)

            if not ok or not verdict_path.exists():
                print(f"[PHASE:3] WARNING — critic failed (round {round_num}), continuing")
                if ledger:
                    ledger.mark_failed(f"critic:r{round_num}", "no verdict file", 0.0)
                return True  # non-fatal

            if ledger:
                ledger.mark_done(f"critic:r{round_num}", verdict_path, 0.0)
            verdict_text = verdict_path.read_text(encoding="utf-8").strip()

        if verdict_text.startswith("VERDICT: APPROVED"):
            print(f"[PHASE:3] APPROVED on round {round_num}")
            if ledger:
                ledger.set_critic_complete("APPROVED")
            return True

        print(f"[PHASE:3] REVISE requested (round {round_num})")
        if round_num == max_rounds:
            print(f"[PHASE:3] Safety cap ({max_rounds} rounds) reached — stopping with warnings")
            if ledger:
                ledger.set_critic_complete("REVISE_CAP")
            return True

        # Writer revision
        revision_step = f"revision:r{round_num}"
        rev_done = ledger.is_done(revision_step, requirements_path, gate_requirements_file) if ledger else False
        if rev_done:
            print(f"[PHASE:3] Round {round_num} revision — skipping (already done)")
            if ledger:
                ledger.update_critic_loop(round_num, "REVISE")
            continue

        revision_prompt = PHASE2_REVISION_TEMPLATE.format(
            round_num=round_num + 1,
            project_dir=project_dir,
            source_count=len(extract_paths),
            extract_list=extract_list,
            output_path=requirements_path,
            verdict_content=verdict_text,
        )
        revision_prompt_file = prompts_dir / f"_requirements_writer_r{round_num + 1}.md"
        revision_prompt_file.write_text(revision_prompt, encoding="utf-8")

        print(f"[PHASE:3] Running requirements_writer revision {round_num + 1} ...")
        if ledger:
            ledger.mark_running(revision_step)

        w_ok, w_log = run_agent_write(
            "requirements_writer", revision_prompt_file,
            f"_requirements_writer_r{round_num + 1}",
            output_path=requirements_path,
            model=model_for("requirements_writer", params),
            project_dir=project_dir,
        )
        log_dir = artifacts_dir / "extracts" / f"_requirements_writer_r{round_num + 1}"
        log_dir.mkdir(parents=True, exist_ok=True)
        if w_log:
            (log_dir / "agent.events.jsonl").write_text(w_log)

        if not w_ok:
            print(f"[PHASE:3] WARNING — writer revision failed (round {round_num + 1})")
            if ledger:
                ledger.mark_failed(revision_step, "writer process error", 0.0)
            return True  # non-fatal

        if ledger:
            ledger.mark_done(revision_step, requirements_path, 0.0)
            ledger.update_critic_loop(round_num, "REVISE")

    return True


# ── Discovery pipeline ─────────────────────────────────────────────────────────
DISCOVERY_PROBE_TEMPLATE = """\
# arch_probe Task

**Project directory:** `{project_dir}`
**Sources analysed:** {source_count}

## Extract Files

{extract_list}
"""

DISCOVERY_CRITIC_TEMPLATE = """\
# arch_critic Task

**Project directory:** `{project_dir}`
**arch_probe output:** `{probe_output_path}`
**Write report to:** `{output_path}`
"""


def run_discovery(project_dir: Path, interactive: bool) -> int:
    run_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = project_dir.parent / f"discovery_{run_ts}"
    artifacts_dir = output_dir / f"_artifacts_{run_ts}"
    plan_dir = output_dir / "plan"
    output_dir.mkdir(parents=True, exist_ok=True)
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    logger.add(str(artifacts_dir / "runner.log"), level="DEBUG", encoding="utf-8",
               format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}")

    if not check_opencode_cli():
        print("[ERROR] 'opencode' CLI not found in PATH.", file=sys.stderr)
        return 1

    create_default_params(plan_dir)
    params = load_params(plan_dir)

    print(f"[PHASE:0] Scanning {project_dir} ...")
    entries = scan_project(project_dir)
    if not entries:
        print("[ERROR] No supported files found.", file=sys.stderr)
        return 1
    print(f"[PHASE:0] Found {len(entries)} entries")

    manifest = build_manifest(project_dir, entries)
    intake_dir = artifacts_dir / "intake"
    intake_dir.mkdir(parents=True, exist_ok=True)
    (intake_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2))

    print("[PHASE:1] Starting source extraction ...")
    results = run_phase1(entries, project_dir, artifacts_dir, params, interactive)

    ok = sum(1 for r in results if r.success)
    failed = sum(1 for r in results if not r.success)
    print(f"[PHASE:1] {ok} ok, {failed} failed.")

    successful = [r for r in results if r.success]
    if not successful:
        print("[DONE] Discovery aborted — no successful extracts.")
        return 1

    # arch_probe
    extracts_dir = artifacts_dir / "extracts"
    prompts_dir = artifacts_dir / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)

    extract_paths = [extracts_dir / r.slug / "extract.json" for r in successful
                     if (extracts_dir / r.slug / "extract.json").exists()]
    extract_list = "\n".join(f"- `{p}`" for p in extract_paths)

    probe_prompt = DISCOVERY_PROBE_TEMPLATE.format(
        project_dir=project_dir,
        source_count=len(extract_paths),
        extract_list=extract_list,
    )
    probe_prompt_file = prompts_dir / "_arch_probe.md"
    probe_prompt_file.write_text(probe_prompt, encoding="utf-8")

    print(f"[PHASE:D1] Running arch_probe on {len(extract_paths)} extract(s) ...")
    probe_result = run_agent("arch_probe", probe_prompt_file, "_arch_probe",
                             model=model_for("arch_probe", params),
                             project_dir=project_dir)

    probe_dir = extracts_dir / "_arch_probe"
    probe_dir.mkdir(parents=True, exist_ok=True)
    (probe_dir / "raw.txt").write_text(probe_result.raw_text or "")
    if probe_result.event_log:
        (probe_dir / "agent.events.jsonl").write_text(probe_result.event_log)

    if not probe_result.success or not probe_result.parsed_json:
        print(f"[PHASE:D1] FAILED — {probe_result.error}")
        return 1

    probe_output_path = probe_dir / "probe_output.json"
    probe_output_path.write_text(json.dumps(probe_result.parsed_json, ensure_ascii=False, indent=2))
    q_count = len(probe_result.parsed_json.get("raw_questions", []))
    print(f"[PHASE:D1] Done — {q_count} raw question(s)")

    # arch_critic
    output_path = output_dir / "discovery_report.md"
    critic_prompt = DISCOVERY_CRITIC_TEMPLATE.format(
        project_dir=project_dir,
        probe_output_path=probe_output_path,
        output_path=output_path,
    )
    critic_prompt_file = prompts_dir / "_arch_critic.md"
    critic_prompt_file.write_text(critic_prompt, encoding="utf-8")

    print("[PHASE:D2] Running arch_critic ...")
    ok_c, event_log = run_agent_write(
        "arch_critic", critic_prompt_file, "_arch_critic",
        output_path=output_path,
        model=model_for("arch_critic", params),
        project_dir=project_dir,
    )
    critic_dir = extracts_dir / "_arch_critic"
    critic_dir.mkdir(parents=True, exist_ok=True)
    if event_log:
        (critic_dir / "agent.events.jsonl").write_text(event_log)

    if not ok_c or not output_path.exists() or output_path.stat().st_size < 200:
        print("[PHASE:D2] FAILED — agent did not write discovery_report.md")
        return 1

    q_count = output_path.read_text(encoding="utf-8").count("\n**Q-")
    print(f"[PHASE:D2] Done → discovery_report.md ({q_count} question(s))")
    print(f"[DONE] Discovery report → {output_path}")
    return 0


# ── Status / Resume helpers ────────────────────────────────────────────────────
_STATUS_ICON = {"done": "✓", "failed": "✗", "running": "⟳", "pending": "○"}


def _print_run_state(ledger: Ledger) -> None:
    st = ledger.raw_state
    print(f"\n{'─' * 70}")
    print(f"  Run:      {st['run_id']}")
    print(f"  Created:  {st['created_at']}")
    print(f"  Updated:  {st['updated_at']}")
    print(f"  Project:  {st.get('project_dir', 'N/A')}")
    print(f"  Critic:   round {st.get('critic_round', 0)}  "
          f"verdict={st.get('last_verdict') or 'N/A'}  "
          f"complete={st.get('critic_complete', False)}")
    print()
    steps = st.get("steps", {})
    if not steps:
        print("  (no steps recorded yet)")
    else:
        print(f"  {'Step':<35} {'Status':<10} {'Elapsed':>8}  {'Tries':>5}  Info")
        print(f"  {'─' * 66}")
        for sid, s in steps.items():
            icon = _STATUS_ICON.get(s.get("state", ""), "?")
            wall = f"{s['wall_s']:.0f}s" if s.get("wall_s") else "  -"
            tries = s.get("attempts", 1)
            info = s.get("error") or (Path(s["artifact"]).name if s.get("artifact") else "")
            print(f"  {icon} {sid:<34} {s.get('state', '?'):<10} {wall:>8}  {tries:>5}  {info}")
    print(f"{'─' * 70}\n")


def cmd_status(output_dir: Path) -> int:
    state_path = output_dir / "state.json"
    if not state_path.exists():
        print(f"[ERROR] No state.json found in {output_dir}", file=sys.stderr)
        return 1
    _print_run_state(Ledger.load(state_path))
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
              "[RESUME] No failed steps to reset")

    if force_step:
        if ledger.reset_step(force_step):
            print(f"[RESUME] Force-reset step '{force_step}' to pending")
        else:
            print(f"[WARNING] Step '{force_step}' not found in ledger")

    project_dir = ledger.project_dir
    run_id = ledger.run_id
    _print_run_state(ledger)

    if not project_dir.exists():
        print(f"[ERROR] Project dir not found: {project_dir}", file=sys.stderr)
        return 1

    artifacts_dir = output_dir / f"_artifacts_{run_id}"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    logger.add(str(artifacts_dir / "runner.log"), level="DEBUG", encoding="utf-8",
               format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}")

    print(f"[RESUME] Resuming run {run_id}")

    if not check_opencode_cli():
        print("[ERROR] 'opencode' CLI not found in PATH.", file=sys.stderr)
        return 1

    plan_dir = output_dir / "plan"
    create_default_params(plan_dir)
    params = load_params(plan_dir)

    entries = scan_project(project_dir)
    if not entries:
        print("[ERROR] No supported files found.", file=sys.stderr)
        return 1

    results = run_phase1(entries, project_dir, artifacts_dir, params, False, ledger=ledger)
    ok = sum(1 for r in results if r.success)
    failed = sum(1 for r in results if not r.success)
    print(f"[RESUME] Extraction: {ok} ok, {failed} failed.")

    phase2_ok = run_phase2(results, artifacts_dir, project_dir, params,
                           ledger.output_dir, ledger=ledger)
    if not phase2_ok:
        print("[DONE] Phase 2 failed — check logs above.")
        return 1

    requirements_path = ledger.output_dir / "_requirements.md"
    extracts_dir = artifacts_dir / "extracts"
    run_phase3_critic_loop(
        requirements_path=requirements_path,
        extracts_dir=extracts_dir,
        artifacts_dir=artifacts_dir,
        project_dir=project_dir,
        params=params,
        output_dir=ledger.output_dir,
        results=results,
        ledger=ledger,
    )
    print(f"[DONE] Requirements document → {requirements_path}")
    return 0 if failed == 0 else 1


# ── Entry point ────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="spectra requirements runner")
    sub = parser.add_subparsers(dest="command")

    run_p = sub.add_parser("run", help="Run the extraction pipeline")
    run_p.add_argument("project_dir", type=Path)
    run_p.add_argument("--interactive", action="store_true", default=False)
    run_p.add_argument("--mode", choices=["extract", "discovery"], default="extract")
    run_p.add_argument("--debug", action="store_true", default=False)

    res_p = sub.add_parser("resume", help="Resume an interrupted run")
    res_p.add_argument("output_dir", type=Path)
    res_p.add_argument("--retry-failed", action="store_true")
    res_p.add_argument("--force-step", metavar="STEP_ID")
    res_p.add_argument("--debug", action="store_true", default=False)

    sta_p = sub.add_parser("status", help="Show run state")
    sta_p.add_argument("output_dir", type=Path)

    args = parser.parse_args()

    debug = getattr(args, "debug", False)
    logger.add(sys.stderr, level="DEBUG" if debug else "INFO", colorize=True,
               format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | {message}")

    if args.command == "status":
        return cmd_status(args.output_dir.resolve())

    if args.command == "resume":
        return cmd_resume(args.output_dir.resolve(),
                          retry_failed=args.retry_failed,
                          force_step=args.force_step)

    if args.command != "run":
        parser.print_help()
        return 1

    project_dir = args.project_dir.resolve()
    if not project_dir.is_dir():
        print(f"[ERROR] Not a directory: {project_dir}", file=sys.stderr)
        return 1

    if args.mode == "discovery":
        return run_discovery(project_dir, args.interactive)

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = project_dir.parent / f"requirements_{run_id}"
    artifacts_dir = output_dir / f"_artifacts_{run_id}"
    plan_dir = output_dir / "plan"
    output_dir.mkdir(parents=True, exist_ok=True)
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    logger.add(str(artifacts_dir / "runner.log"), level="DEBUG", encoding="utf-8",
               format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}")

    ledger = Ledger.create(output_dir / "state.json", run_id, project_dir, output_dir)

    if not check_opencode_cli():
        print("[ERROR] 'opencode' CLI not found in PATH.", file=sys.stderr)
        return 1

    create_default_params(plan_dir)
    params = load_params(plan_dir)

    print(f"[PHASE:0] Scanning {project_dir} ...")
    entries = scan_project(project_dir)
    if not entries:
        print("[ERROR] No supported files found.", file=sys.stderr)
        return 1

    n_files = sum(1 for e in entries if e["kind"] == "file")
    n_folders = sum(1 for e in entries if e["kind"] == "subfolder")
    print(f"[PHASE:0] Found {len(entries)} entries ({n_files} files, {n_folders} folders)")

    manifest = build_manifest(project_dir, entries)
    intake_dir = artifacts_dir / "intake"
    intake_dir.mkdir(parents=True, exist_ok=True)
    (intake_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    print(f"[PHASE:0] Manifest → {intake_dir / 'manifest.json'}")

    if any(e.get("read_tool") == "mcp_pdf-reader" for e in entries):
        if not check_mcp_pdf_reader():
            print("[WARN] pdf-reader MCP not found in opencode.json — PDFs may fail.")

    print("[PHASE:1] Starting source extraction ...")
    results = run_phase1(entries, project_dir, artifacts_dir, params,
                         args.interactive, ledger=ledger)

    ok = sum(1 for r in results if r.success)
    failed = sum(1 for r in results if not r.success)
    print(f"[PHASE:1] {ok} ok, {failed} failed.")

    phase2_ok = run_phase2(results, artifacts_dir, project_dir, params,
                           output_dir, ledger=ledger)
    if not phase2_ok:
        print("[DONE] Phase 2 failed — check logs above.")
        return 1

    requirements_path = output_dir / "_requirements.md"
    extracts_dir = artifacts_dir / "extracts"

    run_phase3_critic_loop(
        requirements_path=requirements_path,
        extracts_dir=extracts_dir,
        artifacts_dir=artifacts_dir,
        project_dir=project_dir,
        params=params,
        output_dir=output_dir,
        results=results,
        ledger=ledger,
    )

    print(f"[DONE] Requirements document → {requirements_path}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
