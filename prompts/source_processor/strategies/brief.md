# Strategy: Brief / Prose Document

Use this strategy for written documents: requirements specs, project briefs, proposals, SOWs, emails, or any document with continuous prose and section headings.

## Extraction focus

1. **Section structure** — use headings as categories to group requirements
2. **Explicit requirements** — look for "must", "shall", "required", "mandatory", "need to"
3. **Non-functional requirements** — performance, security, availability, scalability mentions
4. **Constraints** — budget, timeline, technology stack, compliance
5. **Assumptions** — stated assumptions about scope, users, or environment

## How to read

- Read the full document top to bottom
- Pay attention to numbered lists and bullet points — these often contain requirements
- Tables often encode constraints or acceptance criteria
- Appendices and footnotes sometimes contain critical technical constraints

## Trust level

Set `trust_level` to:
- `formal_decision` — if the document is signed or marked "approved"
- `explicit_statement` — most written briefs and specs
- `notes` — if it appears to be a draft or working notes

## What to watch for

- Scope boundary statements ("out of scope", "not in scope")
- Integration requirements ("must integrate with", "compatible with")
- Deadline or milestone mentions — extract as constraints
- Conflicting statements within the same doc — list in `potential_conflicts`
