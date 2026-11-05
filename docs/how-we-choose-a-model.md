# How we choose an AI model (with real examples from HireTitan)

This page explains, in plain words, how we decided which model reads a resume. You can reuse the same steps for any other AI task later (scoring jobs, tailoring a resume, drafting outreach).

The short version: **write down what "good enough" means, build a small test with known answers, run every candidate model on it, compare the numbers, and pick the cheapest model that clears the bar.**

---

## 1. Decide what "good" means before you test

Without a target you can't say a model "works". For resume reading we wrote three success criteria in `specs/001-setup-and-profile/spec.md`:

| ID | What it says | What it measures |
|---|---|---|
| SC-003 | At least 90% of the fields a person would expect are extracted correctly | **Quality** |
| SC-007 | One extraction costs under $0.05 | **Cost** |
| SC-002 | Extraction finishes within 60 seconds | **Speed** |

Quality, cost and speed are the three things almost every model choice comes down to.

## 2. Build a small test with known answers

A test needs inputs and the right answers, so you can score the model without guessing.

- **Inputs:** 11 made-up resumes in `backend/evals/extract_profile/cases/` (PDF and DOCX, one column and two columns, fresher / mid / senior, one with tables, one with text boxes). They are fake, so no real person's data is in the repo.
- **Right answers:** one file per resume in `backend/evals/extract_profile/expected/`, listing the employers, titles, dates, skills and education that are really in it. For example, `tables.docx.yaml` lists 9 skills.

Why such a mix of layouts? Different layouts break different things. A model that is perfect on a plain resume may fail on a table. Our test caught exactly that (see section 5).

Why English only? HireTitan supports English only, so the test is English only. A test should match what you promise users. We first had a Spanish resume in the set and removed it when we decided not to support other languages.

## 3. Run every candidate the same way

Same prompt, same inputs, same checks. Only the model changes. Otherwise you are comparing the wrong things.

```
PYTHONPATH=backend backend/.venv/Scripts/python.exe -m evals.run extract_profile --models fast,strong --yes
```

Run it from the repository root so it finds your `.env`. The runner:

1. prints an **estimated maximum cost** and does nothing until you add `--yes`, because real models cost real money;
2. reads each resume with the same parser the app uses;
3. sends it to the model with the same prompt the app uses;
4. runs the same safety checks the app uses (the "grounding" check drops anything not found in the resume);
5. compares the result with the answer file and writes a report to `backend/evals/reports/`.

We tested two candidates: `fast` (`gpt-5.4-mini`, cheap and quick) and `strong` (`gpt-6-astra`, bigger and slower). They are called *tiers* because the app asks for a tier, not a model name, so you can swap models without touching the code (`backend/src/hiretitan/platform/llm/models.yaml`).

## 4. The numbers we look at

### Quality: precision and recall

These two words sound technical but the idea is simple.

- **Precision** = of what the model *said*, how much was right? Low precision means it made things up. For a profile this is the dangerous one, because HireTitan must never invent experience.
- **Recall** = of what was *really there*, how much did the model find? Low recall means it missed things.

Example from our run, resume `tables.docx`, which really lists 9 skills:

- `fast` returned 6 skills, and all 6 were correct. Precision 6/6 = 100%.
- It missed docker, git and kafka. Recall 6/9 = 67% for that resume.
- `strong` found all 9.

Across all 11 resumes the totals were:

| | precision | recall |
|---|---|---|
| fast | 100% | 97.9% |
| strong | 100% | 100% |

We also split the score by field (employers, titles, dates, skills, education) so we can see *where* a model is weak. Here the only weak spot was skills.

### Cost

Models charge per *token* (roughly a word piece), with one price for what you send in and a higher price for what comes out. From `models.yaml`, per 1 million tokens:

| | input | output |
|---|---|---|
| fast | $0.75 | $4.50 |
| strong | $10.00 | $50.00 |

So `strong` is roughly 11 to 13 times pricier per token. The run measured the real cost per resume: **$0.0020 for fast and $0.0321 for strong**, which is about 16 times more. Both are far below our $0.05 limit, so both pass SC-007. The question is whether `strong` is worth 16 times the price.

### Speed

We record the 95th-percentile latency (p95: 19 of 20 calls were faster than this). `fast`: 2.9 seconds. `strong`: 6.4 seconds. Both are far inside the 60-second target.

### Reliability

The "unusable" column counts answers the app could not use (broken JSON, wrong shape). Both models had 0 of 11. A model that is accurate but breaks the format half the time is not a good choice.

## 5. Read the details, not only the totals

The report ends with "misses and extras by case". That is where you learn something:

- `fast` missed three skills, in one layout (a table). That is a small, specific gap.
- Everything else, including every date, employer and title, was perfect.

A total of 97.9% hides *which* resumes failed. The per-case list shows it is one unusual layout, and that the review screen (where the person checks and fixes the profile before confirming) already covers it.

## 6. Make the decision, then write it down

The rule we use: **pick the cheapest model that clears every bar, unless the extra quality matters for a real reason.**

Here `fast` clears SC-003, SC-007 and SC-002, and `strong` only fixes three skills in one layout at 16 times the cost, in a flow where the user reviews everything anyway. So the decision is `fast`.

We recorded it in `docs/architecture.md` (ADR-11) and added a test, `backend/tests/unit/evals/test_default_model.py`. The test fails if the default model in the app no longer matches the latest committed report, or if the report stops meeting SC-003 / SC-007. A decision should be backed by evidence you can re-check.

## 7. Other things people compare (we didn't all do them yet)

| What | Why it matters | Where we stand |
|---|---|---|
| Consistency | The same input can give different answers on different runs | We ran each model once. A better test runs each case 3 to 5 times |
| Prompt-injection resistance | A resume might say "ignore your instructions" | We have attack resumes for the parser and screening, but haven't scored each model against them |
| Sample size | 11 resumes is small, and they are synthetic | Enough to compare two models, not enough to claim a precise accuracy for real resumes |
| Context window | Whether a long input fits | Resumes are small, so not a concern here |
| Rate limits | How many calls per minute you may make | Not a concern for one user |
| Privacy and licence | Where the data goes, and the provider's terms | One provider (OpenAI) with your own key |
| Price changes | Providers change prices | Prices in `models.yaml` are typed in by hand, with a "checked on" date |

## 8. Mistakes we made, so you can avoid them

- **A bad key produced a report full of zeros.** The first run used a rejected API key. Every call failed instantly, and the runner still wrote a report: 0% recall, $0.0000 cost, 0 ms latency. A report with no cost and no latency means nothing ran. The runner now stops and says the key was rejected instead of writing a report.
- **Running from the wrong folder.** The runner looks for `.env` in the folder you start it from, so start it from the repository root.
- **Testing what you don't support.** The Spanish resume made `fast` look worse for something we never promised to handle.

## 9. How to repeat this

1. Change the prompt, the model, or the test set.
2. Run the command in section 3 (the estimate comes first; add `--yes` to spend).
3. Read the summary, then the misses.
4. If the new numbers beat the old ones on the things you care about, commit the new report and update the decision. The default-model test tells you if you forgot.

Keep every report. Together they show how the prompt and the model choice improved over time.
