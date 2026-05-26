# Job Harness Text UI

Implement additional features for the `tui` module that facilitate specific requests.

** Use the AskUserQuestion tool if you have uncertainty about this description ** 

# Features

## Job Pipeline Invocation

- if a job is in the "selected" state, then I want to be able to send it to Claude with the job-preparer agent 
- the agent must send the selected job through the pipeline so that the resume and cover letter are created
- the help text in the footer should be updated with the key to do this (key is: p, for Prepare)

## Job Details View

- the details view is sometimes larger than the available vertical window space
- I need keyboard bindings to scroll the job detail window. Use vim's j/k.

