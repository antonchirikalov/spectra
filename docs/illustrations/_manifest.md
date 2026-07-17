# Illustration Manifest

| # | File | Section | Type | Size |
|---|------|---------|------|------|
| 1 | pipelines.png | Pipelines | pipeline | 1.6 MB |
| 2 | extract_pipeline.png | Extract Mode | architecture | 1.1 MB |
| 3 | solution_design_pipeline.png | Solution Design Pipeline | architecture | 1.2 MB |

## Generation Details

- **Generator:** PaperBanana 0.1.0 (Retriever → Planner → Stylist → Visualizer ↔ Critic)
- **Image model:** gpt-image-2 (OpenAI)
- **Critic rounds:** 2
- **Generated:** 2026-06-04

---

## Regeneration Prompts

### pipelines.png (§ Pipelines — Three Pipelines Overview)

**Description:**
```
Pure white background (#FFFFFF). Three parallel vertical pipelines side by side filling the full canvas.
LEFT pipeline labeled 'Extract' in green: Phase 0 Scan → Phase 1 parallel source_processor boxes →
Phase 2 requirements_writer → Phase 3 critic loop (requirements_critic ↔ requirements_writer, up to 5 rounds)
→ output _requirements.md. CENTER pipeline labeled 'Discovery' in blue: Phase 0 Scan → Phase 1 parallel
source_processor boxes → Phase D1 arch_probe (20-30 questions) → Phase D2 arch_critic (8-15 questions) →
output discovery_report.md. RIGHT pipeline labeled 'Solution Design' in purple: input _requirements.md →
Phase 1 parallel solution_designer boxes (one per model: kimi-k3, gpt-4o) → Phase 2 solution_design_selector
→ Phase 3 critic loop (solution_design_critic ↔ solution_designer, up to 3 rounds) → output _solution_design.md.
Each pipeline is a top-to-bottom flow with labeled boxes and arrows. Fill the entire canvas. No empty margins.
```

**Command:**
```bash
cd /Users/anton/Documents/spectra
.venv/bin/python3 .github/skills/image-generator/scripts/paperbanana_generate.py \
  "Pure white background (#FFFFFF). Three parallel vertical pipelines..." \
  "docs/illustrations/pipelines.png" \
  --context "spectra takes a folder of raw client documents and produces three deliverables..." \
  --no-optimize --critic-rounds 2
```

---

### extract_pipeline.png (§ Extract Mode)

**Description:**
```
Pure white background (#FFFFFF). Clean left-to-right flow diagram of the Extract pipeline.
Phase 0 box 'Scan input/' → Phase 1 'Parallel source_processor' showing 3 stacked agent boxes each
producing extract.json, label 'ThreadPoolExecutor'. HITL diamond 'needs_clarification?'.
Phase 2 'requirements_writer' → _requirements.md. Phase 3 'Critic loop' showing requirements_critic
↔ requirements_writer with bidirectional REVISE arrow, green APPROVED exit.
state.json below labeled 'crash recovery'. Fill entire canvas.
```

**Command:**
```bash
cd /Users/anton/Documents/spectra
.venv/bin/python3 .github/skills/image-generator/scripts/paperbanana_generate.py \
  "Pure white background (#FFFFFF). Clean left-to-right flow diagram..." \
  "docs/illustrations/extract_pipeline.png" \
  --context "Extract pipeline: Phase 0 scans folder builds manifest.json..." \
  --no-optimize --critic-rounds 2
```

---

### solution_design_pipeline.png (§ Solution Design Pipeline)

**Description:**
```
Pure white background (#FFFFFF). Solution Design pipeline flow. INPUT _requirements.md on left.
Phase 1 'Parallel generation': N solution_designer boxes side by side (kimi/kimi-k3, openai/gpt-4o),
each producing _design_model.md, labeled 'ThreadPoolExecutor'. Arrows converge to Phase 2
'solution_design_selector' producing _solution_design.md and _selection_report.md 'WINNING_MODEL'.
Arrow to Phase 3 'Critic loop' solution_design_critic ↔ solution_designer, REVISE up to 3 rounds,
green APPROVED exit. Phase 4 summary. state.json below. Fill entire canvas.
```

**Command:**
```bash
cd /Users/anton/Documents/spectra
.venv/bin/python3 .github/skills/image-generator/scripts/paperbanana_generate.py \
  "Pure white background (#FFFFFF). Solution Design pipeline flow..." \
  "docs/illustrations/solution_design_pipeline.png" \
  --context "Solution Design: takes _requirements.md. Phase 1 parallel solution_designer per model..." \
  --no-optimize --critic-rounds 2
```
