```instructions
---
description: Prompt guidelines for the Illustrator agent — how to write description and context for PaperBanana pipeline and direct mode.
---

# Style Guidelines

PaperBanana handles all styling internally (colors, layout, shapes, typography) via its Planner → Stylist → Visualizer ↔ Critic pipeline. The Illustrator agent only needs to provide a good **description** and **context**.

## Fill Rule

**The diagram must fill the full image canvas.** No large empty margins, padding, or whitespace around the illustration — every part of the image area should be used. Add this requirement explicitly in every description prompt:
> "... Fill the entire canvas. No empty margins or padding around the diagram."

A centered diagram floating in a sea of white is unacceptable.

## Background Rule

**All illustrations MUST use a pure white (#FFFFFF) background.** Add this requirement explicitly at the start of every description prompt:
> "Pure white background (#FFFFFF). ..."

This applies to pipeline mode and direct mode alike. Colored, gradient, or dark backgrounds are not acceptable for documents and pitch decks.

## How to Write Prompts

### Pipeline mode (default)

Provide two things:
1. **Description** (2-6 sentences): what the diagram shows, key components, relationships
2. **Context** via `--context` (200-500 words): relevant section text from the draft

The pipeline agents handle layout, colors, composition, and refinement automatically.

### Direct mode (`--direct` flag)

Keep prompts **short** — 2-4 sentences, ~50-100 words. The script auto-prepends style instructions.

- Describe visual structure (columns, hierarchy, flow direction)
- Name key blocks with color hints (e.g., "blue for Copilot, orange for Claude")
- Describe connections briefly (arrows, lines)
- Do NOT list exact text for every label or pixel positions — causes ASCII-art output

**Example:**
```
Three-column comparison of AI platforms. LEFT 'Copilot' in blue with hub-spoke
model icons and cloud sandbox. CENTER 'Claude Code' in orange with Lead Agent,
three Teammate blocks, and Shared Task Board. RIGHT 'Codex CLI' in green with
App Server hub and client connections. Bottom: shared MCP protocol bus.
```

## What to Visualize by Document Type

| Document Type | Recommended Illustrations |
|--------------|----------------------|
| Comparative Analysis | Architecture diagram per approach, comparison infographic, decision flowchart |
| Technology Overview | Architecture diagram, dataflow/pipeline, sequence diagram |
| State of the Art | Methods taxonomy map, approach comparison |
| Research Report | Methodology visualization, results comparison |
```
