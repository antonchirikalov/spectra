---
name: requirements-template
description: Gold-standard structure and quality criteria for requirements documents produced by the requirements_writer agent. Load this skill before writing or reviewing any _requirements.md file.
---

# Requirements Document — Template & Quality Standard

## Purpose

This skill defines the mandatory structure, depth expectations, and quality bar for every requirements document produced in this pipeline. The annotated examples below are drawn from a real, approved requirements document and show exactly what each section must look like.

---

## Mandatory Document Structure

Every `_requirements.md` MUST contain all sections below, in this order:

```
YAML front-matter
Document Title + meta (Generated date, sources count, language)
Document Index (table of all source files)
Domain Grounding (prose paragraph — NO bullets)
1. Stakeholders & Roles (table)
2. Business Context (bullet list, each bullet [Source: ...])
3. Functional Requirements (subsections 3.1, 3.2, ... grouped by domain area + 3.N Out of Scope)
4. Non-Functional Requirements (single table)
5. Business Rules & Constraints (single table)
6. Data Model (table of entities with key attributes)
7. Integration Points (table)
8. Open Questions, Conflicts & Assumptions
   8.1 Conflicts Found (table)
   8.2 Gaps (table)
   8.3 Explicit Assumptions (table)
---
*End of requirements document.*
```

---

## YAML Front-Matter

```yaml
---
exemplar:
  id: <project-slug>
  industry: <industry>
  domain_tags: [<tag1>, <tag2>]
  project_type: <platform | mobile-app | api | integration | other>
  complexity: <low | medium | high>
  source_types: [<list of source_type values from extracts>]
  source_count: <N>
  fr_count: <N>
  nfr_count: <N>
  sections: [domain-grounding, stakeholders, business-context, fr, nfr, business-rules, data-model, integrations, open-questions]
  quality_score: null
  language: <en | ru | other>
---
```

---

## Domain Grounding

Rules: Prose only — no bullet points, no lists. 3–5 sentences that describe: the problem domain, the core value proposition, and the main user flows. A reader with no prior context must understand what the system does after reading this paragraph.

Gold-standard example:

> This project is a four-party, invite-only referral and booking marketplace (Equitea) where verified Clients earn referral fees for introducing off-platform Guests to verified Businesses (restaurants, goods providers, service providers), with the platform managing bookings, subscription billing, and escrow-style referral fee payouts through Stripe Connect.

Note: one dense sentence is sufficient when it fully captures the system. Do not pad to 5 sentences if 1–2 sentences fully describe the domain.

---

## Section 1 — Stakeholders & Roles

Table format. Every role that appears in the source documents must have an entry.

```markdown
| Role | Description |
|------|-------------|
| Admin (operator) | Platform operator. Manages users, approves listings, oversees bookings and payments. |
| Client | Invited individual with a verified profile. Introduces Guests to Businesses. Earns referral fees. |
| Business | Invited company. Lists services. Pays referral fee to Client via platform on successful booking. |
| Guest | Off-platform person referred by a Client. Has no platform account. |

[Source: `source-file.md`, `other-source.md`]
```

---

## Section 2 — Business Context

Bullet list of key business facts: model, revenue streams, geography, timeline, constraints. Each bullet must cite its source.

```markdown
- Platform model: Invite-only marketplace. Access denied to anyone not holding a valid invitation link. [Source: `brief.md`, `chat.txt`]
- Revenue streams: Client onboarding fees (one-off), Client monthly subscriptions (Direct Debit), Business onboarding fees, commission on referral fees. [Source: `brief.md`]
- Geographic rollout: MVP (UK) → Phase 1 (Europe) → Phase 2 (USA, Canada). [Source: `chat.txt`, `meeting.md`]
- Timeline preference: MVP delivery in 4–6 months. [Source: `chat.txt`, `meeting.md`]
- Code and IP ownership: Fully customer-owned. [Source: `qa.md`]
```

---

## Section 3 — Functional Requirements

### Grouping rules
- Group FRs by domain area (Auth, Onboarding, Search, Booking, Payments, Admin, Notifications, etc.) — NOT by source document
- Each domain area = one subsection with a `### 3.N Title` heading
- IDs are sequential across ALL subsections (FR-001 … FR-090 — never restart per subsection)
- The last subsection must be `3.N Out of Scope` listing explicitly excluded features

### FR table format

```markdown
### 3.1 Authentication & Access Control

| ID | Requirement | Priority | Source |
|----|-------------|----------|--------|
| FR-001 | The platform MUST be invite-only. Access must be denied to any user who does not hold a valid, unexpired invitation link. | MUST | `brief.md`, `chat.txt` |
| FR-002 | The system must generate unique, expiring invitation links. Role (Client or Business) must be assigned at the invitation stage. | MUST | `brief.md` |
| FR-004 | The system must support two-factor authentication (2FA) for all user roles. | MUST | `qa.md` |
```

Priority values: MUST (essential), SHOULD (important but not blocking), COULD (nice-to-have).

### Out of Scope subsection format

```markdown
### 3.11 Out of MVP Scope (Phase 2 and Beyond)

> [!IMPORTANT] The following requirements are explicitly excluded from MVP per stakeholder confirmation.

| Feature | Source |
|---------|--------|
| Reviews / ratings system | `chat.txt` (stakeholder: "take reviewing businesses away from that scope completely") |
| Client-to-client messaging | `chat.txt` |
| Full analytics suite | `chat.txt` |
| Native mobile application (iOS / Android) | `brief.md` |
```

### Depth benchmark
- Medium-complexity project: minimum 10 FRs
- High-complexity project: minimum 20 FRs
- Each major domain area should have 3–10 FRs depending on its complexity

---

## Section 4 — Non-Functional Requirements

Single table. Every NFR must have a quantitative target.

```markdown
| ID | Requirement | Category | Source |
|----|-------------|----------|--------|
| NFR-001 | The platform must be mobile-first responsive. | UX | `brief.md`, `meeting.md` |
| NFR-002 | The system must comply with UK GDPR. All personal data handling must meet UK data protection law. | Legal / Compliance | `brief.md`, `qa.md` |
| NFR-004 | The architecture must be scalable to support 1,000,000+ registered users. | Scalability | `qa.md` |
| NFR-013 | The referral fee escrow window must not exceed 48 hours. | Business / Financial | `brief.md` |
```

Anti-pattern — reject these:
- `NFR-001 | The system must be fast. | Performance | brief.md` — no number
- `NFR-002 | The system must be secure. | Security | brief.md` — no measurable criteria

Accepted categories: Performance, Security, Scalability, Availability, Legal/Compliance, UX, Ops/Maintainability, Internationalisation, Data Sovereignty, Business/Financial.

---

## Section 5 — Business Rules & Constraints

Single table. Rules that constrain system behaviour — not "how to build" but "what must always be true at runtime."

```markdown
| ID | Rule | Source |
|----|------|--------|
| BR-001 | No user (Client or Business) can register without a valid, unexpired invitation link. Self-registration is not possible. | `brief.md`, `chat.txt` |
| BR-005 | The referral fee flows: Business → Platform → Client. The platform must not retain funds beyond 48 hours. | `brief.md`, design decision |
| BR-006 | Client subscription continuity is required for active platform access; lapsed subscriptions must result in suspended access. | `brief.md` (inferred from subscription model) |
```

---

## Section 6 — Data Model

Table of entities explicitly referenced in sources. This is not a full data model — only entities with 2+ attributes mentioned across sources.

```markdown
| Entity | Key Attributes (Referenced) | Notes |
|--------|----------------------------|-------|
| User | ID, role (Admin/Client/Business), email, mobile, verification status, subscription status | [Source: brief.md] |
| Booking | ID, Client ID, Business ID, Guest details (name, email, mobile), date/time, status (Pending/Confirmed/Completed/Cancelled), verification_code | [Source: brief.md, design decision] |
| ReferralFee | ID, Booking ID, Client ID, Business ID, amount, escrow timestamp, payout status | [Source: brief.md] |
```

- Mark explicitly out-of-scope entities: `> [!CAUTION] Review entity is out of MVP scope. [Source: chat.txt]`
- Include a note on each entity referencing which source document described it

---

## Section 7 — Integration Points

Every 3rd-party API, payment gateway, identity provider, messaging service, and internal system integration.

```markdown
| Integration | Purpose | Priority | Source |
|-------------|---------|----------|--------|
| Stripe | Client/Business onboarding fee collection, Client monthly subscription (Direct Debit) | MUST | `brief.md` |
| Stripe Connect | Business sub-accounts; referral fee escrow and payout to Client | MUST | `brief.md` |
| Email delivery service (e.g., SendGrid) | Transactional emails: invitations, booking confirmations, payment receipts | MUST | `brief.md` (implied) |
| SMS / OTP provider (e.g., Twilio) | Mobile number verification at registration; booking reminders | SHOULD | `qa.md`, `brief.md` |
| reCAPTCHA / hCaptcha | Bot protection at registration and login | MUST | `qa.md` |
```

---

## Section 8 — Open Questions, Conflicts & Assumptions

### 8.1 Conflicts Found

Every contradiction between source documents — even resolved ones — must appear here.

```markdown
| # | Conflict | Documents in Conflict | Resolution |
|---|----------|-----------------------|------------|
| C-001 | Reviews in MVP: Developer Brief lists Reviews as a functional MVP feature. Stakeholder in chat (March 2026) explicitly excludes reviews from MVP. | `brief.md` vs. `chat.txt`, `meeting.md` | Resolution: Reviews excluded from MVP. Most recent direct stakeholder statement supersedes written spec. |
| C-002 | Payment flow: Brief states "Client pays directly to Business." Q&A doc flags: "Does full transaction flow through the platform OR only the referral fee?" | `brief.md` vs. `qa.md` | RESOLVED. MVP = referral-fee-only through platform (flat fee per Business category). Guest pays Business directly. Post-MVP: full payment through Stripe Checkout. |
```

If no conflicts: write `No inter-source conflicts detected.` — but only if you genuinely found none.

### 8.2 Gaps

Every piece of information absent from all sources but needed for delivery.

```markdown
| # | Gap | Impact |
|---|-----|--------|
| G-002 | Goods provider scope in MVP: Is a goods-provider Business limited to discovery/showcase only, or can Clients purchase goods through the platform? Sam mentions only "table booking or booking of a service." | Core scope definition, pricing model, Stripe integration depth |
| G-005 | Target audience definition: Is the platform targeting exclusively high-net-worth individuals or broader public with premium UX? | Positioning, UX, pricing model |
```

### 8.3 Explicit Assumptions

Every assumption the writer made that is NOT confirmed by source documents.

```markdown
> Assumptions are marked clearly and have NOT been confirmed by source documents. They require validation with the client.

| # | Assumption | Basis |
|---|------------|-------|
| A-001 | Goods providers in MVP = discovery/showcase only. No product purchase transactions in MVP for goods-type Businesses. | Sam's chat references only "table booking or booking of a service." Goods purchases not mentioned. |
| A-004 | Referral fee = flat amount per Business category, configurable by Admin. MVP does not use percentage-of-bill. The platform does not need to know the real bill amount. | Design decision. Brief does not specify fixed vs. percentage; flat fee avoids "how does platform know bill amount" problem for MVP. |
| A-005 | Platform owns the booking lifecycle via an FSM. MVP model: manual Business confirmation. Client submits request → Pending → Business confirms/rejects via Dashboard → Confirmed/Cancelled. No auto-confirm at MVP. | Brief §5.2 lists booking statuses. Transcript confirms platform owns booking. Design decision: manual confirmation for MVP simplicity. |
```

Critical rule: Every assumption row must include both (a) the assumption text and (b) the basis — why this was assumed, which source phrase or design decision led to it.

---

## What Makes a Document Excellent vs. Mediocre

| Excellent | Mediocre |
|-----------|----------|
| Domain Grounding is 1–5-sentence prose that teaches the reader the business context | Domain Grounding is a bullet list or absent |
| FR subsections map to real business areas (Auth, Booking, Payments) | Single giant Section 3 with all FRs in one flat table |
| Every FR has source citation AND MUST/SHOULD/COULD priority | FR rows have no sources, or all priorities are "MUST" |
| NFRs have numbers: `1,000,000+ registered users`, `escrow ≤ 48h` | NFRs say "system must be fast and secure" |
| Section 8 has conflicts (even resolved), gaps with business impact, assumptions with explicit basis | Section 8 says "No conflicts detected" when sources clearly disagree |
| Out-of-scope subsection lists what was intentionally excluded with stakeholder quotes | No scope boundary defined |
| Assumptions include a "Basis" column explaining WHY the assumption was made | Assumption list items without basis |

---

## ID Numbering Rules

- `FR-NNN` — sequential across ALL subsections, no gaps, no duplicates
- `NFR-NNN` — sequential within Section 4
- `BR-NNN` — sequential within Section 5
- `C-NNN` — conflict IDs; referenced in FR/NFR Source column as `[SCOPE CONFLICT: C-001]`
- `G-NNN` — gap IDs
- `A-NNN` — assumption IDs

---

## Source Citation Rules

Every row in every table MUST have a source citation. Three formats:

- Inline in text: `[Source: rfp.pdf]`
- Table Source column: `` `rfp.pdf` `` (in backticks)
- Scope conflict: `` `rfp.pdf` [SCOPE CONFLICT: C-001] ``

A requirement without a source citation is unverifiable and must be flagged as a defect.
