"""Build the ``extract_jobs_from_page`` request: page text goes inside untrusted data blocks."""

from __future__ import annotations

from hiretitan.platform.llm.port import RenderedPrompt
from hiretitan.platform.llm.prompts import LoadedPrompt
from hiretitan.platform.untrusted.delimit import delimit


def render_extract_prompt(prompt: LoadedPrompt, page_text: str, page_url: str) -> RenderedPrompt:
    return prompt.render(
        address_block=delimit("page_address", page_url).text,
        page_block=delimit("careers_page", page_text).text,
    )
