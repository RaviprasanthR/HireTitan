"""002m T035 (US5): the person's conversations are kept, titled, and can be deleted."""

from __future__ import annotations

from tests.api.assistant.test_changes_api import Api, api  # noqa: F401 (the api fixture)

from hiretitan.platform.llm.port import TextDelta

URL = "/api/v1/assistant/conversations"


async def test_US5_AS1_history_kept(api: Api) -> None:  # noqa: F811
    api.llm.add_turn(TextDelta("Hello."))
    first = await api.conversation()
    text = "Where do things stand with my search? " + "x" * 100
    await api.turn(first, text)
    second = await api.conversation()

    listed = (await api.client.get(URL)).json()

    assert {c["id"] for c in listed} == {first, second}
    titles = {c["id"]: c["title"] for c in listed}
    assert titles[first] == text[:80]  # the first 80 characters of the first message
    assert titles[second] is None
    history = (await api.client.get(f"{URL}/{first}/messages")).json()
    assert [m["author"] for m in history] == ["person", "mikasa"]


async def test_US5_AS2_clear(api: Api) -> None:  # noqa: F811
    keep = await api.conversation()
    gone = await api.conversation()

    one = await api.client.delete(f"{URL}/{gone}")
    again = await api.client.delete(f"{URL}/{gone}")

    assert one.status_code == 204
    assert (again.status_code, again.json()["reason"]) == (404, "not_found")
    assert [c["id"] for c in (await api.client.get(URL)).json()] == [keep]

    assert (await api.client.delete(URL)).status_code == 204
    assert (await api.client.get(URL)).json() == []
    assert (await api.client.get(f"{URL}/{keep}/messages")).status_code == 404
