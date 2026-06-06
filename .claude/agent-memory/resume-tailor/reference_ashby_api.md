---
name: Ashby Job Posting Access
description: Public API endpoint for fetching Ashby-hosted job descriptions (any company that uses Ashby for hiring)
type: reference
---

Ashby exposes a public job board API for any company hiring through their ATS. Use it when a posting URL is JavaScript-rendered and not scrapable via curl.

**Endpoint pattern:** `https://api.ashbyhq.com/posting-api/job-board/<companyslug>?includeCompensation=true`

Returns JSON with a `jobs[]` array. Each job has `id`, `title`, `location`, `descriptionPlain`, `descriptionHtml`, `compensation`, `jobUrl`, and `applyUrl`.

**Why:** Ashby's hosted job pages (jobs.ashbyhq.com/<company>/<uuid>) are client-side React apps. curl only gets the SPA shell. The API gives the full description as plain text.

**How to apply:** When given an Ashby job URL, extract the company slug from the URL and hit the API to retrieve the full posting. This is faster than browser-rendering and provides the raw text needed for keyword analysis.
