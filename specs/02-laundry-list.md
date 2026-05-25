# Job Harness Laundry List

A laundry list is a checklist of items to improve the harness.

## Changes

- [x] The Adzuna work is writing Python scripts. Evaluate whether an MCP server like the one for Indeed or ZipRecruiter would be the right approach here, or whether a simple python module is enough.
  > **Decision**: Keep the Python script approach. The Indeed and ZipRecruiter MCPs are external services provided by claude.ai — not something we built. There is no external Adzuna MCP server. The current inline-script approach in the agent works correctly and adding a custom MCP server would be unnecessary complexity.

- [x] The TUI could use a refresh feature. Map this to the "r" key.

- [x] Revise the Docker invocations to use my UID and GUID
  > sqlite-mcp.sh: added `--user $(id -u):$(id -g)`. LinkedIn MCP moved to a wrapper script `scripts/linkedin-mcp.sh` with the same flag; `.mcp.json` updated to use it.

- [x] job-preparer was complaining about not having TeamCreate to run in parallel. It runs in a sub-agent context so double-check the structure and ensure that it can parallelize the work properly.
  > `TeamCreate` and `TeamDelete` were missing from the `tools:` frontmatter in job-preparer.md. Added both.

- [x] add the post-task reflection and error logging prompt below to all agents

- [x] preparing a customized resume + cover letter should be something invoked by the user in response to seeing the rankings. Once scoring and ranking is completed, and the report presented to the user, the AskUserQuestion tool should be called to solicit which resumes and cover letters should be produced.

- [x] remove the GMail (job-seeker-email) from the job-seeker pipeline; keep the agent for the job-seeker-email skill, however


## Post-task Reflection and Error Logging

- [ ] **Self-Diagnosis**: Were there any errors, logic failures, missed edge cases, or tool malfunctions?
- [ ] **Log the issue**: If problems occurred, populate a `<problem_log>` block with:
  - <timestamp>YYYY-MM-DD HH:MM:SS</timestamp>
  - <issue_description>Exact nature of the problem</issue_description>
  - <root_cause>Why did this happen? (e.g. hallucinated context, bad tool parameter)</root_cause>
  - <resolution_attempt>What did you do to correct it? (Or note if human intervention is needed)</resolution_attempt>
- [ ] If no problems occurred, simply output <problem_log>NONE</problem_log>.

Never hide errors or attempt to cover up failed tool calls. Transparency is mandatory.
