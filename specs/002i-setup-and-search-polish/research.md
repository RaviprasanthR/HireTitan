# Research: Setup and search polish

**Feature**: [spec.md](spec.md) · **Plan**: [plan.md](plan.md) · **Date**: 2026-11-16

Findings checked on the running install (Ravi's search of 2026-11-16, 44 companies, 20 jobs kept by the AI check) and in the code on `master` at `7557588`.

## R1. Where the first automatic approval runs

- **Decision**: Two triggers, one shared use case `approve_first_rules` in `search/application/rules.py`:
  1. `POST /onboarding/complete`, after setup is recorded, through a callback the composition root passes to the onboarding router (`OnboardingApiDeps.on_completed`). `setup` never imports `search`; `api_main` wires the callback from `search_wiring`.
  2. API start-up (`api_main` lifespan, next to the company seed load), for installs that finished setup before this feature or whose approval failed (FR-003).
- **Rationale**: Start-up covers existing installs without making a `GET` change data. The callback keeps the setup → search boundary the import-linter enforces.
- **Alternatives considered**: approve inside `GET /status` or when Explore loads (a read that writes; rejected); a frontend call after Finish (an old tab or a failed call leaves the dead end); a setup step that shows the rules (Ravi chose automatic).

## R2. "Never had approved rules" and running only once

- **Decision**: The use case approves only when no row of `app.search_rule_sets` has `approved_at` set (any status). It runs in one transaction under `pg_advisory_xact_lock(<fixed key for first rules>)`, re-checks inside the lock, proposes with the existing proposer, validates, and writes one approved row with `approved_by = 'auto'`. Any error (no profile, no preferences, rules not valid) is logged and swallowed: setup still finishes (FR-004).
- **Rationale**: `approved_at` already records every approval, so no new flag is needed to tell "never" from "once". Delete all truncates the table, so the next setup approves again (spec edge case). The advisory lock serialises a double Finish against start-up.
- **Alternatives considered**: a boolean in `app.settings` (a second source of truth that Delete all must also reset); relying on the unique "one approved" index (a second Finish would supersede the first instead of doing nothing).

## R3. Saving edits on the Search rules page

- **Decision**: New `PUT /search/rules/approved` takes the full rules, validates them with `SearchRules.validate`, and in one transaction writes a new approved version (`approved_by = 'person'`), supersedes the old one and discards any open proposal. New `GET /search/rules/suggested` returns the rules the proposer would suggest now, writing nothing. The old proposal endpoints stay for compatibility and the leftover-proposal case, but the page no longer uses "Suggest", "Approve" or "Discard".
- **Rationale**: Save becomes one atomic call (FR-015). "Start over with suggested rules" and "Update from my profile" fill the editor from `GET /search/rules/suggested` without creating rows (FR-017, FR-018). The version history stays complete.
- **Alternatives considered**: chaining the three existing calls from the browser (from-approved, PUT proposal, approve), which can leave a stray proposal half-way.

## R4. Where job descriptions come from (US6, FR-029)

Today every job reaches the AI check with an empty description: career-ops' providers return only title, place and link, and the runner passes `description` through only when a provider gives one. None of the recorded provider outputs in `backend/tests/fixtures/careerops/` carry one.

- **Decision**: A new HireTitan description reader, `search/infra/descriptions/`, runs **after the free rules and before the AI check**, only for jobs the rules kept, only in `rules_and_ai` searches (and in Check again). Per source:

  | Source of the job | Where the description is read | Host already reached by HireTitan? |
  |---|---|---|
  | Greenhouse | public job API `boards-api.greenhouse.io/v1/boards/{board}/jobs/{id}` (`content`) | yes (listing) |
  | Lever | public postings API `api.lever.co/v0/postings/{board}/{id}` (`descriptionPlain` + lists) | yes |
  | Ashby | public posting API `api.ashbyhq.com/posting-api/job-board/{board}` (`descriptionPlain`, matched by id; one call per board per search) | yes |
  | Workday | public job endpoint `{tenant host}/wday/cxs/{tenant}/{site}/job/{path}` (`jobPostingInfo.jobDescription`) | yes (in the request trace) |
  | Recruitee | public offer API `{board}.recruitee.com/api/offers/{slug}` (`offer.description`) | yes |
  | Amazon, Zoho Recruit, careers pages, anything else | the posting's own page through the careers-page fetcher: `JobPosting` JSON-LD `description`, else the main text of the page | page host |

  Every response shape is pinned by a synthetic recorded fixture and a contract test, as for career-ops (constitution V). The exact field names in the table are confirmed when each fixture is recorded (task in Phase 7); a vendor whose endpoint does not answer as expected falls back to the page read.
- **Politeness and limits**: the vendor calls go through a request allowlist (`infra/descriptions/allowlist.py`, the same format and robots check dates as `infra/careerops/allowlist.py`) enforced by a contract test; page reads go through the existing `CareersPageFetcher` (robots.txt, 2 s spacing per host, disk cache, 2 MB cap). Each read has a 20 s timeout. The text is sanitised and screened like any job text (constitution III), capped at 30,000 characters for storage and 1,200 for the AI card (existing `EXCERPT_MAX`).
- **After reading**: `skills_found` and `years_found` are recomputed with the existing `normalize` helpers, so the card the AI sees and the stored job both gain them.
- **Failure**: a description that cannot be read leaves the job as today (empty description) and marks `description_status = 'unreadable'` on the in-memory job so the AI is told (FR-034). It never stops the search; Stop and out-of-credit still end it between jobs.
- **Rationale**: Using the vendors' own public JSON is more reliable than their JavaScript-rendered pages (Workday and Ashby pages carry no text without a browser). All hosts are ones HireTitan already reads for listings, so no new kind of source is added (constitution VII).
- **Alternatives considered**: changing career-ops' providers (upstream, pinned; HireTitan does not patch it); reading every listed job's description (hundreds of extra requests for jobs the free rules already drop); a headless browser (heavy, against the lean image).

## R5. Area of work and words to avoid (FR-030, FR-031)

- **Decision**: `SearchRules` gains `areas: tuple[str, ...]` from a fixed set: `back_end`, `front_end`, `full_stack`, `mobile`, `data`, `qa`, `devops`, `other`. A reviewed seed file `backend/seed/work_areas.yaml` gives, per area, the signal words used to guess it and the title words to avoid for **other** areas. The proposer guesses areas from the person's target roles, recent job titles and skills (counted signals; ties keep both), then adds avoid words for areas that are clearly different (for example `back_end` → avoid "frontend", "front end", "front-end", "ui developer", "android", "ios", "mobile", "qa", "test engineer", "sdet"; `full_stack` avoids neither front-end nor back-end words). Avoid words carry origin `area:<name>` internally (not shown, FR-014) and can be removed.
- **Rationale**: Deterministic, free and explainable, like the 002 synonym table. It amends 002 FR-005's "only the person adds avoid words" (dated note in that spec).
- **Alternatives considered**: asking the AI for the area (adds a call and a prompt gate to setup); an "area" field in Preferences (changes the setup form, against FR-022).

## R6. Language and framework names in titles (FR-032)

- **Decision**: A reviewed seed file `backend/seed/tech_names.yaml` lists programming languages and major frameworks with their aliases (for example Java; JavaScript / JS; TypeScript; C# / .NET / dotnet; C++; Go / Golang; Python; Ruby / Rails; PHP / Laravel; Kotlin; Swift; Scala; Rust; React; Angular; Vue; Node / Node.js; Django; Spring). A pure rule in `search/domain/tech_names.py` finds the names a title mentions (word-boundary matching, so "Java" never matches "JavaScript" and "Go" needs a word boundary and a tech context such as "Go developer", "Golang", "(Go)"). The rule skips a job only when the title names at least one technology and **none** of the named ones are among the person's skills (`stack_keywords` of the approved rules, compared through the aliases). Reason: "needs Java, which is not in your skills" (several: "needs Java or Kotlin, which are not in your skills").
- **Rationale**: Catches "BackEnd (Java)" for free and records a visible, undoable reason (constitution I). "Java / Python Developer" is kept for a Python person.
- **Alternatives considered**: leaving all stack checks to the AI (works only when a description exists); matching words in descriptions (too many incidental mentions).

## R7. What the AI check is told (FR-033, FR-034) and prompt v3

- **Finding (bug)**: `search_wiring.profile_card_source` fills `ProfileCard.key_skills` from **preference** key skills only, which are empty unless typed in Preferences, so the AI check saw no skills for Ravi.
- **Decision**: `ProfileCard` becomes: `target_roles`, `areas` (from the approved rules), `main_skills` (profile skills plus preference key skills, deduplicated, languages and frameworks from `tech_names.yaml` first, then the rest, up to 30), `years_experience`, `seniority`, `recent_titles` (up to 3 job titles from the confirmed profile, newest first), `preferred_locations`, `work_modes`. The job card gains `description_status` (`read`, `unreadable`, `none`).
- **Prompt `judge_relevance` v3** (`prompts/judge_relevance/v3/`): relevant only when the job's area matches one of the person's areas, its main stack overlaps the person's main skills, and its level is within reach of the person's years; leave out a different area, a main stack that is not the person's, or a level far above or below. With no description: decide on title, company and place; leave out when the title points to another area or stack; otherwise keep and say the description could not be read. The schema, `role` rule and checks stay as in v2.
- **Evaluation gate (constitution IV)**: the `judge_relevance` eval set gains a synthetic back-end Python and Go profile (4.5 years) and about 40 postings: different area in the title, different stack in the title, generic titles with a description that decides, generic titles without a description, far-above-level roles, and true matches. Gate: precision and recall at least 90% overall as today, plus SC-008 (at least 95% of front-end, mobile, QA and Java roles left out; recall on relevant cases at least 95%), 0 unusable answers, run with `--repeat 3`. v3 becomes active (the registry's current version) only after the report passes and is committed.
- **Alternatives considered**: tightening v2 in place (prompts are versioned; a change needs a new version and its report).

## R8. Search panel states (US2)

- **Decision**: Frontend only. The panel shows a "searching" state while the start request is in flight and while the run has no outcome. Before `companies_total > 0` it shows only the indicator and "Searching your companies…". After that it adds one line, "Checked {companies_read} of {companies_total} companies · {added} new jobs so far", and a determinate bar for companies read. The indicator is a CSS sweep (`ht-searching`) with a static form under `prefers-reduced-motion`. Stop says "Stopping… jobs found so far are kept." End messages drop "batches". `BATCH_SIZE` is no longer imported by the panel.
- **Rationale**: The API already has every number needed (`companies_total` is 0 until planning finishes, which caused "0 of 0"). Progress still moves only when a group of companies is stored; the moving indicator covers the gaps (US2 AS3).
- **Alternatives considered**: per-company progress events from the worker (more events and code for little gain).

## R9. Explore rows (US5)

- **Decision**: Explore's `JobCardItem` becomes an expandable row like In pipeline's: the row has an expand button (`aria-expanded`, `aria-controls`), the title is an `<a target="_blank" rel="noopener noreferrer">` to the first-found source, and the expanded part renders a `JobDetails` component extracted from `JobDetailPage` (place, work mode, posted date, decision and reason, decision history, sources, description, injection warning, actions). `JobDetailPage` uses the same component, so both stay in step. Expanded details are fetched with the existing `GET /jobs/{id}` when a row opens.
- **Rationale**: One component for the row and the page; no new endpoint. Other links to `/jobs/:id` keep working (FR-028).
- **Alternatives considered**: putting the full detail in the list response (larger pages for every row).

## R10. Wider setup card (US4)

- **Decision**: `SetupLayout` takes `width: 'narrow' | 'wide'`; the Preferences and Review steps use `wide` (`max-w-6xl`), the name and resume steps stay `max-w-2xl`. Inside, the embedded Preferences page already switches to two columns at `lg`.
- **Rationale**: The two-column layout exists; the card was simply too narrow for it to apply.

## R11. Existing jobs already in Explore

- **Decision**: No automatic re-filtering of jobs already stored. The new rules and prompt apply to new jobs and to Check again (which now reads the description first). The quickstart tells Ravi how to clear the 20 jobs from the 2026-11-16 search (delete them in Explore, or Delete all and run setup again).
- **Rationale**: Re-judging stored jobs silently would hide jobs the person may have looked at; a "re-check all" action is a separate feature if wanted.
