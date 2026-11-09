# Company list → jobs: feasibility test run

Date: 2026-11-03 · Input: the 62 companies in the seed sheet (company name and careers URL only; no contact data used) · Status: **one test run, partly verified**

## Method

1. **Board check:** career-ops v1.38.0 `verify-portals.mjs` (read-only) against each careers URL. It reports whether a supported public job-board API can read the URL, and how many jobs are live.
2. **Careers-page check:** one polite fetch per page (robots.txt honoured, sequential, 1.5 s apart, honest User-Agent `HireTitan-feasibility-check/0.1`). Each page was classified by the job-board signatures in its HTML, the job links and job titles visible without JavaScript, and the text-to-script ratio.
3. **Not done:** a second pass to verify the boards found in step 2 through career-ops, and a retry of 4 SSL failures. Both were stopped before running. Rows marked *unverified* rest on the page check only.

## Results by group

| Group | Count | Companies | Route |
|---|---|---|---|
| **A. Public board API, verified live** | 9 | DevRev (Greenhouse, 39 jobs), Mitsogo (Greenhouse, 38), Workday (Workday, 20), SurveySparrow (Keka, 10), Full Creative (Recruitee, 8), Roanuz (Zoho Recruit, 5), Spendflo (Zoho Recruit, 4), Zocket (Keka, 2), Amazon (Amazon, live) | career-ops scan |
| **B. Board found behind the branded page, career-ops has a provider** *(unverified)* | 8 | Freshworks (SmartRecruiters), Zuper (Keka), KLA (Workday), Alation (Workday; Chennai roles visible), Conga (Workday), DTCC (Oracle HCM), PayPal (Eightfold), Viasat (iCIMS) | career-ops scan once the board URL is stored |
| **C. Board found, no career-ops provider** | 2 | Rocketlane, Growfin (Kula) | New adapter, or careers-page route |
| **D. Plain HTML page with jobs visible** | 6 | Superops, HappyFox, FourKites, Detect Technologies, Foodhub, Zumen | Careers-page fetch + AI extraction |
| **E. JavaScript-only page** | 4 | Securin, Appian, Qualcomm, Novac | Headless browser, maintainer lookup of the underlying board, or "check manually" |
| **F. No jobs visible without JavaScript** | 13 | Kissflow, Everstage, Walmart, Pickyourtrail, Trimble, UPS, Zuora, Finforz, Motorq, Agnikul Cosmos, Facilio, Gocharting, Expertusone | Maintainer lookup first (large companies here usually sit on Workday/Phenom); otherwise "check manually" |
| **G. robots.txt disallows fetching the page** | 4 | Disprz (Keka), ippopay, Toast, Klenty | Board API if one exists (Toast: likely Greenhouse, unverified); otherwise Gmail alerts / manual |
| **H. Points to a site we must not scrape** | 2 | Chargebee (LinkedIn jobs link), Gallabox (Wellfound, 403) | Gmail alerts / manual; check whether Chargebee has its own board |
| **I. Fetch failed (SSL, likely a local certificate-store issue)** | 4 | Athenahealth, Zoho, M2P Fintech, Aithent | Retry needed |
| **J. No careers URL in the sheet** | 10 | Culture Monkey, Pepul, Lumel, Backspace, Paperflite, Enqos, Entropik, Moneyforward, Remitbee, ContentStack | Fill in URLs, then re-test |
| **Total** | **62** | | |

## What this means

- **Works today, structured and reliable:** 9 companies (A).
- **Likely to work after storing the board URL:** +8 (B), so **about 17 via public board APIs**.
- **Workable through careers-page AI extraction:** +6 (D).
- So about **23 of 62 (≈37%)** are reachable with the planned design today, without a headless browser.
- **The biggest lever is maintainer resolution.** Groups F, E, I and J (31 companies) mostly need a person to find the real board or careers URL once. Many large companies here (Walmart, Trimble, UPS, Zuora, Qualcomm, Appian, Athenahealth) usually run Workday, Phenom or Eightfold behind their branded pages. A realistic target after one manual pass is **35–40 of 62**.
- **A headless browser would help only a few** (E plus some of F). Not worth the ~300 MB in R1; keep "check manually".

## Findings that change the design

1. **Keka and robots.txt (compliance, must resolve).** Keka-hosted careers pages (Zocket, SurveySparrow, Disprz) disallow crawlers in robots.txt, but career-ops' Keka provider reads them; its Disprz error mentions the careers page's `embedjobs` identifier, which suggests it parses the page. Constitution VII requires honouring robots.txt for careers pages. Before shipping Keka as a source, check whether the provider uses an API endpoint that robots.txt allows; if not, Keka companies go to the Gmail / "check manually" route. The same check applies to every career-ops provider we enable (record it in the plan for 002).
2. **Rule filter (cost).** Big employers (Amazon, Workday, KLA, Alation) return global job lists. **Decided 2026-11-03: rules first, AI optional.** W3 `search_run` filters with deterministic rules (location, title keywords, posting age, stack keywords) and makes no LLM calls by default; AI relevance is an optional on-demand step (W3b).
3. **Resolution tooling for the seed list.** The `companies` table needs per-row resolution status and a maintainer workflow: run discovery, open the page, paste the board URL, verify live, mark `verified`. This is the same flow a user follows for user-added companies (W8).
4. **Kula** (2 companies): small; decide in 002 whether to add an adapter or treat it as a careers page.

## Seed list as shipped (T057, 2026-11-08)

`backend/seed/companies.yaml` holds the 62 companies with company columns only (name, city, website, careers link). No contact, opening or note column was copied; `test_real_seed.py` checks this. Resolution pass, using the rules of this study and the provider allowlist:

| Resolution | Count | Companies |
|---|---|---|
| `verified` (board HireTitan reads) | 6 | DevRev, Mitsogo (Greenhouse), Workday (Workday), Full Creative (Recruitee), Spendflo (Zoho Recruit), Amazon (Amazon, search phrase "Chennai"). Each board address was built by `board_request` without error; the live check is the group A result above. |
| `careers_page` (careers page read, AI only if needed) | 36 | Every company with a careers link that is not in the next row |
| `check_manually` | 10 | Zocket, SurveySparrow, Disprz, Zuper (Keka: robots.txt not checked, so not read); Roanuz (Zoho Recruit on `zohorecruit.in`, which the board address builder does not support); Chargebee, Klenty, Gallabox (link goes to LinkedIn or Wellfound, never read); ippopay, Toast (robots.txt disallows) |
| `unresolved` (no careers link in the sheet) | 10 | Culture Monkey, Pepul, Lumel, Backspace, Paperflite, Enqos, Entropik, Moneyforward, Remitbee, ContentStack |

**Group B not verified.** Freshworks (SmartRecruiters, off by decision), KLA, Alation, Conga (Workday), DTCC, PayPal, Viasat have no board address stored. They are `careers_page` until someone finds the board URL and confirms it live; that is a maintainer lookup, not done here. The same goes for the group I retry (Athenahealth, Zoho, M2P Fintech, Aithent) and the group J links.

## Next checks (not yet run)

- Verify group B boards through career-ops (one read-only run).
- Retry group I with a proper certificate store.
- Check the Keka provider's request path against Keka's robots.txt.
- Fill in group J URLs and re-run both checks.
