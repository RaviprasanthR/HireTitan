# Success criteria map: 002k

Where each success criterion of [spec.md](spec.md) is shown. "Manual" steps are in [quickstart.md](quickstart.md) §3.

| SC | What it says | Shown by |
|---|---|---|
| SC-001 | Explore row has two actions; resume and date in two extra clicks | `frontend/src/features/explore/ExplorePage.test.tsx` (`FR001 explore row shows only two actions`, `FR002 details record resume and date`); `PipelineControl.test.tsx` (`FR001 compact …`); Playwright journey step 7c |
| SC-002 | Job to copied connection request in under 30 seconds of the person's effort | Manual (quickstart §3 step 1); `DraftPanel.test.tsx` (`US2 AS1`, `EC11 copy …`); Playwright step 7d |
| SC-003 | 100% of connection requests are 200 characters or fewer; count and warning visible | `backend/tests/workflow/drafts/test_outreach.py::test_FR011_connection_request_at_most_200`; `backend/tests/unit/drafts/test_recipient_tone_fallback.py::test_US2_AS4_fallback_note_is_within_200_and_truthful`; `DraftPanel.test.tsx` (`US2 AS2 …`); eval row "Connection requests within 200 characters" |
| SC-004 | 0 fabrications in 30+ synthetic pairs; 100% of seeded fabrications rejected | `backend/tests/unit/drafts/test_facts_checks.py::test_SC004_seeded_fabrications_all_caught`; `backend/tests/unit/evals/test_drafts_evals.py::test_SC004_scorer_counts_seeded_fabrications`; eval rows "Fabrications in accepted text" and "Seeded fabrications caught" (`outreach_drafts`, `tailor_resume`) |
| SC-005 | At least 95% of referrals pass the tone rules first try; the rest repaired or replaced | `backend/tests/unit/drafts/test_recipient_tone_fallback.py` (`test_FR012_*`, `test_SC005_*`); `test_outreach.py::test_FR012_pushy_referral_rejected`; eval row "Referral tone accepted first try" |
| SC-006 | PDF and DOCX match the preview; sections in order | `backend/tests/integration/drafts/test_render.py` (`test_FR018_pdf_docx_same_text_single_column`, `test_SC006_sections_in_order`, `test_FR018_no_tables_or_images`) |
| SC-007 | The app sends nothing | `backend/tests/architecture/test_no_send.py::test_SC007_no_send_scans_drafts` and the existing whole-package scans; the UI says "HireTitan never sends this" (`DraftPanel.test.tsx::FR004 …`) |
| SC-008 | AI unavailable or invalid output always ends with a reason or fallback, no lost data | `test_outreach.py` (`test_US2_AS6_out_of_credit_pauses_and_resumes`, `test_US2_AS4_repair_then_fallback_template`); `test_tailor.py` (`test_FR007_out_of_credit_pauses_tailoring`, `test_US4_AS2_repair_then_plain_reorder`); `backend/tests/api/drafts/test_drafts_api.py::test_US2_AS6_ai_unavailable_409_with_reason` |

## Evals that need the person's AI key (not yet run)

`outreach_drafts` on `--models fast,strong` (decides the referral tier) and `tailor_resume` on `--models strong`: the runner, 30 synthetic cases, the scorer and the report are built and tested with a scripted model. The runs themselves use the person's AI credit and are left for them (tasks T020 and T027):

```
PYTHONPATH=backend backend/.venv/Scripts/python.exe -m evals.run outreach_drafts --models fast,strong --repeat 3 --yes
PYTHONPATH=backend backend/.venv/Scripts/python.exe -m evals.run tailor_resume --models strong --repeat 3 --yes
```

Pass: 0 fabrications, 100% of seeded fabrications caught, 100% of connection requests within 200 characters, at least 95% of referral messages accepted on the first try, p95 within 10 s (messages) and 60 s (resume). If `fast` misses the referral target and `strong` meets it, set `tier: strong` in `backend/src/hiretitan/prompts/draft_referral_message/v1/meta.yaml` and update research R1.
