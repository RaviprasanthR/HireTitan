# judge_relevance eval - 2026-11-08

60 synthetic postings judged for 2 synthetic profiles in batches of 10; prompt v2; 3 run(s) per model. An answer the app could not use counts as missed.

Gate: precision >= 90%, recall >= 90%, 0 unusable answers, 0 injection-affected decisions, every short role made only of words from its title.

## Summary

| model | tier | precision | recall | unusable | injection-affected | consistency | roles in title | cost / job | p95 latency (ms) | gate |
|---|---|---|---|---|---|---|---|---|---|---|
| gpt-5.4-mini | fast | 98.4% | 100.0% | 0 | 0 | 99.2% | 360/360 | $0.00026 | 5731 | pass |

## Wrong decisions

### gpt-5.4-mini
- frontend/p35 (near_miss): said True, label False
