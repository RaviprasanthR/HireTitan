# Success criteria map: Setup and search polish

**Feature**: [spec.md](spec.md) · **Date**: 2026-11-16

Where each success criterion is checked. "Journey" means a Playwright journey in `frontend/e2e/`
against the compose stack with scripted AI and fake job boards (all three pass).

| Criterion | What it says | Checked by |
|---|---|---|
| **SC-001** | After the four setup cards a search starts with one click from Explore | Journey `setup-and-profile.spec.ts` (Finish setup, then Explore shows **Search now**, no "Finish setup first"); `tests/api/setup/test_onboarding_api.py::test_FR001_finish_setup_approves_first_rules`; `ExplorePage.test.tsx` (`FR006_*`, `US1_AS1_shows_search_now_once_rules_are_approved`) |
| **SC-002** | "Searching" within a second of pressing Search now; never "0 of 0" or a batch number | `SearchPanel.test.tsx` (`US2_AS1_shows_searching_at_once_when_search_now_is_pressed`: shown while the server has not yet answered; `US2_AS1_shows_searching_and_no_zero_counts_before_a_company_is_read`; `US2_AS2_*`); journey `job-search.spec.ts` step 3 (the panel never matches `batch` or `0 of 0`) |
| **SC-003** | Search rules shows none of the six old tag texts; "batch" appears nowhere in the Search panel | `SearchRulesPage.test.tsx::SC003_shows_none_of_the_old_tag_texts`; `SearchPanel.test.tsx::SC003_the_word_batch_appears_nowhere_in_the_panel`; journey step 2 |
| **SC-004** | Changing one title takes three clicks or fewer (Edit, change, Save) | `SearchRulesPage.test.tsx::SC004_changing_a_title_takes_three_clicks_or_fewer` |
| **SC-005** | At 1280 × 800 the Preferences step needs at least 40% less vertical scrolling | Unit: `SetupGate.test.tsx` (`FR021_*`: wide card for steps 3 and 4, narrow for 1 and 2, narrow again after going back, narrow in Settings). Measurement: see below |
| **SC-006** | The automatic approval runs at most once per install | `tests/integration/search/test_first_rules.py` (`test_FR002_double_finish_approves_once` with two concurrent sessions, `test_FR002_existing_approval_is_never_replaced`, `test_FR002_a_superseded_approval_still_counts`, `test_FR002_runs_again_after_delete_all`); `test_first_rules_startup.py::test_FR003_startup_twice_keeps_one_set` |
| **SC-007** | Job details without leaving the list; one click on the title opens the posting | `ExplorePage.test.tsx` (`US5_AS1` to `US5_AS6`, `FR028_*`); journey step 4a |
| **SC-008** | At least 95% of front end, mobile, QA and Java roles left out; relevant roles kept at 95% or more | `backend/evals/reports/judge_relevance-2026-11-16.md`: left out 100% (54/54), Go profile recall 95.8% (46/48); `tests/unit/evals/test_judge_relevance_cases.py::test_SC008_*` pin how the two measures are computed; the free rules add `tests/unit/search/test_tech_names.py` and `tests/workflow/search/test_job_search_graph.py::test_FR032_FR036_*` |
| **SC-009** | At least 70% of the jobs that pass the free rules reach the AI with a description | **Not measured on real data.** It needs one real search on a clean install: jobs already stored are not read again, so Ravi's install (which holds the jobs of earlier searches) would measure only new postings. Plan: Delete all my data, set up again, Search now, then count the kept jobs that have a stored description. Journey step 4a proves the path end to end with a fake board whose listing has no text |

## Requirements without a numbered criterion

| Requirement | Checked by |
|---|---|
| FR-003 (first rules at start-up) | `test_first_rules_startup.py` |
| FR-004 (invalid proposal never blocks setup) | `test_onboarding_api.py::test_FR004_*` |
| FR-005 (recorded as automatic) | `test_first_rules.py::test_FR001_first_rules_are_approved` (`approved_by = auto`), migration tests `test_0020_*` |
| FR-007 (no AI call) | `test_FR007_first_approval_makes_no_llm_call` |
| FR-012 (announced politely, bar hidden from assistive tech) | `SearchPanel.test.tsx::US2_AS6_*` (one always-present polite status line; the bar is a named progressbar) |
| FR-015 to FR-020 (Search rules page) | `SearchRulesPage.test.tsx` (`US3_AS3` to `US3_AS8`, `FR020_*`, focus and error tests), `test_rules_api.py::test_FR015_*`, `test_FR016_*`, `test_FR017_*` |
| FR-023 (English, no AI cost, theme, keyboard and focus) | Journey step 8 (no cost words on any page); the contrast tests; story reviews of US2 to US5 (focus, live regions, keyboard) |
| FR-029 (read the text before the AI) | `tests/workflow/search/test_descriptions.py`, `tests/contract/descriptions/test_reader.py` (one recorded synthetic answer per vendor, allowlist, politeness), `tests/security/test_job_text_attacks.py::test_FR029_description_text_is_screened`, `test_fetcher.py::test_SSRF_*` |
| FR-030, FR-031 (area and avoid words) | `test_work_areas.py`, `test_proposer.py` |
| FR-032 (a technology the person does not have) | `test_tech_names.py`, `test_apply_rules.py` |
| FR-033 (the card has the profile's skills) | `test_cards.py`, `tests/integration/search/test_wiring.py::test_FR033_profile_card_has_profile_skills_and_areas` (the 2026-11-16 bug) |
| FR-034 (without text: title only, reason says so) | `test_descriptions.py::test_FR034_*`; prompt v3 system text |
| FR-035 (new prompt version passed its evaluation first) | `test_judge_relevance_v3.py::test_v3_is_current_and_its_passing_report_is_committed`; the report |
| FR-036 (skips have a reason and can be restored) | `test_FR032_FR036_a_job_for_another_stack_is_skipped_with_its_reason`; journey step 4b and the existing Restore step |

## Measurements

- **SC-005**: to be added after the before and after screenshots at 1280 × 800.
