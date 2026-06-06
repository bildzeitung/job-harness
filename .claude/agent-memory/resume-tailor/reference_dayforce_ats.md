---
name: dayforce-ats-access
description: How to extract Dayforce job postings from jobs.dayforcehcm.com URLs (Next.js __NEXT_DATA__)
metadata:
  type: reference
---

Dayforce HCM job postings at `https://jobs.dayforcehcm.com/en-US/mydayforce/alljobs/jobs/<ID>` are Next.js-rendered pages. The full job description lives inside `__NEXT_DATA__` JSON embedded in the page HTML.

**Why:** The visible page is hydrated client-side; a naive `curl` returns a shell. The original LinkedIn-sourced URL (with `?src=LinkedIn`) returns 0 bytes due to redirect handling differences. The API endpoint `jobs.dayforcehcm.com/api/v1/...` returns 404.

**How to apply:**
1. Fetch the URL without query params: `curl -L -A "Mozilla/5.0" "https://jobs.dayforcehcm.com/en-US/mydayforce/alljobs/jobs/<ID>"`
2. Extract `__NEXT_DATA__` JSON: `re.search(r'__NEXT_DATA__[^>]*>(.+?)</script>', html)`
3. Job content is at `data['props']['pageProps']['jobData']`:
   - `jobTitle`, `jobReqId`, `postingExpiryTimestampUTC`
   - `jobPostingAttributes` (JobFamily, JobFunction, HiringMinRate, HiringMaxRate)
   - `jobPostingContent.jobDescriptionHeader` (company blurb, HTML)
   - `jobPostingContent.jobDescription` (the actual JD, HTML with `<ul>/<li>`)
   - `jobPostingContent.jobDescriptionFooter` (boilerplate, salary notes)
