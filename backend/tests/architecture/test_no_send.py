"""Constitution I: the app never sends messages, emails or applications.

Two static checks over ``src/hiretitan`` (AST, so comments and strings don't count):

* no module that can send messages is imported;
* every HTTP or AI client is built against a host in
  ``hiretitan.platform.security.outbound_allowlist``, and no one-shot HTTP helper
  (``httpx.get``, ``urllib.request.urlopen``, ``requests``) is used at all.

Each check also runs on planted sources so a broken scanner can't pass silently.
"""

from __future__ import annotations

import ast
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from hiretitan.platform.security import outbound_allowlist
from hiretitan.platform.security.outbound_allowlist import (
    ALLOWED_HOSTS,
    OutboundHostNotAllowedError,
    allowed_base_url,
)

PACKAGE = Path(__file__).resolve().parents[2] / "src" / "hiretitan"

SENDING_MODULES = (
    "smtplib",
    "aiosmtplib",
    "yagmail",
    "email.mime",
    "sendgrid",
    "mailjet_rest",
    "postmarker",
    "resend",
    "mailchimp_transactional",
    "twilio",
    "vonage",
    "plivo",
    "slack_sdk",
    "slack",
    "telegram",
    "discord",
    "pywhatkit",
    "imaplib",  # read-only mail comes later through Gmail's API, not raw IMAP/SMTP
)

# Raw HTTP helpers that bypass a configured client (and so the allowlist).
FORBIDDEN_HTTP_MODULES = ("requests", "urllib.request", "aiohttp", "http.client")
FORBIDDEN_HTTPX_FUNCTIONS = frozenset(
    {"get", "post", "put", "patch", "delete", "head", "options", "request", "stream"}
)
CLIENT_CONSTRUCTORS = frozenset({"Client", "AsyncClient", "OpenAI", "AsyncOpenAI"})


def _matches(module: str, banned: tuple[str, ...]) -> bool:
    return any(module == b or module.startswith(b + ".") for b in banned)


def _imported_modules(tree: ast.AST) -> list[str]:
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.append(node.module)
            found.extend(f"{node.module}.{alias.name}" for alias in node.names)
    return found


def sending_violations(source: str) -> list[str]:
    tree = ast.parse(source)
    return sorted({m for m in _imported_modules(tree) if _matches(m, SENDING_MODULES)})


def _call_name(func: ast.expr) -> str | None:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _host_is_allowed(node: ast.expr) -> bool:
    """A base_url is allowed if it is a literal URL on an allowlisted host, or a
    call to ``allowed_base_url("<allowlisted host>", ...)``."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return urlsplit(node.value).hostname in ALLOWED_HOSTS
    if isinstance(node, ast.Call) and _call_name(node.func) == "allowed_base_url":
        first = node.args[0] if node.args else None
        return (
            isinstance(first, ast.Constant)
            and isinstance(first.value, str)
            and first.value in ALLOWED_HOSTS
        )
    return False


def outbound_violations(source: str) -> list[str]:
    tree = ast.parse(source)
    problems = [
        f"raw HTTP module {m}"
        for m in _imported_modules(tree)
        if _matches(m, FORBIDDEN_HTTP_MODULES)
    ]
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Name)
            and func.value.id == "httpx"
            and func.attr in FORBIDDEN_HTTPX_FUNCTIONS
        ):
            problems.append(f"line {node.lineno}: one-shot httpx.{func.attr}()")
            continue
        name = _call_name(func)
        if name not in CLIENT_CONSTRUCTORS:
            continue
        base_url = next((kw.value for kw in node.keywords if kw.arg == "base_url"), None)
        if base_url is None or not _host_is_allowed(base_url):
            problems.append(f"line {node.lineno}: {name}() without an allowlisted base_url")
    return problems


def _package_sources() -> list[tuple[Path, str]]:
    return [(p, p.read_text(encoding="utf-8")) for p in sorted(PACKAGE.rglob("*.py"))]


def test_constitution_I_no_sending_modules_imported() -> None:
    violations = {
        str(path.relative_to(PACKAGE)): found
        for path, source in _package_sources()
        if (found := sending_violations(source))
    }
    assert violations == {}


def test_constitution_I_outbound_hosts_allowlisted() -> None:
    violations = {
        str(path.relative_to(PACKAGE)): found
        for path, source in _package_sources()
        if (found := outbound_violations(source))
    }
    assert violations == {}


def test_constitution_I_allowlist_holds_only_openai() -> None:
    assert frozenset({"api.openai.com"}) == ALLOWED_HOSTS
    assert allowed_base_url("api.openai.com") == "https://api.openai.com/v1"
    with pytest.raises(OutboundHostNotAllowedError):
        allowed_base_url("smtp.gmail.com")


def test_allowlist_module_is_scanned() -> None:
    assert Path(outbound_allowlist.__file__).is_relative_to(PACKAGE)


@pytest.mark.parametrize(
    "source",
    [
        "import smtplib\n",
        "from email.mime.text import MIMEText\n",
        "from twilio.rest import Client\n",
        "import slack_sdk.web\n",
        "from telegram import Bot\n",
    ],
)
def test_planted_sender_is_caught(source: str) -> None:
    assert sending_violations(source)


@pytest.mark.parametrize(
    "source",
    [
        "import requests\n",
        "from urllib.request import urlopen\n",
        "import httpx\nhttpx.post('https://hooks.example.com', json={})\n",
        "import httpx\nhttpx.AsyncClient()\n",
        "import httpx\nhttpx.Client(base_url='https://evil.example.com')\n",
        "from openai import AsyncOpenAI\nAsyncOpenAI(api_key='k')\n",
        "from openai import OpenAI\nOpenAI(base_url=allowed_base_url('evil.example.com'))\n",
        "from openai import OpenAI\nOpenAI(base_url=some_variable)\n",
    ],
)
def test_planted_outbound_call_is_caught(source: str) -> None:
    assert outbound_violations(source)


@pytest.mark.parametrize(
    "source",
    [
        "import httpx\nhttpx.AsyncClient(base_url='https://api.openai.com/v1')\n",
        "from openai import AsyncOpenAI\n"
        "AsyncOpenAI(api_key='k', base_url=allowed_base_url('api.openai.com'))\n",
    ],
)
def test_allowlisted_client_passes(source: str) -> None:
    assert outbound_violations(source) == []
