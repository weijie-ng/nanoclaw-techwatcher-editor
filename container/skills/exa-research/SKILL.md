---
name: exa-research
description: >-
  Searches and reads the live web with Exa, through the gateway-mcp tools
  (exa_search, exa_contents, exa_find_similar, exa_answer, exa_quota_status).
  Use proactively whenever a task turns on current or external facts that
  memory can't supply: "what is X", "latest on X", finding sources or primary
  documents, reading a specific page's real text, finding pages similar to a
  URL, or a cited one-shot answer. Includes step-by-step playbooks for company
  research (firmographics, funding, news, competitors) and people research
  (role, background, public profile). Use those when asked to profile, look
  up, vet, or background-check a company or a person.
metadata:
  author: NanoClaw
  version: "1.0.0"
---

# Exa Web Research

Exa is a neural (semantic) web-search engine. Five Exa tools reach it through the
**`gateway-mcp`** MCP server. Auth is automatic — the OneCLI proxy injects the
credential on the wire, so never ask for or supply an API key.

Call the tools by their fully-qualified names (use the exact name your tool list
shows for the `gateway-mcp` server):

| Fully-qualified tool | Use for | Relative cost |
|----------------------|---------|---------------|
| `mcp__gateway-mcp__exa-exa_search` | Ranked live-web results for a query | paid |
| `mcp__gateway-mcp__exa-exa_contents` | Cleaned page text for one or more URLs | cheapest paid |
| `mcp__gateway-mcp__exa-exa_find_similar` | Pages similar to a URL you already have | paid |
| `mcp__gateway-mcp__exa-exa_answer` | One-shot answer to a question, with citations | paid |
| `mcp__gateway-mcp__exa-exa_quota_status` | Key / credit health and per-call cost so far | free |

Each tool's exact parameters and current per-call cost are in its own MCP schema
and description — this skill covers *when* to reach for each and *how* to use it
well, not a restatement of the schema.

## Pick the right tool

- **A question with a definite answer** → `exa_answer`. One call returns a
  synthesized answer with citations — fewer tokens than search-then-read. Verify
  anything load-bearing against its citations.
- **Explore a topic / gather several sources** → `exa_search`, then
  `exa_contents` on the best 2–5 result URLs. This two-step is the workhorse.
- **"More pages like this one"** → `exa_find_similar` on a good URL.
- **A call failed, or spend/limits are a concern** → `exa_quota_status` (free)
  before retrying.

## Using the tools well

**exa_search** — phrase the query as the *ideal page*, not keywords: "the
official pricing page for Acme's enterprise plan" beats "acme pricing
enterprise". Keep `num_results` small (5–10) — each row costs tokens and money.
Narrow before widening:
- `search_type`: `auto` (default), `neural` (semantic), `keyword` (exact
  names/codes), `fast`. If a value is rejected, drop it and let it default.
- `category`: one of `company`, `news`, `research paper`, `github`,
  `linkedin profile`, `pdf`, `tweet`, `personal site`, `financial report`.
- `include_domains` / `exclude_domains` to pin to or away from sites.
- `start_published_date` / `end_published_date` as ISO `YYYY-MM-DD` for recency.

**exa_contents** — batch every URL you need into one call rather than looping.
Cap `max_characters` (start ~2000–4000) and set `highlights: true` when you only
need the passages that answer your question, to keep tokens down.

**exa_find_similar** — set `exclude_source_domain: true` to find peers rather
than more pages from the same site (e.g. a company's competitors).

**exa_answer** — set `text: true` to get the source text alongside the answer.

### Example: two-step search then read

```
exa_search { "query": "official announcement of Acme Robotics Series B round",
             "category": "news", "num_results": 5,
             "start_published_date": "2025-01-01" }
# → pick the 1–2 most authoritative result URLs, then:
exa_contents { "urls": ["https://...", "https://..."],
               "max_characters": 3000, "highlights": true }
```

## Cost & token discipline

- Prefer `exa_answer` for a single fact over a search-then-read chain.
- Keep `num_results` low; batch `exa_contents`; cap `max_characters`; use
  `highlights` when only the relevant passage matters.
- Narrow with `category`, date range, and domain filters before widening.
- Reuse what you already fetched; don't repeat an identical search.

## Research playbooks

Two structured workflows build on the tools above. Read the relevant file before
running one — each gives the query patterns, the tool sequence, a progress
checklist, and the output shape to return.

- **Company research** — firmographics, funding, news, leadership, competitors:
  [reference/company-research.md](reference/company-research.md)
- **People research** — role, background, public profile, with disambiguation
  and ethics rules: [reference/people-research.md](reference/people-research.md)

## Troubleshooting

- **The `exa_*` tools aren't in your tool list** → the `gateway-mcp` server isn't
  wired for this agent group. Don't improvise another search route; tell the user
  the gateway isn't connected.
- **A call returns an auth or credit error** → run `exa_quota_status`. If a key
  is cooling or out of credit, report that to the user instead of retrying in a
  loop.
