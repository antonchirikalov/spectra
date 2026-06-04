# prism — Worker Migration Spec: Copilot CLI → Multi-Provider (opencode + Claude Code)

Status: draft for implementation
Scope: replace the per-agent inference backend with a provider-agnostic routing layer
Default target: Kimi K2.6 via opencode (multimodal, best agentic benchmark, $0.95/$4.00 per 1M on Fireworks)
Other providers: DeepSeek, OpenAI, Qwen, Claude — all selectable per-agent via `params.yaml`

---

## 1. Goal

Today every agent in prism is a `copilot` CLI subprocess locked to GitHub's model catalog and billed at Copilot's published API rates (Claude Sonnet 4.6 at $3/$15 per 1M, GPT-5.5 at $5/$30 per 1M). Under GitHub's June 2026 usage-based billing this drains the monthly AI-Credit allowance in days.

This spec introduces a provider registry and a two-CLI routing layer:
- `opencode run` handles all non-Anthropic providers (Kimi, DeepSeek, OpenAI, Qwen) via OpenAI-compatible endpoints


Default recommended model for all agents: `kimi/kimi-k2.6` — the only Chinese model with native multimodal (required for prism's PNG/WEBP input support), 96.6% tool invocation success rate, and best document Q&A benchmark (DeepSearchQA 83.0) among open-weight models.

The Python brain, `state.json` ledger, file protocol, retry/resume logic, and HITL checkpoints stay unchanged.

---

## 2. What changes vs. what stays

Stays exactly as-is:
- `requirements_runner.py` / `solution_design_runner.py` orchestration (phase ordering, parallelism, critic loops, caps)
- `state.json` atomic ledger, crash recovery, `status` / `resume` / `--force-step`
- File protocol between phases and the per-step output-artifact validation
- `plan/params.yaml` structure (the `models: {}` override becomes the routing table)

Changes:
1. The subprocess invocation (`_invoke_agent` / the `cmd = ["copilot", ...]` block)
2. Agent definitions: `.github/agents/*.agent.md` (Copilot format) → opencode agent markdown
3. Provider + MCP configuration: `~/.config/copilot/mcp.json` → `opencode.json`
4. stdout parsing (Copilot JSONL → opencode JSON events) — minimized by trusting disk artifacts
5. The per-agent model map in `params.yaml`

---

## 3. Prerequisites

```bash
# Install opencode (verify the channel for your OS)
curl -fsSL https://opencode.ai/install | bash
opencode --version          # PIN this version; flags have drifted across releases

# DeepSeek key (5M free tokens on signup, no card)
export DEEPSEEK_API_KEY="sk-..."

# Sanity check the run subcommand and its flags on YOUR installed build
opencode run --help
opencode models deepseek    # confirm current model IDs (V4 naming may differ)
```

Version warning: there are two opencode lineages in the wild (the older Go `opencode-ai/opencode` used `-o/--output-format`; current `opencode.ai` uses `--format`). Do not trust this doc's flag names blindly — confirm against `opencode run --help` once, then pin the version in your environment.

---

## 4. Provider registry (opencode.json)

All providers live in a single `~/.config/opencode/opencode.json`. Every provider except Anthropic uses the same `@ai-sdk/openai-compatible` npm package — only `baseURL` and the env var name differ. Anthropic models are handled separately by the `claude` CLI (see §6); no Anthropic block is needed here.

Add only the providers you plan to use. A provider with no agents pointing at it is inert.

```jsonc
{
  "$schema": "https://opencode.ai/config.json",

  "provider": {

    // Kimi K2.6 — recommended default for prism
    // Fireworks = US-hosted mirror of Moonshot weights; client docs don't go to CN
    "kimi": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "Kimi (Fireworks)",
      "options": {
        "baseURL": "https://api.fireworks.ai/inference/v1",
        "apiKey": "{env:FIREWORKS_API_KEY}"
      },
      "models": {
        "kimi-k2.6": { "name": "Kimi K2.6" }
      }
    },

    // OpenAI — drop-in if you have a key; used for Illustrator already
    "openai": {
      "npm": "@ai-sdk/openai",
      "options": { "apiKey": "{env:OPENAI_API_KEY}" },
      "models": {
        "gpt-5.5":    { "name": "GPT-5.5" },
        "gpt-5.4":    { "name": "GPT-5.4" }
      }
    },

    // DeepSeek — cheapest tier for high-volume extraction
    "deepseek": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "DeepSeek",
      "options": {
        "baseURL": "https://api.deepseek.com/v1",
        "apiKey": "{env:DEEPSEEK_API_KEY}"
      },
      "models": {
        "deepseek-chat":     { "name": "DeepSeek V4 chat" },
        "deepseek-reasoner": { "name": "DeepSeek R1" }
      }
    },

    // Qwen — 1M context, good for massive doc sets
    "qwen": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "Qwen (Alibaba)",
      "options": {
        "baseURL": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "apiKey": "{env:QWEN_API_KEY}"
      },
      "models": {
        "qwen3.6-plus": { "name": "Qwen3.6 Plus" }
      }
    }

  },

  // Port your existing copilot mcp.json entries here.
  "mcp": {
    "pdf-reader": {
      "type": "local",
      "command": ["<your pdf-reader launch command>"]
    },
    "tavily-remote": {
      "type": "remote",
      "url": "<your tavily MCP endpoint>"
    },
    "mcp-atlassian": {
      "type": "local",
      "command": ["<your confluence MCP launch command>"]
    }
  },

  // Pre-grant tools so headless `run` never blocks on a permission prompt.
  "permission": {
    "bash":      "allow",
    "read":      "allow",
    "edit":      "allow",
    "webfetch":  "allow",
    "websearch": "allow"
  }
}
```

Model string convention: `provider/model-id` — e.g. `kimi/kimi-k2.6`, `deepseek/deepseek-chat`, `openai/gpt-5.5`, `anthropic/claude-sonnet-4-6`. The runner splits on `/` to decide which CLI to call (see §6).

To add a new provider: copy any block above, change `name`, `baseURL`, `apiKey` env var, and `models`. No runner code changes needed.

---

## 5. Agent migration

opencode agents are markdown files with YAML frontmatter; the body is the system prompt. Install all 12 globally at `~/.config/opencode/agent/<name>.md` so they resolve regardless of the runner's `cwd` (this is how we sidestep the missing `--add-dir`, see §6).

Frontmatter mapping from Copilot `.agent.md`:

| Copilot `.agent.md` | opencode agent `.md`          | Note |
|---------------------|-------------------------------|------|
| `name`              | filename (`<name>.md`)        | invoked as `--agent <name>` |
| `description`       | `description`                 | keep |
| `model`             | omit — pass via `--model`     | lets the runner route per `params.yaml` |
| `tools`             | `tools` / `mode`              | map to opencode permission tokens |
| (body / prompt)     | (body / prompt)               | copy verbatim |

Recommended `mode: all` for every agent so each is directly selectable by `run --agent`.

opencode tool tokens to grant per agent: `read`, `edit`, `bash`, `glob`, `grep`, `webfetch`, `websearch`, `task`, `todowrite`, `skill`. MCP tools (pdf-reader, tavily, confluence) attach automatically when the MCP server is configured and the agent is allowed to use it.

Per-agent tool needs:

| Agent                      | Tools / MCP it needs                          |
|----------------------------|-----------------------------------------------|
| `source_processor`         | read, webfetch, MCP pdf-reader, MCP confluence |
| `arch_probe`               | read, edit, MCP tavily (web search)            |
| `arch_critic`              | read, edit                                     |
| `requirements_writer`      | read, edit                                     |
| `requirements_critic`      | read, edit                                     |
| `solution_designer`        | read, edit, MCP tavily                         |
| `solution_design_selector` | read, edit                                     |
| `solution_design_critic`   | read, edit                                     |
| `Illustrator`              | bash, edit (uses OPENAI_API_KEY directly — out of scope here) |
| `Confluence Publisher`     | bash (runs publish script)                     |
| `word_form_builder`        | read, edit, MCP tavily                         |

Example translated agent (`~/.config/opencode/agent/source_processor.md`):

```markdown
---
description: Reads one source document, identifies its type, extracts requirements data into extract.json
mode: all
tools:
  read: true
  webfetch: true
---

<paste the existing source_processor system prompt body here, unchanged>
```

---

## 6. The invocation refactor — two CLIs, one routing function

The entire routing logic lives in `_invoke_agent`. Anthropic models go through `claude` CLI (OTel, prompt caching, corporate key already configured); everything else goes through `opencode`. The model string prefix is the only branch condition.

```python
import os, subprocess

DEFAULT_MODEL = "kimi/kimi-k2.6"

def _get_cli(model: str) -> str:
    """Return 'claude' for anthropic/* models, 'opencode' for everything else."""
    provider = model.split("/")[0] if "/" in model else ""
    return "claude" if provider == "anthropic" else "opencode"

def _invoke_agent(self, agent_name: str, prompt_file: str, model: str | None = None):
    m = model or self.params.get("models", {}).get(agent_name, DEFAULT_MODEL)
    cli = _get_cli(m)

    if cli == "claude":
        # Anthropic path — uses corporate API key + OTel, identical flags to Copilot
        model_id = m.split("/", 1)[1]   # "anthropic/claude-sonnet-4-6" → "claude-sonnet-4-6"
        cmd = [
            "claude",
            "-p", f"Read your task from: {prompt_file}",
            "--agent", agent_name,
            "--output-format", "stream-json",
            "--dangerously-skip-permissions",
            "--add-dir", str(REPO_ROOT),
            "--model", model_id,
        ]
        run_kwargs = {"cwd": str(PROJECT_DIR)}

    else:
        # opencode path — all non-Anthropic providers (Kimi, DeepSeek, OpenAI, Qwen …)
        cmd = [
            "opencode", "run",
            "--agent", agent_name,
            "--model", m,                    # "kimi/kimi-k2.6" — passed as-is
            "--format", "json",
            "-q",
            f"Read your task from: {prompt_file}",
        ]
        run_kwargs = {"cwd": str(PROJECT_DIR)}

    return subprocess.run(
        cmd,
        capture_output=True, text=True, timeout=1200,
        **run_kwargs
    )
```

What changed from the original Copilot invocation:

| Was (Copilot) | Is (claude path) | Is (opencode path) |
|---|---|---|
| `copilot` | `claude` | `opencode run` |
| `-p "…"` | `-p "…"` (identical) | positional arg (no `-p`) |
| `--agent name` | `--agent name` (identical) | `--agent name` (identical) |
| `--output-format json` | `--output-format stream-json` | `--format json` |
| `--allow-all --no-ask-user` | `--dangerously-skip-permissions` | `permission` block in opencode.json |
| `--add-dir REPO_ROOT` | `--add-dir REPO_ROOT` (identical) | `cwd=PROJECT_DIR` (see §5) |
| `--model model` | `--model claude-sonnet-4-6` | `--model kimi/kimi-k2.6` |

---

## 7. Output parsing / validation

Your runner already treats "did the expected artifact appear on disk?" as the source of truth — keep that as the primary gate. It is CLI-agnostic and survives any change in stdout format.

Downgrade stdout parsing to diagnostics only:
- opencode `--format json` emits a stream of JSON events, not Copilot's JSONL shape. Do not hard-depend on the old structure.
- If you want token/cost telemetry, parse the final assistant/usage event; otherwise just write stdout to `logs/<slug>.jsonl` and `stderr` to `logs/<slug>.stderr.txt` as you do now.

---

## 8. Per-agent model routing (params.yaml)

All model references use `provider/model-id` format. The runner splits on `/` to pick the CLI. Changing one agent's provider means editing one line; no code changes.

### Recommended start config — Kimi K2.6 everywhere

```yaml
# plan/params.yaml
models:
  source_processor:          kimi/kimi-k2.6
  arch_probe:                kimi/kimi-k2.6
  arch_critic:               kimi/kimi-k2.6
  requirements_writer:       kimi/kimi-k2.6
  requirements_critic:       kimi/kimi-k2.6
  solution_designer:         kimi/kimi-k2.6
  solution_design_selector:  kimi/kimi-k2.6
  solution_design_critic:    kimi/kimi-k2.6
```

### Cost-optimised config — Kimi for quality, DeepSeek for volume

```yaml
models:
  source_processor:          deepseek/deepseek-chat    # high volume, cheapest tier
  arch_probe:                kimi/kimi-k2.6             # DeepSearchQA 83.0, best research
  arch_critic:               deepseek/deepseek-chat
  requirements_writer:       kimi/kimi-k2.6             # best instruction following
  requirements_critic:       kimi/kimi-k2.6             # low hallucination rate
  solution_designer:         kimi/kimi-k2.6
  solution_design_selector:  kimi/kimi-k2.6
  solution_design_critic:    kimi/kimi-k2.6
```

### Mixed with Claude on quality-critical agents

```yaml
models:
  source_processor:          deepseek/deepseek-chat
  arch_probe:                kimi/kimi-k2.6
  arch_critic:               deepseek/deepseek-chat
  requirements_writer:       anthropic/claude-sonnet-4-6   # → routes to claude CLI
  requirements_critic:       anthropic/claude-sonnet-4-6
  solution_designer:         kimi/kimi-k2.6
  solution_design_selector:  anthropic/claude-sonnet-4-6
  solution_design_critic:    anthropic/claude-sonnet-4-6
```

### Solution Design parallel generation

The `--models` CLI flag accepts any number of `provider/model-id` strings:

```bash
# Single provider
python3 solution_design_runner.py run _requirements.md \
  --models kimi/kimi-k2.6

# Head-to-head: Kimi vs Claude
python3 solution_design_runner.py run _requirements.md \
  --models kimi/kimi-k2.6 anthropic/claude-sonnet-4-6

# Three-way: Kimi vs DeepSeek vs GPT
python3 solution_design_runner.py run _requirements.md \
  --models kimi/kimi-k2.6 deepseek/deepseek-reasoner openai/gpt-5.5
```

### Adding a new provider

1. Add one block to `opencode.json` provider section (§4)
2. Add one env var to `.env`
3. Reference it in `params.yaml` as `newprovider/model-id`

No runner code changes.

---

## 9. Cost / caching notes

- DeepSeek does automatic context caching. Cache-hit input is roughly half the miss rate. To benefit, keep the stable prefix (system prompt + output schema) byte-identical across calls — your template-based prompts already do this, so don't interpolate volatile content into the prefix.
- Output tokens dominate agentic bills. Critic loops and long solution-design generations are where spend concentrates; the 3–5 round caps you already enforce are your main cost lever.

---

## 10. Gotchas (read before you ship)

1. Flag drift — pin one opencode version; re-verify `--format`, `--agent`, `run` semantics against `--help`.
2. Permissions — if `run` hangs, it's almost certainly waiting on a tool permission you didn't pre-grant in the `permission` block.
3. Concurrency — your `ThreadPoolExecutor` fans out many agents at once. DeepSeek enforces API rate limits; cap concurrent workers and lean on your existing retry/backoff for 429s.
4. Tool-calling reliability — DeepSeek's multi-tool use is workable but less robust than frontier models. The agents that call Tavily mid-task (`arch_probe`, `solution_designer`) are the most likely to need a prompt nudge or a bump to `deepseek-reasoner`.
5. Data residency — the DeepSeek API is China-hosted. Client RFPs and presale material (e.g. MARGIN International / MIRAS.ART) flowing to a CN endpoint is a compliance question, not a technical one. For sensitive sources, point the same OpenAI-compatible provider block at a Western host of the open weights (e.g. Fireworks / DeepInfra — just a different `baseURL`) or run locally. Clear this with security before any client data leaves.
6. Illustrator stays on OPENAI_API_KEY (PaperBanana) — separate billing, not part of this migration.

---

## 11. Rollout plan

1. Migrate `source_processor` only. Install its opencode agent globally, wire the new `_invoke_agent` behind a flag (`PRISM_WORKER=opencode|copilot`).
2. Run Extract mode on a known input folder under both backends; diff the `extract.json` outputs for parity.
3. Expand to the rest of Extract (writer + critic), then Discovery, then Solution Design.
4. Once stable, flip the default and retire the copilot path.
5. Keep the env flag for a release so you can fall back instantly if a DeepSeek rate limit or quality regression bites mid-presale.

---

## Appendix — model reference (verify before relying on prices)

Prices are 2026 figures for planning. Confirm against each provider's pricing page and `opencode models <provider>` before committing the routing table.

### DeepSeek (direct API — api.deepseek.com/v1)

On DeepSeek's own API the model IDs are `deepseek-chat` (currently aliases to V3.2/V4 — verify the current alias in their docs) and `deepseek-reasoner` (R1). On third-party hosts (Fireworks, DeepInfra) the slugs differ; run `opencode models fireworks` to see what's listed there.

| Model                   | Input $/1M | Cache hit $/1M | Output $/1M | Context | Recommended for |
|-------------------------|----------:|---------------:|------------:|--------:|-----------------|
| DeepSeek V4 Flash       | ~0.14      | ~0.014         | ~0.28       | 1M      | source_processor, arch_probe — highest volume, cheapest tier |
| DeepSeek V3.2 / chat    | ~0.26      | ~0.13          | ~0.38       | ~160K   | extraction workhorse, requirements_writer first pass |
| DeepSeek V4-Pro / reasoner | ~1.74   | ~0.14          | ~3.48       | 1M      | requirements_critic, solution_design_critic, selector |

### Alternative cloud (same opencode.json custom-provider block, swap baseURL)

| Model              | Provider   | Input $/1M | Output $/1M | Notes |
|--------------------|-----------|----------:|------------:|-------|
| Qwen3-235B-A22B    | DeepInfra | ~0.07      | ~0.10       | ultra-cheap MoE; extraction and probe |
| Kimi K2.6          | Fireworks | ~0.95      | ~4.00       | strong coding benchmark; hedge on complex synthesis |

### Claude models (or if routing quality-critical phases via the Claude Code spec)

| Model              | Input $/1M | Cache read $/1M | Output $/1M | Notes |
|--------------------|----------:|----------------:|------------:|-------|
| Claude Haiku 4.5   | ~1.00      | ~0.10           | ~5.00       | budget Claude tier; still 3x cheaper than Sonnet |
| Claude Sonnet 4.6  | ~3.00      | ~0.30           | ~15.00      | quality hedge on writer/critic if DeepSeek tool-calling flakes |
| GPT-5.5            | ~5.00      | —               | ~30.00      | the rate you're escaping |
