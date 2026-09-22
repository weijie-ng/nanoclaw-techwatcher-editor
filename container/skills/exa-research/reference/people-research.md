# People research playbook

A sourced professional profile of a person from **public** information — role,
background, notable work. Uses the `mcp__gateway-mcp__exa-*` tools from
[../SKILL.md](../SKILL.md); the steps below use short names for readability.

## Ethics & scope — read first

- **Public, professional info only.** Bios, company pages, public profiles,
  talks, publications, interviews, press. Never home addresses, personal contact
  details, family, financial, medical, or other private data.
- **Purpose check.** This is for legitimate context (vetting a contact, prepping
  for a meeting, verifying a claim), not surveillance or harassment. If the
  request aims at harm, or targets a private individual with no public role,
  decline and say why.
- **Say what you don't know.** Never fill gaps with guesses.

Copy this checklist and track progress:

```
People research:
- [ ] 1. Disambiguate (anchor by employer / role / location / field)
- [ ] 2. Find the anchor profile
- [ ] 3. Read the best pages
- [ ] 4. Track record (talks, papers, projects, press)
- [ ] 5. Verify specific claims, then write the profile
```

**1. Disambiguate first.** Names collide. Anchor the person with a second signal
in every query — employer, role, location, or field:
`"Jordan Lee VP Engineering Acme Robotics"`. If you can't separate two people,
present both candidates and ask the user which, rather than blending them.

**2. Find the anchor profile.** `exa_search` with `category: "linkedin profile"`
or `"personal site"`, query = name + anchor. Also run a plain search for
`"<name> <company>"` to catch team/about pages and press.

**3. Read the best pages.** `exa_contents` (batched) on the profile, the employer
bio/team page, and any personal site. `highlights: true` keeps it lean when you
only need role and background lines.

**4. Track record.** `exa_search` for public output: `category: "research paper"`
for academics, `"github"` for engineers, `"news"` for press (add a date range for
recent activity).

**5. Verify a specific claim.** `exa_answer` for a pointed, checkable question
("Is <name> currently the CTO of <company>?") returns a cited answer.

## Output shape

- **Who they are** — current role and organization, one line.
- **Background** — prior roles / affiliations; education if public and relevant.
- **Notable work** — key projects, publications, talks, contributions.
- **Recent activity** — dated, if any.
- **Confidence & caveats** — disambiguation risk, thin sourcing, stale info.
- **Sources** — the URLs behind each claim.

## Cautions

- One matching name ≠ the right person. Keep the anchor signal consistent across
  every claim; drop anything you can't tie to the same individual.
- Prefer first-party sources (their own site, their employer, their bylined work)
  and reputable press over aggregator/scraper sites, which often merge people.
- Distinguish "held role X" (past) from "holds role X" (current), with dates.
