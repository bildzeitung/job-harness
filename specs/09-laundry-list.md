# Job Harness Laundry List

Important: **Use the AskUserQuestion tool if you have uncertainty about the tasks; confidence level >=95%**

## Work Items

Work through each of the following subsections. Each subsection is a different module.

### ALL python modules

- [ ] loading the `candidate-profile.json` seems like common code between a number of the modules. Pull it out into its own module. Look for other common items that could be similarlhy refactored into the common library.

### job-seeker

- [ ] the `api_search` calls could be done in parallel. Verify and if so, implement.

### Bash calls

- [ ] there seem to be more processes hanging than usual. Is there a way to tell Bash() tool to timeout and retry if it gets stuck?

