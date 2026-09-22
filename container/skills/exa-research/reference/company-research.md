# Company research playbook

A compact, sourced firmographic profile of a company. Uses the
`mcp__gateway-mcp__exa-*` tools from [../SKILL.md](../SKILL.md) — call them by
their fully-qualified names; the steps below use short names for readability.
Aim for **5–9 tool calls**: narrow with `category` and date filters, batch
`exa_contents`.

Copy this checklist and track progress:

```
Company research:
- [ ] 1. Find and confirm the primary source (right entity)
- [ ] 2. Read core pages (home / about / product / pricing)
- [ ] 3. Funding & financials
- [ ] 4. Recent news (last 6–12 months)
- [ ] 5. Leadership
- [ ] 6. Competitors / landscape
- [ ] 7. Fill remaining facts, then write the profile
```

**1. Find and confirm the primary source.** `exa_search` with
`category: "company"` and a query naming the company plus a distinguishing detail
(domain, sector, HQ) — e.g. `"Acme Robotics official site warehouse automation"`.
Many companies share a name: confirm the entity (domain, founding year, sector)
before going deeper.

**2. Read the core pages.** `exa_contents` on the homepage plus About / Product /
Pricing / Careers URLs in **one batched call**, `max_characters` capped. Capture
what the company does, its model, and size signals.

**3. Funding & financials.** `exa_search` for
`"<company> funding round raised investors"`, optionally `category: "news"` or
`"financial report"`. For public companies, `include_domains: ["sec.gov"]`. Read
the best 1–3 with `exa_contents`.

**4. Recent news.** `exa_search` `category: "news"` with `start_published_date`
set to the last 6–12 months. Capture launches, layoffs, leadership changes,
partnerships, incidents.

**5. Leadership.** `exa_search` for `"<company> founder CEO leadership team"`
(add `category: "linkedin profile"` for named execs). For a deep dive on one
person, switch to the people-research playbook.

**6. Competitors / landscape.** `exa_find_similar` on the homepage with
`exclude_source_domain: true` to surface peers; cross-check with a search for
`"<company> competitors alternatives"`.

**7. Remaining facts.** For any single stat still missing (headcount, founding
year, HQ), `exa_answer` gives a cited one-shot answer.

## Output shape

A tight profile, each claim traceable to a source URL:

- **What it does** — one or two sentences, plus the model (who pays, for what).
- **Basics** — founded, HQ, size/headcount signal, sector.
- **Funding** — total raised, latest round + date + lead investors (or "private,
  undisclosed" / "public: TICKER").
- **Leadership** — founders / CEO and key execs.
- **Recent developments** — 3–5 dated bullets from the last year.
- **Competitors** — 3–6 named peers.
- **Sources** — the URLs behind the above.

## Cautions

- Flag uncertainty. If sources conflict (e.g. two headcount figures), give the
  range with dates rather than silently picking one.
- Marketing copy overstates; prefer filings, reputable news, and primary docs for
  numbers, and note when a figure is self-reported.
- Don't invent figures to fill a field. "Not found" is a valid answer.
