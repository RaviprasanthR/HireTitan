---
name: commit
description: "Create a git commit in the HireTitan format `[<branch> - <feature>] - If applied this commit will <change>`. Use whenever committing in this repo, or when asked to write or check a commit message, start a feature branch, or prepare a merge to master."
argument-hint: "Optional: short feature name or what the change does"
user-invocable: true
---

# HireTitan commit

## User input

```text
$ARGUMENTS
```

## Format (binding: constitution, Development Workflow)

```
[<branch> - <feature>] - If applied this commit will <change>

<optional body: why, notable details, task/requirement IDs>

Co-Authored-By: ... (only if the session's attribution rules ask for it)
```

- **`<branch>`**: the exact current branch name (`git symbolic-ref --short HEAD`), e.g. `master` or `001-setup-and-profile`.
- **`<feature>`**: a short lowercase name for the piece of work in *this* commit, 1–5 words. On a feature branch, prefix the Spec Kit task ID when there is one: `T012 resume upload`. Not the branch name repeated.
- **`<change>`**: completes the sentence "If applied this commit will …". Lowercase imperative verb first (`add`, `fix`, `remove`, `rename`, `update`, `refactor`, `test`, `document`), says *what changes for the project*, no trailing period.
- Body is optional; wrap at 72 chars; explain why, list requirement/scenario IDs (`FR-003`, `US1-AS2`) the commit covers.

Good:
- `[master - project skeleton] - If applied this commit will add the repository skeleton with Spec Kit, constitution and commit conventions`
- `[001-setup-and-profile - T012 resume upload] - If applied this commit will add PDF and DOCX resume upload with a 5 MB size limit`
- `[001-setup-and-profile - T013 resume upload tests] - If applied this commit will test FR-004 rejection of unsupported file types`

Bad: `fix stuff` · `feat: add upload` (Conventional Commits is not used here) · `[001 - upload] - ...` (branch must be exact) · `... will Added upload.` (past tense, capital, period).

## Branch rules

- `master` is the main branch. Never commit feature work on `master` (the initial skeleton was the only exception). If on `master` with feature changes, stop and ask before creating a branch.
- New feature: `git switch master && git pull --ff-only` (if a remote exists), then `git switch -c <NNN-feature-name>` matching the `specs/NNN-name/` folder.
- Merge to `master` only through a GitHub pull request after tests and gates pass; PR title uses the same format with feature = the feature summary.

## Steps

1. Commit only when the user has asked to commit (CLAUDE.md).
2. Make sure the hook is active: `git config core.hooksPath` must print `.githooks`; if not, run `git config core.hooksPath .githooks`.
3. Inspect: `git status --short`, `git diff --staged` (and unstaged diff). Check nothing personal or secret is staged: no `.env`, no `docs/private/`, no real resumes or personal data (constitution VIII). Stop and report if found.
4. One commit = one task/logical change. If the diff mixes unrelated changes, propose splitting.
5. Stage explicit paths (avoid `git add -A` unless the status was reviewed).
6. Draft the subject from the rules above, show it to the user, then commit with a heredoc so formatting is exact:
   ```bash
   git commit -F- <<'EOF'
   [<branch> - <feature>] - If applied this commit will <change>

   <body>
   EOF
   ```
7. If the hook rejects the message, fix the message (never bypass with `--no-verify`) and commit again.
8. Report the commit hash and subject.
