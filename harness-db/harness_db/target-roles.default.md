# Target Job Roles

This is a sample of the canonical list of job types you are targeting. The live
values live in the harness DB (the source of truth) — edit them from the TUI/web
Settings → Target Roles panel. The `job-seeker` pipeline reads them directly with
`harness-db target-roles show` instead of using hardcoded lists. This file ships
as a sensible senior-engineering starter and is imported once on first run.

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

## How to Use This

The pipeline renders the live values straight from the DB:

```bash
harness-db target-roles show
```

Use the **Title Keywords** section to drive search queries and filter results.
Do not hardcode role lists in individual agent files — edit them in Settings →
Target Roles instead.
