# Job Harness Laundry List

Important: **Use the AskUserQuestion tool if you have uncertainty about the tasks; confidence level >=95%**

## Work Items

Work through each of the following subsections. Each subsection is a different module.

### tui

- [x] need a way to close the output window after scoring completes

### ALL agents

- [x] the set of hard disqualifiers are hard-coded. Refactor to centralize this in one place that the user can configure this themselves
- [x] add the job-seeker-company agent, as specified below
- [x] add a table linking company records to job postings (that is, a 1:N relationship between jobs and companies)
- [x] add direction to insert a row in the linking table for each job written to the DB
- [x] ensure that company records are inserted before job records

## job-seeker-company agent

This agent researches companies recorded in the database, recording the information to expedite future job searches. In particular, each company should have at least one URL for where its career (job) postings are, along with any notes on how to fetch jobs and job descriptions from the site.

### Features

The agent should:

- [x] fill-in missing company data or explain why it cannot be found
- [x] write a summary report of all actions taken

