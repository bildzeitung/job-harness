# Job Harness Laundry List

Important: **Use the AskUserQuestion tool if you have uncertainty about the tasks; confidence level >=95%**

## Work Items

Work through each of the following subsections. Each subsection is a different module.

### job-seeker

There were a number of search issues during the last run. Analyze and recommend fixes and/or memory additions:

- ZipRecruiter: Initial probe with location_types: ["REMOTE"] only returned "Need a location and country code" error. All subsequent searches resolved by adding location: Canada, country_admin_code: CA. MCP server was functional throughout.
- Indeed result quality: Searches for "principal engineer" and "staff engineer remote" returned heavily mixed results (civil engineers, mechanical engineers, HVAC technicians, structural engineers). Only 6 of ~50 returned results were relevant software engineering roles. The Indeed CA API does not filter well by software/tech domain when queries are broad.
- hnhiring.com (WebFetch): https://hnhiring.com/june-2026 returned HTTP 403 Forbidden. Research fallback was covered by direct WebSearch against the HN thread, which surfaced Albert's posting via extracted text.
- jobs.ashbyhq.com (WebFetch): All three Ashby individual job pages (hopper/1f6ce154..., hopper/3f6f6ded..., alan/a8c15c2a...) returned only the string "Jobs" — these pages are JavaScript-rendered and not accessible via WebFetch. Job entries were written using metadata extracted from the WebSearch results that referenced them.
- wellfound.com (WebFetch): Returned HTTP 403 Forbidden. Wellfound data was extracted from WebSearch snippets only.
- Greenhouse board 404s: dbt-labs and airbyte boards returned 404 Not Found — these companies likely migrated off Greenhouse.
- Lever board 404s: scale and weights-biases boards returned 404 Not Found.
- Lever returned 0 postings: All matched boards were either 404 or produced zero senior engineering results against the candidate profile.

### Python scripts

- read `./extraction-backlog.jsonl` and suggest harness optimizations

