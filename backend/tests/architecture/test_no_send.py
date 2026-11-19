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
import re
import sys
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

# Feature 002 (constitution VII): companies' careers pages live on hosts nobody can list in
# advance, so exactly one module may build an HTTP client for them. It is held to GET/HEAD,
# robots.txt and rate limits by its own contract tests (T051). Nothing else under
# ``search/`` may build a client, and nothing there may use a mutating HTTP verb.
CAREERS_FETCHER = Path("search/infra/careers_page/fetcher.py")
# Feature 002i: a second exemption. Reading a posting's own text goes to the public job API of the
# board it was listed on (the same hosts career-ops already reads, five vendors, GET only). That
# module may build a client, but only for requests ``descriptions/allowlist.py`` names, which its
# contract test enforces by intercepting every request (tests/contract/descriptions).
DESCRIPTION_READER = Path("search/infra/descriptions/reader.py")
HTTP_CLIENT_MODULES = frozenset({CAREERS_FETCHER, DESCRIPTION_READER})
SEARCH_PACKAGE = Path("search")
MUTATING_VERBS = frozenset({"post", "put", "patch", "delete"})


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


def search_http_violations(source: str, *, is_fetcher: bool) -> list[str]:
    """Rules for code under ``search/``: only the careers-page fetcher builds HTTP clients,
    and no module there calls a mutating HTTP verb (the app never submits anything)."""
    tree = ast.parse(source)
    problems: list[str] = []
    # ``@router.post(...)`` registers an endpoint the app answers; it sends nothing
    route_decorators = {
        id(decorator)
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        for decorator in node.decorator_list
    }
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or id(node) in route_decorators:
            continue
        name = _call_name(node.func)
        if name in CLIENT_CONSTRUCTORS and not is_fetcher:
            problems.append(f"line {node.lineno}: {name}() outside the careers-page fetcher")
        if isinstance(node.func, ast.Attribute) and node.func.attr in MUTATING_VERBS:
            problems.append(f"line {node.lineno}: mutating HTTP verb .{node.func.attr}()")
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
        if path.relative_to(PACKAGE) not in HTTP_CLIENT_MODULES
        and (found := outbound_violations(source))
    }
    assert violations == {}


def test_constitution_I_search_module_has_no_sending_code() -> None:
    violations = {
        str(path.relative_to(PACKAGE)): found
        for path, source in _package_sources()
        if path.relative_to(PACKAGE).is_relative_to(SEARCH_PACKAGE)
        and (found := sending_violations(source))
    }
    assert violations == {}


def test_constitution_VII_careers_pages_fetched_only_through_the_fetcher() -> None:
    violations = {
        str(path.relative_to(PACKAGE)): found
        for path, source in _package_sources()
        if path.relative_to(PACKAGE).is_relative_to(SEARCH_PACKAGE)
        and (
            found := search_http_violations(
                source, is_fetcher=path.relative_to(PACKAGE) in HTTP_CLIENT_MODULES
            )
        )
    }
    assert violations == {}


def test_the_fetcher_is_the_only_outbound_exemption() -> None:
    # A look-alike module elsewhere under search/ must not be mistaken for the exempt one.
    lookalikes = [
        str(path.relative_to(PACKAGE))
        for path in PACKAGE.joinpath(SEARCH_PACKAGE).rglob("fetcher*.py")
        if path.relative_to(PACKAGE) != CAREERS_FETCHER
    ]
    assert lookalikes == []


def test_the_description_reader_is_the_only_other_http_module_under_search() -> None:
    """002i: exactly two modules under ``search/`` build an HTTP client."""
    builders = sorted(
        str(path.relative_to(PACKAGE))
        for path in PACKAGE.joinpath(SEARCH_PACKAGE).rglob("*.py")
        if any(
            _call_name(node.func) in CLIENT_CONSTRUCTORS
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
            if isinstance(node, ast.Call)
        )
    )
    assert builders == sorted(str(p) for p in HTTP_CLIENT_MODULES)


def test_constitution_I_allowlist_holds_only_the_ai_provider_and_google_for_mail() -> None:
    # feature 002c adds the two Google hosts the read-only mail reader needs, and nothing else
    assert frozenset({"api.openai.com", "gmail.googleapis.com", "oauth2.googleapis.com"}) == (
        ALLOWED_HOSTS
    )
    assert allowed_base_url("api.openai.com") == "https://api.openai.com/v1"
    assert allowed_base_url("gmail.googleapis.com", "/gmail/v1") == (
        "https://gmail.googleapis.com/gmail/v1"
    )
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


@pytest.mark.parametrize(
    ("source", "is_fetcher"),
    [
        ("import httpx\nhttpx.AsyncClient()\n", False),
        ("import httpx\nc = httpx.Client()\n", False),
        ("async def f(c):\n    await c.post('https://x.example', json={})\n", True),
        ("async def f(c):\n    await c.put('https://x.example')\n", False),
        ("async def f(c):\n    await c.delete('https://x.example')\n", True),
    ],
)
def test_planted_search_http_violation_is_caught(source: str, is_fetcher: bool) -> None:
    assert search_http_violations(source, is_fetcher=is_fetcher)


@pytest.mark.parametrize(
    ("source", "is_fetcher"),
    [
        ("import httpx\nhttpx.AsyncClient(timeout=15)\n", True),
        ("async def f(c):\n    return await c.get('https://x.example')\n", True),
        ("async def f(c):\n    return await c.head('https://x.example')\n", False),
        ("def f(d):\n    return d.get('k')\n", False),
    ],
)
def test_allowed_search_http_usage_passes(source: str, is_fetcher: bool) -> None:
    assert search_http_violations(source, is_fetcher=is_fetcher) == []


# Feature 002b (FR-015): the contacts code only stores and shows other people's details. It has no
# way to send anything and no HTTP client at all (LinkedIn links are stored, never fetched).
# Feature 002e: the interview notes (a contact, rounds, questions) are the same kind of data.
CONTACTS_GLOBS = (
    "search/domain/contacts*.py",
    "search/application/contacts.py",
    "search/domain/interviews.py",
    "search/application/interviews.py",
    "search/api/interviews.py",
)
CONTACTS_FORBIDDEN_CLIENT_MODULES = ("httpx", "requests", "aiohttp", "urllib.request")


def contacts_client_violations(source: str) -> list[str]:
    tree = ast.parse(source)
    return sorted(
        {m for m in _imported_modules(tree) if _matches(m, CONTACTS_FORBIDDEN_CLIENT_MODULES)}
    )


def _contacts_sources() -> list[tuple[Path, str]]:
    paths = sorted({p for pattern in CONTACTS_GLOBS for p in PACKAGE.glob(pattern)})
    return [(p, p.read_text(encoding="utf-8")) for p in paths]


def test_FR015_no_send_path_in_contacts_code() -> None:
    violations = {
        str(path.relative_to(PACKAGE)): found
        for path, source in _contacts_sources()
        if (found := sending_violations(source))
    }
    assert violations == {}


def test_FR015_contacts_code_has_no_http_client() -> None:
    violations = {
        str(path.relative_to(PACKAGE)): found
        for path, source in _contacts_sources()
        if (found := contacts_client_violations(source))
    }
    assert violations == {}


@pytest.mark.parametrize(
    "source",
    [
        "import httpx\n",
        "from httpx import AsyncClient\n",
        "import requests\n",
        "import aiohttp\n",
        "from urllib.request import urlopen\n",
    ],
)
def test_FR015_planted_http_client_in_contacts_code_is_caught(source: str) -> None:
    assert contacts_client_violations(source)


@pytest.mark.parametrize("source", ["import smtplib\n", "from twilio.rest import Client\n"])
def test_FR015_planted_sender_in_contacts_code_is_caught(source: str) -> None:
    assert sending_violations(source)


def test_FR015_contacts_globs_are_not_stale() -> None:
    # every pattern must still point at the search package, so a rename can't empty the scan
    assert all(pattern.startswith("search/") for pattern in CONTACTS_GLOBS)


# Feature 002k (constitution I): the drafts module only writes text for the person to copy. It has
# no way to send it and no HTTP client at all.
DRAFTS_PACKAGE = Path("drafts")


def _drafts_sources() -> list[tuple[Path, str]]:
    return [
        (p, s)
        for p, s in _package_sources()
        if p.relative_to(PACKAGE).is_relative_to(DRAFTS_PACKAGE)
    ]


def test_SC007_no_send_scans_drafts() -> None:
    sources = _drafts_sources()
    assert len(sources) > 10, "the scan must actually see the drafts module"
    bad: dict[str, list[str]] = {}
    for path, source in sources:
        found = sending_violations(source) + contacts_client_violations(source)
        if found:
            bad[str(path.relative_to(PACKAGE))] = found
    assert bad == {}


@pytest.mark.parametrize(
    "source",
    ["import smtplib\n", "import httpx\n", "import requests\n", "from twilio.rest import Client\n"],
)
def test_SC007_planted_sender_or_client_in_drafts_is_caught(source: str) -> None:
    assert sending_violations(source) or contacts_client_violations(source)


# Feature 002c (constitution I and VII): the mail reader is read-only. Exactly two modules may build
# an HTTP client, each for its own Google host; the Gmail client only GETs, and the sign-in module
# only POSTs (token exchange and revoke). No other call in the package may use a mutating verb, and
# the job-site hosts are never allowlisted (the alert links are shown, never fetched: FR-015).
MAIL_PACKAGE = Path("mail")
GMAIL_CLIENT = Path("mail/infra/gmail_client.py")
GOOGLE_OAUTH = Path("mail/infra/google_oauth.py")
MAIL_VERBS = {GMAIL_CLIENT: frozenset[str](), GOOGLE_OAUTH: frozenset({"post"})}
BANNED_MAIL_CALLS = MUTATING_VERBS | {"request", "send", "stream", "sendall"}
JOB_SITE_HOSTS = (
    "linkedin.com",
    "naukri.com",
    "indeed.com",
    "foundit.in",
    "instahyre.com",
    "cutshort.io",
)


# What the mail package may import: the standard library except the network and process modules
# below, plus these third-party roots. Adding a root is a deliberate review.
MAIL_THIRD_PARTY = frozenset(
    {"hiretitan", "sqlalchemy", "pydantic", "yaml", "fastapi", "starlette", "procrastinate"}
)
MAIL_BANNED_IMPORTS = (
    "smtplib",
    "imaplib",
    "poplib",
    "ftplib",
    "telnetlib",
    "socket",
    "ssl",
    "http.client",
    "urllib.request",
    "xmlrpc",
    "asyncio.streams",
    "subprocess",
    "ctypes",
    "importlib",
    "runpy",
)
MAIL_HTTP_LIBRARY = "httpx"  # only inside the two Google modules
# Names that would hide a call from the checks (a dynamic attribute, a late import, a raw request).
MAIL_BANNED_NAMES = frozenset(
    {
        "getattr",
        "__import__",
        "eval",
        "exec",
        "import_module",
        "build_request",
        "__getattribute__",
        "__dict__",
    }
)
# A Gmail path that changes or sends something. Reading is only messages and profile.
MAIL_WRITE_PATH = re.compile(
    r"/(send|drafts?|modify|batchModify|batchDelete|trash|untrash|delete|insert|import|watch|stop"
    r"|labels|settings|threads)\b",
    re.IGNORECASE,
)
GMAIL_HOST = "gmail.googleapis.com"
OAUTH_HOST = "oauth2.googleapis.com"
GOOGLE_HOST_OWNERS = {GMAIL_HOST: GMAIL_CLIENT, OAUTH_HOST: GOOGLE_OAUTH}


def _is_route_decorator(node: ast.expr, module: Path) -> bool:
    """``@router.delete(...)`` on an API route is the app's own endpoint, not an outgoing call."""
    return (
        module.parts[:2] == ("mail", "api")
        and isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id in {"router", "app"}
    )


def mail_http_violations(source: str, *, module: Path) -> list[str]:
    tree = ast.parse(source)
    allowed_verbs = MAIL_VERBS.get(module)
    google_module = allowed_verbs is not None
    route_decorators = {
        id(decorator.func)
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        for decorator in node.decorator_list
        if isinstance(decorator, ast.Call) and _is_route_decorator(decorator, module)
    }
    problems: list[str] = []
    for imported in _imported_modules(tree):
        root = imported.split(".")[0]
        if _matches(imported, MAIL_BANNED_IMPORTS):
            problems.append(f"imports {imported}, which can reach the network or run code")
        elif root == MAIL_HTTP_LIBRARY:
            if not google_module:
                problems.append("imports httpx outside the two Google modules")
        elif root not in sys.stdlib_module_names and root not in MAIL_THIRD_PARTY:
            problems.append(f"imports {root}, which the mail package does not allow")
    for node in ast.walk(tree):
        line = getattr(node, "lineno", 0)
        if (
            isinstance(node, ast.Call)
            and _call_name(node.func) in CLIENT_CONSTRUCTORS
            and not google_module
        ):
            problems.append(f"line {line}: an HTTP client outside the two Google modules")
        if (
            isinstance(node, ast.Attribute)
            and id(node) not in route_decorators
            and node.attr in BANNED_MAIL_CALLS
            and node.attr not in (allowed_verbs or frozenset())
        ):
            # any use, not only a call: ``send = client.post`` would hide it from a call check
            problems.append(f"line {line}: .{node.attr} is not allowed here")
        if isinstance(node, ast.Name | ast.Attribute):
            name = node.id if isinstance(node, ast.Name) else node.attr
            if name in MAIL_BANNED_NAMES:
                problems.append(f"line {line}: {name} can hide a call from this check")
        if isinstance(node, ast.alias) and node.name.split(".")[-1] in MAIL_BANNED_NAMES:
            problems.append(f"imports {node.name}")
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if MAIL_WRITE_PATH.search(node.value):
                problems.append(f"line {line}: {node.value!r} looks like a Gmail write path")
            for host, owner in GOOGLE_HOST_OWNERS.items():
                if host in node.value and module != owner:
                    problems.append(f"line {line}: {host} is named outside {owner}")
    return problems


def _mail_sources() -> list[tuple[Path, str]]:
    return [
        (p, s) for p, s in _package_sources() if p.relative_to(PACKAGE).is_relative_to(MAIL_PACKAGE)
    ]


def test_SC007_mail_package_scanned() -> None:
    sources = _mail_sources()
    assert len(sources) > 5, "the scan must actually see the mail package"
    bad: dict[str, list[str]] = {}
    for path, source in sources:
        relative = path.relative_to(PACKAGE)
        found = sending_violations(source) + mail_http_violations(source, module=relative)
        if found:
            bad[str(relative)] = found
    assert bad == {}


def test_FR015_no_job_site_host_is_allowlisted() -> None:
    for host in ALLOWED_HOSTS:
        assert not any(host == site or host.endswith("." + site) for site in JOB_SITE_HOSTS), host


def test_FR007_only_the_two_google_modules_build_a_client_in_mail() -> None:
    builders = {
        path.relative_to(PACKAGE)
        for path, source in _mail_sources()
        if any(
            _call_name(node.func) in CLIENT_CONSTRUCTORS
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.Call)
        )
    }
    assert builders <= {GMAIL_CLIENT, GOOGLE_OAUTH}


GMAIL_URL = "https://gmail.googleapis.com/x"
OAUTH_URL = "https://oauth2.googleapis.com/x"


@pytest.mark.parametrize(
    ("source", "module"),
    [
        (f"async def f(c):\n    await c.post('{GMAIL_URL}')\n", GMAIL_CLIENT),
        (f"async def f(c):\n    await c.put('{GMAIL_URL}')\n", GMAIL_CLIENT),
        (f"async def f(c):\n    await c.delete('{GMAIL_URL}')\n", GMAIL_CLIENT),
        ("async def f(c):\n    await c.request('DELETE', '/x')\n", GMAIL_CLIENT),
        (f"async def f(c):\n    await c.put('{OAUTH_URL}')\n", GOOGLE_OAUTH),
        (f"async def f(c):\n    await c.delete('{OAUTH_URL}')\n", GOOGLE_OAUTH),
        ("import httpx\nhttpx.AsyncClient()\n", Path("mail/infra/repos.py")),
        ("async def f(c):\n    await c.send(1)\n", Path("mail/workflow/check.py")),
        ("async def f(c):\n    await c.post('x')\n", Path("mail/workflow/check.py")),
    ],
)
def test_SC007_planted_mail_violation_is_caught(source: str, module: Path) -> None:
    assert mail_http_violations(source, module=module)


OTHER = Path("mail/infra/other.py")


@pytest.mark.parametrize(
    ("source", "module"),
    [
        ("async def f(c):\n    send = c.post\n    await send('x')\n", GMAIL_CLIENT),  # an alias
        ("import httpx as h\nh.AsyncClient()\n", OTHER),
        ("import requests\n", OTHER),
        ("import aiohttp\n", OTHER),
        ("import http.client\n", GMAIL_CLIENT),
        ("from urllib.request import urlopen\n", GMAIL_CLIENT),
        ("import socket\n", OTHER),
        ("import smtplib\n", OTHER),
        ("import importlib\n", OTHER),
        ("from googleapiclient import discovery\n", OTHER),
        ("import httpx\n", OTHER),  # httpx lives only in the two Google modules
        ("def f(c):\n    return getattr(c, 'po' + 'st')\n", GMAIL_CLIENT),
        ("def f():\n    return __import__('requests')\n", OTHER),
        ("def f(c):\n    return c.build_request('POST', 'x')\n", GMAIL_CLIENT),
        ("from importlib import import_module\n", OTHER),
        ("@c.post('/x')\ndef f():\n    pass\n", OTHER),  # a decorator is not a free pass
        ("@c.delete('/x')\ndef f():\n    pass\n", Path("mail/workflow/x.py")),
        ("@other.delete('/x')\ndef f():\n    pass\n", Path("mail/api/x.py")),
        # sign-in may POST, but never to Gmail; the Gmail client never names the sign-in host
        (f"async def f(c):\n    await c.post('{GMAIL_URL}/gmail/v1/users/me/x')\n", GOOGLE_OAUTH),
        (f"URL = '{OAUTH_URL}/token'\n", GMAIL_CLIENT),
        (f"URL = '{GMAIL_URL}/gmail/v1/users/me/profile'\n", OTHER),
        (f"URL = '{GMAIL_URL}/gmail/v1/users/me/messages/send'\n", GMAIL_CLIENT),
        (f"URL = '{GMAIL_URL}/gmail/v1/users/me/drafts'\n", GMAIL_CLIENT),
        (f"URL = '{GMAIL_URL}/gmail/v1/users/me/messages/abc/modify'\n", GMAIL_CLIENT),
        (f"URL = '{GMAIL_URL}/gmail/v1/users/me/messages/abc/trash'\n", GMAIL_CLIENT),
        ("PATH = 'users/me/messages/batchDelete'\n", GMAIL_CLIENT),
        ("PATH = 'users/me/labels'\n", GMAIL_CLIENT),
    ],
)
def test_SC007_planted_mail_bypass_is_caught(source: str, module: Path) -> None:
    assert mail_http_violations(source, module=module)


def test_FR015_only_the_two_google_modules_name_the_google_hosts() -> None:
    allowed = {
        Path("platform/security/outbound_allowlist.py"),
        GMAIL_CLIENT,
        GOOGLE_OAUTH,
    }
    named = {
        path.relative_to(PACKAGE)
        for path, source in _package_sources()
        if GMAIL_HOST in source or OAUTH_HOST in source
    }
    assert named <= allowed, sorted(str(p) for p in named - allowed)


@pytest.mark.parametrize(
    ("source", "module"),
    [
        (f"async def f(c):\n    return await c.get('{GMAIL_URL}')\n", GMAIL_CLIENT),
        (f"async def f(c):\n    return await c.post('{OAUTH_URL}')\n", GOOGLE_OAUTH),
        ("import httpx\nhttpx.AsyncClient(timeout=10)\n", GMAIL_CLIENT),
        ("def f(d):\n    return d.get('k')\n", Path("mail/domain/mime.py")),
        (
            "@router.delete('/mail/connection')\nasync def g():\n    return 1\n",
            Path("mail/api/connection.py"),
        ),
    ],
)
def test_SC007_allowed_mail_usage_passes(source: str, module: Path) -> None:
    assert mail_http_violations(source, module=module) == []
