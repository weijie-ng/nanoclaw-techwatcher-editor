---
name: publication-format
description: >-
  Structures an article or a newsletter before it is drafted, using ten
  skeletons working newsrooms actually use, each with a worked HTML specimen
  that doubles as a render template. Use when someone asks for an article, a
  roundup, a digest, a morning brief, a newsletter, a "5 things" or a weekly
  summary, and whenever material has already been gathered and the open
  question becomes how to arrange it. Trigger words include Smart Brevity,
  why it matters, inverted pyramid, nut graf, lede, martini glass,
  explainer, FAQ, format, structure, skeleton. It decides the shape only:
  news-search and social-search find the material, fact-check verifies it,
  and humanizer is the line-level pass once a draft exists. loop-design is
  the research-and-assembly engine, so run that first when material still has
  to be gathered or verified; publication-format only arranges material that
  already exists.
metadata:
  author: AI Experimentation Lab
---

# Publication format

Ten skeletons for arranging material into a finished piece. Six are article
formats (one subject); four are newsletter skeletons (several items). Pick one
before drafting, read only that format's reference file, and write to its shape.

The choice is the work. A well-reported story in the wrong skeleton reads worse
than a thin one in the right skeleton, because the skeleton decides what the
reader learns first and what they can stop reading without missing.

## Pick one

Match on what you are holding, not on the name you like:

| You are holding | Use |
|---|---|
| One story that just broke, and readers may stop reading at any line | `inverted-pyramid` |
| One story where the reader wants the takeaway in twenty seconds | `smart-brevity` |
| A trend, with a person or a scene that embodies it | `anecdotal-lede` |
| Something that went wrong, and you have the timeline | `martini-glass` |
| A subject readers arrive at already asking questions about | `explainer-faq` |
| A document or a leak whose significance needs setting up first | `delayed-reveal` |
| Several stories, one of them clearly dominant | `top-story-digest` |
| Several stories, none dominant, value is in the selection | `curated-list` |
| Many items on one beat, with a pattern running across them | `thematic-clusters` |
| Several stories and an actual argument that connects them | `narrated-digest` |

Two rows can fit. When they do, ask what the reader does next: acts on it
(`smart-brevity`), files it (`inverted-pyramid`), understands it
(`explainer-faq`), or reconsiders something (`narrated-digest`).

If the request names a format ("do it in Smart Brevity", "just a wire piece"),
that overrides the table.

## The two families

**Article formats** carry one subject. `smart-brevity`, `inverted-pyramid`,
`anecdotal-lede`, `martini-glass`, `explainer-faq`, `delayed-reveal`.

**Newsletter skeletons** carry several. `top-story-digest`, `curated-list`,
`thematic-clusters`, `narrated-digest`.

They nest one way only: a newsletter's lead item may itself be written to an
article skeleton (`top-story-digest` is exactly this, a Smart Brevity lead
followed by short items). An article never contains a newsletter.

## Rules that hold across all ten

- **One skeleton per piece.** Blending is the most common failure. A curated
  list that grows connective prose has become a bad narrated digest; a wire
  story with `Why it matters` bolted on has become a bad Smart Brevity.
- **Every factual claim carries its source, in two layers.** The claim names
  its source in the prose, in the format's own voice, and carries a numbered
  marker pointing to a source list at the end. Both layers, every format, no
  exceptions but `curated-list`, which is already nothing but sources. This is
  not optional and it is not the format's business to opt out of: read
  [reference/citations.md](reference/citations.md) before drafting anything.
  A claim that cannot be sourced gets cut, reduced to what the source supports,
  or stated in the piece as a gap. Never invented, never left to stand alone.
- **Apply the "so what" test to every block.** If a block can be deleted and
  the reader loses nothing, delete it. This is what stops the labelled formats
  degrading into filled-in forms.
- **Order by the format's rule, not by chronology.** Only `martini-glass` is
  chronological by default, and only for its first two thirds.
- **Do not invent facts to fill a slot.** If the skeleton has a `What's next`
  block and nothing is next, cut the block. An empty slot is a signal the
  format is wrong, not a prompt to speculate.

## The ten formats

Each row has a specification and a worked specimen. Read the specification
before drafting. Open the specimen when you need to see the shape rendered, or
when the deliverable is an HTML page and you want a starting file to copy.

When the question is "which structure should this be", or someone wants to see
the shapes side by side before choosing, send them
[assets/overview.html](assets/overview.html): a one-page map of all ten
skeletons and their block order, with no drafting content. It carries no
placeholders, so send it straight from the mount with `send_file`, no copy
needed. The reader can then point at one format and ask to learn more, or to
draft their piece in it.

[reference/citations.md](reference/citations.md) applies to every row and is
read alongside whichever one you pick. It covers what needs a citation, marker
placement, source-entry format, where the source list goes in each format, and
what to do with a claim the material will not support.

| Format | Use when | Specification | Specimen |
|---|---|---|---|
| Smart Brevity | Reader needs the takeaway fast and may act on it | [reference/smart-brevity.md](reference/smart-brevity.md) | [assets/example-smart-brevity.html](assets/example-smart-brevity.html) |
| Inverted pyramid | Breaking news, wire copy, anything cut from the bottom | [reference/inverted-pyramid.md](reference/inverted-pyramid.md) | [assets/example-inverted-pyramid.html](assets/example-inverted-pyramid.html) |
| Anecdotal lede | Features and trend pieces with a human at the centre | [reference/anecdotal-lede.md](reference/anecdotal-lede.md) | [assets/example-anecdotal-lede.html](assets/example-anecdotal-lede.html) |
| Martini glass | Post-mortems and reconstructions with a clear timeline | [reference/martini-glass.md](reference/martini-glass.md) | [assets/example-martini-glass.html](assets/example-martini-glass.html) |
| Explainer / FAQ | "What is X", "why does X matter", retrieval reading | [reference/explainer-faq.md](reference/explainer-faq.md) | [assets/example-explainer-faq.html](assets/example-explainer-faq.html) |
| Delayed reveal | Investigations where the finding needs context to land | [reference/delayed-reveal.md](reference/delayed-reveal.md) | [assets/example-delayed-reveal.html](assets/example-delayed-reveal.html) |
| Top story + digest | A morning brief with one dominant story | [reference/top-story-digest.md](reference/top-story-digest.md) | [assets/example-top-story-digest.html](assets/example-top-story-digest.html) |
| Curated list | Flat linkblog, "5 things", Sunday reads | [reference/curated-list.md](reference/curated-list.md) | [assets/example-curated-list.html](assets/example-curated-list.html) |
| Thematic clusters | One beat covered deeply, patterns across items | [reference/thematic-clusters.md](reference/thematic-clusters.md) | [assets/example-thematic-clusters.html](assets/example-thematic-clusters.html) |
| Narrated digest | Several stories and one argument tying them together | [reference/narrated-digest.md](reference/narrated-digest.md) | [assets/example-narrated-digest.html](assets/example-narrated-digest.html) |

## Workflow

1. **Pick the format** from the table above. Say which one you picked and why,
   in one line, before you start drafting.
2. **Read that one reference file**, plus `reference/citations.md`. Not all
   ten formats. Each format file is self-contained; citations apply to all.
3. **Draft to the skeleton**, block by block, respecting its length budgets.
   Cite as you draft. Retrofitting citations onto a finished draft is how
   claims end up attached to sources that do not support them.
4. **Run both self-checks** against your own draft, the format's and the
   citation one. Fix what fails and check again. If two or more format checks
   keep failing, the format is probably wrong for the material - go back to
   step 1 rather than forcing it. If the citation checks fail, that is a
   reporting gap, not a formatting one: fix the sourcing, do not restructure.
5. **Render only if an HTML deliverable was asked for.** Copy the matching
   specimen into your working directory and replace its content block by block.
   The class names in the specimen match the block names in the specification.
6. **Hand the finished draft to `humanizer`** for the line-level pass. This
   skill sets structure; it does not fix sentences.

## Environment: NanoClaw container

The skill directory is mounted read-only. Copy a specimen out before editing it:

```bash
cp /app/skills/publication-format/assets/example-smart-brevity.html \
   /workspace/agent/brief.html
```

Drafts and rendered pages belong under `/workspace/agent/`. To look at a
rendered page:

```bash
agent-browser open "file:///workspace/agent/brief.html"
```

Every specimen is one self-contained file with its CSS inline, no fonts,
scripts or network calls, on a light DSTA-blue palette, and it closes with the
"Powered by AI Experimentation Lab & MCC" footer. Keep it that way
when you edit one, so the result survives being emailed, pasted into a
channel, or opened offline.

House style for anything published from this container is British English with
no em dashes, per the group's standing instructions. The skeletons here are
American in origin; the spelling is not.
