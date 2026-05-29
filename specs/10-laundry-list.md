# Job Harness Laundry List

Important: **Use the AskUserQuestion tool if you have uncertainty about the tasks; confidence level >=95%**

## Work Items

Work through each of the following subsections. Each subsection is a different module.

### job-seeker agents

A number of the agents have blocks that look similar to this:

```
## Search Requirements (NON-NEGOTIABLE)

Every job you surface MUST satisfy ALL of the following:
1. **Remote** — fully remote or remote-first (not "hybrid", not "remote in [specific city]")
2. **Canada-eligible** — explicitly open to Canadian candidates (not "US only", not requiring US work authorization)
3. **Seniority match** — titles from `seniority_keywords` in the candidate summary
4. **Employment type** — full-time, contract, or freelance; exclude internships and junior roles

Discard any posting that fails criteria 1–3.

## Search Strategy

Use `mcp__claude_ai_Indeed__search_jobs` with `country_code: "CA"` and `location: "remote"` for all queries. Run multiple queries to cover the candidate's domains:

- `search: "principal engineer"` — general principal level
- `search: "staff engineer cloud"` — staff cloud roles
- `search: "cloud architect"` — architecture roles
- `search: "principal software engineer"` — software principal
- `search: "distinguished engineer"` — distinguished level
- `search: "platform engineer senior"` — platform/infra
- `search: "FHIR engineer"` — healthcare interoperability
- `search: "ML infrastructure engineer"` — AI/ML platform
- `search: "senior staff engineer"` — senior staff
```

If this is to be *truly configurable* job harness, then this cannot be hard-coded, but rather must be user-driven. Evaluate the YAML inputs to the harness that exist already, along with the `candidate-summary.json` file. Determine the configuration gaps and propose where and what the user must supply information. For example, it seems like there is overlap between the search requirements and the dislqualifiers. Update the agents to uptake the data.

