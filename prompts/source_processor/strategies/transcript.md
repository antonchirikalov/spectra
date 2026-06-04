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
