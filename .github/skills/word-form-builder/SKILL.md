---
name: word-form-builder
description: Generates interactive Word clarification forms with native SDT checkboxes, dropdowns, and pre-filled tables from a JSON spec. No macros, no document protection required.
---

# Word Form Builder

## When to use
When `word_form_builder` agent needs to generate an interactive `.docx` clarification form.

## Script invocation

```bash
.venv/bin/python .github/skills/word-form-builder/scripts/build_word_form.py \
  --input <form_spec.json> \
  --output <output.docx>
```

## form_spec.json full schema

```json
{
  "meta": {
    "project":   "DTV Mobile Application",
    "reference": "DTVC-961",
    "vendor":    "ScienceSoft",
    "issued_by": "Dhahran Techno-Valley Holding Co. (DTVC)",
    "round":     "2",
    "date":      "21 May 2026",
    "intro":     "To accelerate response, each clarification states a Default assumption — the Bidder's working hypothesis. If the default is acceptable, tick Confirmed as stated. If not, complete the override fields."
  },
  "sections": [
    {
      "title": "IDENTITY AND INTEGRATIONS",
      "questions": [
        {
          "id": "Q-01",
          "title": "Identity architecture — canonical IdP per persona",
          "context": "Paragraph from SoW or requirements explaining the ambiguity.",
          "default_assumption": "Bidder's working hypothesis as a single sentence.",
          "owner_hint": "Technical Architect",
          "decision_impact": "What this answer changes in technical or commercial response.",
          "controls": [
            {
              "type": "table",
              "label": "If override required — confirm canonical IdP per persona",
              "headers": ["Persona", "Canonical IdP", "Federation / Notes"],
              "rows": [
                {
                  "label": "Employee",
                  "fields": [
                    {"type": "dropdown", "options": ["Entra ID", "Oracle IDCS", "STID", "Azure B2C", "Okta", "Other"]},
                    {"type": "text",     "placeholder": "Federation details, JIT provisioning"}
                  ]
                },
                {
                  "label": "Tenant",
                  "fields": [
                    {"type": "dropdown", "options": ["Oracle CRM", "Entra ID", "Oracle IDCS", "Azure B2C", "Other"]},
                    {"type": "text",     "placeholder": "Federation details"}
                  ]
                }
              ]
            },
            {
              "type": "dropdown",
              "label": "The ambiguous SoW reference should be interpreted as",
              "options": ["MS Entra ID (documentation error)", "Microsoft Graph API", "MS Excel (literal)", "Other (specify below)"]
            }
          ]
        },
        {
          "id": "Q-02",
          "title": "Oracle Fusion deployment and integration channels",
          "context": "Context from requirements.",
          "default_assumption": "Default assumption text.",
          "owner_hint": "Enterprise Architect",
          "decision_impact": "Middleware role and Oracle licence dependency.",
          "controls": [
            {
              "type": "dropdown",
              "label": "Oracle Fusion deployment model",
              "options": ["Oracle Cloud SaaS", "On-Premise", "OCI Hosted", "Partner Managed", "Hybrid", "Other"]
            },
            {
              "type": "checkbox_group",
              "label": "Integration channels available to the Developer (tick all that apply)",
              "items": [
                {"label": "Direct REST APIs",             "checked": true},
                {"label": "Oracle Integration Cloud (OIC)", "checked": true},
                {"label": "BIP (BI Publisher) reports",   "checked": false},
                {"label": "SOAP / Web Services",          "checked": false},
                {"label": "Other (specify below)",        "checked": false}
              ]
            }
          ]
        }
      ]
    }
  ]
}
```

## Control types reference

| `type`          | Renders as | Use when |
|----------------|-----------|---------|
| `dropdown`      | Native Word dropdown (click to expand) | One-of-N choice |
| `checkbox_group` | Row of native clickable checkboxes | Multi-select |
| `table`         | Table with label col + SDT fields in other cols | Per-system / per-persona matrix |
| `text_field`    | Greyed placeholder text field | Free-form text override |

## Notes

- `confirm` checkbox and owner text field are **always injected automatically** for every question — do NOT add them to `controls`.
- SDT checkboxes use `w14:checkbox` — requires Word 2010+. Works in Word for Mac, Word Online, and all modern Windows Word versions.
- SDT dropdowns use `w:dropDownList` — Word 2007+.
- Neither requires document protection or macros.
- Brand palette: navy `#061838` (headers), silver `#F4F6F8` (alt rows), border `#C9D3DE`.
