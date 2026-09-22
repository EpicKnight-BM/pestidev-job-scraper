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
3b. Discovers new companies posting through a known ATS platform (Ashby/Greenhouse/Lever/
    SmartRecruiters/Recruitee/Personio/BambooHR/Teamtailor/Workday) via a rotating set of search
    queries — a segment company-name-based guessing on the site side can't reach. Submits found
    tenants for the site's own hourly ATS crawler to harvest; does not read or submit postings
    itself. Added 2026-09-22.
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
| `INCIDENTS.md` | Full narrative behind every dated rule in the prompt files — the run, the date, the root cause. Not read by any agent; see below. |
| `scripts/` | Small POSIX-shell scripts (`fold-name.sh`, `strip-url-tail.sh`) that replace two deterministic string algorithms previously spelled out in prose in multiple prompt files. Every prompt invokes them prefixed with `timeout N` to stay inside `.claude/settings.json`'s `Bash(timeout:*)` allow rule — an unattended run has nobody to approve a command that falls through to the auto-mode classifier. |

The two prompt files are alternative drivers for the same job, running on staggered schedules against
shared state. A run follows exactly one of them — the subagents are for `prompt-v2.md` only, and
their descriptions say so.

## A note on the prompt files

Roughly a third of each prompt file used to be accumulated incident knowledge written inline: a
rule followed by two or three sentences narrating the specific failed run, date, and company that
exposed it. Sections marked `★` and `⚠` exist because something was missed without them.

**The full narrative now lives in `INCIDENTS.md`, not inline.** Each prompt file keeps a short
tag next to the rule — a date plus the terse consequence, e.g. `(confirmed 2026-08-24 — burned 48
tool uses, returned nothing; see INCIDENTS.md § Turn-budget cutoffs)` — and nothing more. This is
deliberate, not a shortcut: the subagents in `.claude/agents/` only ever read their own prompt
file, never `INCIDENTS.md` (spending a turn to open a second file is exactly the kind of cost the
turn-budget rules in those files exist to prevent), so the concrete "this really happened" signal
that makes a rule stick has to survive as that one-line tag — a bare "see INCIDENTS.md" link with
nothing inline would be no different, in practice, from deleting the incident outright.

**When adding a new incident**, follow that same pattern: append the full story to the matching
`INCIDENTS.md` entry (or a new one), and add or update the one-line tag at the rule's call site.
**Never rewrite a rule's substance to make it shorter** — see the "count before you filter" and
"enumerate the WHOLE career page" sections for the clearest examples of rules that look obvious and
were not.

## The `pestidev` name inside the repo

The MCP server in `.mcp.json` is named `pestidev`, and the tool names `mcp__pestidev__get_registry`
and `mcp__pestidev__submit_findings` follow from it. That name refers to the **registry backend**,
not to this repo, and it is matched literally by the allowlist in `.claude/settings.json` and by
both routines' `allowed_tools`. Renaming it silently breaks the allowlist and turns an unattended
run into a permission prompt nobody is there to answer. Leave it alone.

## Credentials

No token is stored in this repo. As of 2026-09-15 both prompt files use the `pestidev` MCP server
exclusively — the curl/REST fallback and its `AI_INGEST_TOKEN` were removed as the routines'
most fragile step (a token pasted into a shell command on every run). A run never handles a
credential at all; if `get_registry` is absent from the tool list, the prompt says to stop and
report it, not to go looking for a token or improvise a curl workaround. Do not commit one here —
the repo is public.
