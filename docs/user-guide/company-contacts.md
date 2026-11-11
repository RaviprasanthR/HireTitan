# Company contacts and notes

The Companies page keeps, for each company, the people you know there and one private note. It also shows whether you have applied to a job at that company. Everything here is your own data: it stays in your own install and HireTitan never contacts anyone.

## 1. Bring your company sheet in

If you keep companies in a spreadsheet (Google Sheets, Excel, LibreOffice), save it as CSV and import it:

1. In the spreadsheet, choose **File → Download → Comma-separated values (.csv)** (Google Sheets) or **File → Save As → CSV UTF-8** (Excel).
2. On the Companies page, press **Import / export**, then **Import a company sheet**, and choose the file.
3. Read the preview. Nothing is saved until you press **Confirm import**.

Only CSV is read; there is no Excel reader, so HireTitan needs no extra library for it.

### What the import does with each column

The header row may sit below empty rows and next to empty columns; HireTitan finds it. Column names are matched without regard to case or punctuation.

| Column (any of these names) | What happens |
|---|---|
| Org Name, Company, Company name, Name | **Required.** Matches the row to a company already on your list (by website first, then by name, ignoring "Inc.", "Pvt Ltd" and similar). A row that matches two companies is skipped and listed. |
| Location, Locations, City | Fills the city if the company has none. Never overwrites a value already there. |
| Company site, Website, Site, URL | Fills the website if empty; also used for matching. |
| Careers page, Careers, Careers URL | Fills the careers link if empty. |
| HR / LinkedIn contacts, LinkedIn contacts, Contacts | Read as people: one person per line group, `Name - Role [High]`, then their LinkedIn link, `email:`, `phone:`, `note:` lines. Text that is not a person is kept as part of the company note. |
| Notes, Note | Becomes the company note. A note you typed yourself is never replaced by an import. |
| Frontend openings, Backend openings | Recognised and **ignored**: openings in a sheet go stale, so HireTitan does not keep them. |
| Anything else | Listed as ignored in the preview. |

A company that is not on your list yet is added as your own company. Running the same import again adds nothing new: people are matched by name (or by their LinkedIn link when the name changed), and an empty cell never erases what is stored.

## 2. See and edit

- Each row shows the company, its city, **Applied** when you have marked a job there as applied, the number of contacts, and the start of your note.
- The company name opens the company's website; the globe icon opens the website and the briefcase icon the careers page.
- The arrow on the right opens the row: every detail HireTitan has about the company, then its contacts and the note. Add, edit or delete a contact there; only the name is required. LinkedIn links must be web addresses (`https://…`).
- Click a column title to sort (click again to reverse it). Use **Show** to list only companies with contacts or with an application, and the search box to find a company by name or city.
- On a job's page, the people you know at that company are shown with the job.

## 3. Export

**Import / export → Export CSV** saves your company list. By default the file has **no** contacts or notes. Tick **Include contacts and notes** to add them; the file then holds other people's names, emails and phones, so keep it private. A file exported with contacts can be imported again with **Import a company sheet** and gives back the same contacts and notes.

## 4. What is never sent anywhere

- Contacts and notes are **never sent to an AI**. The search, the relevance check and every other AI step cannot read them; an automated test fails the build if that ever changes.
- HireTitan **never opens or reads LinkedIn** or any contact link. Links are stored and shown; you click them yourself.
- HireTitan **never sends a message, email or application** to anyone.
- Contacts and notes are **not part of the shipped company list** and never leave your machine unless you export them.

## 5. Removing them

- Deleting a contact removes it at once (after you confirm).
- Deleting one of **your own** companies also removes its contacts and note. A company from the shipped list is only hidden, so its contacts stay.
- **Settings → Delete all my data** removes every contact and note, every company you added, and puts the shipped list back.
