# Candidate job sources — implemented and deferred

This is the running catalog of job-posting sources the harness searches, plus the
ones we researched and chose **not** to wire in (with the reasoning, so the
decision doesn't have to be re-litigated each time someone asks "what about X?").

Researched 2026-06-04.

## Currently wired in

| Source | Mechanism | Agent / module |
|---|---|---|
| LinkedIn | MCP (browser session) | `job-seeker-linkedin` |
| Indeed | MCP | `job-seeker-indeed` |
| ZipRecruiter | MCP | `job-seeker-ziprecruiter` |
| Adzuna Canada | REST API (keyword) | `job-seeker-adzuna` → `api_search adzuna` |
| Greenhouse | Public ATS board API (slug fan-out) | `job-seeker-greenhouse` → `api_search greenhouse` |
| Lever | Public ATS board API (slug fan-out) | `job-seeker-greenhouse` → `api_search lever` |
| **Ashby** | Public ATS board API (slug fan-out) | `job-seeker-greenhouse` → `api_search ashby` |
| **Workable** | Public ATS widget API (slug fan-out) | `job-seeker-greenhouse` → `api_search workable` |
| **Recruitee** | Public ATS offers API (slug fan-out) | `job-seeker-greenhouse` → `api_search recruitee` |
| **Remotive** | Public remote-jobs API (keyword) | `job-seeker-remotive` → `api_search remotive` |
| **Himalayas** | Public remote-jobs API (recency feed) | `job-seeker-remotive` → `api_search himalayas` |
| **We Work Remotely** | RSS category feeds | `job-seeker-remotive` → `api_search wwr` |
| Open-ended research | WebSearch / WebFetch | `job-seeker-research` |

Ashby, Workable, and Recruitee were added to the `greenhouse` ATS agent (2026-06-04
/ 2026-06-05) because they share the same slug-fan-out mechanism and DB-enrichment
semantics (public board API, remote + Canada-OK, `remote_confirmed` +
`canada_confirmed`). Workable and Recruitee boards include on-site roles and skew
EU/SMB, so each fetcher folds the board's own remote flag (`telecommuting` /
`remote`) into the location text to drive the shared remote filter, and the
`canada_confirmed` flag is the same optimistic default the rest of the ATS bundle
uses — actual eligibility is enforced downstream by the scorer / `job-preparer`.

Remotive, Himalayas, and We Work Remotely are global remote-jobs boards bundled
into the `job-seeker-remotive` agent (the `remotive` source). They share a
different mechanism from the ATS sources — keyword search (Remotive), a recency
feed (Himalayas), and RSS category feeds (WWR) — and a different DB-enrichment
rule: `remote_confirmed` only, never `canada_confirmed`, because they confirm
remote but not a Canada-based office.

**Canada relevance:** Himalayas (`locationRestrictions`) and WWR (`region`) carry
an explicit per-posting geographic restriction, and Remotive carries
`candidate_required_location`. A shared `_canada_eligible()` helper drops any
posting whose restriction names only non-Canada regions (e.g. "USA Only",
"Europe Only") **at the source**, so a Canadian doesn't wade through ineligible
roles. Empty/unknown restrictions are kept (don't over-filter); final eligibility
is still confirmed downstream by the scorer / `job-preparer`.

### Adding more boards is config, not code

For the ATS sources (Greenhouse / Lever / Ashby / Workable / Recruitee), adding a
company is one slug in `api-search/api_search/sources_default.yaml`. No code change.
Verify a slug returns postings before adding it:

- Ashby — `curl https://api.ashbyhq.com/posting-api/job-board/{slug}`
- Workable — `curl 'https://apply.workable.com/api/v1/widget/accounts/{slug}?details=true'`
- Recruitee — `curl https://{slug}.recruitee.com/api/offers/`

## Other free, no-auth ATS APIs (easy follow-on sources)

Same slug-fan-out pattern as the wired-in ATS sources — each is one `fetch_*`
generator plus a registry entry in `api_search/sources.py`. Not yet wired in;
add when there's a concrete list of companies worth tracking on them.

| ATS | Public endpoint (`{slug}` = company board) | Notes |
|---|---|---|
| Personio | `https://{slug}.jobs.personio.de/xml?language=en` | XML (reuse `_strip_html`); EU-HQ companies |
| SmartRecruiters | `https://api.smartrecruiters.com/v1/companies/{slug}/postings` | Descriptions need a second `…/postings/{id}` call |

## Deferred: JSearch (Google for Jobs aggregator MCP) — the only paid candidate worth knowing

JSearch (OpenWeb Ninja, via RapidAPI) wraps **Google for Jobs**, aggregating
LinkedIn, Indeed, **Glassdoor**, ZipRecruiter and more in one query. It is the
only researched MCP that buys coverage we can't get free — specifically
**Glassdoor**, which the harness has no other path to. It would become a
`job-seeker-jsearch` MCP agent alongside the LinkedIn/Indeed/ZipRecruiter trio.

**Why deferred:** it's the only paid option, and everything else additive
(Ashby, Remotive, the ATS table above) is free. Revisit only if Glassdoor
coverage or single-call aggregation becomes worth a subscription.

### Pricing (RapidAPI / OpenWeb Ninja, as of 2026-06-04)

| Tier | Price | Included requests | Overage | Rate limit |
|---|---|---|---|---|
| Free | $0 | 200/mo (hard limit) | — | 1,000/hr |
| Pro | $25/mo | 10,000/mo | $0.003/req | 5/sec |
| Ultra | $75/mo | 50,000/mo | $0.002/req | 10/sec |
| Mega | $150/mo | 200,000/mo | $0.001/req | 20/sec |
| Pay-as-you-go | — | — | $0.005/req | 5/sec |

**Request budgeting:** one call returns ~10 jobs for a single page, so a real
run is `title × page`, not one call. ~8 target titles × 2–3 pages ≈ 20–25
requests per seek run; at a run every few days that's ~150–400/month — right at
the edge of the **free tier (200/mo)** and comfortably inside **Pro ($25/mo)**.
The free tier is enough to trial a `job-seeker-jsearch` agent before committing.

Sources: [JSearch (OpenWeb Ninja)](https://www.openwebninja.com/api/jsearch) ·
[RapidAPI pricing](https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch/pricing)

## Deferred / rejected: other MCP servers

| MCP server | Verdict |
|---|---|
| Adzuna Job Search MCP | **Redundant** — we already hit Adzuna directly via `api_search adzuna`. |
| Fantastic.jobs "Career Site Job Listing API" (Apify MCP) | **Redundant + paid** — re-wraps Greenhouse/Lever/Ashby/Workable, which we get free. |
| Apify Greenhouse / Workday-SmartRecruiters scrapers (MCP) | Redundant with direct ATS APIs; only Workday lacks a free API. |
| Greenhouse MCP (official, May 2026) | **Not applicable** — employer-side hiring connector, not a job-seeker search API. |

## Canada-centric, research/scrape only (no clean public API)

These Canada-focused boards have **no machine-readable feed**, so they cannot be
`api_search` sources (the module is API/RSS only, no HTML scraping). They live in
`job-seeker-research`'s **Round 2b: Canada-Centric Boards** `site:` queries:

- **Job Bank Canada** (`jobbank.gc.ca`) — the federal board. Offers only an
  **inbound** employer XML feed; `?rss=1` just returns the HTML search page and
  the dedicated RSS path 404s, so there is no outbound query API to consume.
- **NoDesk** (`nodesk.co`), **TrueUp** (`trueup.io/canada`),
  **Remote Rocketship** (`remoterocketship.com/ca`), **Arc.dev** — curated
  Canada-remote tech boards; no free query API.

Two boards from the original Tier-3 list **did** expose a feed and are now wired
in as `api_search` sources (see the table at the top): **Himalayas** (JSON
recency feed) and **We Work Remotely** (RSS category feeds), both filtered to
Canada-eligible postings.
