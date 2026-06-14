# Spec 15 — Humanize Config Labels

Important: **Use the AskUserQuestion tool if you have uncertainty about the tasks; confidence level >=95%.** Decisions already made by the user are listed below — do not re-ask them.

## Constraint Updates

So far, the constraint has been to keep TUI and Web UI in sync. This spec rescinds that constraint. Future specs will move the web UI into a true multi-tenant app, but *right now* changes will focus on necessary backend changes.

Rather, the *TUI* is designed for use by a single user on their local machine. The *web UI* is (will be) designed to be a multi-tenant app.

## Goal

Create a set of human-friendly labels for Settings -> Config that can be internationalized in future.

Each key must have a corresponding label and help text.

## Database changes

This change will require database changes. 

- a table with supported locales needs to be created; seed this with en-US
- a many-to-many table for config item label & help text for a given locale is needed. This table has a composite key: (config_items key id, locale id), and the two data items of "label" and "help_text"

## TUI changes

- the TUI should be updated to use the labels for the user's locale
- the user needs to be able to set their locale

