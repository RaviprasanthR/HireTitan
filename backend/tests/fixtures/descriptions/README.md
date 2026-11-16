# Recorded description answers (feature 002i)

Small **synthetic** answers shaped like each vendor's public job API (field names as documented by
the vendor), used by `tests/contract/descriptions/`. No real company text. One file per vendor:

| File | Vendor call | Field read |
|---|---|---|
| `greenhouse.json` | `GET boards-api.greenhouse.io/v1/boards/{board}/jobs/{id}` | `content` (escaped HTML) |
| `lever.json` | `GET api.lever.co/v0/postings/{board}/{id}` | `descriptionPlain`, `lists`, `additionalPlain` |
| `ashby.json` | `GET api.ashbyhq.com/posting-api/job-board/{board}` | `jobs[].descriptionPlain` (by `id`) |
| `workday.json` | `GET {tenant}.wdN.myworkdayjobs.com/wday/cxs/{tenant}/{site}/job/{path}` | `jobPostingInfo.jobDescription` |
| `recruitee.json` | `GET {board}.recruitee.com/api/offers/{slug}` | `offer.description`, `offer.requirements` |
