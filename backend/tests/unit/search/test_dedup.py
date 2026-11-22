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


def _job(title: str, city: str | None = "Pune", company: str = "Acme") -> DedupJob:
    return DedupJob(UUID(int=1), company, city, title, None, None, None)


def test_same_posting_again_needs_company_city_and_a_near_identical_title() -> None:
    from hiretitan.search.domain.dedup import same_posting_again

    base = _job("Backend Engineer")
    assert same_posting_again(_job("Backend Engineer"), base)
    assert same_posting_again(_job("Backend  Engineer."), base)  # punctuation only
    assert not same_posting_again(_job("Senior Backend Engineer"), base)  # another level
    assert not same_posting_again(_job("Backend Engineer", city="Chennai"), base)
    assert not same_posting_again(_job("Backend Engineer", city=None), base)  # city unknown
    assert not same_posting_again(_job("Backend Engineer", company="Other"), base)
    # the two roles that looked alike in the real data
    assert not same_posting_again(
        _job("Senior Software Engineer-Frontend"), _job("Senior Software Engineer-Systems")
    )


def test_FR021_a_short_title_inside_a_much_longer_one_is_not_a_candidate() -> None:
    """Seen on a real search (2026-11-22): every word of the short title is in the long one, so a
    word-set score is 100, but "X" and "X, team Y" are usually two different postings."""
    pairs = [
        ("Program Manager II", "Program Manager II, Global Catalog Operations"),
        ("Program Manager II", "Manager II Program Management, Global Catalog Operations"),
        ("Associate, Quality Services", "Associate, Quality Services, DEX SSD Field"),
        ("Program Manager II", "Program Manager II, Amazon Books"),
    ]
    for short, long in pairs:
        assert fuzzy_candidates(job(2, long), [job(1, short)]) == [], (short, long)
        assert fuzzy_candidates(job(2, short), [job(1, long)]) == [], (short, long)


def test_FR021_a_word_more_or_a_reordered_title_is_still_a_candidate() -> None:
    assert (
        len(
            fuzzy_candidates(job(2, "Senior Backend Engineer"), [job(1, "Backend Engineer Senior")])
        )
        == 1
    )
    assert (
        len(fuzzy_candidates(job(2, "Backend Engineer, Payments"), [job(1, "Backend Engineer")]))
        == 1
    )
