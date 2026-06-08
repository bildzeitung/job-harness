# Job Harness Laundry List

Important: **Use the AskUserQuestion tool if you have uncertainty about the tasks; confidence level >=95%**

## Work Items

Work through each of the following subsections. Each subsection is a different module.

### job-seeker

There were a number of search issues during the last run. Analyze and recommend fixes and/or memory additions:

- Adzuna: 4 of 8 queries returned HTTP 429. Queries for "Staff Engineer", "Senior Software Developer", "Principal Engineer", "Cloud Architect" failed; 4 queries succeeded with 7 postings.
- Indeed: "FHIR healthcare engineer remote" returned zero results. Many queries surfaced non-software engineering results requiring manual filtering.
- Lever (research): WebFetch to jobs.lever.co for Aledade, Included Health, HighLevel, Wave HQ all returned HTTP 403. Job summaries synthesized from search snippets.
- Wellfound: HTTP 403 on careers page — relied on search result snippets.
- Tailscale: Page renders jobs dynamically; WebFetch returned only navigation scaffolding.
- Remotive/Workable/Recruitee: All returned 0 postings.
- Agent tool was unavailable (running as sub-agent); all sources executed inline.
- ZipRecruiter probe initially failed without country_admin_code; re-probed with US confirmed connectivity, then proceeded with CA for actual searches.
- Workable and Recruitee board slugs may need re-validation (stale slug risk).

### job-preparer

Side note on false positives: The scorer flagged that the defi disqualifier matched words like "defines"/"defining" (knocked out a PointClickCare Principal Software Engineer AI and a Best Buy Enterprise Architect posting), and remote - us matched "remote - us/canada" (knocked out a Docker Staff Backend Engineer). Worth fixing in disqualifiers.yaml — replace defi with defi or DeFi, and tighten remote - us to remote - us only.

### Python scripts

- read `./extraction-backlog.jsonl` and suggest harness optimizations

