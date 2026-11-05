# Recorded career-ops output

What HireTitan's `runner.mjs` printed when it read one public board for each enabled job-board
provider (T013), plus two error cases (`error_bad_board.json`: a board that does not exist;
`error_bad_provider.json`: a provider that is not enabled). The runner calls the pinned career-ops
v1.38.0 providers (commit `115bc9873e3d43e23883f3c8f16436617facc62c`) directly; `scan.mjs --json`
cannot be used because it prints only a receipt (see research R1).

Recorded on 2026-11-06 from public boards, then scrubbed: company names, job titles, URLs,
descriptions and ids are replaced with invented ones on `example.test` hosts, and each file keeps
at most three postings. What is kept is the shape: which fields are present, which are null, and
the types of the values. No real company's postings are stored here.

To re-record: run `runner.mjs` with `CAREER_OPS_DIR` pointing at a checkout of the pinned commit,
then scrub the output the same way before committing it.

`request_trace.json` is every distinct request the providers made during that recording (method,
host, path, with names replaced by `examplecorp`). The allowlist test (T015) checks it. The
recording also included SmartRecruiters, which is dropped from the fixtures because it is not an
enabled provider (its robots.txt disallows generic clients; see `allowlist.py`).
