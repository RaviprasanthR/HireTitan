# Preference defaults

A fresh HireTitan install starts with the neutral values below. Nothing here is specific to any person, and every value can be changed on the Preferences tab of Profile (or in the setup card's last step). A test (`backend/tests/unit/test_docs.py`) keeps this table in step with the code in `backend/src/hiretitan/preferences/domain/defaults.py`.

| Setting | Default | Why |
|---|---|---|
| Country | `IN` | The project starts with India-friendly defaults. Pick your own country first; it is also used to read phone numbers in your resume. |
| Currency | `INR` | Matches the default country. Pay is shown in lakhs per annum (LPA) for INR and as a yearly amount for other currencies. |
| Pay basis | `fixed` | Compare fixed pay with fixed pay. Switch to `total` if offers you compare include bonuses. |
| Notice period (days) | `30` | A common notice period. Change it, or set an earliest start date instead. |
| Work modes | `onsite, hybrid, remote` | Everything is allowed until you narrow it down, so nothing is hidden by surprise. |
| Job types | `full_time` | Most searches are for full-time roles. Add contract or internship if you want them. |
| Willing to relocate | `false` | Nothing is assumed about moving. |
| Target roles | `empty` | Only you know the roles you want. At least one is needed before preferences can be saved. |
| Seniority levels | `empty` | Not guessed from your resume. |
| Key skills | `empty` | After a profile is confirmed, the page offers your skills as one-click suggestions. |
| Preferred locations | `empty` | Add cities with their country. |
| Blocked locations | `empty` | Nothing is excluded unless you say so. |
| Preferred companies | `empty` | Not assumed. |
| Companies to avoid | `empty` | Not assumed. |

Also empty by default: years of experience (a number you type, never worked out from your profile), minimum and target pay, and the earliest start date.
