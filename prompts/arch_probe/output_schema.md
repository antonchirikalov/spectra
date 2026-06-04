# arch_probe — Output Schema

Your output must be a single JSON code block following this schema exactly.

```json
{
  "ai_detection": {
    "overall_assessment": "low | medium | high",
    "per_source": [
      {
        "source_file": "string — original filename from extract",
        "score": "low | medium | high",
        "signals": [
          "list of specific observations — e.g. 'no named systems or team references', 'uniform granularity across all requirements', 'boilerplate NFR section identical to industry templates'"
        ],
        "note": "optional free-text explanation"
      }
    ]
  },

  "domain_context": {
    "domain": "string — identified business domain (e.g. 'retail banking', 'logistics', 'healthcare')",
    "technology_stack": ["identified technologies, platforms, integrations"],
    "searches_performed": [
      "exact query string used in Tavily search"
    ],
    "key_findings": [
      "string — specific finding relevant to architecture decisions"
    ]
  },

  "raw_questions": [
    {
      "id": "Q-001",
      "text": "string — the question, specific and direct",
      "category": "integration | nfr | data | security | team | business | architecture | migration | compliance",
      "rationale": "string — why this matters for architecture — what decision it unlocks or what risk it surfaces",
      "source_ref": "string — which extract, which specific finding or gap triggered this question"
    }
  ]
}
```

## Field notes

**`ai_detection.overall_assessment`** — aggregate judgment across all sources. Use `high` if most sources show strong AI signals, `medium` if mixed, `low` if documents appear human-authored.

**`ai_detection.per_source.signals`** — be specific. Not "generic language" but "all 12 functional requirements use identical sentence structure and same confidence level; no version history or author visible".

**`domain_context.searches_performed`** — list the actual query strings you submitted to Tavily, not topic descriptions.

**`raw_questions.text`** — write the question as you would ask it in a meeting. Direct. Specific. No filler openers.

**`raw_questions.source_ref`** — reference the extract slug and the specific finding. E.g. `"rfp_main.json: requirement SRC-RFP-014 mentions 'offline mode' but no sync strategy is defined"`.
