# Source Processor — Output Schema

Your output must be a single JSON code block following this schema.
All fields except `source_file` and `source_type` are optional — include only what is present in the document.

```json
{
  "source_file": "string — original filename or folder name",
  "source_type": "string — transcript | chat | brief | qa | pdf | spreadsheet | <type>+<type>",
  "source_type_confidence": "high | medium | low",
  "date": "string — ISO 8601 date if found, e.g. 2026-03-15",
  "participants": ["list of named participants with roles if known"],
  "topics": ["list of main topics covered"],

  "requirements": [
    {
      "id": "string — SRC-<SLUG>-<NNN>, e.g. SRC-KT-001",
      "text": "string — requirement text, one sentence",
      "type": "FR | NFR | CONSTRAINT | ASSUMPTION",
      "confidence": "high | medium | low",
      "speaker": "string — who stated it (for transcripts/chat)",
      "quote": "string — verbatim quote from document"
    }
  ],

  "decisions": ["list of decisions made, as strings"],

  "constraints": ["list of constraints, as strings"],

  "open_questions": ["list of unresolved questions found in the document"],

  "potential_conflicts": [
    "string — describe any contradictions found within this document"
  ],

  "trust_level": "formal_decision | explicit_statement | transcript | chat | notes",

  "needs_clarification": false,
  "clarification_request": "string — what context is missing (only if needs_clarification is true)"
}
```

## Field Notes

**`source_type`** — can be combined, e.g. `"transcript+pdf"` if a PDF contains a meeting transcript.

**`trust_level`** — classify the *document itself*, not individual requirements:
- `formal_decision` — signed specs, approved decisions, contracts
- `explicit_statement` — written requirements documents, RFP docs
- `transcript` — meeting recordings or transcripts
- `chat` — messaging exports (Slack, Teams, email threads)
- `notes` — informal notes, drafts, brainstorm docs

**`confidence`** on requirements:
- `high` — explicitly stated, unambiguous
- `medium` — clearly implied by context
- `low` — inferred, may need confirmation

**`needs_clarification`** — set to `true` only when critical context is missing:
- Unnamed participants in a transcript
- Undated document where date matters
- Contradictory data within the same document
- Empty or unreadable file

**Requirement IDs** — format `SRC-<SLUG>-<NNN>` where `<SLUG>` is 2-3 uppercase letters derived from the source filename (e.g. kickoff transcript → `KT`, tech spec → `TS`).
