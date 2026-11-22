"""Gmail list and fetch contract (T024): FR-009, FR-012, SC-004, R2, R13. Provisional fixtures.

Every request is logged: only ``GET`` on the list and one message is ever made, and every list
request carries the sender query and nothing else.
"""

from __future__ import annotations

import base64
import re
from datetime import UTC, datetime
from urllib.parse import parse_qs

import httpx
import pytest
import respx
from tests.contract.gmail.test_gmail_profile import fixture, make_client

from hiretitan.mail.application.ports import (
    MailMessageNotFoundError,
    MailUnavailableError,
)
from hiretitan.mail.domain.mime import UnreadableMessageError
from hiretitan.mail.domain.senders import build_query

LIST_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages"
TOKEN_URL = "https://oauth2.googleapis.com/token"
NOW = datetime(2026, 11, 18, 9, 0, tzinfo=UTC)
QUERY = build_query(["alerts@jobsite.example.invalid", "jobs@other.example.invalid"], NOW)
QUERY_SHAPE = re.compile(r"^from:\([a-z0-9@._%+\- OR]+\) after:\d+$")
EML = (
    b"From: Job Alerts <alerts@jobsite.example.invalid>\r\n"
    b"To: jobseeker@example.invalid\r\nSubject: 2 new jobs\r\n"
    b"Date: Tue, 17 Nov 2026 00:00:00 +0530\r\n\r\nData Engineer\r\n"
)


def message_answer(raw: bytes = EML, internal_ms: int = 1_763_300_000_000) -> dict[str, object]:
    return {
        "id": "18c0ffee00000001",
        "threadId": "18c0ffee00000001",
        "labelIds": ["INBOX"],
        "snippet": "synthetic",
        "sizeEstimate": len(raw),
        "internalDate": str(internal_ms),
        "raw": base64.urlsafe_b64encode(raw).decode().rstrip("="),  # Gmail leaves padding off
    }


def refresh_route(router: respx.MockRouter) -> None:
    router.post(TOKEN_URL).respond(200, json=fixture("token_refresh.json"))


async def test_FR009_list_uses_query_and_pages() -> None:
    client, _ = make_client()
    with respx.mock() as router:
        refresh_route(router)
        route = router.get(LIST_URL).mock(
            side_effect=[
                httpx.Response(200, json=fixture("messages_list.json")),
                httpx.Response(200, json=fixture("messages_list_page2.json")),
            ]
        )

        first = await client.list_ids(QUERY, max_results=2)
        second = await client.list_ids(QUERY, page_token=first.next_page_token, max_results=2)

    assert first.ids == ["18c0ffee00000001", "18c0ffee00000002"]
    assert first.next_page_token == "synthetic-page-token-2"
    assert second.ids == ["18c0ffee00000003"]
    assert second.next_page_token is None
    params = [parse_qs(call.request.url.query.decode()) for call in route.calls]
    assert params[0] == {"q": [QUERY], "maxResults": ["2"]}
    assert params[1] == {"q": [QUERY], "maxResults": ["2"], "pageToken": ["synthetic-page-token-2"]}


async def test_FR009_an_empty_list_is_no_ids() -> None:
    client, _ = make_client()
    with respx.mock() as router:
        refresh_route(router)
        router.get(LIST_URL).respond(200, json=fixture("messages_empty.json"))

        page = await client.list_ids(QUERY)

    assert (page.ids, page.next_page_token) == ([], None)


async def test_FR009_a_query_that_is_not_the_sender_query_is_never_sent() -> None:
    client, _ = make_client()
    with respx.mock(assert_all_called=False) as router:
        anything = router.route().respond(200, json={})

        for bad in ("in:anywhere", "from:(a@x.invalid) OR label:inbox", "", "after:1"):
            with pytest.raises(ValueError, match="query"):
                await client.list_ids(bad)

    assert anything.call_count == 0  # not even a token refresh


async def test_US2_AS1_get_raw_gives_the_message_the_sender_and_the_received_time() -> None:
    client, _ = make_client()
    with respx.mock() as router:
        refresh_route(router)
        route = router.get(f"{LIST_URL}/18c0ffee00000001").respond(200, json=message_answer())

        message = await client.get_raw("18c0ffee00000001")

    assert message.raw == EML
    assert message.sender == "alerts@jobsite.example.invalid"
    assert message.received_at == datetime.fromtimestamp(1_763_300_000, UTC)
    assert parse_qs(route.calls.last.request.url.query.decode()) == {"format": ["raw"]}


@pytest.mark.parametrize("bad", ["../profile", "a/b", "", "a b", "x" * 200, "a?format=full"])
async def test_SC007_a_message_id_cannot_change_the_path(bad: str) -> None:
    client, _ = make_client()
    with respx.mock(assert_all_called=False) as router:
        anything = router.route().respond(200, json={})

        with pytest.raises(ValueError, match="message id"):
            await client.get_raw(bad)

    assert anything.call_count == 0


async def test_R13_a_deleted_message_is_not_found() -> None:
    client, _ = make_client()
    with respx.mock() as router:
        refresh_route(router)
        router.get(f"{LIST_URL}/18c0ffee00000001").respond(404, json={"error": {"code": 404}})

        with pytest.raises(MailMessageNotFoundError):
            await client.get_raw("18c0ffee00000001")


async def test_R13_a_huge_message_is_refused_before_it_is_decoded() -> None:
    client, _ = make_client()
    answer = message_answer()
    answer["sizeEstimate"] = 50_000_000
    with respx.mock() as router:
        refresh_route(router)
        router.get(f"{LIST_URL}/18c0ffee00000001").respond(200, json=answer)

        with pytest.raises(UnreadableMessageError):
            await client.get_raw("18c0ffee00000001")


async def test_R13_a_reply_that_is_not_a_message_is_unavailable() -> None:
    client, _ = make_client()
    with respx.mock() as router:
        refresh_route(router)
        router.get(f"{LIST_URL}/18c0ffee00000001").respond(200, json={"id": "x", "raw": "***"})

        with pytest.raises(MailUnavailableError):
            await client.get_raw("18c0ffee00000001")


async def test_R13_429_retried_then_gmail_unavailable() -> None:
    client, ended = make_client()
    with respx.mock() as router:
        refresh_route(router)
        route = router.get(LIST_URL).respond(429, json={"error": {"code": 429}})

        with pytest.raises(MailUnavailableError):
            await client.list_ids(QUERY)

    assert route.call_count == 3  # the first try and two retries
    assert ended.messages == []  # a busy Gmail is not the end of the person's access


async def test_R13_a_429_that_clears_is_read() -> None:
    client, _ = make_client()
    with respx.mock() as router:
        refresh_route(router)
        router.get(LIST_URL).mock(
            side_effect=[
                httpx.Response(429),
                httpx.Response(503),
                httpx.Response(200, json=fixture("messages_list_page2.json")),
            ]
        )

        page = await client.list_ids(QUERY)

    assert page.ids == ["18c0ffee00000003"]


async def test_FR005_a_401_on_the_list_is_one_refresh_and_one_retry() -> None:
    client, ended = make_client()
    with respx.mock() as router:
        token = router.post(TOKEN_URL).respond(200, json=fixture("token_refresh.json"))
        route = router.get(LIST_URL).mock(
            side_effect=[
                httpx.Response(401, json=fixture("unauthorized.json")),
                httpx.Response(200, json=fixture("messages_list_page2.json")),
            ]
        )

        page = await client.list_ids(QUERY)

    assert page.ids == ["18c0ffee00000003"]
    assert (token.call_count, route.call_count) == (2, 2)
    assert ended.messages == []


async def test_SC004_request_log_shows_only_sender_queries() -> None:
    client, _ = make_client()
    seen: list[tuple[str, str, str]] = []

    def record(request: httpx.Request) -> httpx.Response:
        if request.url.host == "oauth2.googleapis.com":
            return httpx.Response(200, json=fixture("token_refresh.json"))
        seen.append((request.method, request.url.path, request.url.query.decode()))
        if request.url.path.endswith("/messages"):
            return httpx.Response(200, json=fixture("messages_list.json"))
        return httpx.Response(200, json=message_answer())

    with respx.mock() as router:
        router.route().mock(side_effect=record)
        page = await client.list_ids(QUERY)
        for message_id in page.ids:
            await client.get_raw(message_id)

    assert [method for method, _p, _q in seen] == ["GET", "GET", "GET"]
    list_queries = [q for _m, path, q in seen if path.endswith("/users/me/messages")]
    assert len(list_queries) == 1
    assert QUERY_SHAPE.match(parse_qs(list_queries[0])["q"][0])
    paths = {path for _m, path, _q in seen}
    assert paths == {
        "/gmail/v1/users/me/messages",
        "/gmail/v1/users/me/messages/18c0ffee00000001",
        "/gmail/v1/users/me/messages/18c0ffee00000002",
    }


def forbidden(reason: str) -> dict[str, object]:
    return {"error": {"code": 403, "errors": [{"reason": reason}], "status": "PERMISSION_DENIED"}}


@pytest.mark.parametrize(
    "reason", ["rateLimitExceeded", "userRateLimitExceeded", "dailyLimitExceeded"]
)
async def test_SEC_a_403_that_means_slow_down_does_not_end_the_access(reason: str) -> None:
    client, ended = make_client()
    with respx.mock() as router:
        refresh_route(router)
        router.get(LIST_URL).respond(403, json=forbidden(reason))

        with pytest.raises(MailUnavailableError):
            await client.list_ids(QUERY)

    assert ended.messages == []  # the person is not told to reconnect because Gmail was busy


@pytest.mark.parametrize("reason", ["insufficientPermissions", "authError", "forbidden"])
async def test_FR005_a_403_about_permission_ends_the_access(reason: str) -> None:
    from hiretitan.mail.application.ports import MailAccessEndedError

    client, ended = make_client()
    with respx.mock() as router:
        refresh_route(router)
        router.get(LIST_URL).respond(403, json=forbidden(reason))

        with pytest.raises(MailAccessEndedError):
            await client.list_ids(QUERY)

    assert len(ended.messages) == 1


async def test_SEC_a_message_whose_from_borrows_a_listed_address_has_no_sender() -> None:
    spoof = (
        b'From: "alerts@jobsite.example.invalid" <someone@evil.example.invalid>\r\n'
        b"Subject: x\r\n\r\nbody\r\n"
    )
    client, _ = make_client()
    with respx.mock() as router:
        refresh_route(router)
        router.get(f"{LIST_URL}/18c0ffee00000001").respond(200, json=message_answer(spoof))

        message = await client.get_raw("18c0ffee00000001")

    assert message.sender == ""
