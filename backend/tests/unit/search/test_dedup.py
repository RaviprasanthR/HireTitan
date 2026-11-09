"""T024: exact matches merge; similar titles are only candidates (R8, FR-021, SC-008)."""

from __future__ import annotations

from uuid import UUID

from hiretitan.search.domain.dedup import DedupJob, exact_match, fuzzy_candidates


def uid(n: int) -> UUID:
    return UUID(int=n)


def job(n: int, title: str = "Backend Engineer", **changes: object) -> DedupJob:
    base = {
        "id": uid(n),
        "company_name": "Acme Pvt Ltd",
        "city": "Pune",
        "title": title,
        "canonical_url": f"https://boards.example.com/acme/{n}",
        "ats_vendor": None,
        "requisition_id": None,
    }
    return DedupJob(**{**base, **changes})  # type: ignore[arg-type]


def test_SC008_exact_url_merges() -> None:
    found = job(2, canonical_url="https://boards.example.com/acme/1")
    assert exact_match(found, [job(1)]) == uid(1)


def test_SC008_same_requisition_merges() -> None:
    old = job(1, ats_vendor="lever", requisition_id="R-7")
    found = job(2, ats_vendor="lever", requisition_id="R-7")
    assert exact_match(found, [old]) == uid(1)
    assert exact_match(job(3, ats_vendor="greenhouse", requisition_id="R-7"), [old]) is None


def test_no_exact_match_without_keys() -> None:
    assert exact_match(job(2, canonical_url=None), [job(1, canonical_url=None)]) is None


def test_FR021_similar_title_same_company_is_only_a_candidate() -> None:
    a = job(1, "Backend Engineer")
    b = job(2, "Backend  engineer (Python)")
    assert exact_match(b, [a]) is None
    pairs = fuzzy_candidates(b, [a])
    assert [(p.first, p.second) for p in pairs] == [(uid(1), uid(2))]


def test_FR021_ii_vs_iii_titles_are_candidates_not_merges() -> None:
    a = job(1, "Software Engineer II")
    b = job(2, "Software Engineer III")
    assert exact_match(b, [a]) is None
    assert len(fuzzy_candidates(b, [a])) == 1


def test_different_city_is_not_a_candidate() -> None:
    assert fuzzy_candidates(job(2, city="Chennai"), [job(1)]) == []


def test_unknown_city_is_not_a_candidate() -> None:
    assert fuzzy_candidates(job(2, city=None), [job(1, city=None)]) == []


def test_different_company_is_not_a_candidate() -> None:
    assert fuzzy_candidates(job(2, company_name="Other Corp"), [job(1)]) == []


def test_company_compared_ignoring_case_and_punctuation() -> None:
    assert fuzzy_candidates(job(2, company_name="ACME, pvt ltd."), [job(1)])


def test_unrelated_titles_are_not_candidates() -> None:
    assert fuzzy_candidates(job(2, "Sales Manager"), [job(1)]) == []


def test_pairs_are_ordered_by_id_whichever_job_is_new() -> None:
    older, newer = job(5), job(9, "Backend Engineer II")
    assert fuzzy_candidates(older, [newer])[0].first == uid(5)
    assert fuzzy_candidates(newer, [older])[0].first == uid(5)


def test_a_job_is_not_its_own_candidate() -> None:
    one = job(1)
    assert fuzzy_candidates(one, [one]) == []
