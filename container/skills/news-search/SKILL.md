---
name: news-search
description: >-
  Searches news and returns articles with headline, outlet, publication date
  and a followable link. Supports Google, Bing, DuckDuckGo and Baidu News for
  fast global and Chinese coverage, and NewsAPI.ai (Event Registry) for a
  queryable database with source, author, concept, category and exact
  date-range filters, event clustering and sentiment. Use proactively when the
  task turns on what happened and when: breaking news, "what is the latest on
  X", a developing story, a recall, an outage, an earnings report, a court
  ruling, an election, coverage from a named outlet such as the FT or Reuters,
  everything a named journalist has filed, or how widely a story is being
  reported.
metadata:
  author: AI Experimentation Lab
---

# News Search

One script, five engines, one output envelope. Pick the engine with `--engine`; every engine is trimmed into the same eight-field article row.

**Script:** `/app/skills/news-search/scripts/news_search.py` — run it, never read it; nothing in the source is needed to use it.
**Cost:** one SerpAPI credit per call on `google`, `bing`, `duckduckgo` and `baidu`; one NewsAPI.ai token per call on `newsapi`, which has no repeat-query cache of its own. No API key to supply. An identical call inside the last hour is free — see `--cache-ttl`.

This skill searches news. Its siblings `web-search`, `image-search`, `video-search`, `forum-search` and `social-search` search pages, pictures, videos, discussions and accounts. It finds articles, and there are two routes to the text of one: `--body-len` on `--engine newsapi`, which returns the body Event Registry already holds for a row this search just found, and the `page-read` skill, which fetches a bare URL and is the only route on `google`, `bing`, `duckduckgo` and `baidu`, none of which carries a body anywhere.

Deeper NewsAPI.ai detail — URI discovery, source/concept/category filters, events mode, following one event with `--event`, what `sentiment` and `event_uri` are worth — is in [reference/newsapi.md](reference/newsapi.md).

## Choosing an engine

| Need | Engine | Why |
|------|--------|-----|
| Breaking or general news, global | `--engine google` | The biggest news index here, around a hundred rows in one call, and the only SerpAPI engine of the four that returns a real timestamp. Start here. |
| A second ranking, or a strict recency sort | `--engine bing` | The only SerpAPI engine here whose sort-by-date works, and the only SerpAPI one here that pages. Its `date` is a terse relative string (`27m`, `1d`), so it reads as recency without giving you one to compute on. |
| A search that must not be personalised | `--engine duckduckgo` | Thirty to sixty-five rows in one call, no account signal, and plain-string outlet names. A useful second opinion when Google returns the same five wire stories. |
| A Chinese subject | `--engine baidu` | The Chinese news web that Google barely indexes. The only SerpAPI engine here that reports a corpus total, the only one of the four that honours a result count server-side, and the only one that offers its own query refinements. |
| Named outlets, an exact date range, coverage ranking, or article bodies | `--engine newsapi` | Not a SERP but a queryable database: filter by outlet domain, Wikipedia concept, category and exact `--start-date`/`--end-date`, sort by relevance, date or social pickup, cluster a story into an event with a coverage count, and get real article text rather than a headline: 300 characters in `snippet` by default, or the whole piece in `body` with `--body-len -1`, for the same one token. |

Default engine is `google`. When a story spans ecosystems, run the engines separately and compare — each call is one credit or one token.

**Only two engines date their results.** `google` and `newsapi` supply `iso_date`; `bing`, `duckduckgo` and `baidu` give a display string only (`27m`, `23 days ago`, `昨天16:42`) and their `iso_date` is `null` on every row. Nothing here converts a relative string into a timestamp.

**Only three engines page.** `--page` exists on `bing`, `baidu` and `newsapi`. `google` and `duckduckgo` return thirty to a hundred rows in the one call and take no page parameter at all.

**Baidu bills separately.** Unlike the siblings' `--engine baidu`, this is `baidu_news`, a different SerpAPI engine, so the request is never byte-identical to theirs and never joins their free one-hour repeat cache at SerpAPI. A first Baidu news call here is always a credit.

**Bing is not Singapore.** Bing rejects both `sg` and `en-SG` outright, so `--mkt` defaults to `en-US`. An unsupported market is refused at the API and exits `1`.

## Quick reference

```bash
S=/app/skills/news-search/scripts/news_search.py

# Google News, the default: ten stories, dated
python3 $S "tariffs"

# A story moving right now: skip the cached answer
python3 $S "evacuation order" --cache-ttl 0

# What happened this week, and nothing older
python3 $S "Singapore MAS enforcement" --period 7d

# A wider read of one story; --num only trims what already came back
python3 $S "semiconductor export controls" --num 30

# Bing News: the one engine with a working recency sort
python3 $S "tariffs" --engine bing --sort date --num 5

# Bing News: page two, when page one was all wire copy
python3 $S "tariffs" --engine bing --page 1

# Bing News: rounded to its past-7-days bucket, and it says so on stderr
python3 $S "tariffs" --engine bing --period 3d --num 3

# DuckDuckGo News: an unpersonalised second ranking
python3 $S "tariffs" --engine duckduckgo --num 3

# DuckDuckGo News: another region, in its own <region>-<language> spelling
python3 $S "energy price cap" --engine duckduckgo --kl uk-en

# Baidu News: the Chinese news web, with its own refinements
python3 $S "关税" --engine baidu --num 5

# Baidu News: page two (a paged Baidu call is ten rows, whatever --num says)
python3 $S "关税" --engine baidu --page 1

# NewsAPI.ai: a keyword search of the database, with article text in `snippet`
python3 $S "tariffs" --engine newsapi --num 3

# NewsAPI.ai: the whole article, not the first 300 characters. Same one token,
# so keep --num small: ten full bodies measured 228,452 characters.
python3 $S "tariffs" --engine newsapi --body-len -1 --num 2

# NewsAPI.ai: two named outlets, newest first
python3 $S "tariffs" --engine newsapi --source nytimes.com --source bbc.co.uk --sort date --num 3

# NewsAPI.ai: an exact window, inclusive at both ends
python3 $S "tariffs" --engine newsapi --start-date 20260701 --end-date 20260731

# NewsAPI.ai: an entity rather than a word, so homographs do not creep in
python3 $S --engine newsapi --concept http://en.wikipedia.org/wiki/Tariff --num 5

# NewsAPI.ai: one story, however many outlets covered it
python3 $S "tariffs" --engine newsapi --events --num 3

# NewsAPI.ai: follow one event by its uri -> its dossier and coverage roster
# (the uri comes from --events output or an article row's event_uri)
python3 $S --engine newsapi --event eng-11875134 --num 5

# NewsAPI.ai: find the URIs the filters above need
python3 $S "New York" --engine newsapi --lookup source --num 5
python3 $S "tariff" --engine newsapi --lookup concept --num 4
python3 $S "Business" --engine newsapi --lookup category --num 5

# Everything a named journalist filed, in two calls: name -> URI, URI -> articles
python3 $S "Gideon Rachman" --engine newsapi --lookup author --num 5
python3 $S --engine newsapi --author gideon_rachman@ft.com --sort date --num 10
```

## Options

| Flag | Engines | Default | Purpose |
|------|---------|---------|---------|
| `query` (positional) | all | required, except on `newsapi` | Search query string. On `newsapi` it is the keyword condition and may be omitted when at least one of `--source` / `--concept` / `--category` / `--author` is given; on the other four it is required. Under `--lookup` it is the prefix to match, not a search. |
| `--engine` | all | `google` | One of `google`, `bing`, `duckduckgo`, `baidu`, `newsapi`. |
| `--cache-ttl` | all | `1` | Hours an identical call stays usable. Keyed on the request that goes on the wire, not on how you spelled the flags, and shared across agent groups when the operator mounts a shared cache (so a hit can come from a search another group paid for), else local to this group. One hour rather than a day because news an afternoon old is a wrong answer to "the latest on X". `0` forces a live call and still writes the result back. An empty result is never cached. |
| `--num` | all | `10` | How many rows to keep. On `google`, `bing` and `duckduckgo` it only ever **trims** the page that came back — none of the three accepts a result count, so `--num 50` yields whatever the one page held. `baidu` fetches it server-side (`rn`, clamped to 20, and only on an unpaged call — `rn=30` and above make Baidu return an empty page rather than more rows) and `newsapi` fetches it too (100 articles or 50 events, clamped with a note). Either way it caps what you read, not what the call costs. |
| `--page` | bing, baidu, newsapi | `0` | Result page, 0-based. One page per call, so page 3 costs one credit and returns only page 3; it does not accumulate. On `baidu` a paged request holds ten rows whatever `--num` asked for — the two parameters are mutually exclusive at the API — and prints a note when you ask for more. `google` and `duckduckgo` take no page parameter. |
| `--period` | google, bing, duckduckgo, newsapi | _(unset)_ | Only articles from the last `<count><unit>`, e.g. `7d`, `3m`, `2y`; a bare unit means one of them (`w` = the past week). Units: `s` second, `n` minute, `h` hour, `d` day, `w` week, `m` month, `y` year. Exact on `google` (hours, days, months, years; a week becomes days) and on `newsapi` (a whole day). `bing` rounds it up to its past hour / 24 hours / 7 days / 30 days buckets, `duckduckgo` to day / week / month, and both say which bucket on stderr. Rejected up front if combined with `--start-date` / `--end-date`. |
| `--start-date` | newsapi | _(unset)_ | Earliest publication date, `YYYYMMDD`, inclusive. |
| `--end-date` | newsapi | _(unset)_ | Latest publication date, `YYYYMMDD`, inclusive. An inverted range is refused up front, because Event Registry would answer it with an empty set rather than an error. |
| `--sort` | bing, newsapi | `relevance` | Result order: `relevance`, `date`, `social`, `size`. `bing` takes `relevance` and `date` only. `social` ranks by social-media pickup and is `newsapi` only. `size` ranks events by article count and needs `--events`. On `newsapi`, `date` is Event Registry's own ingest order, and the `iso_date` on the row is the publisher's stamp, so the dates you read can wobble by minutes to hours against the ranking. Google News is the pointed omission: SerpAPI refuses its sort parameter whenever a query is present, so the flag warns and is ignored there. |
| `--gl` | google | `sg` | Country code. |
| `--hl` | google | `en` | Interface / results language code. |
| `--mkt` | bing | `en-US` | Market, `<language>-<COUNTRY>`. Bing publishes a fixed list and rejects anything else at the API, `en-SG` included; there is no client-side check, so a bad market is an exit `1` naming itself. |
| `--kl` | duckduckgo | _(DuckDuckGo's own, `us-en`)_ | Region in DuckDuckGo's `<region>-<language>` spelling: `us-en`, `uk-en` (not `gb-en`), `sg-en`, `fr-fr`, `wt-wt` for none. Not `--gl`'s alphabet, and not half of one: SerpAPI refuses a bare country code outright (`Unsupported \`sg\` region`), so one is caught up front at exit `2` rather than spent on a call that cannot work. |
| `--lang` | newsapi | `eng` | Article language as an ISO 639-3 code — three letters, `eng`, `zho`, `deu`. Checked up front: an unrecognised code returns zero results and no error, which is indistinguishable from a story nobody covered. |
| `--body-len` | newsapi | `300` | Characters of article text to fetch. `-1` fetches the whole article, and then the full text lands in a `body` row extra while `snippet` keeps its first 300 characters, so the eight-field row never changes shape. A call costs one token at any length (measured on `/api/v1/usage`: ten rows at `300` cost 1.0 token for 3,013 characters of body, the same ten at `-1` cost 1.0 token for 228,452), so length is free at the API and expensive only in your context, and `--num` is the knob that keeps it down. Event Registry cuts at a word boundary, so a row can arrive a few characters under what you asked for. `0` and anything below `-1` are refused at exit `2`. |
| `--source` | newsapi | _(unset)_ | Outlet domain, e.g. `nytimes.com`. Repeatable, also accepts a comma-separated list; several are OR'd. Find them with `--lookup source`. |
| `--concept` | newsapi | _(unset)_ | Full Wikipedia URI, e.g. `http://en.wikipedia.org/wiki/Tariff`. Repeatable, OR'd. A bare name is refused up front. Find them with `--lookup concept`. |
| `--category` | newsapi | _(unset)_ | Category URI, e.g. `dmoz/Business` or `news/Business`. Repeatable, OR'd. Find them with `--lookup category`. |
| `--author` | newsapi | _(unset)_ | Author URI, e.g. `jane_smith@nytimes.com` — a byline bound to the outlet that carried it, so a journalist who writes for two outlets has two URIs and needs both flags. Repeatable, OR'd. A value without an `@` is refused up front, because Event Registry answers a bare name with an empty set that reads as "wrote nothing". Find them with `--lookup author`. |
| `--events` | newsapi | off | Return clustered events — one story, however many outlets covered it — instead of articles. Changes the envelope: `events` replaces `articles`. |
| `--event` | newsapi | _(unset)_ | Follow one event by its `uri` (from `--events` output, or an article row's `event_uri`) and return its dossier — title, summary, coverage count, sentiment, social score, tagged concepts, categories and location — plus the articles that covered it. Ignores every search filter; `--num`, `--page`, `--sort` and `--body-len` shape the article roster. Changes the envelope: an `event` dossier joins `articles`. |
| `--lookup` | newsapi | _(unset)_ | `source`, `concept`, `category` or `author`. Treats the query as a prefix and returns matching URIs for the four filters above. Searches nothing else: every other filter is ignored, with a warning. Changes the envelope: `lookups` replaces `articles`. |

Nothing you type is dropped in silence. A flag the engine has no use for prints `Warning: --period does not apply to --engine baidu; ignoring it.` on stderr; a `--sort` an engine has no equivalent for prints one too; and a malformed `--period`, a bad date, a bare `--concept`, a half-pair `--kl` or a non-ISO-639-3 `--lang` is refused before the call is made, at exit `2`. **Read stderr** — it is where every ignored flag, every rounded period, every clamped count and the missing-gateway warning are reported, and the only place they appear.

## Output

JSON to stdout. Progress, warnings, and errors to stderr. Every response carries `status`, `engine`, `query`, `cached`, and `articles`, and `query` is `null` when a `newsapi` search ran on filters alone (or under `--event`); `baidu` adds `related_searches` and `total_results`, and `newsapi` adds `total_results` — and swaps `articles` for `events` under `--events` or `lookups` under `--lookup`, or adds an `event` dossier beside `articles` under `--event`.

`cached` is `true` when nothing was billed and the rows are up to `--cache-ttl` hours old — say so if the user asked what is happening right now.

`status` is `"ok"` when the engine returned at least one article, event or lookup and `"no_results"` when it did not. It always agrees with the exit code below, so branching on either one gives the same answer. Baidu's refinement queries and the corpus total never count as a result on their own.

Every article, on all five engines, is trimmed to the same eight fields:

```json
{
  "position": 1,
  "title": "US says dozens of countries helped China dodge Trump's tariffs",
  "link": "https://www.bbc.com/news/articles/c78gy6ep3n5o",
  "source": "BBC",
  "snippet": null,
  "date": "08/14/2026, 08:39 AM, +0000 UTC",
  "iso_date": "2026-08-14T08:39:46Z",
  "thumbnail": "https://ichef.bbci.co.uk/news/480/cpsprodpb/d8fc/live/..."
}
```

- `position`: the row's 1-based index in the array you are reading, stamped here rather than taken from the engine. Google restarts its numbering inside a cluster, Bing publishes none, Baidu restarts on every page
- `link`: the article, and the URL to cite
- `source`: the outlet. Left exactly as the engine sent it, so on `bing` a syndicated copy names its carrier too (`CNBC on MSN`) — that is who published the copy at that link, which is what a citation needs
- `date`: the engine's own display string, and four of the five engines send display text (`27m`, `23 days ago`, `昨天16:42`, `08/14/2026, 08:39 AM, +0000 UTC`). Quote it, do not do arithmetic on it. The fifth is `newsapi`, which sends the ISO stamp itself, the same string as `iso_date`: say the date in your own words there rather than quoting it at a user
- `iso_date`: a real UTC timestamp, and the only field you may compute on. `google` and `newsapi` supply one; on `bing`, `duckduckgo` and `baidu` it is `null` on every row, by design — nothing guesses a timestamp out of "22d"
- `snippet`: the engine's precis, and always `null` on `google`, which publishes headlines and outlets and nothing else. On `newsapi` it is the first `--body-len` characters of the article body (300 by default; under `-1` it keeps its first 300 characters and the whole text moves to the `body` extra), which is text but is not a summary
- `thumbnail`: an image URL where the engine gave one
- Any field the engine did not supply is `null`, so read every one defensively

**Row extras**, present only when the engine supplied them:

- `cluster` (`google`, `bing`): the grouping headline the row was lifted out of, e.g. `News about tariffs • China`. Both engines return clusters of related coverage; their children are flattened into `articles` in place, deduplicated by link. It is a heading, not a source. On `google` the key appears only on a row that came out of a cluster; on `bing` every clustered row carries it, `null` where the cluster had no headline
- `authors` (`google`, `newsapi`): a list of bylines
- `body` (`newsapi`, only under `--body-len -1`): the whole article text. `snippet` still holds its first 300 characters, so nothing that only wanted the opening has to change
- `sentiment`, `event_uri`, `is_duplicate` (`newsapi`): see [reference/newsapi.md](reference/newsapi.md)

**Top-level extras.** `baidu` always carries `related_searches` (`[{"query": ...}]`, `[]` when none — Baidu's own refinements, and how a query in the wrong register gets fixed) and `total_results` when Baidu reported one. `newsapi` carries `total_results` when NewsAPI.ai reported one, and never under `--lookup`: the size of the whole matching corpus, not of this page. The `events` and `lookups` rows and the `--event` dossier each have their own shape, all documented in [reference/newsapi.md](reference/newsapi.md).

## Exit codes

| Code | Meaning | JSON on stdout? |
|------|---------|-----------------|
| `0` | Results returned. `"status": "ok"`. | Yes |
| `1` | HTTP or network failure, a gateway `credential_not_found`, a non-JSON or wrong-shaped body, an invalid `--num` or `--page`, an error in SerpAPI's own `error` field other than an empty SERP, or an error NewsAPI.ai reported. | No |
| `2` | Invalid command line: unknown flag, a missing query, a bad `--engine` / `--sort` / `--lookup` choice, a malformed `--period` or `YYYYMMDD` date, `--period` combined with a date range, an inverted date range, `--sort size` without `--events`, `--lookup` with `--events`, a `--lang` that is not three letters, a `--body-len` of `0` or below `-1`, a `--kl` that is not a `<region>-<language>` pair, or a `--concept` that is not a full URI. Emitted by argparse, which writes its usage message to stderr. | No |
| `3` | The request succeeded but the engine returned nothing. The envelope is still printed, with `"status": "no_results"`, so you can inspect it; treat it as "no hits", not as a crash. | Yes |

Do not treat exit `2` as an empty result set: stdout is empty there, so `json.loads()` on it will fail. Only `0` and `3` print JSON.

SerpAPI reports an empty SERP as an error string rather than an empty list. The script recognises that case and turns it back into a `no_results` envelope, so "nothing matched" stays distinguishable from "the call broke". It also recognises SerpAPI's *transient* failure ("We couldn't get valid results for this search") and says so in as many words, because that one is worth retrying and the others are not. NewsAPI.ai answers HTTP `200` even for its own errors, so a parameter it dislikes is still an exit `1` — the message is its own words, not a status code.

## Common mistakes

- **Not quoting multi-word queries** — wrap the query in quotes: `python3 $S "chip export controls"`, not `python3 $S chip export controls`. The same applies to non-Latin queries: `python3 $S "关税" --engine baidu`.
- **Using `python` instead of `python3`** — `python` may not exist on the system.
- **Doing arithmetic on `date`** — `27m`, `23 days ago` and `昨天16:42` are display strings, not timestamps, and none of them carries a year. Only `iso_date` is machine-readable, and only `google` and `newsapi` supply one. If you need to know exactly when something ran, use one of those two or open the article.
- **Raising `--num` to get more stories on `google`, `bing` or `duckduckgo`** — none of the three accepts a result count, so `--num` trims the page that already came back. `--page` fetches more, and only on `bing`; `google` and `duckduckgo` have no page two here at all, and already return thirty to a hundred rows.
- **Expecting `--sort date` to work on `google`** — Google News refuses its own sort parameter whenever a query is present, so the flag warns and is ignored. Use `--engine bing --sort date`, or `--engine newsapi --sort date` for a dated database query.
- **Reading a `cluster` row as a citation** — `cluster` is Google's or Bing's grouping headline for a story ("News about tariffs • China"), not an outlet and not a URL. Cite the row's own `link` and `source`.
- **Treating a `--period` on `bing` or `duckduckgo` as exact** — both round it up to their own buckets, so `--period 3d` on Bing searches the last seven days and says so on stderr. `newsapi` is the one engine with an exact `--start-date` / `--end-date`.
- **Passing a bare name to `--source`, `--concept` or `--category`** — they take URIs, not words: a domain, a full Wikipedia URL, a taxonomy path. Run `--lookup source "New York"`, `--lookup concept "tariff"` or `--lookup category "Business"` first and use what comes back. A bare `--concept` is refused at exit `2`; a mistyped `--source` returns an empty set that reads as "nobody covered this".
- **Ranking `--events` by `--sort size`** — the biggest event by article count is often a keyword coincidence rather than the biggest story. `relevance` is the honest default; check `article_count` on the rows yourself.
- **Expecting the article text from `google`, `bing`, `duckduckgo` or `baidu`**: none of the four returns a body, ever, and no flag makes them. `snippet` is the engine's precis where it has one, so read the page with `page-read` before asserting what an article says, and cite the row's own URL rather than the outlet's homepage. `--engine newsapi` is the one engine that carries the text itself: `--body-len -1` returns it whole.
