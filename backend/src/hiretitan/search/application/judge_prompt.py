"""Build the ``judge_relevance`` request: the cards go inside untrusted data blocks (FR-039)."""

from __future__ import annotations

import json
from dataclasses import dataclass

from hiretitan.platform.llm.port import RenderedPrompt
from hiretitan.platform.llm.prompts import LoadedPrompt
from hiretitan.platform.untrusted.delimit import delimit
from hiretitan.search.domain.cards import JobCardInput, ProfileCard, job_cards


@dataclass(frozen=True, slots=True)
class JudgePrompt:
    prompt: RenderedPrompt
    refs: list[str]  # the refs the answer must contain, each once


def render_judge_prompt(
    prompt: LoadedPrompt, profile: ProfileCard, jobs: list[JobCardInput]
) -> JudgePrompt:
    cards, refs = job_cards(jobs)
    profile_block = delimit("profile_card", json.dumps(profile.to_dict(), ensure_ascii=False))
    jobs_block = delimit("job_cards", json.dumps(cards, ensure_ascii=False))
    rendered = prompt.render(profile_block=profile_block.text, jobs_block=jobs_block.text)
    return JudgePrompt(rendered, refs)
