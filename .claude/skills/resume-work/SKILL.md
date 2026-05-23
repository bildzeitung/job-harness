---
name: resume-work
description: Evaluate the CV with the resume-evaluator agent, then apply all cleanup items directly to the CV file.
allowed-tools: Read, Edit, Write, Bash, Agent
---

Run the resume-evaluator agent against the current CV. Once it returns its findings, apply every cleanup item it identifies — directly editing the file at `$RESUME_FILE`. Do not stop to ask for confirmation on individual items; apply all cleanup changes in one pass.

Steps:
1. Spawn the `resume-evaluator` agent (subagent_type: resume-evaluator). Pass it the full path to the CV file and instruct it to read the file itself. Ask it to return a structured list of cleanup items with exact before/after text for each change.
2. For each cleanup item in the returned list, apply the edit to the CV file at `$RESUME_FILE` using the Edit tool.
3. Report a summary of what was changed.
