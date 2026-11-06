"""Fixtures for the W3 graph tests: a fake scanner, a scripted LLM and a profile card."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.fakes.search_env import Env, make_env


@pytest.fixture
def env(sessions: async_sessionmaker[AsyncSession]) -> Env:
    return make_env(sessions)
