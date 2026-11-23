# mail_alerts eval, 2026-11-23: PASS

The six fixed alert readers over the synthetic fixtures in `tests/fixtures/mail` (no AI).
SC-002 targets: at least 95% of jobs with title, company and link right; 0 invented
values; at least 90% of the built-in sites' emails read without the AI.

| Site | Emails | Jobs | Correct | Title | Company | Link | Invented | Read without AI |
|---|---|---|---|---|---|---|---|---|
| linkedin | 12 | 72 | 100.0% | 72 | 72 | 72 | 0 | 12/12 |
| naukri | 10 | 66 | 100.0% | 66 | 66 | 66 | 0 | 10/10 |
| indeed | 10 | 55 | 100.0% | 55 | 55 | 55 | 0 | 10/10 |
| foundit | 10 | 59 | 100.0% | 59 | 59 | 59 | 0 | 10/10 |
| instahyre | 10 | 36 | 100.0% | 36 | 36 | 36 | 0 | 10/10 |
| cutshort | 10 | 45 | 100.0% | 45 | 45 | 45 | 0 | 10/10 |

- Emails from built-in sites: 62
- Jobs taken out correctly: 100.0% (target 95%)
- Invented values: 0 (target 0)
- Read without the AI: 100.0% (target 90%)
- Emails in a layout no fixed reader knows (left to the AI): 3

The layouts are guesses until real alerts are checked (T005); the AI fallback is
measured with the deferred evals, which need a key.
