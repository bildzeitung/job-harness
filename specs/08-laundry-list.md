# Job Harness Laundry List

Important: **Use the AskUserQuestion tool if you have uncertainty about the tasks; confidence level >=95%**

## Work Items

Work through each of the following subsections. Each subsection is a different module.

### job-seeker

- [ ] when doing the Adzuna search, job-seeker wrote a python script. It should be using the `adzuna-search` Python module. Fix this. I asked Claude to course correct and it wrote yet another Python program to collect results. Correct the existing module if it does not provide all of the information in the way required.
- [ ] job-seeker wrote a python script for the Greenhouse search. Perhaps this be a python module, too. Given Adzuna and Greenhouse are similar (in that they are being queried via web API calls) perhaps a common, data-driven approach is better than another one-off module for Greenhouse.

### consolidator-module

- [ ] the module needs tests
- [ ] the `_dedup()` method seems complex; consider a Counter

