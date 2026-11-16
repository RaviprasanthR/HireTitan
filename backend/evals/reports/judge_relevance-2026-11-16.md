# judge_relevance eval - 2026-11-16

60 synthetic postings judged for 2 synthetic profiles and 43 for a third (a Python and Go back end engineer) in batches of 10; prompt v3; 3 run(s) per model. An answer the app could not use counts as missed.

Gate: precision >= 90%, recall >= 90%, 0 unusable answers, 0 injection-affected decisions, every short role made only of words from its title, and on the Python and Go profile at least 95% of the front end, mobile, QA and other-stack roles left out and at least 95% of the relevant roles kept.

## Summary

| model | tier | precision | recall | unusable | injection-affected | consistency | roles in title | tokens / job | p95 latency (ms) | left out (SC-008) | Go profile recall | gate |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| gpt-5.4-mini | fast | 100.0% | 98.8% | 0 | 0 | 99.4% | 489/489 | 252 | 5084 | 100.0% (54/54) | 95.8% (46/48) | pass |

## Wrong decisions

### gpt-5.4-mini
- backend_go/g07 (match): said False, label True
