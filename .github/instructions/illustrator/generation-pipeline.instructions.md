---
description: Two-phase illustration generation pipeline for Illustrator agent — Plan one optimized prompt, Generate one PNG per illustration using the PaperBanana package (llmsresearch/paperbanana) with OpenAI provider.
---

# Generation Pipeline

## Overview

The Illustrator uses a two-phase pipeline:

```
Phase 1: Plan (parse placeholders, prepare description + context)
Phase 2: Generate (PaperBanana package: Retriever → Planner → Stylist → Visualizer ↔ Critic)
```

The `paperbanana` package handles prompt engineering, reference retrieval, aesthetic refinement, image generation, and iterative critique internally. The Illustrator's job is to **extract the right description and context** from the draft and feed them to the script.

## Model & Dataset

- **Image model:** `gpt-image-2` — automatically selected by PaperBanana when `IMAGE_MODEL` env var is not set (default in `.env`).
- **Reference dataset:** 295-example PaperBananaBench dataset cached at `~/.cache/paperbanana/reference_sets/` — used automatically, no flags needed.
- **No extra flags required.** Do NOT add `--model`, `--direct`, `--no-optimize`, or any dataset path flags. The script reads env/cache automatically.

## Prerequisites

All commands use `.venv/bin/python3` — relative to the workspace root (default CWD for `run_in_terminal`).

**Before generating, verify the venv exists:**
```bash
ls .venv/bin/python3
```

**If missing — create it:**
```bash
python3 -m venv .venv && .venv/bin/pip install "git+https://github.com/llmsresearch/paperbanana[openai]"
```

## Phase 1: Plan

1. Read the target document (`DOCUMENT_PATH` — provided by the caller in the prompt). If `{BASE_FOLDER}/research/_plan/params.md` exists, read it too.
2. **Extract all `<!-- ILLUSTRATION: type=..., section=..., description="..." -->` placeholders** left by the Writer. Each placeholder has a caption line below it: `*Рис. N. Caption*`
3. For each placeholder, parse:
   - `type` — architecture, comparison, pipeline, infographic, conceptual
   - `section` — which document section this belongs to
   - `description` — Writer's detailed description of what to visualize (200+ chars)
4. If no placeholders found, fall back to independent identification:
   - Architecture/system design sections
   - Pipeline/workflow descriptions
   - Comparison sections with complex relationships
   - Abstract concepts that benefit from visual representation
5. For each illustration, prepare:
   - **Description** (2-6 sentences): what to visualize, key components, relationships. Use the Writer's `description` as the primary input.
   - **Context** (200-500 words): copy the relevant section text from the draft for the Planner agent to understand the domain.
   - Do NOT micro-manage layout, colors, composition, or background — PaperBanana's Planner/Stylist/Critic agents handle all styling decisions internally.
6. Record the plan internally before proceeding to generation.
7. Determine illustration label: read `language` from `params.md` if available; otherwise use the language specified in the calling prompt; default is Russian ("Рис.", "Fig." for English).

## Phase 2: Generate

### Step 1: Choose Generation Mode

For each illustration, select the mode based on type:

| Mode | When to use | Command |
|---|---|---|
| **pipeline** (default) | All illustrations | `.venv/bin/python3 .github/skills/image-generator/scripts/paperbanana_generate.py "[description]" "path.png" --context "[section text]" --critic-rounds 3` |
| **`--auto`** | When quality matters more than speed | `.venv/bin/python3 .github/skills/image-generator/scripts/paperbanana_generate.py "[description]" "path.png" --context "[section text]" --auto --max-iterations 5` |

> **Pipeline takes 3–5 min per illustration (5–7 API calls).** Always use `run_in_terminal` with `timeout: 0` (no timeout limit).

### Step 2: Craft the Prompt

**For pipeline mode (DEFAULT — all illustrations):**

Provide a clear description (2-6 sentences) and pass 200-500 words of section context via `--context`. The Planner/Stylist/Critic cycle handles layout, colors, and refinement automatically. Do NOT add styling instructions — PaperBanana does this internally.

### Step 3: Generate

**Launch ALL illustration commands in parallel** — use `run_in_terminal` with `mode: async` for every command, starting all of them before waiting for any to finish. Collect all terminal IDs, then check results once all are done. **Never wait for one illustration to complete before starting the next.**

> **CRITICAL: Never create a wrapper script** (e.g. `generate_all.py`, `run_illustrations.sh`) to batch the commands. Call `run_in_terminal` directly for each illustration — one call per PNG, all in parallel.

After all are generated:

1. **EMBED ILLUSTRATIONS IN THE DOCUMENT** — this step is MANDATORY:

   Every embedded illustration MUST have **two lines**: an image link and a visible italic caption:
   ```markdown
   ![Рис. 1. Caption text](../illustrations/diagram_1.png)

   *Рис. 1. Caption text*
   ```
   Use "Рис." for Russian, "Fig." for English (from params.md if present, else from calling prompt, default Russian).

   **Path A — Placeholders exist:**
   Replace each `<!-- ILLUSTRATION: ... -->` placeholder in the draft with the image link line. The Writer already placed a `*Рис. N. Caption*` caption below the placeholder — **keep it**, only replace the HTML comment.

   **Path B — No placeholders (fallback):**
   You MUST STILL embed illustrations. For each generated PNG:
   - Find the target section heading (H2 `##`) in `DOCUMENT_PATH`
   - Locate the end of the first paragraph after that heading
   - Insert both the image link AND the italic caption line

2. Create `illustrations/_manifest.md` — must include **Regeneration Prompts** section (see below).
3. **VERIFY:** Read `DOCUMENT_PATH` and confirm every generated PNG is referenced. If any is missing, insert it.

**Output without embedded images = FAILED. Every PNG must appear as `![...]` in `DOCUMENT_PATH`.**

## Manifest Format (with Regeneration Prompts)

The `_manifest.md` MUST contain two parts:

**Part 1 — Summary table:**
```markdown
# Illustration Manifest

| # | File | Section | Type | Description |
|---|------|---------|------|-------------|
| 1 | diagram_1.png | §02 | flow | Short description |
...

## Generation Details
- **Generator:** PaperBanana (model versions)
- **Critic rounds:** N
- **Generated:** YYYY-MM-DD
```

**Part 2 — Regeneration prompts (MANDATORY):**

For EACH diagram, record the exact description, context, and full CLI command used to generate it. This enables one-command regeneration without reconstructing prompts.

```markdown
## Regeneration Prompts

### diagram_N.png (§NN — Short Title)

**Description:**
\`\`\`
The exact description string passed to paperbanana_generate.py
\`\`\`

**Context:**
\`\`\`
The exact context string passed via --context
\`\`\`

**Command:**
\`\`\`bash
.venv/bin/python3 .github/skills/image-generator/scripts/paperbanana_generate.py \
  "description..." \
  "illustrations/diagram_N.png" \
  --context "context..." \
  --critic-rounds 3
\`\`\`
> Note: gpt-image-2 and the reference dataset are selected automatically — no extra flags needed.```

This section is critical for re-runs and selective regeneration.

## Re-run Behavior

When Orchestrator requests re-generation (after Critic flagged ILLUSTRATION_ISSUES: YES):
1. Read the Critic's feedback to identify which diagrams need improvement
2. Only regenerate flagged diagrams — keep approved ones
3. Refine the prompt based on Critic's feedback
4. Update `_manifest.md` with new entries
