# Seed data

Data files the app loads on start. They are shipped with HireTitan and updated through releases.

| File | Arrives in | What it holds |
|---|---|---|
| `companies.yaml` | T057 (needs the maintainer's company sheet) | The shipped company list: key, name, city, website, careers URL, job-board vendor and id, resolution status. **Company-level facts only.** No HR contacts, notes or any personal data (constitution VIII). |
| `title_synonyms.yaml` | T017 | Role phrases and their synonyms, in English, used to propose and apply search rules. |

The company loader (T016) inserts new rows and updates only rows the person has not edited, hidden or deleted. Tests use synthetic copies in `tests/fixtures/companies/`, never this folder.
