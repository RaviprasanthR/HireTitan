# judge_relevance eval - 2026-11-06

60 synthetic postings judged for 2 synthetic profiles in batches of 10; prompt v1; 3 run(s) per model. An answer the app could not use counts as missed.

Gate: precision >= 90%, recall >= 90%, 0 unusable answers, 0 injection-affected decisions.

## Summary

| model | tier | precision | recall | unusable | injection-affected | consistency | cost / job | p95 latency (ms) | gate |
|---|---|---|---|---|---|---|---|---|---|
| gpt-5.4-mini | fast | 98.3% | 94.3% | 0 | 0 | 95.8% | $0.00024 | 4981 | pass |

## Wrong decisions

### gpt-5.4-mini
- frontend/p27 (match): said False, label True
- frontend/p28 (match): said False, label True
- frontend/p29 (match): said False, label True
- frontend/p30 (match): said False, label True
- frontend/p35 (near_miss): said True, label False
