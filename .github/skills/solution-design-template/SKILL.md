---
name: solution-design-template
description: Gold-standard structure and quality criteria for the technical solution proposals produced by the solution_designer agent and judged by the critic. Load this skill before writing or reviewing any _solution_design.md file. Works for any software project; AI/ML becomes the spine whenever the system has one (the common case). Single recommended architecture; no multiple options; no effort/time/cost estimates anywhere.
---

# Solution Design Document — Template & Quality Standard

## Purpose

This skill is the **single source of truth** for the structure, depth, and quality bar of every solution design document in this pipeline. Both the **writer** (solution_designer) and the **reviewer/critic** load it — the writer as an authoring guide, the critic as a checklist. If the two ever disagree, this file wins.

The target is a **publication-quality technical proposal** in the mould of a real client-facing solution document: one committed architecture — with AI/ML at its core whenever the system has an AI/ML dimension — demonstrated through concrete scenarios and module tables, with figure placeholders where a diagram explains better than prose.

## Three rules that override everything below

1. **One architecture, not several.** The document puts forward ONE design. Credible alternatives are dismissed in a single prose sentence where the decision is made — never laid out as options for the reader to weigh, and never as a per-aspect Pro/Con trade-off table.
2. **No estimates of any kind.** No money, no durations (days/weeks/months), no S/M/L/XL, no story points, no team sizes. Phases are defined by *what they deliver* and *their exit criterion* — never by how long or how much. The only permitted hedge is a single caveat on the infrastructure section.
3. **No bold text anywhere in the document.** Do not use `**bold**` markdown in the output. Bold formatting reads as AI-generated and undermines credibility. Use heading levels, tables, and plain prose instead. The only exception is code or command literals inside backticks.
4. **Lists over inline enumerations.** Whenever three or more items appear in sequence, use a bullet list — not a comma-separated run-on sentence. This applies inside prose paragraphs too: if a sentence would read "A, B, and C," break it into a three-item list instead.
5. **AI/ML is the spine — when the system has one.** This template fits any software project. When the system has an AI/ML dimension (the common case in this pipeline), it is the centre of gravity: models, data flows, training/feedback loops, and human-in-the-loop controls are first-class content, not an appendix. When a project genuinely has no AI/ML component, the AI-specific parts below become **"if applicable"** — do not manufacture ML to satisfy them; give the system's actual core engine the same depth instead. Sections explicitly marked *(AI/ML systems)* are conditional; everything else is mandatory for every project.

---

## Mandatory Document Structure

Every `_solution_design.md` MUST contain these, in this order:

```
YAML front-matter
H1 Title  +  subtitle "Technical Proposal"
1. Solution Overview
   1.1 Business Context
   Stakeholder Role Reference (table)
   1.2 Core Architecture
   1.3 Key Innovation / Integration  (for AI/ML systems: the model→downstream closed loop)
2. Technology Stack
   2.1 Architecture Pattern (single, committed)
   Module / Component breakdown (table[s])
3. Delivery Phasing
   intro + phase table
   Phase 0 — Discovery & Architecture Validation
   one section per functional phase (deep-dive)
4. Non-Functional Requirements (table)
5. Infrastructure & Deployment (overview + platform/service reference table)
(optional) closing italic provenance line
```

---

## YAML Front-Matter

```yaml
---
solution_design:
  requirements_source: <relative path to _requirements.md>
  generated_date: <YYYY-MM-DD>
  illustration_count: <N>
---
```

Do **not** add a `complexity`, `effort`, or `estimate` field. (Removed deliberately — see Rule 2.)

---

## Section 1 — Solution Overview

### 1.1 Business Context
2–4 paragraphs: the business problem, why existing tools fall short, the regulatory/market backdrop, and one sentence stating plainly what the system *is* and what it deliberately is *not*. State the central architectural idea here. No marketing language.

### Stakeholder Role Reference
A table covering every human actor and every external system:

| # | Role | Type | System Role | Key Interests | Source |
|---|------|------|-------------|---------------|--------|

- One row per actor/system from the requirements.
- The **Source** column quotes the requirements verbatim where they speak to that actor's need — one short quote per row, in quotation marks.

### 1.2 Core Architecture
Name the central design (e.g. a layered authentication architecture, an event-driven pipeline, a closed-loop scoring system). A table laying out the main layers/components and what each *establishes*. State plainly why no single component is a single point of failure. Place the system-context / overview figure here.

### 1.3 Key Innovation / Integration
THE differentiator — the single technical bet that drives the rest of the design. This section is mandatory in some form for every project.
- **For an AI/ML system (the common case):** a table plus a paragraph showing how ML outputs feed downstream decisions **in real time** — which model signal drives which consequence — with the closed loop made explicit: an anomalous/failed ML signal produces an automatic downstream effect. Mandatory even if the requirements mention ML only lightly.
- **For a non-AI system:** name the one core technical bet (the consistency model, the event backbone, the integration contract, the data model — whatever it is) and show how it propagates through the system and what it buys. No ML framing forced.

---

## Section 2 — Technology Stack

### 2.1 Architecture Pattern
Commit to ONE pattern. Open with the single-sentence dismissal of the main alternative ("a full microservices split front-loads distributed-systems overhead before the domain is stable; we therefore use a modular monolith with two extracted ML services"), then describe the chosen pattern and *why it fits these specific NFRs and this domain*. Include a figure placeholder.

### Module / Component breakdown
One or two tables:

| # | Module | Description |
|---|--------|-------------|

- List every module of the system.
- Explicitly mark the system's specialised / heavy-compute services and pin each to its optimal runtime — for an AI/ML system this is the model services (e.g. a Python GPU service for embeddings, a Python service for the scoring model) split from the core business runtime; for other systems it is whatever genuinely needs isolating (a streaming worker, a search/indexing service, a reporting engine).
- Name concrete technologies for the core runtime, any ML model(s) and libraries (where the system uses them), datastore (and vector index if similarity search is needed), queue/async layer, object storage, and any specialised store the domain demands. Every choice traceable to a requirement or a verified research finding — with confirmed current version numbers, not remembered ones.

---

## Section 3 — Delivery Phasing

A short intro paragraph describing the delivery arc, then a phase table:

| Phase | Core Delivery | Modules | Phase Exit Criterion |
|-------|---------------|---------|----------------------|

- **No Effort/Duration/Cost column. Ever.**
- The exit criterion is a concrete, demonstrable capability ("a verified user can do X end-to-end and the result is independently verifiable"), not a milestone label.
- The first phase is **Phase 0 — Discovery & Architecture Validation**: a pre-development validation phase that verifies every technical claim against the requirements/spec and produces a signed-off architecture before any code is written. List its deliverables in a table; its exit criterion is joint client + vendor sign-off.

### Per-phase deep-dive (one `##` section per functional phase)
Each functional phase section MUST contain, in order:
1. A 1-paragraph intro: what the phase completes and its exit state.
2. **An end-to-end scenario walkthrough** — a named, concrete narrative ("Gallery scenario", "Transaction scoring scenario") following one real flow through the modules, naming the actual libraries/models/algorithms invoked at each step. This is the most persuasive part of the document. The walkthrough is the only data-flow narrative — **do NOT add a separate "Data-Flow Narrative" section or paragraph** after the walkthrough.
3. A figure placeholder + caption for the phase data flow; a second one for the phase module architecture if warranted.
4. A module table (`# | Module | Description`) for everything delivered in the phase.

A far-out phase that depends on operational data not yet available (typically the ML-maturity phase) gets a short **Design note** flagging it as a directional blueprint to be re-planned at the prior phase's exit — without any date or cost.

### AI/ML phase(s) — additional mandatory content *(AI/ML systems only)*
*Applies only where the system has an AI/ML phase. Skip entirely for non-AI projects — its absence is then not a finding.*
- The model(s) and the exact decision logic (variables, weights, bands, thresholds) where the domain has them.
- **Training-data strategy** — where labels come from, and the explicit rule that labels derive from human decisions, never from the model's own outputs (no feedback-loop contamination).
- **Human-in-the-loop** — no ML suggestion alters a live decision without explicit human confirmation; advisory outputs stay advisory.
- **Model lifecycle** — retraining triggers (event- or data-driven: accumulated labelled volume, detected drift, or a manual trigger — never a fixed calendar schedule), version history, shadow/parallel evaluation before promotion, automatic rollback on regression, explainability logging.
- Fine-tuning / domain-adaptation plan if the corpus grows, and any RAG/assistant capability under evaluation, with its governance open questions (e.g. GDPR erasure vs. retention) stated honestly.

---

## Section 4 — Non-Functional Requirements

A table:

| Category | Requirement | Design Approach |
|----------|-------------|-----------------|

- One row per NFR from the requirements; quote the specific target value ("≤500ms p95", "99.5% uptime", "≤5s scoring end-to-end").
- The Design Approach names the concrete mechanism that hits it (the framework, the index, the deployment topology, the encryption scheme) — backed by a benchmark you verified, not asserted.
- Cover at minimum: API latency, the core processing/compute SLA (the ML inference SLA where the system has one), availability, scale, data retention, security, and the relevant regulation(s).

---

## Section 5 — Infrastructure & Deployment

This section is mandatory for every project; only the deployment model changes.

- **Pick the deployment model from the requirements, not by default.** It may be a named cloud vendor (AWS / Azure / GCP / …), multi-cloud, on-premises / self-hosted, sovereign/air-gapped, or hybrid. State which one and why in the first line. If the requirements name a vendor or mandate on-prem, design to that; if they are silent, choose one and justify it briefly.
- **Research-intensive — must not be written from memory.** Confirm current product/service names for the chosen target (managed services for a cloud vendor; the self-hosted equivalents — e.g. Kubernetes, Postgres, Kafka, MinIO, Vault — for on-prem), the right compute families for the workload (GPU where the system runs ML inference), region/residency and data-sovereignty constraints, and the reference architecture the target platform publishes for this workload class.
- A short overview paragraph: how traffic enters, where workloads run, how any heavy-compute tier is isolated (the GPU/ML tier where applicable), how state is stored, how secrets/keys are managed.
- Open with a one-line caveat that the infrastructure design is a first-pass approximation to be refined during discovery. **This is the only hedge permitted in the whole document** — never hedge on functionality.
- A figure placeholder + caption for the topology.
- A **platform / service reference table**:

| Category | Service / Component | Usage |
|----------|---------------------|-------|

Cover compute (incl. any GPU/ML node where applicable), storage, database (and vector index where similarity search is used), cache/queue, CDN or edge (where applicable), load balancing/ingress, networking, the full security stack (WAF/edge protection, KMS/HSM or self-hosted key management, secrets, IAM/RBAC), notifications, monitoring/tracing, and artifact/container registry. For a named cloud, name its managed services; for on-prem, name the self-hosted components that play each role. Every entry must be one you confirmed exists and fits.

---

## Figures (ILLUSTRATION placeholders)

Wherever a diagram explains better than prose, insert a placeholder immediately followed by a caption:

```
<!-- ILLUSTRATION: <slug>
     Description: one precise sentence — components, arrows, what flows where, what to emphasise.
     Style: technical diagram, boxes and arrows, no gradients
-->
*Figure N. Caption describing the figure as if it already exists.*
```

- Always an HTML comment, never visible text. The `Description:` must be specific enough for the Illustrator agent to draw it without reading the rest of the document.
- Number figures sequentially across the whole document.
- **Minimum 1** (the Section 1.2 architecture overview is mandatory). **No fixed upper cap** — a serious proposal carries one figure per major flow and per phase architecture; use as many as genuinely earn their place. Do not pad, do not starve.

---

## Quality Bar — For Writers (pre-submit checklist)

- [ ] Exactly ONE architecture put forward — no options for the reader to choose between
- [ ] Zero estimates anywhere (no money, time, S/M/L/XL, story points, team size)
- [ ] Section 1 has 1.1 Business Context, the Stakeholder Role Reference table, 1.2 Core Architecture, 1.3 Key Innovation / Integration
- [ ] Stakeholder table quotes the requirements (one short quote per relevant row)
- [ ] Section 1.3 is concrete: for an AI/ML system the real-time model→downstream closed loop is explicit; for a non-AI system the single core technical bet and its propagation are explicit
- [ ] Architecture Pattern is committed, with the alternative dismissed in one sentence
- [ ] Module tables mark the specialised / heavy-compute services and pin their runtime (the ML services where applicable)
- [ ] Phase table has Phase / Core Delivery / Modules / Exit Criterion — and NO effort column
- [ ] Phase 0 Discovery present with deliverables table and sign-off exit criterion
- [ ] Every functional phase has: scenario walkthrough + figure + module table (NO separate Data-Flow Narrative section)
- [ ] *(AI/ML systems)* the AI/ML phase covers training-data strategy, human-in-the-loop, model lifecycle
- [ ] NFR table addresses every NFR from requirements with a concrete mechanism
- [ ] Infrastructure & Deployment section states the deployment model (cloud vendor / on-prem / hybrid) and has the discovery caveat, topology figure, and full platform/service reference table
- [ ] Architecture overview figure present in Section 1.2; figures numbered sequentially
- [ ] Every technology, version, service, and benchmark was confirmed by a search this session
- [ ] Every requirement, NFR, and integration is addressed somewhere or deferred to a named phase
- [ ] No marketing language ("cutting-edge", "revolutionary", "best-in-class", "robust" with nothing behind it)

---

## Quality Bar — For Reviewers (Critic)

### Dimension 1 — Structure
- [ ] All sections present in correct order (Overview → Tech Stack → Delivery Phasing → NFR → Infrastructure)
- [ ] YAML front-matter present with required fields, and NO effort/complexity field
- [ ] Section 1 contains 1.1, Stakeholder table, 1.2, 1.3
- [ ] Phase 0 Discovery present
- [ ] At least one functional-phase deep-dive
- [ ] NFR table present; Infrastructure & Deployment platform/service reference table present
- [ ] At least 1 `<!-- ILLUSTRATION: ... -->` placeholder (the 1.2 overview)

### Dimension 2 — Formatting
- [ ] Stakeholder roles, module breakdowns, phase plan, NFRs, and infrastructure services each rendered as tables (not prose or bullets)
- [ ] Section 1 is structured into subsections, not a flat prose block
- [ ] Figure captions present beneath their placeholders, numbered sequentially
- [ ] No `**bold**` markdown anywhere in the document body
- [ ] No inline comma-separated enumerations of 3+ items — each such list rendered as bullets

### Dimension 3 — Content Quality
- [ ] ONE architecture only — flag any document that presents multiple options to choose between
- [ ] ZERO estimates — flag any money, duration, S/M/L/XL, story-point, or team-size figure
- [ ] Section 1.3 is concrete, not generic — for an AI system a real model→downstream link (not "we use ML"); for a non-AI system a real core-technical bet (not a vague slogan)
- [ ] *(AI/ML systems only)* each AI/ML phase covers training data, human-in-the-loop, and model lifecycle
- [ ] Architecture Pattern names and dismisses its main alternative in prose
- [ ] Every NFR from requirements is addressed with a concrete mechanism
- [ ] Every integration from requirements is addressed
- [ ] Technologies, versions, and cloud services are specific and plausibly current (not obviously invented/stale)
- [ ] Every functional phase has a scenario walkthrough
- [ ] No marketing language

### Severity Mapping

| Dimension | Check failed | Severity |
|-----------|-------------|----------|
| Content | Presents multiple options to choose between | HIGH |
| Content | Contains any time/cost/effort estimate | HIGH |
| Structure | Missing a top-level section | HIGH |
| Structure | Section 1 missing a required subsection | HIGH |
| Structure | Missing NFR table | HIGH |
| Structure | No ILLUSTRATION placeholder at all | HIGH |
| Content | NFR from requirements not addressed | HIGH |
| Content | Section 1.3 absent or generic (no real innovation/closed loop) | HIGH |
| Content | *(AI/ML systems)* AI/ML phase missing training-data / HITL / lifecycle treatment | HIGH |
| Structure | Phase 0 Discovery missing | MEDIUM |
| Structure | A functional phase missing its scenario walkthrough | MEDIUM |
| Structure | Missing infrastructure platform/service reference table | MEDIUM |
| Structure | Missing stakeholder role table | MEDIUM |
| Formatting | A mandated table rendered as prose/bullets | MEDIUM |
| Formatting | Bold (`**...**`) text used anywhere in the document body | MEDIUM |
| Formatting | Inline comma-separated enumeration of 3+ items instead of a bullet list | MEDIUM |
| Content | Technology/version/service looks invented or clearly stale | MEDIUM |
| Content | Integration from requirements not addressed | MEDIUM |
| Content | Marketing language | LOW |

**Verdict rules**
- **APPROVED** — zero HIGH findings and no more than 2 MEDIUM findings
- **REVISE** — one or more HIGH findings, or 3+ MEDIUM findings

### IGNORE in review
`<!-- ILLUSTRATION: ... -->` content is for the Illustrator agent. Do not flag a diagram as "missing" when the placeholder comment is present — the placeholder is the deliverable at this stage.
