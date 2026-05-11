# Wiki Build Guide

## Overview

The wiki is a synthesized knowledge base — not a dump of raw slides.
Each page covers a logical topic (industry vertical, product, client group)
synthesized from many source documents. Think Karpathy-style: raw sources
are immutable, wiki pages are the distilled intelligence on top.

## Step 1 — Sample the Corpus

List the contents of `<slug>_sources/` and read ~20 directory names.
Group them mentally: what industries are represented? What products?
What client names appear? What internal docs should be skipped?

## Step 2 — Design Categories

A typical B2B SaaS corpus splits into:
- `solutions/` — one page per industry vertical
- `products/` — one page per product line
- `clients/` — one page per client industry group  
- `concepts/` — company overview, competitive analysis, threat reports

Adapt these to the actual corpus. If it's a law firm, maybe `practice_areas/`
and `case_studies/`. If it's a hospital, `departments/` and `procedures/`.
Use judgment. Aim for 15–30 total pages.

## Step 3 — Write the Source Map Script

Create `WIKI_DIR/scripts/build_source_map.py` (or adapt the bundled one)
with `classify(filename: str) -> str | None` rules based on what you saw.

Key patterns:
- **Skip** internal/operational docs: OKR, weekly reports, HR docs, etc.
- **Client docs** often have a prefix like `Clients__ClientName__filename`
- **Product docs** usually contain the product name in the filename
- **Solution docs** contain industry keywords

Run it and review the output. Adjust rules until coverage > 80%.

## Step 4 — Initialize Wiki Structure

Create these files in `WIKI_DIR`:

```
WIKI_DIR/
├── CLAUDE.md       ← schema, maintenance rules
├── index.md        ← global index with links to all pages
├── log.md          ← operation log (fill in after build)
├── solutions/
├── products/
├── clients/
├── concepts/
└── _sources/
    └── source_map.json
```

`CLAUDE.md` should document:
- The wiki's purpose and source
- Directory structure
- Page format (YAML frontmatter schema)
- Maintenance rules (how to add new pages, update sources)

## Step 5 — Wiki Page Format

Every page must have YAML frontmatter:
```yaml
---
title: Page Title
category: solutions | products | clients | concepts
tags: [relevant, tags]
sources:
  - "exact_source_directory_name"
  - "another_source_directory_name"
last_updated: YYYY-MM-DD
---
```

Page structure:
- `## 概述` / `## Overview` — 1-2 paragraph synthesis
- `## 核心内容` / `## Core Content` — logical subsections
- `## 关键指标` / `## Key Metrics` — quantitative data if available
- `## 关联页面` / `## Related Pages` — `[[wikilink]]` cross-references
- `## 来源` / `## Sources` — list of source document names (will be converted to wikilinks)

## Step 6 — Spawn Parallel Sub-agents

Split the wiki pages into groups of 3-4 and spawn one sub-agent per group.
This is the right level of parallelism — enough to be fast, few enough that
each agent has manageable context.

**Critical instruction for each sub-agent:**
> For each page in your group: read the source documents for that page,
> then IMMEDIATELY write the wiki page before moving to the next source.
> Do NOT read all sources first and then write all pages — you will stall.

Pass each sub-agent:
- The list of pages it should write
- The source map entries for those pages
- The path to `<slug>_sources/`
- The wiki page format spec above
- The wiki directory path

Sub-agents should create complete, information-dense pages. Target 300-800
lines per page. Extract: key capabilities, concrete numbers/metrics, named
clients, product features, competitive differentiators.

## Step 7 — Fix Wikilinks

After all pages are written, scan for broken wikilinks:
- Pages should reference other pages by their base name: `[[天净]]` not `[[products/天净]]`
- Cross-references should point to actual existing pages

Use `grep -r '\[\[' WIKI_DIR --include="*.md"` to find all wikilinks and
verify they resolve.

## Step 8 — Build Index

Write `index.md` as a summary table for each category:
```markdown
| Page | Summary | Source Count |
|------|---------|-------------|
| [[PageName]] | one-line description | N |
```

## Step 9 — Move Sources into Wiki

```bash
mv <slug>_sources/ WIKI_DIR/sources/
```

Then update `CLAUDE.md` to reflect the new path.

## Step 10 — Rebuild Source Wikilinks

Run `06_rebuild_source_links.py` to convert `## 来源` plain text to
`[[sources/xxx|display_name]]` wikilinks using the frontmatter `sources:` field.
