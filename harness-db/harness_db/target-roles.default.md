# Target Job Roles

This is the canonical list of job types you are targeting. Every `job-seeker`
searcher reads this file at startup (via `$JOB_DATA_ROOT/target-roles.md`)
instead of using hardcoded lists. **This is your file to edit** — it ships as a
sensible senior-engineering starter; tune it to your own search.

Positive *targets* live here. Hard *exclusions* live in
`$JOB_DATA_ROOT/disqualifiers.yaml`.

## Target Role Titles

- Principal Engineer
- Staff Engineer
- Distinguished Engineer
- Senior Staff Engineer
- Cloud Architect
- Platform Engineer
- Senior Software Developer
- Staff Software Developer
- Principal Software Engineer
- Head of Engineering

## Title Keywords (for search queries and filtering)

Any posting whose title contains one or more of these keywords qualifies by
seniority:

```
Principal, Staff, Distinguished, Senior Staff, Cloud Architect, Platform Engineer,
Head of Engineering,
Senior Software, Staff Software,
Senior Engineer, Senior Developer, Lead Engineer, Lead Developer,
Senior Backend, Senior Frontend, Senior Full Stack
```

## Domains of Interest

Replace these examples with the domains your resume actually targets:

- Cloud infrastructure
- Distributed systems
- AI / ML platform and infrastructure
- Developer platforms and internal tooling

## How to Use This File

Searchers read it from your job-data root:

```bash
cat "$JOB_DATA_ROOT/target-roles.md"
```

Use the **Title Keywords** section to drive search queries and filter results.
Do not hardcode role lists in individual agent files — edit this file instead.
