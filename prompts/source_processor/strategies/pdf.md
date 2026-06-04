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
