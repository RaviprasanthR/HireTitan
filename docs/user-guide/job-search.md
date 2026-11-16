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

When you finish setup, HireTitan sets up your search rules from your profile and preferences, so **Search now** is ready on Explore straight away. You can check and change them any time on the **Search rules** tab of Profile; nothing is hidden there.

The page shows the rules in three plain groups:

- **Jobs we keep:** the job titles you want (with close variants).
- **Jobs we leave out:** words to avoid in titles, places to skip, and how old a job may be. A job whose title names a language or framework you do not list (for example "Java Developer" when your skills are Python and Go) is left out too, with the reason "needs Java, which is not in your skills". A job that goes with a language you do have is kept: "Java / Python Developer" stays for a Python person, and a Django title is for a Python person.
- **What helps rank a job:** your area of work (back end, front end and so on), your skills and the places you prefer. When the AI check is on, it uses these to decide whether a job suits you. Work mode, seniority and years of experience come from Preferences.

HireTitan guesses your **area of work** from your roles, your latest job titles and your skills, and adds title words to avoid for areas that clearly differ (for a back end person: "frontend", "android", "QA" and similar). Remove any word you do not want, or change the area.

To change the rules press **Edit rules**, make your changes and press **Save rules**; they become the rules your searches use at once. **Cancel** changes nothing. **Start over with suggested rules** fills the editor with what your profile and preferences suggest now (nothing is saved until you press Save). If you change your profile or preferences, a note offers **Update from my profile**.

Rules come first: a job that breaks a rule is skipped before any AI is used. A skipped job is never deleted. Open the search summary, find it under **Skipped** and press **Restore**.

## 4. How a search runs and how to stop it

Jobs that pass the rules are judged in groups of 10 by the efficient (`fast`) model, which keeps only the ones that are relevant for your profile and gives a short reason for each. A job already judged is not judged again, so a repeat search only looks at what is new.

**Reading each job first.** Most job boards list only a title, a place and a link. Before the AI looks at a job that passed the rules, HireTitan reads the job's own text from where it was posted: the public job API of the board (Greenhouse, Lever, Ashby, Workday and Recruitee) or the posting's own page, using the same politeness rules as the rest of the search (robots.txt, spacing between requests, never a private address). The AI then judges the job on what it says, against your area of work, your skills and your years of experience: a front end role, or a Java role for a Python and Go person, is left out. If a job's text cannot be read, the AI decides on the title alone and keeps a plain title such as "Software Engineer"; the reason then ends with "Description could not be read." Open the job to see its text, and **Check again** reads it again.

**While it runs.** The panel says "Searching your companies…" with a spinning ring and a changing light phrase from the first second; the ring fills as companies are checked. Once the first company is read it adds "Checked 8 of 44 companies · 3 new jobs so far".

- **Stop.** Press **Stop** at any time. The batch being processed is stored, and **Continue searching** starts with the companies not yet read.
- **Always with the AI.** Every search uses the AI to judge the jobs. If the AI is not working (no key, or no credit), jobs that pass the rules are listed as "not checked by AI", and **Check again** on a job asks the AI later.

## 5. "Out of credit"

If the AI provider says your account has no credit left, the search stops after storing the batch it was on, and the page shows the provider's own message. Add credit on the provider's site, press **Check again** in the banner or in Settings, and start the search again. Nothing already found is lost.

## 5b. The Explore list

Click a job in Explore and it opens in place to show its place, why it is listed, the text of the posting, where it was found and how it was decided. The **job title** is a link to the posting itself on the company's site (it opens in a new tab). Opening the row does not leave the list.

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
