# Job Harness Multi-User Evolution Part 1

Important: **Use the AskUserQuestion tool if you have uncertainty about the tasks; confidence level >=95%**

## Goal

To transform the job harness from a single to multi-user system for productization into a cloud-deployable application. This transformation will be done in a staged fashion in order to ensure reliable continued operation.

This is the first phase of this product evolution.

## Current Phase Goals

The user-facing inputs, both runtime and configuration, need to be data-driven.

### User profile

Each user needs to have their own profile identifier and active / inactive flag.

- create a script to add a user ID to the database
- provide a TUI panel to add/change user details
- provide a CLI option to specify the user (otherwise, pick it up from a dotfile)
- provide a web workflow to create an account
- provide a web workflow to change profile details

### Configuration items

The list of configurable items is a key-value pair and will change over time. A table of configuration items is needed.

Configuration items that will need to be migrated:

- [ ] `JOB_DATA_ROOT`
- [ ] `RESUME_FILE`
- [ ] `ADZUNA_APP_ID`
- [ ] `ADZUNA_API_KEY`

```
+------------------+       +-----------------+       +--------------------+
| Users            |       | UserConfigItems |       | ConfigItems        |
+------------------+       +-----------------+       +--------------------+
| PK str   UID     |       | FK str UID      |       | PK str ItemID      |
| binary   active? |<-m:n->| FK int ItemID   |<-m:n->|    str name        |
| datetime created |       |    str value    |       |    str description |
+------------------+       +-----------------+       +--------------------+
```

Consider the table structure above for storing users, configuration items, and linking them together.

### Source selection

The job seeker needs to read the job sources, currently kept in `$JOB_DATA_ROOT/jobs/sources-config.json`, from the database. Consider the table structure below:

```
+--------------+       +-----------------+       +--------------------+
| Users        |       | UserConfigItems |       | Sources            |
+--------------+       +-----------------+       +--------------------+
| PK str   UID |       | FK str UID      |       | PK str SourceID    |
|              |<-m:n->| FK int SourceId |<-m:n->|    str name        |
|   ...        |       |                 |       |    str description |
|              |       |                 |       | binary active      |
+--------------+       +-----------------+       +--------------------+
```

Add a memory to ensure that the `Sources` table is updated whenever the agents are altered (due to slugs changing, different boards being found, or brand new additions).

### Disqualifiers

Disqualifiers should be provided by the database and modifiable by the user.

The pre-filters should be a list with a multi-select. The user should also be able to add custom pre-filters as well.

The scoring modifiers should also be a multi-select by the named block. Users should be able to add their own blocks.

### Target roles

The database should hold lists of the following:

- Target Role Titles
- Title Keywords (for search queries and filtering)
- Domains of Interest

The user should be able to multi-select them, as well as add to the list.

Create a module to write the `target-roles.md` file. Use `~/home/job-data/target-roles.md` as a template for how the file should look. The TUI and web interface should have the same code path. That is, the file generation is a library that the TUI and web both use.

## Completion criteria

- [ ] Source selection is read from the database
- [ ] User can adjust source selection from the TUI or the Web UI
- [ ] `job-search` tool no longer asks for user input on sources
- [ ] Web is at parity with the TUI
- [ ] User can provide or modify all needed configuration items via TUI or web
- [ ] User can add / change / delete disqualifiers
- [ ] Target role data can be specified by the user
- [ ] `target-roles.md` file is generated from the database via TUI or web

## Constraints

This phase does not touch where output files are written. The `JOB_DATA_ROOT` should be configurable, but the phase does not scope to changing how outputs are written; that is for a later phase.
