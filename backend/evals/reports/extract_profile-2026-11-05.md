# extract_profile eval - 2026-11-05

11 synthetic resumes; prompt v1. Scores are micro-averaged over all cases; an answer the app could not use counts as empty.

## Summary

| model | tier | precision | recall | SC-003 (>= 90%) | cost / resume | SC-007 (< $0.05) | p95 latency (ms) | unusable |
|---|---|---|---|---|---|---|---|---|
| gpt-5.4-mini | fast | 100.0% | 97.9% | pass | $0.0020 | pass | 2870 | 0 |
| gpt-6-astra | strong | 100.0% | 100.0% | pass | $0.0321 | pass | 6381 | 0 |

## Precision / recall by field

| model | employers | titles | dates | skills | education |
|---|---|---|---|---|---|
| gpt-5.4-mini | 100% / 100% | 100% / 100% | 100% / 100% | 100% / 95% | 100% / 100% |
| gpt-6-astra | 100% / 100% | 100% / 100% | 100% / 100% | 100% / 100% | 100% / 100% |

## Misses and extras by case

### gpt-5.4-mini
- **tables.docx** (ok)
  - missed skills: docker, git, kafka

### gpt-6-astra
- none
