# Job search

HireTitan finds jobs on the careers sites of the companies on its list, keeps the ones that fit your profile and shows them in one list. It reads job postings only. It never applies, sends a message or signs in anywhere for you.

## 1. Where jobs come from

- **Company job boards.** For each company on your Companies page, HireTitan reads the public job board of the company's hiring system through the bundled career-ops tool: Greenhouse, Lever, Ashby, Workday, Recruitee, Zoho Recruit and Amazon. Only the board's public address is requested, and only hosts on a fixed allowlist.
- **Careers pages.** A company with no known board is read from its own careers page. HireTitan checks the site's `robots.txt` first, waits at least 2 seconds between requests and caches pages on disk. It looks for structured job data first, then for job-shaped links. If the AI page reading is switched on, it may be used when a page has text but no jobs found; it can only return links that are on the page.
- **Jobs you add yourself.** **Add a job** on the jobs page takes a link and the description you paste. HireTitan does not open the link.

SmartRecruiters and Keka are not read, because their sites do not permit it or have not been checked. Companies that use them stay on your list and appear under **Check manually**.

## 2. Why some companies say "Check manually"

A company is listed there when HireTitan cannot read its jobs by the rules above: the careers page asks robots not to fetch it, needs a login, is built so that no jobs can be found in it, or its board is one HireTitan does not read. The list shows the careers link and the date last checked, so you can open the page yourself. A failed company never stops a search.

## 3. What the search rules do

On the **Search rules** tab of Profile, HireTitan proposes rules from your profile and preferences: the job titles you want (with close variants), places, how old a posting may be, and words that rule a job out. You edit them and press **Approve**. Rules come first: a job that breaks a rule is skipped before any AI is used. A skipped job is never deleted. Open the search summary, find it under **Skipped** and press **Restore**.

## 4. How a search runs and how to stop it

Jobs that pass the rules are judged in groups of 10 by the efficient (`fast`) model, which keeps only the ones that are relevant for your profile and gives a short reason for each. A job already judged is not judged again, so a repeat search only looks at what is new.

- **Stop.** Press **Stop** at any time. The batch being processed is stored, and **Continue searching** starts with the companies not yet read.
- **Rules only.** Turn on **Rules only** to run with no AI at all. Jobs that pass the rules are then listed as "not checked by AI". **Check again** on a job asks the AI later.

## 5. "Out of credit"

If the AI provider says your account has no credit left, the search stops after storing the batch it was on, and the page shows the provider's own message. Add credit on the provider's site, press **Check again** in the banner or in Settings, and start the search again. Nothing already found is lost.

## 6. Applied and inquired

Home has two tabs. **Explore** lists new jobs to look at. **In pipeline** lists the jobs you have applied to or asked about, as a table of company, role, date, status (green **Applied**, blue **Inquired**) and source.

Each job has two one-click buttons. **I inquired** is for when you asked about a job but have not applied. **I applied** is for when you applied, including after an earlier inquiry, and it turns the Inquired job into an Applied one. Both use today's date. For another date, open **Other date**, pick it and press the button. **Undo** is offered for 10 seconds, and on the job's own page. Later searches leave jobs in your pipeline alone, and the Companies page shows an **Applied** or **Inquired** chip for the company.

## 7. Your data

**Delete all my data** in Settings removes your jobs, search rules, run history, company edits and added companies, and puts the shipped company list back to its original state.
