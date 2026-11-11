# Sheet fixtures (synthetic only)

Everything here is invented. Names are "Example ..." or "Sample ...", links are placeholders
(`linkedin.com/in/...-example`), emails are at `example.com`. No real person or company appears.
Never replace these with a real spreadsheet (constitution VIII, FR-026).

## product_companies_sample.csv

Same shape as the maintainer's sheet: five empty rows and two empty columns before the header.
Matched against `backend/tests/fixtures/companies/seed_v1.yaml` (Example Alpha, Beta, Gamma).

| Row | What it tests |
|---|---|
| Example Alpha | matched by website (`www.` and trailing slash); 3 contacts with tags |
| Example Beta Inc. | matched by name only (suffix `Inc.` ignored); 1 contact |
| Sample Delta Pvt Ltd | unknown company, added as own; 1 contact |
| Example Gamma | contacts cell with no person, so it becomes a company note |
| (no name) | skipped, its contact is not saved |
| Example Beta + alpha website | matches two companies, skipped |
| Sample Epsilon | 25 people, first 20 kept and the row is reported shortened |
| Sample Zeta | note of 6,000 characters, shortened to 5,000 and reported |
| Sample Eta | labelled email and phone lines; 2 contacts |
| Sample Theta, Sample Iota | the same person name at two companies stays two contacts |
| Sample Kappa | no contacts, careers link present |
| Sample Lambda | one contact whose second line is not a link (kept as a note line) |

Rows in: 13. Matched: 3 (Alpha, Beta, Gamma). Added: 8. Skipped: 2.
**Contacts expected after import (SC-001): 30** = 3 (Alpha) + 1 (Beta) + 1 (Delta) + 20 (Epsilon)
+ 2 (Eta) + 1 (Theta) + 1 (Iota) + 1 (Lambda). The openings columns are ignored (FR-008).

## not_a_sheet.csv

A CSV with no company-name column; the importer must refuse it and list the headers it saw.
