# arch_critic — Discovery Report Schema

Write `discovery_report.md` following this exact structure. The report must be complete and self-contained — a reader who has not seen the source documents must understand the context.

---

## File structure

```
---
generated_at: <ISO 8601 datetime>
project_dir: <path>
sources_analysed: <N>
mode: discovery
---

# Discovery Report: <project name or directory name>

## 1. Document Analysis

Brief characterisation of the analysed documents (1–3 sentences per source). What type of document is it, what level of detail does it contain, and what is its apparent purpose?

## 2. AI-Generation Assessment

| Source | Score | Key signals |
|--------|-------|-------------|
| filename.ext | Low / Medium / High | comma-separated signals |

**Overall:** <Low / Medium / High> — <1–2 sentence interpretation: what this means for the quality of requirements in these documents>

If overall score is Medium or High, add a note:
> Note: A medium/high AI-generation score means the documents may lack the specificity needed for detailed architecture design. The questions below are especially important to surface real constraints.

## 3. Domain Context

**Domain:** <identified domain>
**Key technologies:** <comma-separated list>

**Research summary:** 2–4 sentences summarising what was learned from domain research and how it informed the questions below.

## 4. Discovery Questions

Group questions by category. Use these category headings (include only categories that have questions):

### Architecture & Integration
### Data & Ownership
### Non-Functional Requirements
### Security & Compliance
### Team & Governance
### Business Context & Priorities
### Migration & Rollout

Within each category, number questions sequentially overall (Q-01, Q-02, …).

Format each question as:

**Q-NN.** <question text>

Optionally, if the impact is non-obvious, add a single-line annotation:

> *Decision impact:* <what cannot be decided or scoped without this answer>

```

---

## Writing rules

- Use the same language as the source documents (Russian or English)
- Section 4 questions must be the curated final set — specific, direct, no AI openers
- "Decision impact" is optional — only add it when the consequence is genuinely non-obvious to a technical reader; skip it if the question speaks for itself
- When used, write it as a blunt one-liner naming the concrete consequence. No abstract nouns (understanding, clarity, insight). No repeated sentence openers across entries
- Do not include rejected questions or explain your review process
- Sections 1–3 should be factual and brief; Section 4 is the core value
- Total length: aim for 2–4 pages of readable content, not a wall of text
