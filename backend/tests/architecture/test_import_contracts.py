"""Constitution VI: layer and module boundaries are enforced by import-linter.

The contracts live in ``backend/.importlinter``. The first test checks the real
package; the planted-violation tests copy the package to a temp dir, add one
offending module per contract and check that ``lint-imports`` fails, so a
contract that silently stops matching anything is caught.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2]
CONFIG = BACKEND / ".importlinter"
LINT_IMPORTS = Path(sys.executable).parent / (
    "lint-imports.exe" if os.name == "nt" else "lint-imports"
)


def _run_lint_imports(src_root: Path, cwd: Path) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PYTHONPATH": str(src_root)}
    return subprocess.run(
        [str(LINT_IMPORTS), "--config", str(CONFIG), "--no-cache", "--no-logo"],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_constitution_VI_import_contracts_hold() -> None:
    result = _run_lint_imports(BACKEND / "src", BACKEND)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "0 broken" in result.stdout


# violation name -> {path inside the hiretitan package: source}
PLANTED_VIOLATIONS: dict[str, dict[str, str]] = {
    "domain_imports_framework": {"profile/domain/bad.py": "import fastapi\n"},
    "domain_imports_runtime": {
        # the runtime package may not exist yet, so the plant brings its own
        "platform/runtime/__init__.py": "",
        "preferences/domain/bad.py": "import hiretitan.platform.runtime\n",
    },
    "lower_layer_imports_higher": {"profile/domain/bad.py": "import hiretitan.profile.api\n"},
    "infra_imports_api": {"setup/infra/bad.py": "import hiretitan.setup.api\n"},
    "module_bypasses_application": {
        "profile/application/bad.py": "import hiretitan.preferences.infra\n",
    },
    "platform_imports_feature": {"platform/bad.py": "import hiretitan.profile\n"},
    # feature 002: the search module is held to the same contracts
    "search_domain_imports_sqlalchemy": {"search/domain/bad.py": "import sqlalchemy\n"},
    "search_lower_layer_imports_higher": {"search/domain/bad.py": "import hiretitan.search.api\n"},
    # feature 002c: the mail module is held to the same contracts
    "mail_domain_imports_sqlalchemy": {"mail/domain/bad.py": "import sqlalchemy\n"},
    "mail_infra_imports_api": {
        "mail/api/__init__.py": "",
        "mail/infra/bad.py": "import hiretitan.mail.api\n",
    },
    "mail_imports_search": {"mail/infra/bad.py": "import hiretitan.search.application\n"},
    "mail_imports_profile": {"mail/domain/bad.py": "import hiretitan.profile.domain\n"},
    "search_imports_mail": {"search/application/bad.py": "import hiretitan.mail.domain.senders\n"},
    "profile_imports_mail": {"profile/application/bad.py": "import hiretitan.mail.infra\n"},
    "search_bypasses_application": {
        "search/application/bad.py": "import hiretitan.profile.infra\n",
    },
    "other_module_bypasses_search_application": {
        "profile/application/bad.py": "import hiretitan.search.infra\n",
    },
    "platform_imports_search": {"platform/bad.py": "import hiretitan.search\n"},
    # feature 002k: the drafts module imports no other feature module, and its domain is pure
    "drafts_imports_search": {"drafts/application/bad.py": "import hiretitan.search.application\n"},
    "drafts_imports_profile": {"drafts/workflow/bad.py": "import hiretitan.profile.application\n"},
    "drafts_domain_imports_framework": {"drafts/domain/bad.py": "import sqlalchemy\n"},
    "drafts_lower_layer_imports_higher": {"drafts/domain/bad.py": "import hiretitan.drafts.api\n"},
    "other_module_bypasses_drafts_application": {
        "profile/application/bad.py": "import hiretitan.drafts.infra\n",
    },
    "platform_imports_drafts": {"platform/bad.py": "import hiretitan.drafts\n"},
}


def _lint_with_plants(plants: dict[str, str], tmp_path: Path) -> subprocess.CompletedProcess[str]:
    src_root = tmp_path / "src"
    shutil.copytree(
        BACKEND / "src" / "hiretitan",
        src_root / "hiretitan",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    for rel_path, source in plants.items():
        target = src_root / "hiretitan" / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            target.write_text(source, encoding="utf-8")
    return _run_lint_imports(src_root, tmp_path)


@pytest.mark.parametrize("violation", sorted(PLANTED_VIOLATIONS))
def test_constitution_VI_planted_violation_fails(violation: str, tmp_path: Path) -> None:
    result = _lint_with_plants(PLANTED_VIOLATIONS[violation], tmp_path)

    assert result.returncode != 0, f"{violation} was not caught:\n{result.stdout}"
    assert "BROKEN" in result.stdout


# feature 002b (FR-022): contacts and notes never reach an AI prompt, so the search workflow,
# the prompts and the LLM platform may not import the contacts code. Each plant brings its own
# contacts module because the real one is written later in the feature.
CONTACTS_MODULE = "search/application/contacts.py"
CONTACTS_PLANTS = {
    "search_workflow": "search/workflow/bad.py",
    "prompts": "prompts/bad.py",
    "platform_llm": "platform/llm/bad.py",
}


@pytest.mark.parametrize("where", sorted(CONTACTS_PLANTS))
def test_FR022_workflows_prompts_and_llm_cannot_import_contacts(where: str, tmp_path: Path) -> None:
    plants = {
        CONTACTS_MODULE: "",
        CONTACTS_PLANTS[where]: "import hiretitan.search.application.contacts\n",
    }

    result = _lint_with_plants(plants, tmp_path)

    assert result.returncode != 0, f"{where} was not caught:\n{result.stdout}"
    assert "BROKEN" in result.stdout


def test_FR022_drafts_contracts_present() -> None:
    config = CONFIG.read_text(encoding="utf-8")
    assert "hiretitan.drafts.domain" in config  # pure-domain and layer containers
    assert "contract:drafts-boundary" in config
    for module in ("hiretitan.drafts.infra", "hiretitan.drafts.workflow", "hiretitan.drafts.api"):
        assert config.count(module) >= 4, module  # forbidden for the four other modules


def test_FR022_drafts_workflow_may_not_import_contacts(tmp_path: Path) -> None:
    plants = {
        CONTACTS_MODULE: "",
        "drafts/workflow/bad.py": "import hiretitan.search.application.contacts\n",
    }

    result = _lint_with_plants(plants, tmp_path)

    assert result.returncode != 0, result.stdout
    assert "BROKEN" in result.stdout


def test_FR006_mail_contracts_present() -> None:
    config = CONFIG.read_text(encoding="utf-8")
    assert "contract:mail-boundary" in config
    assert "contract:mail-layers" in config
    assert config.count("hiretitan.mail.domain") >= 2  # pure-domain, and the others' boundaries
    for module in ("hiretitan.mail.infra", "hiretitan.mail.workflow", "hiretitan.mail.api"):
        assert config.count(module) >= 4, module  # forbidden for the four other modules
