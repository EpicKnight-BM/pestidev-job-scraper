# Incident log

This file holds the full narrative behind rules in `prompt.md`, `prompt-v2.md`, and the three
`.claude/agents/*.md` subagent prompts — the specific run, date, and root cause that proved each
rule necessary. Those prompt files only keep a short inline tag (date + terse consequence) next to
each rule, pointing back here.

**This split exists on purpose, not as a place to dump text.** The prompt files are read by
unattended agents on every run; this file is not — none of those agents open it, and none should
be told to, since spending a turn reading it would cost real budget for no operational benefit.
Keeping the concrete "this really happened" detail inline (even compressed to one line) is what
makes a subagent actually obey a rule instead of treating it as an arbitrary preference; this file
exists for the humans (and future sessions) who need the full story — when auditing a rule, when
deciding whether it's still needed, or when a new incident needs to be added to an existing entry.

**When a new incident confirms or extends a rule already listed here:** add it to the existing
entry (matching the pattern of the entries below — one section per rule, incidents appended
chronologically) rather than creating a duplicate entry, and update the inline tag in whichever
prompt file(s) cite it if the tag's own summary (e.g. a repeat count) changes.

---

## Turn-budget cutoffs (`company-discovery.md`)

A percentage-of-your-own-turns rule ("stop at roughly two-thirds of your turns") proved
unreliable — the agent has no reliable way to know exactly how many turns it has spent — and was
replaced with a hard query count (12 queries, full stop). Failures under the old percentage rule,
six confirmed so far:

- **2026-08-24** — burned 48 tool uses against a 20-turn cap, returned nothing at all.
- **2026-08-26**
- **2026-09-08**
- **2026-09-12**
- **2026-09-13**
- **2026-09-18** — at the (by then increased) cap: 22 buckets searched, still mid-rotation, cut off
  before writeup.

At least two of these (08-26, 09-18) happened *after* the percentage-based soft rule was already
in the file, which is why it was replaced with a hard count instead of tightened further.

## Checkpoint must fire on a dry run, not just a productive one (`company-discovery.md`)

**2026-09-08** — a run spent ~15 queries across all three buckets and every single hit was already
known, so no candidate ever passed the domain check. The old candidates-only checkpoint (which
only wrote to disk when something passed) therefore never fired, the checkpoint file stayed
missing the whole run, and the orchestrator's recovery step found nothing to read even though the
agent had genuinely done ~15 queries' worth of work. Fixed by checkpointing after every query,
whether it produced a passing candidate or not.

## Domain dedup — dropping a whole shared-ATS-host platform by mistake (`company-discovery.md`)

**2026-08-24** — a run reported `droppedAsKnown: 10` after treating `job-boards.greenhouse.io`,
`jobs.lever.co` / `jobs.eu.lever.co`, `jobs.ashbyhq.com`, `jobs.smartrecruiters.com` and `join.com`
as "already known" **hosts**, because `knownDomains` happened to contain some other company's
board on the same host. Every genuinely new company on those platforms was thrown away. Root
cause: a substring/host-level match instead of matching on the full tenant identity (subdomain
label or first path segment).

## Domain dedup — re-checking an already-tracked site ahead of schedule (`company-discovery.md`)

**2026-07-22** — `job-boards.greenhouse.io/gravity` got re-verified after ~24 hours instead of
waiting the full 7-day window, because a fresh search hit on one of its job URLs wasn't recognized
as the same already-tracked domain (matched on exact URL path instead of bare domain/board-slug).

## `knownDomainsFile` must be loaded, and as a file path, not inline (`company-discovery.md`)

**2026-09-02** — the domain list was omitted from the dispatch as "too large to hand the agent
inline" (~900 lines). The search ran blind with nothing to de-duplicate against, and 5 of the 6
candidates returned (SolvencyAnalytics, KFS Group, GitRabbit, INSPYRE, Telio Group) were already
tracked or already permanently rejected — the entire discovery step produced one usable company.
Fixed by passing a file path the agent loads and greps directly instead of pasting the list into
the dispatch prompt.

## Query-bucket rotation — platform-only passes return mostly known companies (`company-discovery.md`)

**2026-09-02** — a run spent all four of its queries on the platform bucket (join.com, recruitee,
teamtailor, personio) and 5 of its 6 candidates were already known. The role and sector buckets are
where untracked companies actually surface.

## `ats-crawl` host takeover (`company-discovery.md`, `site-processor.md`, `prompt.md`, `prompt-v2.md`)

Since 2026-08-26 the site runs its own ATS crawler (`cron_jobs_ATSCRAWL-background.mjs`, source
`ats-crawl`, hourly), which calls the public board API of every company in its `ats_tenants` table
and ingests the Hungarian rows directly. It started with four providers (Ashby, Greenhouse, Lever,
SmartRecruiters) on 2026-08-26, added Recruitee and Personio on 2026-08-30, and added BambooHR and
Teamtailor on 2026-09-01 — eight hosts total. Before this, hand-scraping those platforms was
expected work; after, every posting found on one of them is duplicate work already being done
hourly by something else.

## `apply.workable.com` is Cloudflare rate-limited (`company-discovery.md`, `site-processor.md`)

**2026-08-24** — every fetch of `apply.workable.com/sspinc/` and its widget API returned HTTP 429 /
`error code: 1015` across four attempts, with delays and a spoofed user-agent. 1015 is a rate-limit
ban on the caller, not a transient error, so retrying doesn't help. This does NOT make the company
itself unreachable — Secret Sauce Partners was reachable and useful via its own `/careers` page the
same run.

## `nix` / NIX Hungary Kft. / nixstech.com (`company-discovery.md`, `site-processor.md`, `site-change-check.md`, `prompt.md`, `prompt-v2.md`)

**2026-07-21** — this company slipped through the exclusion list and its postings leaked live
duplicate rows onto the board; three `nixstech.com` job URLs still sit in `knownUrls` from that
incident. **2026-08-21** — `sites["nixstech"]` was re-fetched on schedule even though
`permanentlyRejected` already held three separate entries for it, showing that a stale `sites`
entry left untouched is harmless but one that keeps getting refreshed is the same incident waiting
to happen again. Now enforced as a hard "do not fetch, do not send a `sitesChecked` entry" stop
ahead of the first fetch in every relevant agent.

## Query-turn budget exhaustion — recovering via checkpoint, not resuming the agent (`prompt-v2.md`)

`company-discovery` has hit its `maxTurns` ceiling and returned nothing at least six times (dates
above, under "Turn-budget cutoffs"). **2026-09-08** confirmed that calling `ScheduleWakeup` or a
fresh `Agent` dispatch to "resume" a cut-off run is always wrong — `ScheduleWakeup` only
reschedules the orchestrator's own wakeup, and a new `Agent` call spawns a blank agent with no
memory of the run in progress. A prior version of this rule called for resuming via `SendMessage`
instead; that was also superseded once the checkpoint file was shown to make even a *correct*
resume unnecessary — reading the checkpoint directly and using its contents as the final result is
both correct and cheaper.

## join.com tenant collisions in the known-domains file (`prompt-v2.md`)

**Confirmed recurring, same three companies each time (2026-09-05, 2026-09-12, 2026-09-18):** when
the known-domains file held bare hostnames only, KFS Group, GitRabbit, and INSPYRE — all join.com
tenants — kept re-surfacing as "new" discoveries, because a lone `join.com` line can't distinguish
their tenant from any other company on that host. Each run caught and self-corrected this by hand
before submitting, at the cost of wasted discovery budget. Fixed by writing the full tenant path
(`join.com/companies/kfs1`) instead of the bare host.

## `www.`-prefix domain mismatches in the known-domains dedup (`prompt-v2.md`, `company-discovery.md`)

**Confirmed 2026-09-20 (run `cse_01VdsjjGybKcs61QcRPEXWFL`)** — AiCAN re-surfaced as a "new"
discovery candidate even though it was already tracked (`sites.aican.url` is
`https://www.aican.hu/karrier/`), because the known-domains file preserved the registry's stored
`www.` prefix verbatim while `company-discovery`'s search returned the bare `aican.hu` — two
strings that are the same site but differ as text, which an exact `grep -qxF` never equates. The
orchestrator's mandatory post-discovery cross-check against the live registry caught it before
submission, so nothing bad went out, but the discovery budget was spent re-investigating a company
already on the board. Fixed by stripping a leading `www.` from ordinary (non-shared-ATS-host)
hostnames on both ends: the orchestrator writes `knownDomainsFile` without it, and
`company-discovery` strips it from its own candidate domain before the `grep -qxF` check. This is
the same class of gap as the join.com tenant-path fix above, just for the common case instead of
the shared-ATS one — see INCIDENTS.md § join.com tenant collisions in the known-domains file.

## `storedListingUrls` dispatch field must be named exactly, and its absence must be loud (`site-change-check.md`, `prompt-v2.md`)

**2026-09-02 (run `cse_01UZLKkW6NMYxuJraYEq79pk`)** — the orchestrator's dispatch omitted the
`storedListingUrls` field. Every agent in that run inferred `changed: false` from the missing
field ("No storedListingUrls provided for comparison"), and all 14 sites came back `changed: false`
with empty sets — including yettel (53 stored URLs), knorrbremse-joinus (22), and
rendszerinformatika (9), none of which had actually emptied. Recovering from it cost six extra
reconciliation dispatches and most of the run's 26 minutes. Fixed two ways: the agent now reports
`changed: true` with every current URL treated as new when the field is missing (never a silent
`false`), opening its `note` with the exact words `NO storedListingUrls IN DISPATCH`; and the
orchestrator must never write that resulting empty-diff set into `sitesChecked`, since doing so
would overwrite a good stored listing with nothing.

## URL rotation vs. a genuinely new posting — joinus.hu (`site-change-check.md`, `site-processor.md`, `prompt.md`, `prompt-v2.md`)

**Confirmed 2026-09-02 on joinus.hu (Knorr-Bremse)** — the exact same posting ("Embedded Middleware
Developer Trainee – EBS/ABS System and Integration Team", same company, same body) had two
different URLs across two crawls: an earlier-indexed link ending `...-f16d` now 404s, and the live
posting's own canonical URL now points to `...-f16d-f3ee`. Treated naively (every URL absent from
the stored set is "new"), this mints a fresh duplicate row on the board every time the URL rotates,
since `(source, url)` is the database row identity. Now caught by the stable-prefix comparison in
`scripts/strip-url-tail.sh` before a "new" URL is treated as a new posting.

## Nexum `/jsbq` endpoint reports only the newest page, not the real total (`site-processor.md`)

**2026-08-24 on mvm.karrierportal.hu** — the JSON's top-level `total` field was 164, but the run
reported `postingsFound: 9` (the length of `rows`, i.e. only the newest batch the endpoint actually
returns — `?page=2` and similar params don't work). Technically the rows it saw, but it read as
"MVM has 9 postings and we enumerated all of them" when 155 were never looked at. Fixed by always
reporting the endpoint's own `total` as `postingsFound` when the two differ, and naming the gap in
`note`.

## Count before you filter — five same-shape misses in one week (`site-processor.md`, `prompt.md`)

**2026-07-22/23** — vector.hu, novaservices.hu, KELER, sysdata-pse.com, and
rendszerinformatika.hu were five separate user-reported incidents that were the SAME root failure:
some of a site's postings were evaluated, the qualifying ones submitted, and the site reported as
done — without anyone knowing how many postings the site actually had. "I found some and evaluated
them" looks identical whether it was 2 of 2 or 2 of 8. Fixed by making the full enumeration count
mandatory and explicit (`postingsFound`) before any filtering happens.

## vector.hu — links sitting unread in an already-fetched page (`site-processor.md`, `prompt.md`)

**Confirmed** — vector.hu/karrier/ajanlatok had 6 job links present in one plain fetch; only some
got submitted, and the missed ones were ordinary IT dev roles that should have passed. The links
were not hidden behind JavaScript or a second page — they were sitting in HTML already fetched and
simply not read to the end.

## Never conclude "unreachable" from a first glance — DATAPAO and Nexum/Hireify (`site-processor.md`, `prompt.md`)

**2026-08-04 audit** proved a past "confirmed dead" verdict wrong for `karrierportal.hu` (the
Nexum ATS) and Hireify, and recovered 10 real junior/medior postings across 5 companies that had
been sitting unread. Same audit: DATAPAO's Greenhouse-hosted `/careers/` looked JS-heavy at a
glance, but a plain fetch already had 6 direct `job-boards.eu.greenhouse.io/datapao/jobs/<id>`
links sitting in the raw HTML, unread (all 6 turned out Senior/Manager/CFO that day, but the site
itself was very much reachable). Separately, **novaservices.hu**'s `/karrier` needs JS and shows
nothing in a plain fetch, but its `/sitemap.xml` lists every `/careers/<slug>` posting directly.

The same 2026-08-04 audit also caught the opposite failure mode — false positives from a bare
keyword match on an IT-relevance filter: "Biztonsági Munkatárs" at a transport/logistics company
turned out to be PHYSICAL security (vagyonőr, gazdaságvédelem), not IT security, and
"Hálózatszervezési és üzemeltetési munkatárs" at a postal company meant organising the physical
POST-OFFICE BRANCH network, not IT networking. Both required reading enough of the body to confirm
the role was actually about computers/software/IT infrastructure, not just matching on
"biztonsági"/"hálózat" in the title.

## keler.hu — PDF-only listing (`site-processor.md`, `prompt.md`)

**2026-07-23** — keler.hu's entire careers page links to PDF files instead of HTML pages, and
returned zero findings for weeks despite real junior-friendly openings, because a PDF-only listing
was treated as a dead end instead of a normal listing whose posting identity happens to be a PDF
URL.

## Career page never reached at all — ulyssys.hu and karrier.nisz.hu (`site-processor.md`, `prompt.md`)

**2026-08-01** — two confirmed misses where the career page itself was never found: ulyssys.hu
(real page is `/hu/karrier.html`, missing a "Rendszermérnök" posting) and karrier.nisz.hu (found
only on a later run). The second case is the reason a first-pass miss is not treated as permanent —
newly-discovered companies get retried rather than marked "no career page" after one failed guess.

## karrier.4iggroup.hu — a pre-scoped search/filter listing (`site-processor.md`, `prompt.md`)

**2026-08-01** — `/it/search/` is a query-string-driven filter interface whose default loaded view
was pre-scoped and not the full list. It was never properly enumerated this way, and 4iG's real
Budapest IT roles were never reached.

## Anchored roles on one page treated as one posting — electronholding.com (`site-processor.md`, `prompt.md`)

**2026-08-01** — electronholding.com/careers#positions lists multiple distinct, individually
anchored roles ("AI Integration Specialist (junior)" and "Alkalmazásüzemeltető") on one page. Both
were missed even though each was its own distinguishable card with its own anchor id.

## Numbered URL siblings re-listing one opening — innoview.hu (`site-processor.md`, `prompt.md`)

**2026-07-29** — innoview.hu/en/allas/java-developer/ and its numbered siblings `-2`/`-3`/`-4` were
all the identical "Java Developer" opening, re-listed under separate fully-distinct URLs on the
same listing page (not query-string variants, not in-page anchors). All four got submitted as
separate findings in one run, creating four duplicate rows on the board. This is a same-run
problem — `knownActiveTitles`/`activeTitlesByCompany` only protects against re-finding a title
across separate runs, so duplicate entries discovered together in one enumeration have to be
caught while reading the listing, before returning findings.

## Known API-rejected title shapes (`site-processor.md`, `prompt.md`, `prompt-v2.md`)

Titles with genuinely IT-relevant bodies that still failed the title-only `skippedNonIt` check,
confirmed against the live API:

- **"Közmű SAP szakértő"** (2026-08-24, MVM Informatika Zrt.) — "közmű szakértő" (utility
  specialist) carries no IT token even though the body is SAP IS-U application support.
- **"Szoftverüzemeltető"** (2026-09-08, Direktor Szoftver Kft.) — "üzemeltető" (operator) alone
  isn't recognised, neither is "szoftver" alone. The same shape applies to any `<noun> +
  üzemeltető` title unless the noun itself is a recognised token.

`check_titles` (added 2026-09-08) now checks this authoritatively before a title reaches this
fallback path at all — see below.

## `check_titles` added to catch bounced submissions before a detail-page fetch (`site-processor.md`, `prompt.md`)

**Added 2026-09-08** after two runs in a row submitted findings that then bounced at
`submit_findings` time: `skippedNonIt` on titles that were genuinely IT roles by content
("Adatelemzési szakértő", "IT operátor (L2)") but matched none of the live `job_categories`
keywords with no visibility into them, and `skippedDuplicate` on a posting another source already
carried. Both cost a detail-page fetch and a reasoning pass for a result that was always going to
be rejected downstream.

## `experienceLiteral` must trace to real text, never a guess (`site-processor.md`, `prompt.md`)

**As of 2026-07-23**, the API hard-discards a bare level word in this field unless the title itself
independently confirms it, because that's exactly how a bare guess with zero textual backing
slipped through twice: **2026-07-21** at flexinform, and **2026-07-23** at sysdata-pse.com
("Tesztautomatizálási mérnök", which had no level word or years figure anywhere in the real
posting and was stamped "medior" anyway).

## Location resolution — a bare street address isn't "unstated" (`site-processor.md`, `prompt.md`)

**2026-09-03** — whitehair.hu's "Front-end fejlesztő" gave only "Nádorliget utca 7/a" as its
location (Budapest XI. kerület, postcode 1117), but was recorded as raw street text with none of
the API's recognized hint words, so the API's location backstop silently dropped it
(`skippedLocation`) even though the job is genuinely in Budapest.

## Dead links left in `listingUrls` — webshippy (`site-processor.md`)

**2026-08-24** — `/senior-fullstack-developer/` and `/robot-system-engineer/` were still linked
from webshippy's EN listing, both returned genuine "Az oldal nem található" 404 pages, and both
were recorded in `listingUrls` anyway, making the next run diff against a ghost forever.

## Runaway agent on webshippy — turn budget (`site-processor.md`)

**2026-08-24** — this agent ran past 30 tool uses on webshippy and had to be prompted by the
orchestrator to wrap up before it returned anything.

## One unresponsive page consuming a whole run — jobs.ozeki.hu (`site-change-check.md`, `site-processor.md`, `prompt.md`, `prompt-v2.md`)

**2026-08-17** — a Step 2 re-check fetch of `jobs.ozeki.hu` via bare `WebFetch` (no timeout
parameter, cannot be interrupted once it hangs) hung for THIRTY-THREE MINUTES without returning.
The run had to be killed manually before it ever reached Step 3 or its Step 4 submission — so it
submitted NOTHING, despite the repo, the token, the API and every filter working perfectly. Fixed
by fetching exclusively with `curl` wrapped in an outer shell `timeout`, never bare `WebFetch`.

## Lost work after a failed submission with no printed payload — Diligent and Qualysoft (`prompt.md`, `prompt-v2.md`)

**2026-08-26** — a run verified 12 findings across Diligent and Qualysoft, lost `submit_findings`
to two internal errors, and reported the failure correctly — but printed no payload, so a full
run's work was gone with no way to replay it by hand. Fixed by requiring the complete submission
payload to be printed verbatim whenever the final submit fails after retries.

## Tech-label drift — free text submitted instead of the canonical list (`prompt.md`, `prompt-v2.md`)

**2026-08-01** — rows were submitted with free-text technology labels ("SharePoint", "Power
Automate", "Fortinet, Palo Alto, Cisco, VPN", "Generative AI, Claude, Prompt Engineering") outside
the board's fixed canonical keyword list, inconsistent with every other source on the board, and
had to be manually corrected after the fact.

## Fan-out without a budget — prompt.md driven run imitating the orchestrator pattern (`prompt.md`)

**2026-09-04** — a run driven by `prompt.md` (the single-context, no-subagent design) dispatched
~12 parallel `Task` subagents anyway, imitating `prompt-v2.md`'s orchestrator pattern with none of
its budget guardrails. That fan-out burned the account's entire 5-hour usage allowance inside one
~22-minute run, and the run was killed by the rate limit before it ever reached the submission
step — every finding those subagents produced was computed and then lost, since the submission
call is the only thing that saves a run's work.
