#!/usr/bin/env python3
"""News Search: one wrapper for four SerpAPI news engines — Google News, Bing
News, DuckDuckGo News and Baidu News — and the NewsAPI.ai article database.

--engine selects which one runs. The first four are search engines: one call
buys one page of whatever their news vertical ranked, dated with a display
string and nothing more. The fifth is not a SERP at all but a queryable
database, with an exact date range, an outlet filter, sentiment and event
clustering — so all five are trimmed into the same eight-field article row and
only NewsAPI.ai's extras hang beside it.

No API key lives here. Requests go out through the container's OneCLI gateway
(HTTPS_PROXY), which appends the SerpAPI key as `api_key` for serpapi.com and
the NewsAPI.ai key as `apiKey` for eventregistry.org on the way past. Both
clients are therefore built with no key at all, and the agent never sees one.
"""

import argparse
import datetime
import hashlib
import io
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path

import requests
import serpapi

# Ensure UTF-8 output
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# The one SerpAPI client, with no api_key. The library sets `api_key=None` on
# every request and requests drops a None-valued parameter, so nothing goes out
# from here and the gateway's injection is unimpeded.
#
# session.verify has to be pointed at the gateway's CA by hand: the gateway
# terminates TLS with its own certificate and names that CA in SSL_CERT_FILE,
# which requests ignores. It reads REQUESTS_CA_BUNDLE and CURL_CA_BUNDLE only,
# neither of which the gateway sets, so it would fall back to certifi and fail
# verification on every proxied call. Proxies need no such help: requests picks
# HTTPS_PROXY up from the environment itself, token included.
CLIENT = serpapi.Client()
_CA_BUNDLE = os.getenv("SSL_CERT_FILE")
if _CA_BUNDLE:
    CLIENT.session.verify = _CA_BUNDLE

# One minute is the ceiling for a page of news: long enough that a slow SERP or
# a wide database query is not thrown away, short enough that a wedged request
# does not hold the agent's turn open.
REQUEST_TIMEOUT = 60

# Exit code for "the request worked but the engine had nothing usable". It is 3
# rather than 2 because argparse already owns 2 for command-line usage errors,
# and a caller must be able to tell a bad invocation from an empty result set.
NO_RESULTS_EXIT = 3

# What the gateway answers with when no vault secret matches the host it was
# asked to reach. Matched on the body rather than on the status, which has
# already changed once (401 today, 502 for a host it cannot resolve at all).
# Host-agnostic, so the same constant covers both serpapi.com and
# eventregistry.org.
GATEWAY_NO_CREDENTIAL = "credential_not_found"

# SerpAPI reports an empty SERP as an error ("Google News hasn't returned any
# results for this query.", and the same sentence for the other three) rather
# than as an empty result array. That is a search that found nothing, not a
# search that failed, so it is turned back into an empty payload and reported
# as no_results — otherwise every fruitless query would exit 1 with no
# envelope, and the difference between "nothing matched" and "the call broke"
# would be lost.
EMPTY_SERP_ERROR = re.compile(r"returned any results", re.IGNORECASE)

# The other error SerpAPI answers with, usually as a 503: the upstream engine
# was reachable but would not produce a usable page. The search never ran, so
# it stays a failure, but it is the one error here worth retrying.
TRANSIENT_SERP_ERROR = re.compile(r"couldn't get valid results", re.IGNORECASE)

# NewsAPI.ai is Event Registry's product name and eventregistry.org is the host
# the vault secret is keyed on; the two names are the same service throughout.
EVENTREGISTRY_BASE = "https://eventregistry.org/api/v1"

# Bing's `first` counts result *slots*, one-based, and a news page is ten of
# them: first=11 returned the second page's rows. `count` is not sent at all —
# a count=30 request came back with ten rows, so the parameter is decorative.
BING_PAGE_SLOTS = 10

# Baidu News is the one SerpAPI engine here that sizes its own page: rn=20
# returned exactly 20 rows against the default ten. 20 is also as far as it
# goes, whatever the documentation says — rn=25 still came back with 20 rows,
# and rn=30 and rn=50 both answered "Baidu News hasn't returned any results for
# this query." That empty SERP is indistinguishable from a subject nobody
# covered, so a --num above the real ceiling would silently turn a well-covered
# topic into no_results. Clamped here instead.
BAIDU_MAX_RESULTS = 20

# `pn` is a result offset, and it counts in tens whatever rn says — the value
# SerpAPI's own pagination links use (page 2 is pn=10, page 3 is pn=20).
#
# The two parameters are mutually exclusive: pn=10&rn=20 and pn=20&rn=20 both
# came back "Baidu News hasn't returned any results for this query." while
# pn=20 alone returned ten rows and rn=20 alone returned twenty. So a paged
# Baidu call is ten rows and --num trims; only an unpaged one can be widened.
BAIDU_PAGE_SLOTS = 10

# Event Registry's own python client asserts articlesCount <= 200; the server
# disagrees and errors above 100. Trust the server.
ER_MAX_ARTICLES = 100
ER_MAX_EVENTS = 50

# What --body-len defaults to, and the length `snippet` is held to whatever the
# caller asks for. Event Registry's own default is -1, the *entire* article body
# on every row: a 100-row answer of full texts for a field the envelope calls a
# snippet. So 300 is sent unless the caller says otherwise.
#
# Length is free at the API and costs only context: /api/v1/usage rose by
# exactly 1.0 token for a ten-row call at 300 (3,013 body characters) and by
# exactly 1.0 for the same call at -1 (228,452 characters).
ER_BODY_LEN = 300

# None of the SerpAPI engines here honours a result count except Baidu, so
# --num trims what came back. It caps what the agent has to read, not what the
# search costs.
DEFAULT_NUM = 10

# Cache lifetime in hours. One hour rather than social-search's day: this is
# news, and "the latest on X" an afternoon old is a wrong answer, not a cheap
# one. It also matches the free repeat window SerpAPI already gives byte-
# identical requests, so within the hour the cache is saving latency, and past
# it — and on newsapi, which has no such window at all — it saves a credit.
# --cache-ttl 0 forces a live call and still writes the result back.
DEFAULT_CACHE_TTL_HOURS = 1

# "3m", "7d", "w" — the one relative time filter, in the shape a person types
# it. The count is optional, so "w" is the past week. Units: s second,
# n minute, h hour, d day, w week, m month, y year.
PERIOD = re.compile(r"^(\d+)?([snhdwmy])$")

# The same units as hours, so one grammar can be mapped onto four engines that
# each express time differently. A month is 30 days and a year 365, which is
# what every engine's own "past month" bucket means.
PERIOD_HOURS = {"s": 1 / 3600, "n": 1 / 60, "h": 1, "d": 24, "w": 168,
                "m": 720, "y": 8760}

# The two engines that take fixed windows rather than a number, as
# (hours covered, the value they want, the name to print). Widest last, since
# _bucket() falls back to the final row when a request outruns the table.
# Bing's four `qft` intervals, and DuckDuckGo's `df`, whose month is 31 days
# rather than the 30 the grammar's "m" means.
BING_INTERVALS = ((1, "4", "past hour"), (24, "7", "past 24 hours"),
                  (168, "8", "past 7 days"), (720, "9", "past 30 days"))
DDG_WINDOWS = ((24, "d", "past day"), (168, "w", "past week"),
               (744, "m", "past month"))

# Only a stamp of this exact shape reaches `iso_date`. Google News and
# NewsAPI.ai both send one; bing, duckduckgo and baidu send display text like
# "22d", "23 days ago" or "昨天16:42", and guessing a timestamp out of those
# would put a fabricated date in a field callers are told to trust.
ISO_STAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$")

# Event Registry speaks ISO 639-3, not the two-letter codes every other engine
# here uses, and answers an unrecognised code with zero results and no error —
# indistinguishable from a genuine miss. Validated up front for that reason.
ER_LANG = re.compile(r"^[a-z]{3}$")


def redact(text):
    """Strip anything credential-shaped out of a message before it hits stderr.

    Two things can appear in a failure string: the gateway proxy URL, which
    carries the container's own access token (`aoc_...`) as basic-auth
    userinfo, and — if the gateway ever echoes a request line back — an
    injected key. Neither belongs in a log the user may see.

    Both injected parameter names are covered: the gateway appends `api_key`
    for serpapi.com and `apiKey` for eventregistry.org, and this script talks
    to both, so matching only the first would leave the NewsAPI.ai key in clear
    on the one path that can echo it.

    The token pattern allows punctuation on purpose: requests prints the whole
    proxy URL in its error strings, so a token containing `-`, `_` or `.` would
    otherwise have its tail survive into the message in clear.
    """
    text = re.sub(r"aoc_[\w.\-]+", "<redacted>", text)
    return re.sub(r"(api_key=|apiKey=)[^&\s'\"]+", r"\1<redacted>", text)


# Default value for every engine-specific flag. Argparse defaults are left as
# None so we can tell "user typed it" from "not supplied" and warn when a flag
# does not apply to the chosen engine; the real defaults are applied here.
# Filters that default to None are not sent at all, which is not the same as
# sending an empty one — --kl unset lets DuckDuckGo apply its own us-en.
DEFAULTS = {
    "num": DEFAULT_NUM,
    "page": 0,
    "period": None,
    "start_date": None,
    "end_date": None,
    "sort": "relevance",
    "gl": "sg",
    "hl": "en",
    # Bing rejects both `sg` and `en-SG` outright ("Unsupported `en-SG` Bing
    # market."), so the siblings' Singapore default would make every default
    # Bing call exit 1. en-US is the market that answers.
    "mkt": "en-US",
    "kl": None,
    "lang": "eng",
    "body_len": ER_BODY_LEN,
    "source": None,
    "concept": None,
    "category": None,
    "author": None,
    "events": False,
    "event": None,
    "lookup": None,
}

# argparse dest -> the flag spelling a user types, for warning messages.
CLI_NAME = {
    "num": "--num",
    "page": "--page",
    "period": "--period",
    "start_date": "--start-date",
    "end_date": "--end-date",
    "sort": "--sort",
    "gl": "--gl",
    "hl": "--hl",
    "mkt": "--mkt",
    "kl": "--kl",
    "lang": "--lang",
    "body_len": "--body-len",
    "source": "--source",
    "concept": "--concept",
    "category": "--category",
    "author": "--author",
    "events": "--events",
    "event": "--event",
    "lookup": "--lookup",
}

# Per-engine metadata: which flags apply, and the name every stderr line about
# that engine is built from. One label rather than five hand-written strings,
# with the result counted at the point of printing, is what stops the progress
# line and the exit code disagreeing.
#
# A flag is listed only where it was seen to work on the wire. The pointed
# omissions: `page` is absent from google and duckduckgo because neither news
# engine takes an offset (both return 30-100 rows in the one call anyway);
# `sort` is absent from google because SerpAPI refuses `so` alongside `q`
# ("`q` and `so` parameters can't be used together."), so a sort is
# unreachable for any query this skill can express; `period` is absent from
# baidu because baidu_news carries no date parameter at all.
ENGINES = {
    "google": {"flags": ("num", "period", "gl", "hl"), "label": "Google News"},
    "bing": {"flags": ("num", "page", "period", "sort", "mkt"),
             "label": "Bing News"},
    "duckduckgo": {"flags": ("num", "period", "kl"), "label": "DuckDuckGo News"},
    "baidu": {"flags": ("num", "page"), "label": "Baidu News"},
    "newsapi": {
        "flags": ("num", "page", "period", "start_date", "end_date", "sort",
                  "lang", "body_len", "source", "concept", "category", "author",
                  "events", "event", "lookup"),
        "label": "NewsAPI.ai",
    },
}

# Event Registry's two sort vocabularies are not the same one: `size` ranks by
# how many articles an event gathered and exists only on events. Asking for it
# on articles is an error, so the flag is refused before the call.
SORTS_ARTICLES = {"relevance": "rel", "date": "date", "social": "socialScore"}
SORTS_EVENTS = {"relevance": "rel", "date": "date", "social": "socialScore",
                "size": "size"}

# A third sort vocabulary: the articles *inside* one event rank by cosine
# similarity to the event's centroid by default (`cosSim`, "most representative
# coverage first"), which the article database has no equivalent for. So --event
# maps `relevance` to cosSim rather than to the `rel` SORTS_ARTICLES uses; `rel`
# is a sort key the getEvent endpoint would reject.
EVENT_ARTICLE_SORTS = {"relevance": "cosSim", "date": "date",
                       "social": "socialScore"}

# The four suggest endpoints, spelled out rather than derived from the flag:
# "category" pluralises to "Categories", so building the name by appending an
# "s" would send suggestCategorysFast and get a 404 for one of the four.
LOOKUP_ENDPOINTS = {
    "source": "suggestSourcesFast",
    "concept": "suggestConceptsFast",
    "category": "suggestCategoriesFast",
    "author": "suggestAuthorsFast",
}


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Search news via SerpAPI and NewsAPI.ai. --engine picks Google "
            "News, Bing News, DuckDuckGo News or Baidu News (four news search "
            "engines, one page per call) or newsapi (the NewsAPI.ai article "
            "database, with outlet, concept, category and exact date filters, "
            "event clustering and sentiment)."
        ),
        epilog=(
            "Flags apply per engine: --num to all; --page to bing, baidu and "
            "newsapi; --period to google, bing, duckduckgo and newsapi; "
            "--sort to bing and newsapi; --gl and --hl to google; --mkt to "
            "bing; --kl to duckduckgo; --start-date, --end-date, --lang, "
            "--body-len, --source, --concept, --category, --events and "
            "--lookup to newsapi. Passing a flag the chosen engine cannot use "
            "prints a warning on stderr and is otherwise ignored."
        ),
    )
    parser.add_argument(
        "query", nargs="?", default=None,
        help="Search query string. Optional on --engine newsapi when at least "
             "one of --source / --concept / --category is given",
    )
    parser.add_argument(
        "--engine", default="google",
        choices=["google", "bing", "duckduckgo", "baidu", "newsapi"],
        help="Engine to query (default: google)",
    )
    parser.add_argument(
        "--cache-ttl", type=float, default=DEFAULT_CACHE_TTL_HOURS,
        help=f"Hours a cached identical call stays usable (default: "
             f"{DEFAULT_CACHE_TTL_HOURS}; 0 forces a live call)",
    )
    parser.add_argument(
        "--num", type=int, default=None,
        help=f"Number of articles to keep (default: {DEFAULT_NUM}); trims on "
             "google, bing and duckduckgo, and is fetched server-side on "
             "baidu and newsapi",
    )
    parser.add_argument(
        "--page", type=int, default=None,
        help="[bing, baidu, newsapi] Result page, 0-based (default: 0). Each "
             "page is a separate call and a separate credit",
    )
    parser.add_argument(
        "--period", default=None,
        help="[google, bing, duckduckgo, newsapi] Only articles from the last "
             "<count><unit>, e.g. 7d, 3m, 2y, or a bare unit for one of them "
             "(w = the past week). Units: s second, n minute, h hour, d day, "
             "w week, m month, y year. Exact on google and newsapi; bing and "
             "duckduckgo round it to their own buckets and say so on stderr. "
             "Cannot be combined with --start-date / --end-date",
    )
    parser.add_argument(
        "--start-date", default=None,
        help="[newsapi] Earliest publication date, YYYYMMDD, inclusive. "
             "Cannot be combined with --period",
    )
    parser.add_argument(
        "--end-date", default=None,
        help="[newsapi] Latest publication date, YYYYMMDD, inclusive. Cannot "
             "be combined with --period",
    )
    parser.add_argument(
        "--sort", default=None,
        choices=["relevance", "date", "social", "size"],
        help="[bing, newsapi] Result order (default: relevance). bing takes "
             "relevance and date only; size ranks events by article count and "
             "needs --events",
    )
    parser.add_argument(
        "--gl", default=None,
        help="[google] Country code (default: sg)",
    )
    parser.add_argument(
        "--hl", default=None,
        help="[google] Language code (default: en)",
    )
    parser.add_argument(
        "--mkt", default=None,
        help="[bing] Market, <language>-<COUNTRY> (default: en-US). Bing "
             "rejects markets it does not publish, including en-SG",
    )
    parser.add_argument(
        "--kl", default=None,
        help="[duckduckgo] Region, <region>-<language> such as uk-en or "
             "de-de (default: DuckDuckGo's own us-en)",
    )
    parser.add_argument(
        "--lang", default=None,
        help="[newsapi] Article language as an ISO 639-3 code, e.g. eng, zho, "
             "deu (default: eng)",
    )
    parser.add_argument(
        "--body-len", type=int, default=None,
        help="[newsapi] Characters of article text to fetch (default: "
             f"{ER_BODY_LEN}), or -1 for the whole article, which lands in a "
             "`body` row extra rather than in `snippet`. A call costs one "
             "token at any length",
    )
    parser.add_argument(
        "--source", action="append", default=None,
        help="[newsapi] Outlet domain such as nytimes.com. Repeatable, also "
             "accepts a comma-separated list; several are OR'd. Find them "
             "with --lookup source",
    )
    parser.add_argument(
        "--concept", action="append", default=None,
        help="[newsapi] Full Wikipedia URI such as "
             "http://en.wikipedia.org/wiki/Tariff. Repeatable; several are "
             "OR'd. Find them with --lookup concept",
    )
    parser.add_argument(
        "--category", action="append", default=None,
        help="[newsapi] Category URI such as dmoz/Business or "
             "news/Business. Repeatable; several are OR'd. Find them with "
             "--lookup category",
    )
    parser.add_argument(
        "--author", action="append", default=None,
        help="[newsapi] Author URI such as jane_smith@nytimes.com — a byline, "
             "not a free-text name. Repeatable; several are OR'd. Find them "
             "with --lookup author",
    )
    parser.add_argument(
        "--events", action="store_true", default=None,
        help="[newsapi] Return clustered events (one story covered by many "
             "outlets) instead of articles",
    )
    parser.add_argument(
        "--event", default=None, metavar="URI",
        help="[newsapi] Follow one event by its uri (from --events output or "
             "an article row's event_uri): return the event dossier plus the "
             "articles that covered it. Ignores the search filters",
    )
    parser.add_argument(
        "--lookup", default=None,
        choices=["source", "concept", "category", "author"],
        help="[newsapi] Look the query up as a prefix and return matching "
             "URIs, for use with --source / --concept / --category / "
             "--author. Searches nothing else",
    )
    args = parser.parse_args()

    # Validated here rather than at the API. Event Registry answers HTTP 200
    # for its own errors and answers several bad inputs with an empty result
    # set and no error at all, so a typo that reached the wire would look like
    # a story nobody covered — after it had cost a token. parser.error exits 2,
    # which is where a caller looks for "you typed it wrong".
    # Normalise the repeatable filters once, so the "is there anything to
    # search for?" test below and the body that goes on the wire agree: an
    # empty --source is a filter argparse counts and Event Registry never sees,
    # which would turn a filter-only search into an unrestricted sweep of the
    # whole corpus. --source also splits on commas; --concept, --category and
    # --author do not, because a Wikipedia URI can contain one
    # (.../wiki/Washington,_D.C.) and so can a byline (smith,_jr@ft.com).
    args.source = _csv(args.source) or None
    args.concept = [value for value in args.concept or [] if value.strip()] or None
    args.category = [value for value in args.category or [] if value.strip()] or None
    args.author = [value for value in args.author or [] if value.strip()] or None

    # --lookup first: it ignores --source / --concept / --category / --author,
    # so the general "give me a query or a filter" message below would answer a
    # forgotten prefix by naming the four flags that cannot supply one.
    if args.event is not None:
        # A drilldown, not a search: it takes one event uri and ignores every
        # search condition, so it is mutually exclusive with the two other
        # newsapi modes rather than a filter on them.
        if args.events:
            parser.error("--event cannot be combined with --events")
        if args.lookup is not None:
            parser.error("--event cannot be combined with --lookup")
    if args.lookup is not None:
        if not args.query:
            parser.error(f"--lookup {args.lookup} needs a query to use as the prefix")
        if args.events:
            parser.error("--lookup cannot be combined with --events")
    # --event stands in for the query, but only on newsapi where it is honoured:
    # on any other engine it is an ignored flag, so a query is still required.
    event_active = args.engine == "newsapi" and args.event is not None
    if not args.query and not event_active:
        if args.engine != "newsapi":
            parser.error(f"query is required for --engine {args.engine}")
        if not (args.source or args.concept or args.category or args.author):
            parser.error(
                "--engine newsapi needs a query, or at least one of --source "
                "/ --concept / --category / --author"
            )
    if args.period is not None:
        if not PERIOD.match(args.period):
            parser.error(
                f"--period {args.period!r} is not <count><unit>, e.g. 7d, 3m, "
                "2y or w (units: s n h d w m y)"
            )
        if args.start_date or args.end_date:
            parser.error("--period cannot be combined with --start-date / --end-date")
    for dest in ("start_date", "end_date"):
        value = getattr(args, dest)
        if value is None:
            continue
        try:
            datetime.datetime.strptime(value, "%Y%m%d")
        except ValueError:
            parser.error(f"{CLI_NAME[dest]} {value!r} is not a YYYYMMDD date")
    if args.start_date and args.end_date and args.start_date > args.end_date:
        # An inverted range is not an error to Event Registry, just a window
        # nothing can fall in — an empty answer that reads as "no coverage".
        parser.error(
            f"--start-date {args.start_date} is later than --end-date {args.end_date}"
        )
    if args.sort == "size" and not args.events:
        parser.error("--sort size is only valid with --events")
    if args.lang is not None and not ER_LANG.match(args.lang):
        parser.error(
            f"--lang {args.lang!r} is not an ISO 639-3 code (three letters), "
            "e.g. eng, deu, zho"
        )
    if args.body_len is not None and (args.body_len == 0 or args.body_len < -1):
        # Both measured. articleBodyLen=0 drops the `body` key from the wire
        # response entirely, so `snippet` would be null on every row with
        # nothing saying why; and -2 returned the whole article exactly as -1
        # does, so anything below -1 is refused rather than silently aliased to
        # the one spelling documented.
        parser.error(
            f"--body-len {args.body_len} is not valid; use 1 or greater, or "
            "-1 for the whole article"
        )
    if args.cache_ttl < 0:
        parser.error("--cache-ttl must be 0 or greater.")
    if args.kl is not None and "-" not in args.kl:
        # Refused rather than noted: SerpAPI does not pass a half-pair through
        # to DuckDuckGo, it answers "Unsupported `sg` region - kl parameter."
        # and the run dies at exit 1 after the request has gone out. Say so
        # before the call, in the place a caller looks for a typo.
        parser.error(
            f"--kl {args.kl!r} is not a <region>-<language> pair; DuckDuckGo "
            f"has no bare country codes (try {args.kl}-en)"
        )
    for value in args.concept or []:
        if not value.startswith(("http://", "https://")):
            parser.error(
                f"--concept {value!r} is not a full Wikipedia URI, e.g. "
                "http://en.wikipedia.org/wiki/Apple_Inc."
            )
    for value in args.author or []:
        # An Event Registry author URI is a byline bound to the outlet that
        # published it, `name@domain`. A bare "Jane Smith" is not one, and
        # Event Registry answers it with an empty set rather than an error —
        # indistinguishable from a journalist who wrote nothing. Refused here,
        # pointing at the lookup that turns a name into the URI.
        if "@" not in value:
            parser.error(
                f"--author {value!r} is not an Event Registry author URI, "
                "which is a byline plus its outlet (jane_smith@nytimes.com). "
                f"Find it with: --lookup author {value!r}"
            )
    return args


def resolve_options(args):
    """Warn about flags the chosen engine ignores, then fill in defaults."""
    allowed = set(ENGINES[args.engine]["flags"])
    for dest in sorted(DEFAULTS):
        if getattr(args, dest) is not None and dest not in allowed:
            print(
                f"Warning: {CLI_NAME[dest]} does not apply to --engine "
                f"{args.engine}; ignoring it.",
                file=sys.stderr,
            )
    return {
        dest: (DEFAULTS[dest] if getattr(args, dest) is None else getattr(args, dest))
        for dest in DEFAULTS
    }


def period_hours(value):
    """--period as a number of hours. The one grammar, four engines' units."""
    count, unit = PERIOD.match(value).groups()
    return int(count or 1) * PERIOD_HOURS[unit]


def google_when(value):
    """--period as Google News's own `when:` operator, appended to the query.

    Google News takes h, d, m and y and nothing else. A week is exact as a
    multiple of days, so it is converted rather than rounded. Seconds and
    minutes have no representation and are widened to the hour: Google
    silently ignores a `when:` it cannot parse (it is its own operator, not a
    SerpAPI parameter), so passing "when:30n" through would return an
    unfiltered SERP that looked filtered.
    """
    count, unit = PERIOD.match(value).groups()
    number = int(count or 1)
    if unit in ("h", "d", "m", "y"):
        return f"when:{number}{unit}"
    if unit == "w":
        return f"when:{number * 7}d"
    print(
        f"Note: --period {value} rounds up to Google News's 1-hour minimum; "
        "results may be older than asked.",
        file=sys.stderr,
    )
    return "when:1h"


def _bucket(value, engine, table, overflow):
    """--period as one of an engine's fixed windows.

    Bing and DuckDuckGo each offer a handful of windows and no arbitrary one,
    so a request is widened to the smallest bucket that covers it — never
    narrowed, which would hide articles the caller asked for. A request past
    the widest bucket is the exception: it has nowhere to widen to, so it
    narrows, and gets its own wording.

    Clamped here rather than left to the engine, because neither validates the
    parameter: Bing answered qft=interval="99" with twelve unfiltered rows and
    no error, so a bad bucket is invisible on the wire and this note is the
    only signal a caller ever gets.
    """
    hours = period_hours(value)
    for limit, bucket, name in table:
        if hours <= limit:
            if hours != limit:
                print(
                    f"Note: --period {value} rounds up to {engine}'s {name} "
                    "bucket; results may be older than asked.",
                    file=sys.stderr,
                )
            return bucket
    print(f"Note: --period {value} exceeds {engine}'s {overflow}.", file=sys.stderr)
    return table[-1][1]


def bing_qft(period, sort):
    """--period and --sort date as Bing's `qft` clause string, or "".

    Both clauses go in one qft joined by a space — Bing's own separator is a
    "+", which is a URL-encoded space, and requests does that encoding.
    """
    clauses = []
    if period:
        interval = _bucket(period, "Bing", BING_INTERVALS,
                           "30-day maximum; searching the last 30 days instead")
        clauses.append(f'interval="{interval}"')
    if sort == "date":
        clauses.append('sortbydate="1"')
    elif sort != "relevance":
        # Bing has no equivalent of `social` or `size`, and --sort is in bing's
        # flags for the sake of `date`, so resolve_options() cannot catch this
        # one. Without the warning the request is byte-identical to a relevance
        # search and the caller reads relevance-ranked rows as "most shared".
        print(
            f"Warning: --sort {sort} does not apply to --engine bing; ignoring it.",
            file=sys.stderr,
        )
    return " ".join(clauses)


def ddg_df(value):
    """--period as DuckDuckGo's `df` bucket: day, week or month.

    Same widening rule as Bing, and the same reason for doing it here: df is
    the only granularity on offer.
    """
    return _bucket(value, "DuckDuckGo", DDG_WINDOWS,
                   "past-month maximum; searching the last month instead")


def er_date_start(value):
    """--period as Event Registry's `dateStart`, a plain YYYY-MM-DD.

    The database indexes a publication date, not a timestamp, so any window
    shorter than a day searches the whole of that day. That is a widening, and
    the only one on this engine, so it is announced.
    """
    hours = period_hours(value)
    start = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=hours)
    stamp = start.strftime("%Y-%m-%d")
    if hours < 24:
        print(
            f"Note: --period {value} rounds up to NewsAPI.ai's day "
            f"granularity; searching from {stamp}.",
            file=sys.stderr,
        )
    return stamp


def _csv(values):
    """Repeatable flag values, with each one also split on commas."""
    out = []
    for value in values or []:
        out.extend(part.strip() for part in value.split(",") if part.strip())
    return out


def build_params(engine, query, opts):
    """Build the SerpAPI query string for the chosen engine.

    No api_key: the gateway appends it. Sending one here would be overwritten
    at best and would put a credential in the container at worst.
    """
    if engine == "google":
        # Google News has no date parameter. `when:` is a query operator, so
        # the filter rides in `q` — and `so`, the sort parameter, is refused
        # outright alongside a `q`, which is why --sort is not offered here.
        if opts["period"]:
            query = f"{query} {google_when(opts['period'])}"
        return {"engine": "google_news", "q": query, "gl": opts["gl"], "hl": opts["hl"]}

    if engine == "bing":
        params = {"engine": "bing_news", "q": query, "mkt": opts["mkt"]}
        if opts["page"]:
            params["first"] = opts["page"] * BING_PAGE_SLOTS + 1
        qft = bing_qft(opts["period"], opts["sort"])
        if qft:
            params["qft"] = qft
        # `count` is deliberately absent: a count=30 request returned ten rows,
        # so sending it would only make --num look like it bought more.
        return params

    if engine == "duckduckgo":
        params = {"engine": "duckduckgo_news", "q": query}
        if opts["kl"]:
            # Already known to be a <region>-<language> pair: a bare country
            # code is refused at parse time, because SerpAPI rejects one
            # outright rather than passing it on.
            params["kl"] = opts["kl"]
        if opts["period"]:
            params["df"] = ddg_df(opts["period"])
        # `start` is not offered: one call already returns 30-65 rows, which is
        # more than --num ever keeps.
        return params

    # baidu — note this is engine=baidu_news, a different engine from the
    # engine=baidu that web-search, video-search and forum-search all send. The
    # request is therefore never byte-identical to theirs and never joins their
    # free one-hour repeat cache: a Baidu news call here is always a credit.
    params = {"engine": "baidu_news", "q": query}
    if opts["page"]:
        # pn only, never pn with rn — see BAIDU_PAGE_SLOTS. A page past the
        # first is therefore ten rows, whatever --num asked for.
        params["pn"] = opts["page"] * BAIDU_PAGE_SLOTS
        if opts["num"] > BAIDU_PAGE_SLOTS:
            print(
                f"Note: --num {opts['num']} cannot be combined with --page on "
                f"Baidu News; a paged request holds {BAIDU_PAGE_SLOTS} results.",
                file=sys.stderr,
            )
    else:
        per_page = opts["num"]
        if per_page > BAIDU_MAX_RESULTS:
            print(
                f"Note: --num {per_page} exceeds Baidu News's ceiling of "
                f"{BAIDU_MAX_RESULTS} per request; requesting {BAIDU_MAX_RESULTS}.",
                file=sys.stderr,
            )
            per_page = BAIDU_MAX_RESULTS
        params["rn"] = per_page
    # rtt is never sent: rtt=4 (sort by time) stalled for twelve seconds and
    # came back "Baidu News hasn't returned any results for this query." with pn
    # and rn each proven fine on their own, so there is no working time sort to
    # expose.
    return params


def _er_day(yyyymmdd):
    """YYYYMMDD from the command line as the YYYY-MM-DD Event Registry wants."""
    return f"{yyyymmdd[:4]}-{yyyymmdd[4:6]}-{yyyymmdd[6:]}"


def build_body(query, opts):
    """Build the Event Registry POST as (url, body).

    No apiKey: the gateway appends it as a query parameter, so the body it
    signs is the one written here.

    Every list-valued condition sends its `...Oper` explicitly. Event Registry
    defaults conceptOper and keywordOper to "and", which turns two outlets or
    two concepts into a demand that both appear — a silent near-empty answer
    rather than the union a repeated flag reads as.
    """
    if opts["lookup"]:
        # The suggest endpoints take a prefix and nothing else; no search
        # condition applies to them.
        body = {"prefix": query, "page": opts["page"] + 1, "count": opts["num"]}
        if opts["lookup"] == "concept":
            body["lang"] = "eng"
            body["conceptLang"] = "eng"
        return f"{EVENTREGISTRY_BASE}/{LOOKUP_ENDPOINTS[opts['lookup']]}", body

    if opts["event"]:
        # A single-event drilldown: one event uri, the dossier plus the article
        # roster that covered it. Every search condition is ignored (main() warns
        # when one was passed), so this returns before the cond block below.
        count = opts["num"]
        if count > ER_MAX_ARTICLES:
            print(
                f"Note: --num {count} exceeds NewsAPI.ai's ceiling of "
                f"{ER_MAX_ARTICLES} articles per event; requesting {ER_MAX_ARTICLES}.",
                file=sys.stderr,
            )
            count = ER_MAX_ARTICLES
        body = {
            "eventUri": opts["event"],
            # info is the dossier, articles the coverage roster: one call, both.
            "resultType": ["info", "articles"],
            # summary, concepts, categories and location are on by default;
            # socialScore is the one dossier field that must be asked for.
            "includeEventSummary": True,
            "includeEventSocialScore": True,
            "articlesPage": opts["page"] + 1,
            "articlesCount": count,
            "articlesSortBy": EVENT_ARTICLE_SORTS[opts["sort"]],
            "articleBodyLen": opts["body_len"],
        }
        return f"{EVENTREGISTRY_BASE}/event/getEvent", body

    cond = {}
    if query:
        cond["keyword"] = query
    sources = _csv(opts["source"])
    if sources:
        # An array even for one entry: a comma-joined string is matched as a
        # single source URI, which no outlet has, and quietly narrows the
        # answer instead of failing.
        cond["sourceUri"] = sources
        cond["sourceOper"] = "or"
    if opts["concept"]:
        cond["conceptUri"] = list(opts["concept"])
        cond["conceptOper"] = "or"
    if opts["category"]:
        cond["categoryUri"] = list(opts["category"])
        cond["categoryOper"] = "or"
    if opts["author"]:
        cond["authorUri"] = list(opts["author"])
        # authorOper is sent for the same reason its three siblings are: Event
        # Registry defaults the list operators to "and", which would demand two
        # journalists share a byline rather than return either one's work. It is
        # the one key here not confirmed against a live response — a single
        # --author, which is the ordinary case, does not depend on it either way.
        cond["authorOper"] = "or"
    cond["lang"] = opts["lang"]
    if opts["period"]:
        cond["dateStart"] = er_date_start(opts["period"])
    if opts["start_date"]:
        cond["dateStart"] = _er_day(opts["start_date"])
    if opts["end_date"]:
        cond["dateEnd"] = _er_day(opts["end_date"])

    if opts["events"]:
        count = opts["num"]
        if count > ER_MAX_EVENTS:
            print(
                f"Note: --num {count} exceeds NewsAPI.ai's ceiling of "
                f"{ER_MAX_EVENTS} events per request; requesting {ER_MAX_EVENTS}.",
                file=sys.stderr,
            )
            count = ER_MAX_EVENTS
        if opts["body_len"] != ER_BODY_LEN:
            print(
                "Warning: --body-len does not apply to --events; ignoring it. "
                "Events carry a summary, not article bodies. Drop --events to "
                "read the articles themselves.",
                file=sys.stderr,
            )
        body = {
            **cond,
            "resultType": "events",
            "eventsPage": opts["page"] + 1,
            "eventsCount": count,
            "eventsSortBy": SORTS_EVENTS[opts["sort"]],
            "includeEventSummary": True,
        }
        return f"{EVENTREGISTRY_BASE}/event/getEvents", body

    count = opts["num"]
    if count > ER_MAX_ARTICLES:
        print(
            f"Note: --num {count} exceeds NewsAPI.ai's ceiling of "
            f"{ER_MAX_ARTICLES} articles per request; requesting {ER_MAX_ARTICLES}.",
            file=sys.stderr,
        )
        count = ER_MAX_ARTICLES
    body = {
        **cond,
        "resultType": "articles",
        # Event Registry pages from 1; every other engine here from 0.
        "articlesPage": opts["page"] + 1,
        "articlesCount": count,
        "articlesSortBy": SORTS_ARTICLES[opts["sort"]],
        "articleBodyLen": opts["body_len"],
    }
    return f"{EVENTREGISTRY_BASE}/article/getArticles", body


def _serpapi_error(payload):
    """Classify SerpAPI's `error` string. Returns (data, error_message).

    Two of its errors are not failures of ours to report as such: a missing
    gateway credential is an operator problem with a known fix, and an empty
    SERP is a result. Everything else is passed through.
    """
    message = str(payload["error"])
    if payload["error"] == GATEWAY_NO_CREDENTIAL:
        host = payload.get("hostname", "serpapi.com")
        return None, (
            f"the OneCLI gateway has no credential for {host}. "
            "Ask an operator to add the SerpAPI key to the vault with "
            "host pattern serpapi.com and query-parameter injection "
            "(param name api_key)"
        )
    if EMPTY_SERP_ERROR.search(message):
        return {}, None
    if TRANSIENT_SERP_ERROR.search(message):
        return None, (
            f"{redact(message)} This is the engine failing, not an empty "
            "result — retry in a minute, or try another engine"
        )
    return None, f"SerpAPI returned an error: {redact(message)}"


def fetch(params, timeout=REQUEST_TIMEOUT):
    """GET the SerpAPI endpoint through the gateway and return the parsed body.

    Returns (data, error_message). Exactly one is None. Error bodies are parsed
    rather than discarded: SerpAPI reports a bad market, a bad engine or a
    spent quota as a 4xx whose JSON explains what went wrong, and the gateway
    reports a missing vault secret as a body naming the host it could not
    credential.

    Client.request, not the friendlier Client.search: search() hands back a
    SerpResults for a JSON body and raw text for anything else, which would
    collapse the two response-shape failures the exit-code table lists as
    distinct exit-1 messages.
    """
    try:
        body = CLIENT.request("GET", "/search", params, timeout=timeout).content
    except serpapi.HTTPError as exc:
        # HTTPConnectionError subclasses this one and carries no response, so
        # the guard is not optional. TLS failures arrive that way too, since
        # requests' SSLError is a ConnectionError.
        if exc.response is None:
            return None, redact(str(exc))
        try:
            payload = exc.response.json()
        except ValueError:
            payload = None
        if isinstance(payload, dict) and payload.get("error"):
            return _serpapi_error(payload)
        # No SerpAPI error body, so this status came from the gateway or a
        # proxy in front of it rather than from the search: SerpAPI reports its
        # own key and quota failures as JSON, which the branch above catches.
        route = exc.status_code in (401, 403, 407, 429)
        return None, f"{exc.status_code} {exc.response.reason}" + (
            ". This is the route out, not the query: retry once, then ask an "
            "operator to check the OneCLI gateway and the SerpAPI vault secret"
            if route else ""
        )
    except AttributeError:
        # serpapi's own HTTPError constructor calls .get on the decoded error
        # body and guards only a decode failure, so a body that is valid JSON
        # but not an object dies in there before any clause here sees it.
        return None, "SerpAPI returned an error in an unexpected shape"
    except serpapi.TimeoutError:
        # Module-qualified: the name shadows the builtin, and it is not an
        # HTTPError, so it needs its own clause.
        return None, f"no response within {timeout}s; retry, or try another engine"
    except OSError as exc:
        # Everything else requests can raise subclasses OSError, including the
        # bare one it raises when session.verify names a path that is not there.
        return None, redact(str(exc))

    try:
        # Lenient decode: a single bad byte in a snippet must not throw away a
        # search already paid for.
        payload = json.loads(body.decode("utf-8", errors="replace"))
    except ValueError:
        return None, "SerpAPI returned a non-JSON response"
    if not isinstance(payload, dict):
        return None, "SerpAPI returned an unexpected JSON shape (expected an object)"
    # SerpAPI also reports quota, key, and unsupported-parameter problems in an
    # "error" field with HTTP 200, so a 2xx body still has to be checked.
    if payload.get("error"):
        return _serpapi_error(payload)
    return payload, None


def fetch_eventregistry(url, body, timeout=REQUEST_TIMEOUT):
    """POST the Event Registry endpoint and return the parsed body.

    Same contract as fetch(): (data, error_message), exactly one None, so
    main() has one shape for both backends.

    requests direct rather than the serpapi client, because this is a JSON POST
    to a different host — and verify has to name the gateway CA for the same
    reason CLIENT.session.verify does, since requests reads REQUESTS_CA_BUNDLE
    and CURL_CA_BUNDLE but not the SSL_CERT_FILE the gateway sets.

    Every check below runs regardless of status. Event Registry answers HTTP
    200 for its own errors — a bad sort key, an unknown parameter, an
    unparseable date — so branching on the status would let all of them through
    as data. The 401 is the mirror image: it arrives as a plain sentence of
    text, not JSON, which is why the decode is guarded rather than assumed.
    """
    try:
        resp = requests.post(url, json=body, timeout=timeout, verify=_CA_BUNDLE or True)
    except requests.Timeout:
        # Before OSError: RequestException subclasses OSError, so the generic
        # clause would swallow this one and lose the retry advice.
        return None, f"no response within {timeout}s; retry, or try another engine"
    except OSError as exc:
        return None, redact(str(exc))

    if GATEWAY_NO_CREDENTIAL in resp.text:
        # Checked on the text before any decode: the gateway's refusal is not
        # Event Registry's JSON and need not be JSON at all.
        return None, (
            "the OneCLI gateway has no credential for eventregistry.org. "
            "Ask an operator to add the NewsAPI.ai key to the vault with "
            "host pattern eventregistry.org and query-parameter injection "
            "(param name apiKey)"
        )
    try:
        payload = resp.json()
    except ValueError:
        return None, (
            f"NewsAPI.ai returned a non-JSON response (HTTP {resp.status_code}): "
            f"{redact(resp.text[:200])}"
        )
    if isinstance(payload, dict):
        if payload.get("error"):
            return None, f"NewsAPI.ai returned an error: {redact(str(payload['error']))}"
        return payload, None
    if isinstance(payload, list):
        # The three suggest*Fast endpoints answer with a bare array at the top
        # level, so an "expected an object" guard would reject every --lookup.
        return payload, None
    return None, "NewsAPI.ai returned an unexpected JSON shape (expected an object or an array)"


# --- Cache ------------------------------------------------------------------


def cache_dir():
    """The operator-mounted shared cache when there is one, else the group's own.

    `social-cache` is the historical name of the mount, not a statement about
    what may live in it: it is on by default for every group (SOCIAL_CACHE_DIR),
    so sharing costs nothing to set up and a search another group already paid
    for is free here. page-read keeps its own subdirectory of it for the same
    reason.
    """
    shared = Path("/workspace/shared/social-cache")
    if shared.is_dir():
        return shared / "news-search"
    return Path("/workspace/agent/.news-search")


def cache_key(engine, request):
    """Keyed on the request that goes on the wire, never on the flags that built
    it. Two invocations spelled differently can produce the same call, and on
    newsapi --period has already become an absolute date range by this point —
    so a key built from the flags would serve yesterday's window to today's
    `--period 1d`."""
    material = engine.encode() + b"\0" + json.dumps(request, sort_keys=True, default=str).encode()
    return hashlib.sha256(material).hexdigest()[:16] + ".json"


def read_cache(path, ttl_hours):
    if ttl_hours <= 0:
        return None
    try:
        age = time.time() - path.stat().st_mtime
    except OSError:
        return None
    if age >= ttl_hours * 3600:
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        # A truncated or unreadable cache file is a miss, not a failure: the
        # live call below overwrites it.
        return None


def write_cache(path, payload):
    """Atomic: groups share the directory, so a half-written file must never be
    visible under its final name."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handle, tmp_name = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
        with os.fdopen(handle, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, default=str)
        Path(tmp_name).replace(path)
    except OSError as exc:
        print(f"Warning: could not write cache {path}: {exc}", file=sys.stderr)


# --- Extraction -------------------------------------------------------------


def _obj(value):
    """A nested object, or an empty one when the payload holds something else.

    Every nested read below goes through this or _rows(). The response is
    another service's JSON, so a field arriving with the wrong type has to end
    as one field being null, never as a traceback in place of the envelope.
    """
    return value if isinstance(value, dict) else {}


def _seq(value):
    """A nested array, or an empty one. The list-shaped half of _obj()."""
    return value if isinstance(value, list) else []


def _rows(data, key):
    """An engine's result array, with anything that is not an object dropped."""
    return [item for item in _seq(data.get(key)) if isinstance(item, dict)]


def _iso(value):
    """A UTC timestamp where the engine plainly sent one, else None.

    The only thing that ever populates `iso_date`. Three of the five engines
    date an article with display text ("22d", "23 days ago", "昨天16:42"); a
    lenient parse of those would put a made-up timestamp in the one field
    callers are told they may compute on.
    """
    return value if isinstance(value, str) and ISO_STAMP.match(value) else None


def _int(value):
    """A count where it is genuinely an integer, else None.

    isinstance(True, int) is True in Python, so the bool guard is not
    decorative: a flag arriving where a total belongs would otherwise be
    reported as a corpus of one.
    """
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _num(value):
    """A score where it is genuinely a number, else None. _int's float sibling.

    Same bool guard, same reason: isinstance(True, float) is False but
    isinstance(True, int) is True, so a flag arriving where a sentiment belongs
    would otherwise be reported as a score of 1.
    """
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _label(value):
    """Event Registry's language-keyed text as one string.

    Titles, summaries and concept labels arrive as {"eng": "..."} maps, not
    strings, and a plain .get() would put that dict in the envelope where a
    headline belongs. English first, then whatever single language the row
    happens to be in, so a --lang zho search still gets a readable title.
    """
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        text = value.get("eng")
        if isinstance(text, str):
            return text
        for item in value.values():
            if isinstance(item, str):
                return item
    return None


def _queries(items, key):
    """Pull refinement query strings out, deduplicated, order kept.

    `items` comes from _rows(), so every entry is an object.
    """
    out = []
    seen = set()
    for item in items:
        text = item.get(key)
        # isinstance, because a label is a query string and `seen` is a set: an
        # array or an object arriving in that slot is unhashable, not a query.
        if isinstance(text, str) and text and text not in seen:
            seen.add(text)
            out.append({"query": text})
    return out


def _article(position, title, link, source, snippet, date, iso_date, thumbnail):
    """One row of the shared article shape all five engines are trimmed into.

    `date` stays the string the engine sent — display text on four of them
    ("22d", "23 days ago", "昨天16:42", "08/14/2026, 08:39 AM, +0000 UTC"), an
    ISO stamp on NewsAPI.ai alone. Anything to compute on is in `iso_date`,
    and only where the engine actually supplied one; every other field is null
    where it did not.
    """
    return {
        "position": position,
        "title": title,
        "link": link,
        "source": source,
        "snippet": snippet,
        "date": date,
        "iso_date": iso_date,
        "thumbnail": thumbnail,
    }


def _simple(item, position=None):
    """One row from an engine that needs no interpretation.

    Bing, DuckDuckGo and Baidu all publish title, link, source, snippet, date
    and thumbnail under exactly those names, and none of the three carries a
    timestamp anywhere in the payload — so the four call sites differ only in
    which array they read, and `iso_date` is null on all of them.
    """
    return _article(
        position, item.get("title"), item.get("link"), item.get("source"),
        item.get("snippet"), item.get("date"), None, item.get("thumbnail"),
    )


def _flatten(articles, seen, row):
    """Append a row, dropping one whose link has already been emitted.

    Google and Bing both return the same article twice — once on its own and
    once inside a cluster of related coverage — so flattening the clusters into
    the article list doubles rows unless they are deduplicated here.

    `position` is stamped at append time rather than taken from the engine:
    Google restarts its numbering inside every cluster, Bing has none at all,
    and Baidu restarts on every page, so an engine-supplied position would not
    index the array it sits in.
    """
    link = row.get("link")
    if isinstance(link, str):
        if link in seen:
            return
        seen.add(link)
    row["position"] = len(articles) + 1
    articles.append(row)


def _google_article(item, cluster):
    """One Google News row, flat or from inside a cluster; the shape is one."""
    source = _obj(item.get("source"))
    row = _article(
        None,
        item.get("title"),
        item.get("link"),
        source.get("name"),
        # google_news carries no snippet on any row shape — the headline and
        # the outlet are all it publishes.
        None,
        item.get("date"),
        _iso(item.get("iso_date")),
        item.get("thumbnail") or item.get("thumbnail_small"),
    )
    authors = [name for name in _seq(source.get("authors")) if isinstance(name, str)]
    if authors:
        row["authors"] = authors
    if cluster:
        row["cluster"] = cluster
    return row


def extract_google(data):
    """Google News: a ranked list of stories, some of them clustered.

    Two row shapes arrive in the one `news_results` array and both have to be
    read. A flat row is an article. A cluster row is a heading — "News about
    tariffs • China" — with `stories` nested under it and no link, date or
    source of its own, so it is not an article and emitting it as one would put
    a null-linked row in the middle of the results. Its children are lifted
    into place instead, keeping the cluster's rank, each naming the heading it
    came from in `cluster`.

    `menu_links` is dropped: it is Google News's topic navigation, not a result
    for this query.
    """
    articles = []
    seen = set()
    for item in _rows(data, "news_results"):
        stories = _rows(item, "stories")
        if stories:
            for story in stories:
                _flatten(articles, seen, _google_article(story, item.get("title")))
        else:
            _flatten(articles, seen, _google_article(item, None))
    return {"articles": articles}


def extract_bing(data):
    """Bing News: organic rows, then the articles of its story clusters.

    `events` is Bing's grouping of related coverage, the same idea as Google's
    `stories` and flattened the same way rather than given a key of its own —
    one rule for both engines, and it keeps `events` unambiguously NewsAPI.ai's
    --events mode.

    The block is a first-page feature and vanishes under `first` or `qft`, so
    nothing here may depend on it being there.

    `source` is left verbatim, syndication and all ("CNBC on MSN"): the string
    names who published the copy at that link, which is what a citation needs.
    """
    articles = []
    seen = set()
    for item in _rows(data, "organic_results"):
        _flatten(articles, seen, _simple(item))
    for event in _rows(data, "events"):
        for item in _rows(event, "news"):
            row = _simple(item)
            row["cluster"] = event.get("title")
            _flatten(articles, seen, row)
    return {"articles": articles}


def extract_duckduckgo(data):
    """DuckDuckGo News: one flat list, no clusters, no timestamps.

    Its `date` is human-relative ("23 days ago") and there is no machine-
    readable field anywhere in the payload, so `iso_date` is null on every row.
    """
    articles = [_simple(item, index) for index, item
                in enumerate(_rows(data, "news_results"), start=1)]
    return {"articles": articles}


def extract_baidu(data):
    """Baidu News: the Chinese news web, under `organic_results`.

    The array is called organic_results even though this is the news engine —
    reading `news_results` here, as the other three engines use, returns
    nothing at all.

    Dates are Chinese display text and arrive in several shapes in the one
    response ("昨天16:42", "7天前", "5月23日"), none of them carrying a year, so
    they are passed through untouched and `iso_date` stays null.

    `related_searches` is Baidu's own query refinements and is worth keeping —
    it is how a query in the wrong register gets fixed. `top_searches` is
    dropped: it is the site's trending list, unrelated to this query.
    """
    articles = [_simple(item, index) for index, item
                in enumerate(_rows(data, "organic_results"), start=1)]
    response = {
        "articles": articles,
        "related_searches": _queries(_rows(data, "related_searches"), "query"),
    }
    total = _int(_obj(data.get("search_information")).get("total_results"))
    if total is not None:
        response["total_results"] = total
    return response


def _er_article(index, item):
    """One Event Registry article row.

    Shared by the database query (extract_newsapi) and the event drilldown
    (extract_event): both return articles in the identical shape, so the row is
    built once here.

    `dateTimePub` is the publisher's own stamp and `dateTime` is Event
    Registry's ingest time, always the later of the two; a reader asking when a
    story ran means the first, so it wins and the second is only a fallback.

    `body` is the article text truncated by articleBodyLen, which is why it
    lands in `snippet` and not somewhere that implies a summary.

    Dropped: `wgt` and `relevance` are internal ranking scores, `sim` a
    duplicate-similarity figure, and `shares` came back as {} on every row
    observed — a field the service no longer fills.
    """
    source = _obj(item.get("source"))
    stamp = item.get("dateTimePub") or item.get("dateTime")
    row = _article(
        index,
        item.get("title"),
        item.get("url"),
        source.get("title") or source.get("uri"),
        item.get("body"),
        stamp,
        _iso(stamp),
        item.get("image"),
    )
    sentiment = _num(item.get("sentiment"))
    if sentiment is not None:
        row["sentiment"] = sentiment
    if item.get("eventUri"):
        row["event_uri"] = item["eventUri"]
    if item.get("isDuplicate"):
        # Only when true: it is false on almost every row, and a dead field on
        # every article is worse than its absence.
        row["is_duplicate"] = True
    names = [
        author["name"] for author in _rows(item, "authors")
        if isinstance(author.get("name"), str)
    ]
    if names:
        row["authors"] = names
    return row


def extract_newsapi(data):
    """NewsAPI.ai articles: a page of a database query, not a SERP."""
    articles = _obj(_obj(data).get("articles"))
    rows = [
        _er_article(index, item)
        for index, item in enumerate(_rows(articles, "results"), start=1)
    ]
    response = {"articles": rows}
    total = _int(articles.get("totalResults"))
    if total is not None:
        # The size of the whole matching corpus, not of this page.
        response["total_results"] = total
    return response


def extract_events(data):
    """NewsAPI.ai events: one story, however many outlets covered it.

    `title` and `summary` are language-keyed maps rather than strings, so both
    go through _label(). `article_count` is the coverage figure and the reason
    to ask for events at all.

    `eventDate` is a day with no time attached, so `iso_date` is null by
    design: minting a T00:00:00Z out of it would claim a precision Event
    Registry did not report.
    """
    events = _obj(_obj(data).get("events"))
    rows = []
    for index, item in enumerate(_rows(events, "results"), start=1):
        rows.append({
            "position": index,
            "uri": item.get("uri"),
            "title": _label(item.get("title")),
            "summary": _label(item.get("summary")),
            "date": item.get("eventDate"),
            "iso_date": None,
            "article_count": _int(item.get("totalArticleCount")),
            "sentiment": _num(item.get("sentiment")),
        })
    response = {"events": rows}
    total = _int(events.get("totalResults"))
    if total is not None:
        response["total_results"] = total
    return response


# A dossier lists the entities and subjects Event Registry tagged the event
# with, not the whole ranked tail: the top handful, each carrying the uri you
# can feed straight back into --concept / --category for a wider search.
ER_DOSSIER_CONCEPTS = 10
ER_DOSSIER_CATEGORIES = 5


def _er_concepts(info):
    """The event's top concepts as {uri, label, type}, ranked as they arrive."""
    out = []
    for item in _rows(info, "concepts")[:ER_DOSSIER_CONCEPTS]:
        label = _label(item.get("label"))
        if label:
            out.append({"uri": item.get("uri"), "label": label,
                        "type": item.get("type")})
    return out


def _er_categories(info):
    """The event's top categories as {uri, label}."""
    out = []
    for item in _rows(info, "categories")[:ER_DOSSIER_CATEGORIES]:
        label = _label(item.get("label")) or item.get("uri")
        if label:
            out.append({"uri": item.get("uri"), "label": label})
    return out


def extract_event(data, uri):
    """One event followed by its uri: the dossier plus its article roster.

    getEvent keys its answer by the event uri, so the payload is unwrapped one
    level before reading. `info` carries the dossier (title, summary, date,
    coverage count, sentiment, social score, and the concepts / categories /
    location the event was tagged with); `articles.results` is the coverage, in
    the same shape every other NewsAPI.ai article uses.

    A uri with no event behind it comes back as an empty object, which leaves
    `event` absent and `articles` empty — a no_results the caller reads the same
    way as any other empty answer.
    """
    event = _obj(_obj(data).get(uri))
    info = _obj(event.get("info"))
    articles = _obj(event.get("articles"))
    rows = [
        _er_article(index, item)
        for index, item in enumerate(_rows(articles, "results"), start=1)
    ]
    response = {"articles": rows}
    total = _int(articles.get("totalResults"))
    if total is not None:
        response["total_results"] = total

    # Only build the dossier when the event exists: an absent `event` key is how
    # has_results() tells a bad uri from a real event whose article page is empty.
    title = _label(info.get("title"))
    if info and (title or info.get("uri")):
        dossier = {
            "uri": info.get("uri") or uri,
            "title": title,
            "summary": _label(info.get("summary")),
            "date": info.get("eventDate"),
            # A day with no time, like an events-mode row, so no iso_date is minted.
            "iso_date": None,
            "article_count": _int(info.get("totalArticleCount")),
            "sentiment": _num(info.get("sentiment")),
        }
        social = _num(info.get("socialScore"))
        if social is not None:
            dossier["social_score"] = social
        concepts = _er_concepts(info)
        if concepts:
            dossier["concepts"] = concepts
        categories = _er_categories(info)
        if categories:
            dossier["categories"] = categories
        location = _label(_obj(info.get("location")).get("label"))
        if location:
            dossier["location"] = location
        response["event"] = dossier
    return response


def extract_lookups(data):
    """The suggest*Fast endpoints: URIs for the filter flags.

    The body is a bare array, and the four taxonomies label themselves
    differently — a source's name is `title`, a concept's is an {"eng": ...}
    map under `label`, a category's is a plain string under the same key, and
    an author's is `name` — so `label` is normalised here and the
    taxonomy-specific field lands in `type`.
    """
    rows = []
    for index, item in enumerate(
        [entry for entry in _seq(data) if isinstance(entry, dict)], start=1
    ):
        rows.append({
            "position": index,
            "uri": item.get("uri"),
            "label": (_label(item.get("label")) or item.get("title")
                      or item.get("name")),
            "type": item.get("dataType") or item.get("type") or item.get("parentUri"),
        })
    return {"lookups": rows}


EXTRACTORS = {
    "google": extract_google,
    "bing": extract_bing,
    "duckduckgo": extract_duckduckgo,
    "baidu": extract_baidu,
    "newsapi": extract_newsapi,
}

# The three list keys an envelope can carry results in. One tuple, so trimming,
# the summary line and the verdict all agree on what counts as a result.
RESULT_KEYS = (("articles", "article"), ("events", "event"), ("lookups", "lookup"))


def has_results(response):
    """True when the engine returned anything usable.

    The three result lists, plus the single-event `event` dossier (a dict, so
    it is not in RESULT_KEYS): following an event uri and getting its dossier is
    a result even when that event's article page came back empty. Baidu's
    related searches and Event Registry's corpus total do not count: an engine
    that offered nothing but follow-up queries and a headline figure found no
    article, and saying otherwise would have the exit code claim a result the
    envelope does not hold.
    """
    if response.get("event"):
        return True
    return any(bool(response.get(key)) for key, _ in RESULT_KEYS)


def summarise(response):
    """One stderr line naming what the envelope actually holds.

    Counted rather than fixed wording, and evaluated after the response is
    built: this returns "nothing" in exactly the cases has_results() rejects,
    so the progress line can never announce results that the exit code denies.
    """
    def plural(items, noun):
        return f"{len(items)} {noun}{'' if len(items) == 1 else 's'}"

    parts = []
    if response.get("event"):
        # The dossier is one event; its roster is counted separately below.
        parts.append("1 event dossier")
    parts += [plural(response[key], noun) for key, noun in RESULT_KEYS
              if response.get(key)]
    return ", ".join(parts) if parts else "nothing"


def main():
    args = parse_args()

    engine = args.engine
    meta = ENGINES[engine]

    opts = resolve_options(args)

    if "lookup" in meta["flags"] and opts["lookup"] and any(
        getattr(args, dest) is not None
        for dest in ("period", "start_date", "end_date", "sort", "source",
                     "concept", "category", "author", "lang")
    ):
        # The suggest endpoints take a prefix and a page and nothing else, so a
        # filter passed alongside --lookup is not narrowing anything; without
        # this the caller would read the URI list as already filtered.
        #
        # Gated on the engine like the --num and --page checks below: on an
        # engine that has no --lookup, resolve_options() has already said the
        # flag is being ignored, and calling a filter that engine *did* apply
        # ignored on top of that would contradict it.
        print(
            "Warning: --lookup ignores every search filter; only --num and "
            "--page apply.",
            file=sys.stderr,
        )

    if "event" in meta["flags"] and opts["event"] and any(
        getattr(args, dest) is not None
        for dest in ("period", "start_date", "end_date", "source", "concept",
                     "category", "author", "lang")
    ):
        # --sort, --num, --page and --body-len shape the article roster, so they
        # are not named here; only the search conditions the drilldown drops are.
        print(
            "Warning: --event ignores every search filter; --num, --page, "
            "--sort and --body-len shape its article roster.",
            file=sys.stderr,
        )

    # Validate --num and --page only for the engines that actually use them.
    # For the others resolve_options() has already warned that the flag is
    # being ignored, and rejecting a value we are about to discard would
    # contradict that warning.
    if "num" in meta["flags"] and opts["num"] < 1:
        print("Error: --num must be 1 or greater.", file=sys.stderr)
        sys.exit(1)
    if "page" in meta["flags"] and opts["page"] < 0:
        print("Error: --page must be 0 or greater.", file=sys.stderr)
        sys.exit(1)

    # What the progress and failure lines name. On newsapi the query is
    # optional, so a filter-only search is announced by its filters rather than
    # by the word None.
    subject = args.query or opts["event"] or ", ".join(
        _csv(opts["source"]) + list(opts["concept"] or [])
        + list(opts["category"] or []) + list(opts["author"] or [])
    )

    if not os.getenv("HTTPS_PROXY") and not os.getenv("https_proxy"):
        # Without the gateway there is nothing to add the key, so the call would
        # come back as the service's own "invalid key" and read like a vault
        # problem. Name the real cause instead.
        print(
            "Warning: HTTPS_PROXY is unset, so this request will not pass "
            "through the OneCLI gateway and will carry no API key.",
            file=sys.stderr,
        )

    if engine == "newsapi":
        url, body = build_body(args.query, opts)
        request = {"url": url, "body": body}
    else:
        params = build_params(engine, args.query, opts)
        request = params

    # The raw payload is what is cached, not the trimmed envelope: extraction
    # is free, and a cache of finished output would freeze today's row shape
    # into files the next version of this script has to keep reading.
    cache_path = cache_dir() / cache_key(engine, request)
    data = read_cache(cache_path, args.cache_ttl)
    cached = data is not None
    if cached:
        print(f"Cache hit for {meta['label']} (no billable call): {cache_path}",
              file=sys.stderr)
    else:
        print(f"Querying {meta['label']} for: {subject}", file=sys.stderr)
        if engine == "newsapi":
            data, error = fetch_eventregistry(url, body)
        else:
            data, error = fetch(params)
        if error is not None:
            print(f"Error: {meta['label']} request failed: {error}", file=sys.stderr)
            sys.exit(1)

    if engine == "newsapi" and opts["lookup"]:
        response = extract_lookups(data)
    elif engine == "newsapi" and opts["event"]:
        response = extract_event(data, opts["event"])
    elif engine == "newsapi" and opts["events"]:
        response = extract_events(data)
    else:
        response = EXTRACTORS[engine](data)

    # --num caps what the caller has to read. Baidu and NewsAPI.ai sized their
    # own page and are already at or under it; the other three ignore a count
    # entirely, so trimming is the only thing that honours the flag there.
    for key, _ in RESULT_KEYS:
        if key in response:
            response[key] = response[key][: opts["num"]]

    # A whole article is not a snippet. Under --body-len -1 the text moves to a
    # `body` row extra and `snippet` keeps the precis the envelope documents, so
    # the eight-field row is the same shape at every body length. Done here
    # rather than in extract_newsapi() for the same reason the trim above is: it
    # reshapes rows already built, and it runs after the trim so no work is
    # spent on rows about to be dropped.
    if engine == "newsapi" and opts["body_len"] == -1:
        for row in response.get("articles", []):
            if isinstance(row.get("snippet"), str):
                row["body"] = row["snippet"]
                row["snippet"] = row["snippet"][:ER_BODY_LEN]

    print(f"{meta['label']} returned {summarise(response)}.", file=sys.stderr)
    if engine == "newsapi" and opts["event"] and not has_results(response):
        # A bad uri, not a narrow filter, is the only way --event comes back
        # empty, so the generic note below would blame the wrong thing.
        print(
            "Note: NewsAPI.ai returned no event for that uri. An event uri "
            "comes from --events output or an article row's event_uri; run "
            "--events first, and copy the uri exactly.",
            file=sys.stderr,
        )
    elif (engine == "newsapi" and not opts["lookup"] and not opts["event"]
            and not has_results(response)):
        # Not under --lookup: the suggest endpoints ignore every filter this
        # note blames, so there it would name --lang and --source as the cause
        # of an empty answer that only means no URI starts with that prefix.
        print(
            "Note: NewsAPI.ai matched nothing. A --lang that is not the "
            "article's language, or an over-narrow --source / --concept / "
            "--author combination, returns an empty set rather than an error.",
            file=sys.stderr,
        )

    # Decide the verdict before serialising so the status field and the exit
    # code always agree; a caller that branches on either one sees the same
    # answer.
    ok = has_results(response)

    if ok and not cached:
        # An empty answer is never cached: it is usually a transient upstream
        # miss, and storing it would poison the key for --cache-ttl hours.
        write_cache(cache_path, data)

    output = {
        "status": "ok" if ok else "no_results",
        "engine": engine,
        "query": args.query,
        "cached": cached,
        **response,
    }
    json.dump(output, sys.stdout, ensure_ascii=False, indent=2)
    print(file=sys.stdout)

    if not ok:
        print(
            f"Error: {meta['label']} returned no results for: {subject}",
            file=sys.stderr,
        )
        sys.exit(NO_RESULTS_EXIT)


if __name__ == "__main__":
    main()
