---
name: resume-tailor
description: Customizes the resume/CV for a specific job posting — ATS bypass, gap analysis, competitive edge, and cover letter. Pass a job posting URL as the argument.
allowed-tools: Read, Edit, Write, Bash, Agent
---

Spawn the `resume-tailor` agent to tailor the CV for a specific job posting.

The skill argument (if provided) is the job posting URL. If no URL was given, the agent will ask the user for one.

Steps:
1. Run `bash -c 'echo $RESUME_FILE'` to get the resume path. Spawn the `resume-tailor` agent (subagent_type: resume-tailor). Pass it the job posting URL from the skill argument (if any), the resume path from `$RESUME_FILE`, and a reminder that it must never edit the original — all output files (tailored CV and cover letter) go under `./applications/`.
2. The agent will produce a tailored copy and a summary table. Report that summary back to the user, including the name of the output file.
