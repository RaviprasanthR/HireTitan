# judge_relevance eval - 2026-11-16

60 synthetic postings judged for 2 synthetic profiles and 43 for a third (a Python and Go back end engineer) in batches of 10; prompt v3; 3 run(s) per model. An answer the app could not use counts as missed.

Gate: precision >= 90%, recall >= 90%, 0 unusable answers, 0 injection-affected decisions, every short role made only of words from its title, and on the Python and Go profile at least 95% of the front end, mobile, QA and other-stack roles left out and at least 95% of the relevant roles kept.

## Summary

| model | tier | precision | recall | unusable | injection-affected | consistency | roles in title | tokens / job | p95 latency (ms) | left out (SC-008) | Go profile recall | gate |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| gpt-5.4-mini | fast | 98.1% | 91.8% | 10 | 0 | 88.3% | 479/479 | 252 | 4600 | 81.5% (44/54) | 100.0% (48/48) | FAIL |

## Wrong decisions

### gpt-5.4-mini
- backend/p27 (match): said False, label True
- backend/p28 (match): said False, label True
- backend/p29 (match): said False, label True
- backend/p30 (match): said False, label True
- backend/p41 (seniority): said True, label False
- frontend/p27 (match): said False, label True
- frontend/p28 (match): said False, label True
- frontend/p29 (match): said False, label True
- frontend/p35 (near_miss): said True, label False
