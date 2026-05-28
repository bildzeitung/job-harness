# Job Harness Laundry List

Important: **Use the AskUserQuestion tool if you have uncertainty about the tasks; confidence level >=95%**

## Work Items

Work through each of the following subsections. Each subsection is a different module.

### tui

- [ ] `app.py` is too complicated. Refactor it so that the company panel is a custom widget.
- [ ] custom widgets (scorer_panel, company_panel) should live in their own subdirectory.
- [ ] to explore company data, create a detail view that pops up in the same way that the job listing works
- [ ] i want to be able to mark a job as "rejected". This is a terminal state that means the user has indicated they will not apply to a job in ("selected", "scored", "new") state. The new state will need to be added to the `docs/`, too.

