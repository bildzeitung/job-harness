# Job Harness Laundry List

Important: **Use the AskUserQuestion tool if you have uncertainty about the tasks; confidence level >=95%**

## Work Items

Work through each of the following subsections. Each subsection is a different module.

### ALL python modules

- [ ] loading the `candidate-profile.json` seems like common code between a number of the modules. Pull it out into its own module. Look for other common items that could be similarlhy refactored into the common library.

### job-seeker

- [ ] the `api_search` calls could be done in parallel. Verify and if so, implement.
- [ ] below, a `job-seeker python script` is listed. This action was to `Generate INSERT statements for all postings`. Can this be moved into a script that reads the JSON and loads it into the DB? Generating the SQL and then using the statements seems inefficient. Also, since the script would use SQLAlchemy, we get better, more secure escaping.

### Bash calls

- [ ] there seem to be more processes hanging than usual. Is there a way to tell Bash() tool to timeout and retry if it gets stuck?

### tui

- [ ] In the company panel, the detail view, include a section with job listings related to that company
- [ ] In the job listing panel, add a column for the score; it should be the leftmost column

## job-seeker python script

```python
import json
d = json.load(open('/home/dmklein/job-data/jobs/search-2026-05-28.json'))
postings = d['postings']

# Build INSERT statements
statements = []
for p in postings:
   def esc(s):
       if s is None:
           return 'NULL'
       return \"'\" + str(s).replace(\"'\", \"''\") + \"'\"

   stmt = f'''INSERT OR IGNORE INTO postings (url, title, company, platform, post_date, applicant_count, employment_type,
location_note, description_summary, first_seen, status, job_description_text)
VALUES ({esc(p.get('url'))}, {esc(p.get('title'))}, {esc(p.get('company'))}, {esc(p.get('platform'))}, {esc(p.get('post_date'))},
{esc(p.get('applicant_count'))}, {esc(p.get('employment_type'))}, {esc(p.get('location_note'))},
{esc(p.get('description_summary'))}, '2026-05-28', 'new', {esc(p.get('job_description_text'))})'''
   statements.append(stmt)

print(f'Generated {len(statements)} statements')
# Write to a temp file
with open('/tmp/insert_postings.sql', 'w') as f:
   f.write(';\n'.join(statements) + ';')
print('Written to /tmp/insert_postings.sql')
"
```
