# pestidev-job-scraper

**This is not the pestidev.hu website.** It contains no site code. It is the instruction set —
prompts and subagent definitions — that a scheduled [Claude Code](https://claude.com/claude-code)
cloud routine reads on every run to find Hungarian IT job postings and push them into the board
that pestidev.hu serves.

The site itself, and the Netlify functions behind it, live in a separate repo owned by the site's
maintainer. This repo only feeds that board.

## What it does

Twice a day a cloud routine checks this repo out, reads one of the prompt files at the root, and
follows it end to end:

1. Fetches the registry (already-tracked sites, already-seen postings, permanently rejected sites)
   and the hourly upload budget.
2. Re-checks tracked company career pages for changes.
3. Discovers new Hungarian companies that run their own career pages.
4. Reads each posting's actual detail page and applies six filters (junior/medior/intern level, IT
   relevance, and so on).
5. POSTs the surviving findings, plus the list of sites checked, in a single call.

The registry submission is the entire product of a run. Nothing is committed, branched or pushed —
these routines produce no git output.

The postings targeted are the ones the maintainer's own Netlify scraper does **not** already cover:
roles on individual company career pages rather than the big aggregator job boards.

## Layout

| Path | What it is |
| --- | --- |
| `prompt.md` | The original single-file pipeline. One agent does everything inline. Driven by the "Daily job-board scrape (pestidev)" routine. |
| `prompt-v2.md` | The subagent design. An orchestrator dispatches per-site work to the agents below. Driven by the "Daily job-board scrape v2 — subagents (pestidev)" routine. |
| `.claude/agents/site-change-check.md` | Cheap check of whether one tracked career page's posting URLs changed. Haiku. |
| `.claude/agents/site-processor.md` | One company end to end: find the listing, enumerate every posting, count before filtering, read each detail page, apply the six filters. Sonnet. |
| `.claude/agents/company-discovery.md` | Search for untracked Hungarian companies with their own career pages. Does not open or judge postings. Sonnet. |
| `.claude/settings.json` | Tool allowlist that lets the routines run unattended, with the incident history explaining each rule. |
| `.mcp.json` | Registers the `pestidev` MCP server (the registry API). |

The two prompt files are alternative drivers for the same job, running on staggered schedules against
shared state. A run follows exactly one of them — the subagents are for `prompt-v2.md` only, and
their descriptions say so.

## A note on the prompt files

Roughly a third of each prompt file is accumulated incident knowledge: corrections written after
specific failed runs, each with a date and the company that exposed it. Sections marked `★` and `⚠`
exist because something was missed without them.

**Relocate that material, never rewrite it.** It reads as verbose and redundant; it is neither. See
the "count before you filter" and "enumerate the WHOLE career page" sections for the clearest
examples of rules that look obvious and were not.

## The `pestidev` name inside the repo

The MCP server in `.mcp.json` is named `pestidev`, and the tool names `mcp__pestidev__get_registry`
and `mcp__pestidev__submit_findings` follow from it. That name refers to the **registry backend**,
not to this repo, and it is matched literally by the allowlist in `.claude/settings.json` and by
both routines' `allowed_tools`. Renaming it silently breaks the allowlist and turns an unattended
run into a permission prompt nobody is there to answer. Leave it alone.

## Credentials

No token is stored in this repo. The registry bearer token lives in each routine's stored prompt,
which is not version-controlled, and is only used on the curl fallback path. On the MCP path the run
never handles a credential at all. Do not commit one here — the repo is public.
