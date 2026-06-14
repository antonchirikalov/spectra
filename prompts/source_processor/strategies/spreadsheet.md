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
