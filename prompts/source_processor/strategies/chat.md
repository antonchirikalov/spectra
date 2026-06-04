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
