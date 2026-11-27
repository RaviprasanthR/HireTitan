"""Mikasa's reads of the profile, preferences and search rules (002m contracts/actions.md).

Profile facts are read-only to Mikasa (FR-018). The person's own contact details are left out,
as in 002k; every text field is bounded and screened.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from hiretitan.actions.spec import ActionContext, ActionError, ActionSpec, ReadResult
from hiretitan.actions.text import screened
from hiretitan.preferences.application.service import get_preferences
from hiretitan.preferences.infra.repo import PreferencesRepo
from hiretitan.profile.infra.repos import VersionsRepo
from hiretitan.search.infra.models import SearchRuleSetRow
from hiretitan.search.infra.repos import RuleSetsRepo

NO_PROFILE = ActionError("no_profile", "There is no confirmed profile yet.")


class NoArgs(BaseModel):
    pass


async def get_profile(ctx: ActionContext, args: NoArgs) -> ReadResult | ActionError:
    version = await VersionsRepo(ctx.session).current()
    if version is None:
        return NO_PROFILE
    content = version.content
    profile, flagged = screened(
        {
            "headline": content.headline,
            "summary": content.summary,
            "experience": [
                {
                    "employer": e.employer,
                    "title": e.title,
                    "start": e.start,
                    "end": e.end,
                    "current": e.current,
                    "location": e.location,
                    "bullets": list(e.bullets),
                }
                for e in content.experience
            ],
            "education": list(content.education),
            "skills": list(content.skills),
            "projects": list(content.projects),
            "certifications": list(content.certifications),
        }
    )
    profile["flagged"] = flagged
    return ReadResult(items=[profile], total=1)


async def read_preferences(ctx: ActionContext, args: NoArgs) -> ReadResult:
    stored = await get_preferences(PreferencesRepo(ctx.session))
    content, _ = screened(stored.content)
    return ReadResult(
        items=[
            {
                "saved": stored.saved_at is not None,
                "saved_at": stored.saved_at.isoformat() if stored.saved_at else None,
                "preferences": content,
            }
        ],
        total=1,
    )


def _rule_set(row: SearchRuleSetRow | None) -> dict[str, Any] | None:
    if row is None:
        return None
    rules, _ = screened(row.rules, cap=200)
    return {
        "version": row.version,
        "approved_at": row.approved_at.isoformat() if row.approved_at else None,
        "rules": rules,
    }


async def get_search_rules(ctx: ActionContext, args: NoArgs) -> ReadResult:
    repo = RuleSetsRepo(ctx.session)
    return ReadResult(
        items=[
            {
                "approved": _rule_set(await repo.approved()),
                "proposal": _rule_set(await repo.proposed()),
                "page": "/profile/search-rules",
            }
        ],
        total=1,
    )


READS: tuple[ActionSpec, ...] = (
    ActionSpec(
        name="get_profile",
        description="The person's confirmed profile: headline, summary, experience, education, "
        "skills, projects, certifications. The only source of facts about the person.",
        args=NoArgs,
        kind="read",
        handler=get_profile,
        mirrors=("GET /profile",),
    ),
    ActionSpec(
        name="get_preferences",
        description="The person's job preferences: roles, places, work mode, pay and the rest.",
        args=NoArgs,
        kind="read",
        handler=read_preferences,
        mirrors=("GET /preferences",),
    ),
    ActionSpec(
        name="get_search_rules",
        description="The approved search rules, and a proposal waiting for approval if any.",
        args=NoArgs,
        kind="read",
        handler=get_search_rules,
        mirrors=("GET /search/rules",),
    ),
)
