# Data model: Explore row actions and outreach drafts (002k)

Migration `0021_drafts` (parent `0020_first_rules`), schema `app`. Three new tables, no change to existing tables. All ids are UUIDv7. Delete all my data empties every `app` table already (`setup/application/delete_all.py`), and a test confirms the three new tables are included.

## job_keywords

What `extract_job_keywords` read from one job's description (research R3). One row per job.

| Column | Type | Rules |
|---|---|---|
| `job_id` | uuid PK, FK `jobs.id` ON DELETE CASCADE | |
| `description_sha256` | text | 64 chars; the row is stale when the job's description hash differs |
| `role_summary` | text | ≤ 160 chars |
| `keywords` | jsonb | array of ≤ 30 strings, each 1–40 chars, de-duplicated case-insensitively |
| `must_have` | jsonb | array of ≤ 10 strings, each 1–80 chars |
| `injection_signals` | jsonb | array from the untrusted-text screen; may be empty |
| `prompt_version`, `model` | text | as recorded by the call |
| `created_at` | timestamptz | |

## outreach_drafts

One current draft per job, kind and recipient (spec FR-008).

| Column | Type | Rules |
|---|---|---|
| `id` | uuid PK | |
| `job_id` | uuid FK `jobs.id` ON DELETE CASCADE | |
| `kind` | text | `connection_request` \| `referral_message` |
| `recipient_contact_id` | uuid NULL, FK `company_contacts.id` ON DELETE SET NULL | set when picked from contacts |
| `recipient_name` | text | 1–120 chars, cleaned; a snapshot, kept if the contact is removed |
| `recipient_role` | text NULL | ≤ 120 chars |
| `recipient_kind` | text | `recruiter` \| `hiring_manager` \| `engineer` \| `other` (the only recipient value the AI sees, R2) |
| `recipient_key` | text | `contact:<id>` or `typed:<lower(name)>`; UNIQUE (`job_id`, `kind`, `recipient_key`) |
| `status` | text | `writing` \| `ready` \| `failed` |
| `run_id` | uuid NULL, FK `workflow_runs.id` ON DELETE SET NULL | the `outreach_draft` run that writes it (research R7) |
| `template` | text NULL | the checked AI text with `{recipient_first_name}` / `{my_name}` placeholders; ≤ 2000 chars |
| `text` | text NULL | the filled text the person sees and edits; ≤ 2000 chars (connection request: the save is allowed above 200 but flagged, spec FR-011) |
| `source` | text NULL | `ai` \| `fallback` (fallback = basic template from profile facts, US2 scenario 4) |
| `edited` | boolean | default false; true after the person saves a change |
| `cited_fact_ids` | jsonb | array of profile fact ids |
| `failure_reason` | text NULL | plain words for `failed` (AI unavailable, out of credit, no profile) |
| `prompt_name`, `prompt_version`, `model` | text NULL | null for a fallback with no AI call |
| `created_at`, `updated_at` | timestamptz | |

**States**

```text
(request) ──> writing ──> ready ──(person edits)──> ready, edited = true
                 │
                 └──> failed ──(retry)──> writing
ready ──(regenerate, person asked)──> writing   # replaces template and text
```

A request while the same row is `writing` → `409 draft_in_progress`. While `writing`, the API reports the run's state: a paused run (out of credit, key rejected) is shown with its reason and resumes by itself when the key works again; a failed run turns the row to `failed`, so a retry is allowed.

**Filling placeholders**: the AI writes `template` with placeholders. After the checks, the workflow node fills them from the row's own `recipient_name` (first word) and the profile's contact name, runs the length check on the filled text, and saves `template` and `text` together. The names are never put into a request (research R2). Reads have no side effects.

## tailored_resumes

One tailored resume per job (spec FR-019).

| Column | Type | Rules |
|---|---|---|
| `id` | uuid PK | |
| `job_id` | uuid UNIQUE, FK `jobs.id` ON DELETE CASCADE | |
| `profile_version_id` | uuid NULL, FK `profile_versions.id` ON DELETE SET NULL | the profile version it was built from (a snapshot, spec edge case) |
| `status` | text | `writing` \| `ready` \| `failed` |
| `run_id` | uuid NULL, FK `workflow_runs.id` ON DELETE SET NULL | the `tailor_resume` run |
| `document` | jsonb NULL | the resume document the person sees and edits (below) |
| `keyword_match` | jsonb NULL | `{matched: [..], missing: [{keyword, reason: "not_in_profile" \| "not_in_resume"}], score}`; recomputed on every save |
| `source` | text NULL | `ai` \| `fallback` (plain reordering, R5) |
| `edited` | boolean | default false |
| `failure_reason` | text NULL | |
| `prompt_name`, `prompt_version`, `model` | text NULL | |
| `created_at`, `updated_at` | timestamptz | |

States as for drafts, with `409 resume_in_progress`.

**Resume document** (JSON, validated by a Pydantic model; size ≤ 64 KB):

```text
contact:     {name, email?, phone?, location?, links[]}       # copied from the profile, never from the AI
summary:     string ≤ 1200
experience:  [{experience_id, employer, title, start, end, current, location?,
               bullets: [{text ≤ 400, source: {experience_id, index} | null}]}]   # source null = typed by the person
skills:      [string]                                          # only profile skills from the AI; the person may edit
projects:    [{project_id, name, description?, technologies[]}]
education:   [{education_id, institution, qualification?, field_of_study?, start?, end?, grade?}]
certifications: [{certification_id, name, issuer?, date?}]
```

Employer, title, dates, institutions and contact fields are copied from the profile by id when the worker builds the document (R5). The person can edit any field in the preview. Their edits are theirs and are not checked against the profile (spec US4 scenario 3); only AI output is checked.

## Read models (no table)

- **Recipient choice** for a job: the company's contacts from `search.application.contacts` (name, role, the pre-selected kind from the role keyword rule) plus "Someone else" (typed name and role).
- **Profile facts for drafting**: from the confirmed profile, a list of `{id, kind, text}` for experience bullets, skills, projects and certifications, plus computed years of experience. The person's name and contact details are left out (R2).
- **Tailored resumes list** (Profile page): job title, company, `updated_at`, `source`, `edited`, links.

## Relationships

```text
jobs 1 ── 0..1 job_keywords
jobs 1 ── 0..* outreach_drafts ──> 0..1 company_contacts (SET NULL)
jobs 1 ── 0..1 tailored_resumes ──> 0..1 profile_versions (SET NULL)
```

**Per item**: `DELETE /drafts/{id}` and `DELETE /jobs/{job_id}/tailored-resume` remove one row (constitution VIII, spec FR-009).

**Job deleted**: jobs are soft-deleted (state `deleted`), so the CASCADE does not fire. The `DELETE /jobs/{id}` handler runs the registered job clean-ups, and `drafts` registers one that deletes the job's rows in all three tables (spec FR-009). Wiring: `drafts_wiring.py` adds it to the search API deps, so `search` never imports `drafts`.

## Validation summary

| Rule | Where |
|---|---|
| Connection request ≤ 200 characters after filling | `drafts/domain/checks.py`, before `ready` |
| Numbers, technology terms, names, citations in AI text come from the profile | `drafts/domain/checks.py` (R4) |
| Referral: has an easy decline, no pressure phrases | `drafts/domain/tone.py` |
| Only backed keywords offered to the tailor step; match recomputed on save | `drafts/domain/keywords.py` |
| Contacts and the person's contact details never in a prompt | import contract + recorded-call test |
| Lengths and enums | database CHECK constraints + Pydantic |
