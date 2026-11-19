"""Connect, show and disconnect the person's mailbox (feature 002c, US1).

Everything here is about the *connection*; nothing is specific to job alerts (FR-006), so a later
feature can reuse it. Secrets go only to the secrets store and to Google.

Changes to the connection (finish a sign-in, disconnect, change the client) run one at a time, so a
Disconnect pressed while a sign-in is finishing cannot be undone by it. The secrets store is
synchronous file work, so every call to it runs in a worker thread, never on the event loop.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final, Literal

from hiretitan.mail.application.consents import PendingConsents
from hiretitan.mail.application.ports import (
    GoogleAuth,
    GoogleSecrets,
    MailAccessEndedError,
    MailboxProfile,
    MailStore,
    MailUnavailableError,
    SecretsFileError,
    SecretsStore,
)
from hiretitan.mail.domain.oauth import code_challenge, granted_only_readonly, new_verifier
from hiretitan.platform.clock import ClockPort

_log = logging.getLogger(__name__)

WINDOW_HOURS: Final = 24
MAX_QUERY_VALUE: Final = 2048  # a longer code or state is not Google's
ConnectionState = Literal["not_connected", "connected", "needs_reconnect"]
Outcome = Literal["connected", "denied", "wrong_scope", "state", "exchange_failed"]
Publish = Callable[[str, dict[str, Any]], Awaitable[None]]
StopCheck = Callable[[], Awaitable[None]]


class NoCredentialsError(Exception):
    """The person has not given a Google client id and secret yet (US1 AS5)."""


@dataclass(frozen=True, slots=True)
class ConnectionView:
    state: ConnectionState
    address: str | None
    credentials_set: bool
    credentials_from_environment: bool
    redirect_uri: str
    last_check_started_at: datetime | None
    last_error: str | None
    window_hours: int = WINDOW_HOURS


class ConnectionService:
    def __init__(
        self,
        *,
        store: MailStore,
        secrets: SecretsStore,
        auth: GoogleAuth,
        profile: MailboxProfile,
        consents: PendingConsents,
        clock: ClockPort,
        redirect_uri: str,
        stop_check: StopCheck,
        publish: Publish,
    ) -> None:
        self._store = store
        self._secrets = secrets
        self._auth = auth
        self._profile = profile
        self._consents = consents
        self._clock = clock
        self._redirect_uri = redirect_uri
        self._stop_check = stop_check
        self._publish = publish
        self._changing = asyncio.Lock()

    async def _read(self) -> GoogleSecrets:
        return await asyncio.to_thread(self._secrets.read)

    async def view(self) -> ConnectionView:
        problem: str | None = None
        credentials_set = False
        try:
            known = await self._read()
            credentials_set = bool(known.client_id and known.client_secret)
        except SecretsFileError:
            problem = "The Google secrets file cannot be read."
        row = await self._store.connection()
        from_env = self._secrets.credentials_from_environment
        if row is None:
            return ConnectionView(
                "not_connected", None, credentials_set, from_env, self._redirect_uri, None, problem
            )
        return ConnectionView(
            "connected" if row.state == "connected" else "needs_reconnect",
            row.address,
            credentials_set,
            from_env,
            self._redirect_uri,
            row.last_check_started_at,
            row.last_error or problem,
        )

    async def save_credentials(self, client_id: str, client_secret: str) -> None:
        """Raises ``CredentialsFromEnvironmentError`` when the environment holds them and
        ``SecretsFileError`` when the file cannot be used. A token belongs to the client that
        issued it, so a different client id hands the old token back and asks to reconnect."""
        async with self._changing:
            before = await self._read()
            await asyncio.to_thread(self._secrets.save_credentials, client_id, client_secret)
            if before.client_id and before.client_id != client_id.strip() and before.refresh_token:
                await self._revoke_quietly(before.refresh_token)
                if await self._store.connection() is not None:
                    await self._store.set_state(
                        "needs_reconnect", "Connect again with the new Google client."
                    )
                    await self._publish_quietly("needs_reconnect")

    async def start_consent(self) -> str:
        """The Google address the browser goes to. ``NoCredentialsError`` without credentials."""
        known = await self._read()
        if not known.client_id or not known.client_secret:
            raise NoCredentialsError
        verifier = new_verifier()
        state = self._consents.start(verifier)
        return self._auth.authorize_url(
            client_id=known.client_id,
            redirect_uri=self._redirect_uri,
            state=state,
            code_challenge=code_challenge(verifier),
        )

    async def finish_callback(
        self, *, code: str | None, state: str | None, error: str | None
    ) -> Outcome:
        """Where Google's redirect ends up. Always an outcome, never an exception: the browser
        has nowhere to show one."""
        if (state and len(state) > MAX_QUERY_VALUE) or (code and len(code) > MAX_QUERY_VALUE):
            return "state"
        async with self._changing:
            verifier = self._consents.take(state)
            if verifier is None:
                return "state"
            if error is not None or not code:
                return "denied"
            held: str | None = None
            saved = False
            try:
                known = await self._read()
                if not known.client_id or not known.client_secret:
                    return "exchange_failed"
                grant = await self._auth.exchange_code(
                    client_id=known.client_id,
                    client_secret=known.client_secret,
                    redirect_uri=self._redirect_uri,
                    code=code,
                    code_verifier=verifier,
                )
                held = grant.refresh_token or grant.access_token
                if not granted_only_readonly(grant.scope):
                    await self._give_back(held)  # nothing wider than read-only is ever kept
                    return "wrong_scope"
                if not grant.refresh_token:
                    await self._give_back(held)
                    return "exchange_failed"
                address = await self._profile.address_for(grant.access_token)
                await asyncio.to_thread(self._secrets.save_refresh_token, grant.refresh_token)
                saved = True
                await self._store.connect(address, self._clock.now())
            except (MailAccessEndedError, MailUnavailableError):
                await self._give_back(held, forget=saved)
                return "exchange_failed"
            except Exception:
                # a damaged file, a database error: whatever was granted must not stay live
                # at Google without being kept here
                _log.exception("Connecting Gmail failed after Google answered.")
                await self._give_back(held, forget=saved)
                return "exchange_failed"
            if known.refresh_token and known.refresh_token != grant.refresh_token:
                await self._revoke_quietly(known.refresh_token)  # a reconnect replaces the old one
        await self._publish_quietly("connected")
        return "connected"

    async def disconnect(self) -> bool:
        """Stop a running check, forget everything kept, hand the access back to Google.

        Returns whether Google confirmed the revoke (a failed revoke is reported, the local data
        is removed anyway). Jobs stay."""
        async with self._changing:
            self._consents.clear()  # a sign-in still open must not bring the connection back
            await self._stop_check()
            token: str | None = None
            try:
                token = (await self._read()).refresh_token
            except SecretsFileError:
                _log.warning("The Google secrets file is damaged; removing it.")
            revoked = True
            if token is not None:
                revoked = await self._revoke_quietly(token)
            await self._store.erase_all()
            try:
                await asyncio.to_thread(self._secrets.clear_token)
            except SecretsFileError:
                await asyncio.to_thread(self._secrets.clear_all)
        await self._publish_quietly("not_connected")
        return revoked

    async def mark_needs_reconnect(self, error: str) -> None:
        """Gmail refused the saved access (FR-005): say so on the Settings page."""
        await self._store.set_state("needs_reconnect", error[:300])
        await self._publish_quietly("needs_reconnect")

    async def _give_back(self, token: str | None, *, forget: bool = False) -> None:
        """Hand a just-granted token back to Google; ``forget`` also drops it from the secrets
        file (only once it was saved there: a failed reconnect keeps an earlier working token)."""
        if token is not None:
            await self._revoke_quietly(token)
        if forget:
            try:
                await asyncio.to_thread(self._secrets.clear_token)
            except SecretsFileError:
                _log.warning("The Google secrets file cannot be changed.")

    async def _revoke_quietly(self, token: str) -> bool:
        try:
            await self._auth.revoke(token)
        except MailUnavailableError:
            _log.warning("Google could not be reached to revoke the access; it is removed here.")
            return False
        return True

    async def _publish_quietly(self, state: ConnectionState) -> None:
        """An event only refreshes the page; failing to send one is never the request's failure."""
        try:
            await self._publish("mail.connection_changed", {"state": state})
        except Exception:
            _log.warning("Could not publish the mail connection event.", exc_info=True)
