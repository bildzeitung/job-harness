# Job Harness Text UI

Implement a read-only TUI for the Job Harness so that the user can explore the current state of the job database.

** Use the AskUserQuestion tool if you have uncertainty about this description ** 

# Screen Layout

```
+------------------+------+-------+
| TABLE HEADER     | DATE | STATE |
+------------------+------+-------+
| Short Job Name | 2026/05/01 | new |
| Short Job Name | 2026/05/02 | scored |
...
+------------------+------+-------+
Up / Down: Select job  <Enter>: Expand listing
```

# Features

## Configuration

- read the location of the job database from `.claude/settings.local.json`

## Job Listing Table

- list the jobs, starting from the most recent 
- show a short job name (company + position?)
- show the date the job was entered in to the DB
- show the state the entry is in

## Job State

- assign each job state a colour
- for example, 'new' could be green; terminal states could be 'red'; non-terminal states 'blue'

## User interaction

- the top row of the Job Listing Table should initially be in a "selected" state
- the arrow keys should be able to select the next or previous row
- there may be enough data such that the data spans multiple screens; allow it to scroll
- PgUp and PgDown should scroll the table one page
- hitting Enter should toggle a display of the full data available for a job

# Constraints

- implement in Python
- use Textual to create the UI
- the database is SQLite
- use a data mapper of some sort (SQLAlchemy?)
