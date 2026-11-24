"""The catalogue of actions, and what is deliberately left out (FR-016, research R14).

Left-out endpoints are not in the catalogue at all, so the model has no way to call them;
Mikasa declines and links to the page where the person does it themselves.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from hiretitan.actions.spec import ActionSpec, to_tool_spec
from hiretitan.platform.llm.port import ToolSpec


class ExcludedActionError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class Excluded:
    page: str  # where the person does it themselves
    why: str


EXCLUDED: Final[Mapping[str, Excluded]] = {
    "POST /data/delete-all": Excluded("/settings", "Delete all my data is yours to do."),
    "PUT /settings/ai-key": Excluded("/settings", "The AI key is set in Settings."),
    "DELETE /settings/ai-key": Excluded("/settings", "The AI key is removed in Settings."),
    "POST /status/ai/check": Excluded("/settings", "The key check runs from Settings."),
    "POST /mail/connect": Excluded("/settings/gmail", "Gmail is connected in Settings."),
    "PUT /mail/credentials": Excluded("/settings/gmail", "Google sign-in is set in Settings."),
    "DELETE /mail/connection": Excluded("/settings/gmail", "Gmail is disconnected in Settings."),
    "POST /profile/reviews/manual": Excluded("/profile", "Profile facts change on Profile."),
    "POST /profile/reviews/{review_id}/confirm": Excluded(
        "/profile", "Profile facts change only on the review screen."
    ),
    "POST /profile/reviews/{review_id}/discard": Excluded(
        "/profile", "Profile reviews are decided on the review screen."
    ),
    "PUT /profile/reviews/{review_id}/draft": Excluded(
        "/profile", "Profile facts are edited on the review screen."
    ),
    "POST /profile/versions": Excluded("/profile/versions", "Profile versions are kept there."),
    "POST /resumes": Excluded("/profile", "Resume files are uploaded on Profile."),
    "DELETE /resumes/{resume_id}": Excluded("/profile", "Resume files are removed on Profile."),
    "POST /onboarding/complete": Excluded("/", "Setup is finished in the setup steps."),
    "POST /companies/contacts/linkedin-import": Excluded(
        "/companies", "A LinkedIn export is a file you import on Companies."
    ),
    "PUT /drafts/{draft_id}": Excluded("/", "A draft's text is edited on its job's page."),
    "PUT /jobs/{job_id}/tailored-resume": Excluded(
        "/", "A tailored resume is edited in its preview."
    ),
    "PUT /jobs/{job_id}/description": Excluded(
        "/", "A job's description is pasted on its page, so it is never sent to the AI."
    ),
    "DELETE /pipeline/resumes/{file_id}/uses": Excluded(
        "/profile", "A removed resume file's name is cleared when the file is removed."
    ),
    "POST /runs/{run_id}/decision": Excluded(
        "/review", "A resume import's questions are answered on the Review page."
    ),
    "POST /runs/{run_id}/retry": Excluded("/review", "A paused import is retried on Review."),
    "PUT /search/rules/approved": Excluded(
        "/profile/search-rules", "Mikasa changes rules only through a proposal you approve."
    ),
    "POST /search/rules/proposal": Excluded(
        "/profile/search-rules", "Fresh rules from your profile are proposed on that page."
    ),
}

# Names a model might reach for: refused outright, so nobody adds them by accident.
EXCLUDED_NAMES: Final = frozenset(
    {
        "delete_all_data",
        "set_ai_key",
        "remove_ai_key",
        "check_ai_key",
        "connect_gmail",
        "disconnect_gmail",
        "set_gmail_credentials",
        "confirm_profile_review",
        "discard_profile_review",
        "edit_profile_review",
        "edit_profile",
        "upload_resume",
        "remove_resume_file",
        "save_profile_version",
        "complete_onboarding",
        "import_linkedin_contacts",
        "edit_draft_text",
        "edit_tailored_resume_text",
        "send_message",
        "send_email",
        "submit_application",
    }
)


class Catalogue:
    def __init__(self) -> None:
        self._specs: dict[str, ActionSpec] = {}

    def register(self, spec: ActionSpec) -> None:
        if spec.name in EXCLUDED_NAMES:
            raise ExcludedActionError(f"{spec.name} is deliberately not an action (FR-016)")
        if spec.name in self._specs:
            raise ValueError(f"{spec.name} is already registered")
        self._specs[spec.name] = spec

    def get(self, name: str) -> ActionSpec | None:
        return self._specs.get(name)

    def specs(self) -> list[ActionSpec]:
        return list(self._specs.values())

    def tool_specs(self) -> list[ToolSpec]:
        return [to_tool_spec(spec) for spec in self._specs.values()]
