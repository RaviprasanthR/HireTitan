"""Which profile facts go into a prompt, and which names a draft may mention. Pure."""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence

from hiretitan.drafts.domain.facts import Fact
from hiretitan.drafts.domain.profile_view import ProfileView

_WORD = re.compile(r"[A-Za-z0-9+#.]+")


def select_facts(facts: Sequence[Fact], keywords: Iterable[str], limit: int = 12) -> list[Fact]:
    """The facts that overlap most with the job's keywords first, in profile order on ties.

    Always keeps the first summary fact if there is one, so a thin overlap still has context.
    """
    words = {w.casefold() for keyword in keywords for w in _WORD.findall(keyword)}

    def score(fact: Fact) -> int:
        return len({w.casefold() for w in _WORD.findall(fact.text)} & words)

    ranked = sorted(enumerate(facts), key=lambda pair: (-score(pair[1]), pair[0]))
    chosen = [fact for _, fact in ranked[:limit]]
    summary = next((f for f in facts if f.kind == "summary"), None)
    if summary is not None and summary not in chosen:
        chosen = [summary, *chosen[: limit - 1]]
    order = {f.id: i for i, f in enumerate(facts)}
    return sorted(chosen, key=lambda f: order[f.id])


def allowed_names(profile: ProfileView, company: str, title: str) -> list[str]:
    """Names a draft may mention: the job's company and title words, and the person's own
    employers, schools, projects and certifications."""
    names = [company, title]
    names += [job.employer for job in profile.experience]
    names += [edu.institution for edu in profile.education]
    names += [project.name for project in profile.projects]
    for cert in profile.certifications:
        names.append(cert.name)
        if cert.issuer:
            names.append(cert.issuer)
    return [name for name in names if name]
