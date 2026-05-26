# Job Harness Laundry List

Important: **Use the AskUserQuestion tool if you have uncertainty about this description**

## Work Items

Work through each of the following subsections. Each subsection is a different module.

### tui

- [ ] allow the user to choose which column to sort by; use must be able to use the keyboard to choose the sort column
- [ ] by default, jobs should be listed by state, then date, then job title
- [ ] states are ordered as follows: selected, scored, new, applied, skipped

### agents

- [ ] the job database lists jobs in the `new` state; i need a way to run the harness so that these are either scored or skipped; this possibly relates to the next item where jobs seem to stay "new".
- [ ] in `docs/job-states.md` the diagram states "soft skill mismatch (excluded this run, re-evaluated next)". Does this really happen? Identify this case and fix it such that we do not stay in "new".

### docs

- [ ] Mermaid diagrams do not understand `\n`. Use `<br>` instead.
