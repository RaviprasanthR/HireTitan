# Data model: Resume picker

Migration `0019_resume_picker`, parent `0018_interview_tracking`. Schema `app`. See [research.md](research.md) R1, R2, R4.

## `job_pipeline_details` (002e table, three columns added)

| Column | Type | Null | Notes |
|---|---|---|---|
| `resume_file_id` | uuid | yes | FK `app.resume_files(id)` `ON DELETE SET NULL`. Set while the chosen file exists. |
| `resume_name` | text | yes | The file's name when chosen (copy of `resume_files.original_name`). |
| `resume_added_on` | date | yes | The day the file was added (from `resume_files.created_at`). |

Constraints:
- `resume_name_length`: `char_length(resume_name) BETWEEN 1 AND 255`.
- `resume_snapshot_together`: `(resume_name IS NULL) = (resume_added_on IS NULL)`.
- `resume_link_has_snapshot`: `resume_file_id IS NULL OR resume_name IS NOT NULL`.

Index: `ix_job_pipeline_details_resume_file_id` on `resume_file_id` (the `SET NULL` on file removal and the usage counts).

The row is still removed with its job, carried by the merge, and pruned when empty; "empty" now means contact, source **and** `resume_name` are all null.

## `pipeline_settings` (new)

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | smallint | no | Primary key; check `id = 1` (one row). |
| `last_resume_file_id` | uuid | yes | FK `app.resume_files(id)` `ON DELETE SET NULL`. The person's last choice when marking a job; null = None. |

The row is created on first write (`INSERT ... ON CONFLICT (id) DO UPDATE`). A missing row means None.

## Display rule (pure, `search/domain/resume_choice.py`)

| `resume_file_id` | `resume_name` | Shown as |
|---|---|---|
| set | set | **chosen**: name, added day |
| null | set | **removed**: "name (removed)", clearable |
| null | null | **none**: a dash |

## State changes

| Event | Job's resume columns | `pipeline_settings.last_resume_file_id` |
|---|---|---|
| Mark applied / inquired, body has `resume_file_id` = file | set to the file (id + snapshot) | file |
| Mark applied / inquired, body has `resume_file_id` = null | cleared | null |
| Mark applied / inquired, field absent | unchanged | unchanged |
| Edit card: set / change | set to the file | unchanged |
| Edit card: clear (also clears a removed note) | cleared | unchanged |
| Undo applied / inquired | cleared | unchanged |
| Resume file removed | `resume_file_id` → null (database), snapshot kept | → null (database) |
| "Also clear the name from those jobs" (before the removal) | cleared on every job pointing at the file | → null if it was that file |
| Duplicate merge | kept job's own if any, else the other job's (all three together) | unchanged |
| Job removed / Delete all | gone with the row / truncated | truncated |

## Validation

- A file can be chosen only if `ResumeLookup.get(id)` returns it and it is offerable (`parse_status != 'not_resume'`); otherwise 422 with a field error on `resume_file_id`.
- Writes only for jobs in a pipeline state (applied or inquired), under the job row lock, as for 002e's details.
