# Research: Explore row actions and outreach drafts (002k)

Decisions taken while planning, with the reason and what else was weighed. Code facts were read from `master` at `0e38ec3` on 2026-11-17.

## R1. A model for each case

- **Decision**: every AI task in this feature is its own versioned prompt, and each prompt's `meta.yaml` names its tier, as the existing prompts already do (`extract_profile`, `judge_relevance`). The tier picks the model through `platform/llm/models.yaml` (OpenAI today: `fast` = `gpt-5.4-mini`, `strong` = `gpt-6-astra`).

  | Task (prompt) | Tier | Why |
  |---|---|---|
  | `extract_job_keywords` v1 | **fast** | Reads untrusted job text into a small, strict list (constitution III). Bounded output and no judgement about the person, so the small model is enough and cheap to re-run per job. |
  | `draft_connection_request` v1 | **fast** | About 150 characters inside a strict schema; length, truthfulness and placeholder checks are deterministic, and a repair is cheap. |
  | `draft_referral_message` v1 | **fast** | A few hundred characters in a strict schema (body plus a separate easy-decline sentence) around facts HireTitan has already selected. Tone, length and truthfulness are checked by deterministic rules with one repair, so the small model is enough; it is also quicker and cheaper for a message the person may write several times per job (Ravi, 2026-11-17: "check if we need astra model for msg"). The eval runs both tiers; if fast misses SC-005 (≥ 95% first-attempt tone pass), `meta.yaml` moves to `strong`. |
  | `tailor_resume` v1 | **strong** | Chooses and rewords many bullets while keeping every fact and number; the most demanding task in the app. |

- **Rationale**: Ravi asked for the right model for each case. The tier-per-prompt mechanism exists, is recorded on every call (`llm_calls.model`) and lets an eval decide a change later without code. Changing a task's model is a one-line `meta.yaml` change plus its eval (constitution IV: from v2 a prompt must pass its eval).
- **Alternatives**: a per-task model map in `models.yaml` (rejected: duplicates the tier in `meta.yaml` and ties tasks to one provider's model names); one strong model for everything (rejected: slower and pricier for the extraction and the short note with no quality gain the checks would not already give).
- **Note**: `worker_main.py` records `model_for(provider, "fast")` as the ingest model whatever the prompt's tier. Not changed here (extract_profile is `fast`), but the new tasks take the model from the `LlmResult`, never from a fixed tier.

## R2. Contacts never reach the AI: placeholders

- **Decision**: the AI never receives the recipient's name, role, LinkedIn link or any contact field, and never the person's own name or contact details. The drafting prompts get only a **recipient kind** chosen from a closed list (`recruiter`, `hiring_manager`, `engineer`, `other`) and write the message with fixed placeholders (`{recipient_first_name}`, `{my_name}`). HireTitan fills them in deterministically after the checks, in the workflow node, from the draft row's `recipient_name` and the profile's contact name; those values are never put into a request (analysis U1: filling on the API's first read would make a GET write). The `contacts-stay-out-of-ai-paths` contract still holds because the node reads the draft's own snapshot, not contacts code, and the recorded-call test proves no request contains them. The kind is the person's own choice, pre-filled from the contact's role and confirmed in the form, so it is a four-value category they picked, not contact data (analysis P1). The kind is pre-selected from the contact's role by a keyword rule (for example "talent", "recruit", "HR" → recruiter; "manager", "lead", "head", "director" → hiring manager; "engineer", "developer" → engineer) and the person can change it.
- **Rationale**: feature 002b's FR-022 says contacts MUST NOT be sent to the AI provider in any call, enforced by the `contacts-stay-out-of-ai-paths` import contract and a recorded-call test. Placeholders also make it impossible for the model to misspell a name or invent a surname or title (spec FR-013), and they keep the person's own contact details out of prompts, as `extract_profile` already does by masking them.
- **Alternatives**: send the name and role (rejected: breaks FR-022 of 002b and the constitution's privacy aim); send the role only (rejected: still contact data, and the closed kind gives the tone hint the model needs).
- **Length**: for the connection request, the character budget given to the model is `200 − len(greeting with the real first name)`. The final text is counted after filling, and anything over 200 fails the check (spec SC-003).

## R3. Job description: extract once, structured and bounded

- **Decision**: a fast, tool-less step `extract_job_keywords` turns the stored, sanitized job description (`jobs.description`, up to 30 000 characters) into a strict schema: up to 30 keywords (each up to 40 characters, a skill, tool, domain or practice the posting asks for), up to 10 must-have items, and a one-line role summary (up to 160 characters). The result is stored per job with a hash of the description, and is re-used until the description changes. The drafting and tailoring prompts receive only this structured result, never the raw description (constitution III).
- **Rationale**: constitution III requires privileged steps to see only bounded, structured data derived from untrusted text. Storing it means the three actions on a job cost one extraction, and the ATS keyword match (R6) uses the same list.
- **Alternatives**: pass the raw description to the drafting model (rejected: constitution III); reuse `judge_relevance`'s output (rejected: it holds a verdict and a short role, not keywords).
- **Injection signals**: the existing sanitizer in `platform/untrusted` runs first; any signal it finds is stored with the keywords and returned as `injection_signals` with each draft and tailored resume, and the UI shows a notice: "This posting contains text that looks like instructions to an AI. HireTitan ignored it." (spec FR-006, EC-12).
- **Language**: the drafting and tailoring prompts write in the language of the person's profile, whatever the description's language (spec EC-05).

## R4. Truthfulness checks (deterministic)

- **Decision**: a pure domain module checks every draft and tailored resume before the person sees it:
  1. **Numbers and years**: every number in the output must appear in the cited profile facts (bullets, dates) or equal the computed years of experience (rounded down, also accepted as "N+").
  2. **Skills and tools**: every term from the existing technology table (`search/domain/tech_names.py`, loaded from the seed) that appears in the output must be in the profile's skills or in a cited bullet.
  3. **Organisations and titles**: in drafts, every capitalised name run that is not at the start of a sentence must be the job's company, a profile employer, institution, project or certification name, a known technology, or a placeholder. Anything else fails. In the tailored resume, employers, titles, dates and institutions are not written by the model at all: they are copied from the profile by id (R5), so they cannot be invented.
  4. **Citations**: each draft lists the profile fact ids it used; ids must exist in the confirmed profile.
- **Rationale**: constitution II asks for an automatic rejection of outputs whose numbers or skills are not in the cited facts. The profile's own `grounding.py` does the same job against resume text; this check runs against the confirmed profile instead and reuses its normalisation helpers.
- **Alternatives**: a second LLM as judge (rejected: the constitution wants deterministic checks, `docs/architecture.md` §"Truthfulness check"); a fuzzy bullet similarity threshold for rewording (rejected: rewording is allowed, so similarity would refuse good output; fixed facts plus numbers and terms carry the risk).
- **Risk**: rule 3 may refuse a harmless capitalised word ("Backend"). The repair turn names the word; the eval (SC-004) measures the false-refusal rate, and a common-word allow list is the fix if it is high.

## R5. Tailored resume shape: ids, not free text, for facts

- **Decision**: `tailor_resume` returns a strict schema: a rewritten summary; for each chosen experience, its profile id and an ordered list of bullets, each `{source: <experience id, bullet index>, text}`; an ordered list of profile skills (by value, only from the profile); and the ids of chosen projects. HireTitan builds the document from the profile: contact header, employer, title, dates and education come from the profile by id, and only the summary and bullet wording come from the model. A bullet's numbers and technology terms must appear in its own source bullet (R4).
- **Fallback**: after one failed repair, HireTitan shows a **plain reordering**: experiences and bullets in profile order, skills ordered by keyword match, the profile's own summary, and a message that the AI rewording was not used (spec US4 scenario 2).
- **Rationale**: copying facts by id makes "nothing invented" structural for the riskiest fields and keeps the check small.
- **Alternatives**: free-text resume plus a checker (rejected: much harder to verify); bullet selection only, no rewording (rejected: Ravi asked for an ATS-optimised version; clarified-requirements §7 allows rephrasing).

## R6. ATS keyword match

- **Decision**: deterministic. Keywords come from R3. A keyword is **backed** when its normalised form appears in the profile (skills, bullets, project technologies, certifications). Only backed keywords are passed to `tailor_resume` as wanted keywords. After tailoring and after every edit, **matched** = keywords found in the resume text; **missing** = the rest, each marked "not in your profile" or "in your profile but not in this resume". The score shown is matched ÷ all keywords.
- **Rationale**: clarified-requirements §7 defines the match this way and says only keywords the profile backs may be added (spec FR-017).

## R7. Running the AI: the existing workflow runner, one-node graphs

- **Decision**: two workflows registered in the worker's workflow registry, built like 002's `recheck` (`search/workflow/recheck.py`): `outreach_draft` (subject = the draft id) and `tailor_resume` (subject = the tailored resume id). Each is a one-node LangGraph graph run by the existing `WorkflowRunner` through the existing `run_workflow` queue task. The node runs: keywords (if missing or stale) → draft or tailor → checks → repair or fallback → store → publish an event on the existing event stream (`draft.ready`, `draft.failed`, `tailored_resume.ready`, `tailored_resume.failed`). The draft row keeps its `run_id`. The UI shows "Writing…" and updates from the event, with a refetch fallback. No interrupt: review edits the stored row afterwards.
- **Rationale**: the runner already gives retries with back-off, a user-facing failure message, the `AiUnavailable` pause (out of credit, key rejected) and `resume_paused_runs` when the key works again, which re-queues a paused draft by itself. Running in the worker keeps the API free of AI calls (only the worker is wired to the LLM) and survives a closed browser tab.
- **Alternatives**: a plain `procrastinate` task (rejected during task planning, 2026-11-17: it would re-build retry, pause and resume that the runner already has); the multi-node W5/W6 graphs with a review interrupt from `docs/architecture.md` (rejected for this slice: nothing to resume after the review); a direct call from the API (rejected: the tailor call can take 30 s or more, and the API has no LLM wiring).
- **Concurrency**: one running request per draft (job, kind, recipient) and per tailored resume; a second gets `409 draft_in_progress` / `409 resume_in_progress` (spec edge case). The row's state follows its run: `writing` while the run is queued, running or paused (with the pause reason shown), `failed` when the run failed.

## R8. PDF and DOCX output

- **Decision**: one document model renders to DOCX with `python-docx` (already a runtime dependency) and to PDF with `reportlab` (already used in tests; moved from the dev group to runtime). One template: single column, standard headings (Summary, Experience, Skills, Projects, Education, Certifications), built-in fonts, no tables, images, text boxes, headers or footers. Files are rendered on request and not stored.
- **Rationale**: both libraries are pure Python wheels for Windows, macOS and Linux (no system packages, constitution VIII "docker compose up"), and are permissively licensed (reportlab BSD, python-docx MIT), so the licence gate passes. Rendering on request keeps Delete all simple and the files always match the saved text.
- **Alternatives**: WeasyPrint from HTML (rejected: needs Pango and other system libraries, a bigger image, and harder Windows dev setup); storing the rendered files (rejected: two copies of the same data).
- **ATS check (SC-006)**: tests extract text from both files (`pdfplumber`, `python-docx`, already dependencies) and compare it with the document model line by line.

## R9. Where the code lives

- **Decision**: a new feature module `hiretitan.drafts` (api, workflow, infra, application, domain), covering outreach drafts, job keywords and tailored resumes. It reads jobs and contacts through `search.application`, and the confirmed profile through `profile.application`. Wiring in a new `drafts_wiring.py`, like `search_wiring.py`.
- **Rationale**: drafting is a different capability from searching; `search` is already the largest module. A separate module keeps the import contracts readable: `drafts.workflow` joins the `contacts-stay-out-of-ai-paths` contract as a source, so the AI path cannot import contacts code even by accident.
- **Alternatives**: inside `search` (rejected: grows an already large module, and the contacts contract would need finer carving); inside `profile` (rejected: drafts belong to jobs).

## R10. Explore row

- **Decision**: `PipelineControl` gets a `compact` form used by the Explore row: **I applied** and **I inquired** only (one click, today, the 002f starting resume, Undo). The full form (Resume used, Other date) moves into the expanded Explore row and stays where it is in In pipeline, the job page and the edit dialog. The "Other date" button is renamed **Pick a date** in the full form so it says what it does.
- **Rationale**: Ravi found the row confusing (2026-11-17). The behaviour of one click is unchanged, so 002e and 002f tests keep passing.
- **Alternatives**: remove the choices completely (Ravi chose to keep them in the details).

## R11. Tailored resume and the person's resumes

- **Decision**: a saved tailored resume is listed on the Profile page under a **Tailored resumes** heading (job title, company, date, Download PDF / DOCX, Open), and on its job. It is not added to the uploaded `resume_files` (those are parse inputs for the profile) and is not offered in the **Resume used** choice in this feature.
- **Rationale**: `resume_files` feed profile extraction and carry parse states; mixing generated files in would confuse both. Offering a tailored resume in **Resume used** is a natural follow-up, noted for later.
- **Alternatives**: store the PDF as a `resume_files` row (rejected: above).

## R12. Evaluation

- **Tier comparison**: `evals/outreach_drafts` runs each case on both `fast` and `strong` and reports the metrics side by side, so the referral message's tier (R1) is chosen on evidence.
- **Decision**: two eval sets, synthetic only (constitution VIII): `evals/outreach_drafts` (30 profile and job pairs, both kinds, including thin profiles, long and injected descriptions, and seeded fabrications in recorded outputs) and `evals/tailor_resume` (30 pairs). They report: fabrication rate (target 0), seeded fabrication detection (100%), connection request length (100% ≤ 200), not-pushy pass rate on first attempt (≥ 95%), keyword match, the false-refusal rate of the checks, and p95 latency per task from `llm_calls.latency_ms` against the plan's goals (10 s, 10 s, 60 s). Running them against a real model is a gate Ravi approves (small cost), as for earlier evals.
