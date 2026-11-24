"""One chat turn with Mikasa (002m research R1, R2, R4, R9, R10).

``begin`` checks and stores the person's message and claims the conversation (one turn at a
time, EC-01). ``run_turn`` then streams Mikasa's reply: up to six model rounds, each tool call
answered by the action catalogue with a bounded data block, the reply checked before it is
stored. A turn that read the profile is buffered and checked against it first (FR-018a). The
person can stop it; what was written so far is kept as ``stopped`` (FR-002).
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Final, Literal
from uuid import UUID

import anyio

from hiretitan.assistant.application.ports import (
    ActionCatalog,
    CallContext,
    LlmRound,
    ProfileClaimsChecker,
    ToolOutcome,
    TurnStore,
)
from hiretitan.assistant.domain.context import WINDOW, wrap_result
from hiretitan.assistant.domain.posting import looks_like_posting
from hiretitan.assistant.domain.reply_checks import check_reply
from hiretitan.assistant.domain.routes import APP_ROUTES
from hiretitan.platform.llm.port import (
    AiUnavailable,
    ChatMessage,
    ConversePort,
    ConverseRequest,
    RetryableLlmError,
    TextDelta,
    ToolCall,
    TurnEnd,
)
from hiretitan.platform.llm.prompts import LoadedPrompt
from hiretitan.platform.untrusted.screen import screen

log = logging.getLogger(__name__)

PERSON_TEXT_MAX: Final = 2000
MAX_ROUNDS: Final = 6
TURN_SECONDS: Final = 90.0
TASK: Final = "mikasa_turn"
REFUSED_TEXT: Final = "Sorry, I couldn't do that."
UNBACKED_TEXT: Final = (
    "I don't see that in your confirmed profile, so I won't say it. "
    "You can check your profile on [[page:/profile]]."
)


class TurnError(Exception):
    reason: str = "turn_error"


class ConversationNotFoundError(TurnError):
    reason = "not_found"


class TurnRunningError(TurnError):
    reason = "turn_running"


class MessageTooLongError(TurnError):
    reason = "too_long"


class EmptyMessageError(TurnError):
    reason = "empty"


class LooksLikePostingError(TurnError):
    reason = "looks_like_posting"


# ---- events streamed to the panel (contracts/rest-api.md, "Turn stream") ---------------------


@dataclass(frozen=True, slots=True)
class TextEvent:
    delta: str
    name: Literal["text"] = "text"


@dataclass(frozen=True, slots=True)
class RefEvent:
    ref: str
    name: Literal["ref"] = "ref"


@dataclass(frozen=True, slots=True)
class NoticeEvent:
    kind: str
    text: str
    name: Literal["notice"] = "notice"


@dataclass(frozen=True, slots=True)
class ErrorEvent:
    reason: str
    message: str
    provider_message: str | None = None
    name: Literal["error"] = "error"


@dataclass(frozen=True, slots=True)
class DoneEvent:
    message_id: UUID | None
    status: str
    text: str
    name: Literal["done"] = "done"


TurnEvent = TextEvent | RefEvent | NoticeEvent | ErrorEvent | DoneEvent


@dataclass(frozen=True, slots=True)
class TurnDeps:
    llm: ConversePort
    catalog: ActionCatalog
    store: TurnStore
    claims: ProfileClaimsChecker
    prompt: LoadedPrompt
    now: Callable[[], datetime]
    max_rounds: int = MAX_ROUNDS
    turn_seconds: float = TURN_SECONDS
    monotonic: Callable[[], float] = time.monotonic


async def begin(deps: TurnDeps, conversation_id: UUID, text: str) -> UUID:
    """Check and store the person's message, and claim the conversation for the turn."""
    if not text.strip():
        raise EmptyMessageError
    if len(text) > PERSON_TEXT_MAX:
        raise MessageTooLongError
    if looks_like_posting(text):
        raise LooksLikePostingError
    if not await deps.store.conversation_exists(conversation_id):
        raise ConversationNotFoundError
    now = deps.now()
    if not await deps.store.claim_turn(conversation_id, now):
        raise TurnRunningError
    try:
        signals = [
            {"rule": flag.rule_id, "severity": flag.severity, "excerpt": flag.excerpt}
            for flag in screen(text)
        ]
        return await deps.store.add_person_message(conversation_id, text, signals, now)
    except BaseException:
        await deps.store.release_turn(conversation_id)
        raise


class _RefusedError(Exception):
    pass


class _TimeoutError(Exception):
    pass


@dataclass
class _Turn:
    """What a turn has gathered so far."""

    live: list[str] = field(default_factory=list)  # text already streamed
    buffered: list[str] = field(default_factory=list)  # text held for the profile check
    refs: list[str] = field(default_factory=list)
    trace: list[dict[str, Any]] = field(default_factory=list)
    profile_read: bool = False
    context: list[str] = field(default_factory=list)  # other results, for the profile check
    repairs_left: int = 1
    finished: bool = False

    def text(self) -> str:
        return "".join(self.live) + "".join(self.buffered)


async def run_turn(deps: TurnDeps, conversation_id: UUID, *, page: str) -> AsyncIterator[TurnEvent]:
    """Stream Mikasa's reply to the person's last message. Always ends with ``DoneEvent``."""
    turn = _Turn()
    deadline = deps.monotonic() + deps.turn_seconds
    try:
        known = await deps.store.known_refs(conversation_id)
        messages = await _history(deps, conversation_id, page)
        rounds_used = 0
        while True:
            if rounds_used == deps.max_rounds:
                yield NoticeEvent("limit", "That took too many steps, so I stopped there.")
                break
            rounds_used += 1
            calls: list[ToolCall] = []
            round_text: list[str] = []
            async for event in _converse(deps, messages, deadline):
                if isinstance(event, TextDelta):
                    round_text.append(event.text)
                    if turn.profile_read:
                        turn.buffered.append(event.text)
                    else:
                        turn.live.append(event.text)
                        yield TextEvent(event.text)
                elif isinstance(event, ToolCall):
                    calls.append(event)
            if round_text:
                messages.append(ChatMessage(role="mikasa", text="".join(round_text)))
            if not calls:
                break
            for call in calls:
                was_reading_profile = turn.profile_read
                outcome = await _call(deps, conversation_id, call, messages, turn)
                if outcome is not None:
                    known.update(outcome.refs)
                if turn.profile_read and not was_reading_profile:
                    yield NoticeEvent("checking_profile", "Checking against your profile…")
        if turn.profile_read and turn.buffered:
            turn.buffered = [await _checked_against_profile(deps, messages, turn, deadline)]
        checked = check_reply(turn.text(), known_refs=known, routes=APP_ROUTES)
        if checked.removed_refs or checked.removed_links:
            log.warning(
                "Mikasa reply: removed %d unknown refs and %d bad links",
                len(checked.removed_refs),
                len(checked.removed_links),
            )
        for ref in checked.refs:
            yield RefEvent(ref)
        message_id = await _finish(deps, conversation_id, turn, checked.text, "complete")
        yield DoneEvent(message_id, "complete", checked.text)
    except _RefusedError:
        log.warning("Mikasa: a tool call failed validation twice; the turn was refused")
        turn.trace.append({"outcome": "refused"})
        text = (turn.text() + "\n\n" + REFUSED_TEXT).strip()
        message_id = await _finish(deps, conversation_id, turn, text, "complete")
        yield DoneEvent(message_id, "complete", text)
    except AiUnavailable as error:
        error_info = {"reason": error.reason, "provider_message": error.provider_message}
        message_id = await _finish(
            deps, conversation_id, turn, turn.text(), "failed", error=error_info
        )
        yield ErrorEvent("ai_unavailable", _unavailable_text(error.reason), error.provider_message)
        yield DoneEvent(message_id, "failed", turn.text())
    except RetryableLlmError:
        message_id = await _finish(
            deps, conversation_id, turn, turn.text(), "failed", error={"reason": "busy"}
        )
        yield ErrorEvent("busy", "The AI provider is busy right now. Try again in a moment.")
        yield DoneEvent(message_id, "failed", turn.text())
    except _TimeoutError:
        message_id = await _finish(
            deps, conversation_id, turn, turn.text(), "failed", error={"reason": "timeout"}
        )
        yield ErrorEvent("timeout", "That took too long, so I stopped. Try a smaller question.")
        yield DoneEvent(message_id, "failed", turn.text())
    except Exception:
        # Anything else (a database error in an action, a bug): the turn still ends with a
        # visible reason, keeps what was written and frees the conversation (SC-008).
        log.exception("Mikasa turn failed")
        message_id = await _finish(
            deps, conversation_id, turn, turn.text(), "failed", error={"reason": "internal"}
        )
        yield ErrorEvent("internal", "Something went wrong on my side. Try again.")
        yield DoneEvent(message_id, "failed", turn.text())
    finally:
        if not turn.finished:
            # The person pressed Stop (the stream was closed) or something broke: keep what
            # was written, and free the conversation, even while being cancelled.
            with anyio.CancelScope(shield=True):
                await _finish(deps, conversation_id, turn, turn.text(), "stopped")


async def _history(deps: TurnDeps, conversation_id: UUID, page: str) -> list[ChatMessage]:
    rendered = deps.prompt.render(today=deps.now().date().isoformat(), page=_page(page))
    stored = await deps.store.recent(conversation_id, WINDOW)
    history = [
        ChatMessage(role="person" if m.author == "person" else "mikasa", text=m.text)
        for m in stored
        if m.text
    ]
    return [ChatMessage(role="note", text=rendered.user.strip()), *history]


def _page(page: str) -> str:
    """The open page as a plain path (it comes from the browser)."""
    path = page.split("?")[0].split("#")[0].strip()
    if not path.startswith("/") or len(path) > 200 or any(c.isspace() for c in path):
        return "/"
    return path


async def _converse(
    deps: TurnDeps, messages: list[ChatMessage], deadline: float, *, tools: bool = True
) -> AsyncIterator[TextDelta | ToolCall]:
    rendered = deps.prompt.render(today=deps.now().date().isoformat(), page="/")
    request = ConverseRequest(
        task=TASK,
        prompt=rendered,
        messages=list(messages),
        tools=deps.catalog.tool_specs() if tools else [],
        tier=deps.prompt.version.tier,
        max_output_tokens=deps.prompt.version.max_output_tokens,
    )
    async for event in deps.llm.converse(request):
        if deps.monotonic() > deadline:
            raise _TimeoutError
        if isinstance(event, TurnEnd):
            await deps.store.record_round(
                LlmRound(
                    prompt_name=deps.prompt.version.name,
                    prompt_version=str(deps.prompt.version.version),
                    provider=event.provider,
                    model=event.model,
                    usage=event.usage,
                    outcome=event.outcome,
                )
            )
        else:
            yield event


async def _call(
    deps: TurnDeps,
    conversation_id: UUID,
    call: ToolCall,
    messages: list[ChatMessage],
    turn: _Turn,
) -> ToolOutcome | None:
    """Run one tool call and add its result to the history. None when it was not valid."""
    messages.append(
        ChatMessage(
            role="tool_call",
            tool_call_id=call.id,
            tool_name=call.name,
            arguments_json=call.arguments_json,
        )
    )
    outcome = await deps.catalog.call(
        call.name, call.arguments_json, CallContext(conversation_id, deps.now())
    )
    turn.trace.append(
        {"tool": call.name, "kind": outcome.kind, "valid": outcome.valid, "refs": outcome.refs}
    )
    if not outcome.valid:
        if turn.repairs_left == 0:
            raise _RefusedError
        turn.repairs_left -= 1
        messages.append(
            ChatMessage(
                role="tool_result",
                tool_call_id=call.id,
                text=f"That call was not valid: {outcome.problem}. "
                "Fix the call, or answer without it.",
            )
        )
        return None
    if call.name == "get_profile":
        turn.profile_read = True
    else:
        turn.context.append(json.dumps(outcome.payload, ensure_ascii=False, default=str))
    turn.refs.extend(ref for ref in outcome.refs if ref not in turn.refs)
    messages.append(
        ChatMessage(
            role="tool_result", tool_call_id=call.id, text=wrap_result(call.name, outcome.payload)
        )
    )
    return outcome


async def _checked_against_profile(
    deps: TurnDeps, messages: list[ChatMessage], turn: _Turn, deadline: float
) -> str:
    """The held text if the profile backs it; else one rewrite; else the claim is left out."""
    text = "".join(turn.buffered)
    context = "\n".join(turn.context)
    unbacked = await deps.claims.unbacked(text, context)
    if not unbacked:
        return text
    messages.append(
        ChatMessage(
            role="note",
            text="HireTitan check: your last reply stated things that are not in the person's "
            f"confirmed profile: {', '.join(unbacked[:10])}. Rewrite the reply using only facts "
            "from the profile.",
        )
    )
    rewrite = "".join(
        [
            e.text
            async for e in _converse(deps, messages, deadline, tools=False)
            if isinstance(e, TextDelta)
        ]
    )
    if rewrite and not await deps.claims.unbacked(rewrite, context):
        return rewrite
    log.warning("Mikasa reply: unbacked profile claims remained after one rewrite")
    return UNBACKED_TEXT


async def _finish(
    deps: TurnDeps,
    conversation_id: UUID,
    turn: _Turn,
    text: str,
    status: str,
    *,
    error: dict[str, Any] | None = None,
) -> UUID | None:
    """Store Mikasa's message (once) and free the conversation."""
    if turn.finished:
        return None
    turn.finished = True
    try:
        if not text and status == "stopped" and not turn.trace:
            return None  # stopped before anything happened: nothing to keep
        return await deps.store.add_mikasa_message(
            conversation_id,
            text=text[:4000],
            status=status,
            refs=turn.refs,
            tool_trace=turn.trace,
            error=error,
            now=deps.now(),
        )
    finally:
        await deps.store.release_turn(conversation_id)


def _unavailable_text(reason: str) -> str:
    return {
        "key_missing": "Mikasa needs an AI key. You can add one in Settings.",
        "key_rejected": "Your AI provider rejected the key. You can change it in Settings.",
        "out_of_credit": "Your AI provider says you are out of credit.",
    }.get(reason, "The AI can't be used right now.")
