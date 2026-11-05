# extract_profile eval - 2026-11-05

15 synthetic documents (resumes and files that are not); prompt v2. Scores are micro-averaged over all cases; an answer the app could not use counts as empty.

## Summary

| model | tier | precision | recall | SC-003 (>= 90%) | cost / resume | SC-007 (< $0.05) | p95 latency (ms) | unusable | non-resumes rejected | resumes rejected by mistake |
|---|---|---|---|---|---|---|---|---|---|---|
| gpt-5.4-mini | fast | 100.0% | 100.0% | pass | $0.0019 | pass | 3228 | 0 | 4 / 4 | 0 / 11 |
| gpt-6-astra | strong | 100.0% | 100.0% | pass | $0.0193 | pass | 6428 | 0 | 4 / 4 | 0 / 11 |

## Precision / recall by field

| model | employers | titles | dates | skills | education |
|---|---|---|---|---|---|
| gpt-5.4-mini | 100% / 100% | 100% / 100% | 100% / 100% | 100% / 100% | 100% / 100% |
| gpt-6-astra | 100% / 100% | 100% / 100% | 100% / 100% | 100% / 100% | 100% / 100% |

## Misses and extras by case

### gpt-5.4-mini
- none

### gpt-6-astra
- none
