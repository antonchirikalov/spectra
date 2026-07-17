# Source Extraction Task

## Source Document

Read `C:\Users\achirikalov\Documents\agents\spectra\tests\golden_input\brief.md` using the `read` tool.

## Manifest Entry

```json
{
  "kind": "file",
  "slug": "brief",
  "path": "C:\\Users\\achirikalov\\Documents\\agents\\spectra\\tests\\golden_input\\brief.md",
  "read_tool": "read"
}
```

## Output Schema

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

  "files_processed": [
    "list of file paths actually read — required for subfolder entries, optional for single files"
  ],

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


## Strategies

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


# Strategy: Chat / Messaging Export

Use this strategy for Slack exports, Teams message threads, email chains, or any conversation in short message format.

## Extraction focus

1. **Decisions confirmed** — explicit "+1", "agreed", "sounds good" after a proposal
2. **Requirements stated informally** — "we need X", "can you make sure Y"
3. **Rejections** — "no", "that won't work", "let's not do that" — do NOT include rejected items
4. **File attachments mentioned** — may point to other source documents
5. **Action items** — "@person can you..." or "I'll..."

## How to read

- Process messages chronologically
- Thread replies may supersede top-level messages — check both
- Reactions (👍, ✅) can confirm decisions
- High message frequency on a topic = high importance
- Short one-word messages ("yes", "ok") are confirmation signals for the preceding proposal

## Participants

List all active participants (people who wrote messages). If messages show only usernames without real names, note this and set `needs_clarification: true` with a request to identify participants.

## Trust level

Set `trust_level: "chat"`.

## What to watch for

- Messages marked as edited — the edited version is the current intent
- Long gaps in time (days between messages) — may indicate changed context
- Link references to external documents — note in `open_questions` if those docs aren't in the project
- Off-topic jokes or social messages — skip them, extract only substantive content
- Contradictions across time (something agreed on Monday, questioned on Friday)


# Strategy: PDF Document

Use this strategy when the source is a PDF file. PDFs can contain many content types — determine the sub-type first.

## Step 1: Determine PDF sub-type

Read the first page (use `mcp_pdf-reader` → `read_pdf` with `start_page: 1, end_page: 1`).

Identify which sub-type best describes this PDF:

| Sub-type | Signals |
|---|---|
| `brief` | Prose paragraphs, section headings, project or business document |
| `spec` | Technical specifications, data models, API docs, numbered sections |
| `transcript` | Speaker labels, timestamps, Q&A format |
| `chart` | Mostly tables, charts, financial data, KPIs |
| `form` | Form fields, checkboxes, questionnaire format |

Set `source_type` to the combined form, e.g. `"pdf"` or `"transcript+pdf"`. You may use `"pdf"` alone if sub-type is unclear.

## Step 2: Read the full PDF

Use `mcp_pdf-reader` tools:
- `read_pdf` — for text-heavy PDFs (returns full text)
- `smart_extract_pdf` — for structured/mixed PDFs (better for tables and forms)
- `ocr_pdf` — only if text extraction returns empty or garbled text (scanned document)

Read all pages. For long PDFs (>30 pages), focus on:
- Table of contents (if present) to understand structure
- Executive summary / overview section
- Requirements sections (often titled "Requirements", "Scope", "Deliverables")
- Appendices that list acceptance criteria

## Step 3: Apply sub-type strategy

After determining sub-type, apply the matching extraction approach:
- `brief` or `spec` → follow `strategies/brief.md`
- `transcript` → follow `strategies/transcript.md`
- `chart` or `form` → follow `strategies/spreadsheet.md`

## Trust level

- `formal_decision` — signed PDF, contract, formal approval
- `explicit_statement` — RFP document, formal specification
- `notes` — informal PDF, presentation deck


# Strategy: Q&A Document

Use this strategy for structured Q&A documents: vendor questionnaires, RFP responses in question-answer format, pre-bid clarifications, or any document with numbered questions and answers.

## Extraction focus

1. **Each answered question** = potential requirement or constraint
2. **Unanswered questions** = open items, add to `open_questions`
3. **Conditional answers** = requirements with conditions, mark `confidence: "medium"`
4. **Rejections** — if a question asks "can you do X?" and answer is "no", it is a constraint

## How to read

- Treat each Q&A pair as a unit
- Question text often reveals what the client considers important — use it to frame requirements
- Answers starting with "We will..." / "Our solution..." = explicit commitments → requirements
- Answers starting with "We plan to..." / "We intend to..." = lower confidence
- Look for patterns: multiple questions on the same topic = high-priority area

## Trust level

Set `trust_level` based on context:
- `explicit_statement` — if it's a formal RFP response or signed questionnaire
- `notes` — if it appears to be a draft or internal working document

## What to watch for

- Questions the client asks about your capabilities → their requirements
- Follow-up answers that modify earlier answers — use the most recent
- Compliance questions ("Do you comply with ISO 27001?") → constraints
- Pricing-related Q&A → note as constraints but do not invent numbers


# Strategy: Spreadsheet / Tabular Data

Use this strategy for Excel files (`.xlsx`) and any table-heavy documents — budget sheets, project plans, feature matrices, requirement trackers, pricing tables.

## What you receive

The manifest entry's `read_tool` field will be `mcp_excel`. Use the `excel` MCP server tools to read the file:

- Call `read_sheet_names` (or equivalent) to list sheets
- Call `read_sheet_data` (or equivalent) to read each sheet's contents

The file path is in the manifest entry's `path` field.

## Extraction focus

1. **Identify what each sheet represents** — budget, timeline, feature list, etc.
2. **Column headers** define the meaning of each row — always read them first
3. **Look for requirement signals:**
   - Feature/function columns → functional requirements
   - Priority columns (P1/P2, Must/Should) → importance weighting
   - Status columns (Included/Excluded, Yes/No) → scope decisions
   - Timeline/milestone columns → deadline constraints
4. **Budget sheets** → note budget constraints (do not extract specific numbers unless explicitly scoped)
5. **Feature matrices** → each row is potentially a requirement

## Trust level

Set `trust_level`:
- `formal_decision` — if it's a signed-off project plan or approved budget
- `explicit_statement` — most formal spreadsheets
- `notes` — if labeled as draft or working copy

## What to watch for

- Empty cells may mean "not applicable" or "unknown" — do not infer
- Merged cells (shown as repeated values in JSON) — use the header row for context
- Multiple sheets with conflicting data — list in `potential_conflicts`
- Very large sheets (100+ rows) — focus on non-empty rows; summarize patterns rather than listing every row as a requirement


# Strategy: Meeting Transcript

Use this strategy for meeting transcripts, interview recordings, and Q&A session logs.

## Extraction focus

1. **Speaker attribution** — always capture who said what
2. **Decisions made** — look for phrases like "we decided", "agreed", "let's go with"
3. **Action items** — "I'll handle", "you should", "we need to" + person
4. **Requirements stated** — often phrased informally: "we need X", "it has to do Y"
5. **Open questions** — unresolved discussions, "we'll figure out later", "TBD"

## How to read

- Identify all participants at the start (if present in the transcript header)
- Read through chronologically — context builds up
- A requirement stated by a senior stakeholder (CTO, VP) has higher weight than a casual mention
- Disagreements mid-discussion are `potential_conflicts` unless resolved later

## Speaker names

Capture `speaker` field for each requirement. Use the format from the transcript:
- "Ahmad Al-Rashid (CTO)" if role is known
- "Ahmad" if only first name is used
- "Speaker 1" if anonymous — and set `needs_clarification: true`

## Trust level

Set `trust_level: "transcript"`.

Exception: if the transcript describes a formal sign-off or approval meeting, use `formal_decision`.

## What to watch for

- Statements that contradict earlier statements in the same transcript
- Requirements that were proposed but then rejected — do NOT include rejected items
- Late-in-meeting clarifications that supersede earlier statements — use the final version
- "Maybe" / "possibly" / "we're considering" — mark these as `confidence: "low"`


