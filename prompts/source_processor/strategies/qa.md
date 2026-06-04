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
