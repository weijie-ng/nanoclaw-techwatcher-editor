# NewsAPI.ai reference

The NewsAPI.ai (Event Registry) surface that does not fit in SKILL.md. The shared envelope and the flags are there; only what is specific to `--engine newsapi` is below.

## Contents

- What it is
- Finding URIs with `--lookup`
- Filters
- Events mode
- Following one event with `--event`
- Row extras, and how far to trust them
- Not here

## What it is

The other four engines are search engines: one call buys one page of whatever their news vertical ranked for a phrase. NewsAPI.ai is a queryable database of indexed news. You do not rank a phrase against it, you state conditions — this keyword, from these outlets, about this concept, in this language, between these dates — and it returns the matching rows plus a count of how many matched in total.

Three consequences worth planning around:

- `total_results` is the size of the **whole matching corpus**, not of what came back. 62,016 there and three rows in `articles` is normal, and the figure is a useful measure of how heavily something is covered.
- One token per call regardless of `--num`, and there is **no repeat-query cache** the way SerpAPI has one. So a single wide call is cheaper than paging: `--num 100` costs exactly what `--num 10` costs, and `--page 1` is a second token.
- A condition that matches nothing returns an empty set with **no error**. Every empty answer here is ambiguous between "nobody covered this" and "one of your URIs is wrong", which is why the script prints a note on stderr whenever this engine comes back empty, and why `--lang`, `--concept` and inverted date ranges are checked before the call.

`keyword` matches the article **body**, not just the headline, so a keyword search returns pieces that mention the word in passing. When the subject is an entity rather than a word, `--concept` is the sharper instrument.

## Finding URIs with `--lookup`

`--source`, `--concept`, `--category` and `--author` take URIs, not names. `--lookup` is how you get them: it treats the query as a prefix, hits the matching suggest endpoint, and returns `lookups` instead of `articles`. It searches nothing else — every other filter is ignored, with a warning on stderr — and it is the cheap first half of a two-call workflow.

```bash
S=/app/skills/news-search/scripts/news_search.py

python3 $S "New York" --engine newsapi --lookup source --num 5
# {"position": 1, "uri": "nypost.com",   "label": "New York Post",  "type": "news"}
# ... then:
python3 $S "housing" --engine newsapi --source nytimes.com --num 10

python3 $S "tariff" --engine newsapi --lookup concept --num 4
# {"position": 1, "uri": "http://en.wikipedia.org/wiki/Tariff",        "label": "Tariff",        "type": "wiki"}
# {"position": 2, "uri": "http://en.wikipedia.org/wiki/Trump_tariffs", "label": "Trump tariffs", "type": "wiki"}
# ... then:
python3 $S --engine newsapi --concept http://en.wikipedia.org/wiki/Tariff --num 5

python3 $S "Gideon Rachman" --engine newsapi --lookup author --num 5
# {"position": 1, "uri": "gideon_rachman@ft.com", "label": "Gideon Rachman", "type": "author"}
# ... then, with no query at all, because the byline is the whole condition:
python3 $S --engine newsapi --author gideon_rachman@ft.com --sort date --num 10

python3 $S "Business" --engine newsapi --lookup category --num 5
# {"position": 1, "uri": "dmoz/Business",                       "label": "dmoz/Business",              "type": "dmoz"}
# {"position": 2, "uri": "iptc/economy,_business_and_finance",  "label": "iptc/economy, business ...", "type": "iptc"}
# {"position": 3, "uri": "news/Business",                       "label": "news/Business",              "type": "news"}
# {"position": 4, "uri": "dmoz/Business/Accounting",            "label": "dmoz/Business/Accounting",   "type": "dmoz/Business"}
```

A `lookups` row is four fields:

| Field | Sources | Concepts | Categories |
|-------|---------|----------|------------|
| `uri` | the outlet domain (`nypost.com`) | the full Wikipedia URL | the taxonomy path (`dmoz/Business`) |
| `label` | the outlet's name | the concept's English name | the path, humanised for `iptc` |
| `type` | the source's `dataType` (`news`, `blog`, `pr`) | the concept type: `wiki`, `person`, `org`, `loc` | the parent path, so `dmoz/Business/Accounting` has type `dmoz/Business` |

Two things the table does not say. **Three taxonomies coexist** for categories — `dmoz/*`, `news/*` and `iptc/*` — and a lookup returns all three mixed together; pick one deliberately rather than taking row one. And `dmoz/*` is **hierarchical**, so `dmoz/Business` is broader than `dmoz/Business/Accounting` and the lookup will offer you both.

`--lookup` is also the fastest way to check whether an outlet is indexed at all before you build a filter around it.

## Filters

All three are repeatable, and several values of the same flag are OR'd — the script sends the operator explicitly, because Event Registry's own default for concepts is AND, which would turn two of anything into a demand that both appear.

- **`--source nytimes.com`** — the outlet domain, as `--lookup source` spells it. Also accepts a comma-separated list, so `--source nytimes.com,bbc.co.uk` and two separate `--source` flags are the same thing. A domain that is not indexed narrows the answer to nothing rather than failing.
- **`--concept http://en.wikipedia.org/wiki/Tariff`** — an entity Event Registry tagged the article with, not a word it contains. This is what disambiguates a homograph, and it catches articles that discuss the entity without using your phrasing. The full URI is required; a bare name exits `2`.
- **`--category dmoz/Business`** — a subject area. Broad, and best used to narrow a keyword rather than on its own.
- **`--author gideon_rachman@ft.com`** — the byline, as `--lookup author` spells it. The URI binds a journalist to one outlet, so someone who files for two mastheads has two URIs and needs a `--author` for each; the repeated flag ORs them, which is what "everything they wrote" means in practice. This is the filter to reach for when the subject is *who wrote it* rather than what it was about — a keyword search on the name returns articles that mention them as much as articles by them.
- **`--lang eng`** — ISO 639-3, three letters: `eng`, `zho`, `deu`, `fra`, `spa`. Defaults to `eng`. **A code the service does not recognise returns zero results and no error**, so the script refuses anything that is not three lower-case letters — but that check cannot tell a real code from a plausible-looking one, so an unexpectedly empty answer is worth re-running with `--lang` dropped.
- **`--start-date` / `--end-date`** — `YYYYMMDD`, **inclusive at both ends**, and the only exact date range any engine in this skill offers. Cannot be combined with `--period`; `--period` on this engine resolves to a `dateStart` at day granularity, so anything under 24 hours searches the whole of that day and says so on stderr.

Combining filters intersects them: `--source bbc.co.uk --concept ... --start-date ...` means all three conditions at once, while repeating one flag unions its own values.

## Events mode

`--events` asks the database for stories rather than articles. One event is one thing that happened, with every outlet that covered it clustered under it, so `article_count` is a **coverage figure**: how many indexed articles Event Registry attached to that story.

```json
{
  "position": 1,
  "uri": "eng-11875134",
  "title": "US says dozens of countries helped China dodge tariffs",
  "summary": "The White House accused more than forty countries of...",
  "date": "2026-07-28",
  "iso_date": null,
  "article_count": 2476,
  "sentiment": 0.49
}
```

- `title` and `summary` arrive from the API as language-keyed maps and are flattened to one string here — English where there is one, otherwise whatever language the event is in.
- `date` is `eventDate`, a **day with no time attached**, so `iso_date` is `null` by design. Minting a `T00:00:00Z` out of it would claim a precision the service did not report.
- `article_count` is the number worth quoting when the question is how widely a story was reported. It and `sentiment` are always present on an event row, `null` where the service gave no figure, unlike the article-row extras below.
- `total_results` sits beside `events` and counts matching events, not articles.

**`--sort size` is a trap worth naming.** It ranks by `article_count`, which sounds like "the biggest story" and is not: a keyword that appears incidentally in a heavily syndicated piece will out-rank the actual news. Sorting `tariffs` by `size` put a UK online-casino listicle first, with 2,476 articles attached, none of them about trade. `relevance` is the default here for that reason; if you do sort by `size`, read the titles before believing the ranking.

`--events` cannot be combined with `--lookup`, and `--sort size` is refused without `--events` (articles have no such sort key).

## Following one event with `--event`

`--events` finds events; `--event <uri>` follows one. Give it a `uri` from an `--events` row or an article row's `event_uri` and it returns that event's dossier alongside the articles that covered it — the drilldown the `event_uri` field exists for. It ignores every search condition (a passed filter warns on stderr); `--num` and `--page` size the article roster, `--sort` orders it (`relevance` here is Event Registry's `cosSim`, most-representative-coverage first — not the `rel` an article search uses), and `--body-len` sets how much of each article's text comes back, exactly as in an ordinary article search.

```bash
S=/app/skills/news-search/scripts/news_search.py

# Discover an event, then follow it:
python3 $S "bridge collapse" --engine newsapi --events --num 3
# ... take a uri from the output, then:
python3 $S --engine newsapi --event eng-11875134 --num 10 --sort date
```

The envelope adds an `event` dossier beside the usual `articles` list:

```json
{
  "event": {
    "uri": "eng-11875134",
    "title": "US says dozens of countries helped China dodge tariffs",
    "summary": "The White House accused more than forty countries of...",
    "date": "2026-07-28",
    "iso_date": null,
    "article_count": 2476,
    "sentiment": 0.49,
    "social_score": 812.5,
    "concepts": [{"uri": "http://en.wikipedia.org/wiki/Tariff", "label": "Tariff", "type": "wiki"}],
    "categories": [{"uri": "dmoz/Business", "label": "dmoz/Business"}],
    "location": "Washington, D.C."
  },
  "articles": [ "... the coverage roster, in the ordinary article shape ..." ],
  "total_results": 2476
}
```

- `date` is `eventDate`, a day with no time, so `iso_date` is `null` for the same reason it is on an events-mode row.
- `article_count` is the coverage figure; `total_results` beside `articles` is how many articles the roster could draw from, and `--num` / `--page` walk it.
- `social_score` appears when the service scored the event, and is absent otherwise; `sentiment` follows the same rule as elsewhere (English text only).
- `concepts` and `categories` are the top few Event Registry tagged the event with, each carrying the `uri` you can feed straight into `--concept` / `--category` for a wider search; `location` is the place name where there is one.
- The `articles` rows are the identical eight-field shape a normal `--engine newsapi` search returns, `--body-len -1` and all.

A `uri` with no event behind it — mistyped, or an event not in the index — returns an empty envelope (`status: no_results`, exit `3`) with a note on stderr, not an error: it reads as "no such event", not "the call broke".

`--event` cannot be combined with `--events` or `--lookup`: it is a third mode, not a filter on the other two.

## Row extras, and how far to trust them

On `--engine newsapi` an article row can carry four fields beyond the shared eight. Each appears only when the service supplied it.

- **`sentiment`** — a float from −1 to +1. Computed for **English only**; on any other language the field is absent. It is a machine score of the text's tone, not an editorial judgement and not a measure of whether the news is good or bad: a calm report of a disaster scores near zero. Useful in aggregate across many rows, misleading quoted from one.
- **`event_uri`** — the event this article belongs to. Follow it with `--event <uri>` (see below) to pull that event's dossier and the rest of its coverage. It is present on roughly half the rows and absent on the rest, so check for the key before following it.
- **`is_duplicate`** — present and `true` only when the row is a reprint of another indexed article (wire copy republished). Absent otherwise. Worth checking before reporting that six outlets covered something.
- **`authors`** — a list of bylines, where the outlet published them.

And two fields that are easy to over-read:

- **`snippet`** is `body` truncated to `--body-len` characters, 300 by default: the article's **opening**, not a summary of it. It stops mid-sentence and it does not know what the piece concluded. `--body-len -1` adds the whole text as a `body` row extra beside it, for the same one token.
- **`total_results`** counts the corpus your conditions matched, so it moves with every filter you add. It is a coverage indication, not a result count, and a large one alongside three rows means your `--num` was three.

Dropped from the row on purpose: `wgt`, `relevance` and `sim` are internal ranking and similarity scores with no documented scale, and `shares` came back as `{}` on every row observed.

## Not here

This skill searches; it does not follow a `link` (a web URL). It does follow an event `uri` with `--event`, which resolves to Event Registry's own indexed data rather than to a fetched page. Live extraction of a page, and anything that fetches a URL and returns its contents, belong to the sibling `page-read` skill, which reads any URL from any of the six search skills and is not news-only. Event Registry's `articleMapper` (URL → article URI) is out of scope for good: it returns `null` for every URL tested, including URLs Event Registry itself had just emitted, so there is no route from a bare URL back into the database. Article text for a row this skill found is `--body-len` on `--engine newsapi`; article text for anything else is `page-read`.
