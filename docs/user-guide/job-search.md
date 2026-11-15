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

## 7. Interview tracking

Open a job in **In pipeline** with the arrow at the end of its row (or on the job's own page) to keep your own record of how it went. Nothing here is sent anywhere or written for you.

- **Point of contact:** name, role, email, phone and LinkedIn link of the person you deal with. Only the name is needed.
- **How the job came:** direct, or through a hiring firm (type the firm's name), or not set.
- **Rounds:** press **Add round** and pick screening, technical, HR, managerial or other. Each round has a date and time, interviewers, a result (**Scheduled**, **Cleared** or **Failed**) and feedback. Rounds are numbered 1, 2, 3; removing one does not renumber the rest. Once a round is **Failed**, no new round can be added.
- **Questions:** under each round, add the questions you were asked and, if you like, your answer.
- **Status:** the Status column follows your rounds: **Applied** or **Inquired** until the first round, then **Round 2 scheduled**, **Round 1 cleared**, or **Failed in round 2**. A failed round wins over later ones.

Details can only be changed while the job is Applied or Inquired. If you undo that mark, what you recorded stays and can be read. If you remove the job, its details go with it. If you merge two duplicate jobs, the job you keep also gets the contact, source and rounds it was missing.

Unsaved edits are never dropped silently: closing the row, leaving the page or closing the tab asks first.

**What stays private:** these notes live only in your own database. They are never sent to an AI, never fetched or opened, and **Delete all my data** removes them.

## 8. The resume you used

HireTitan keeps the resume files you uploaded on the Profile page. For each job in your pipeline you can say which one you used, so months later you still know which version a company received. It is a label for your own reference: HireTitan does not attach, send or change any resume.

- **While marking a job:** beside the date, **Resume used** lists your stored files (newest first) and **None**. It starts on the resume you chose the last time you marked a job, or on the job's own resume when it already has one. Leave it alone and **I applied** stays one click. If you have no stored file, the choice is not shown.
- **Later:** in a job's edit card (the pencil), **Resume file** and **Save resume** set, change or clear it. Closing the card with an unsaved change asks first.
- **Where it shows:** the **Resume** column of In pipeline (a long name is cut short, and the whole name shows on hover), and the details of the job: its row, its page and its edit card, with the day the file was added.
- **Undo** of an applied or inquired mark forgets the resume for that job.
- **If you remove a resume file:** the Profile page tells you how many jobs use it. Those jobs keep the file's name as a note marked **(removed)**, which you can clear from a job's edit card with **Clear**. To remove the name everywhere in one step, tick **Also clear the name from these jobs** in the removal dialog (it is off by default).
- **Merging duplicates:** the job you keep keeps its own resume, and takes the other job's only when it has none.

**What stays private:** the choice and the file name live only in your own database. They are never sent to an AI, and **Delete all my data** removes them.

## 9. Your data

**Delete all my data** in Settings removes your jobs, search rules, run history, company edits and added companies, and puts the shipped company list back to its original state.
