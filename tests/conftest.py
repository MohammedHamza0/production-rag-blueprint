"""Shared pytest fixtures for unit and integration test suites."""

from unittest.mock import AsyncMock, MagicMock
import uuid
import pytest
from httpx import ASGITransport, AsyncClient

from src.api.dependencies import (
    get_db_session,
    get_llm_provider,
)
from src.llm.mock_provider import MockLLMProvider
from src.main import app


@pytest.fixture
def mock_db_session():
    """Provides a fully mocked SQLAlchemy AsyncSession."""
    session = AsyncMock()
    mock_res = MagicMock()
    mock_res.first.return_value = None
    mock_res.all.return_value = []
    mock_res.scalar_one_or_none.return_value = None
    mock_res.scalars.return_value.all.return_value = []
    session.execute.return_value = mock_res
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.add = MagicMock()
    return session


@pytest.fixture
def async_app_client(mock_db_session):
    """Provides an httpx.AsyncClient hooked to the FastAPI ASGI app."""
    app.dependency_overrides[get_db_session] = lambda: mock_db_session
    app.dependency_overrides[get_llm_provider] = lambda: MockLLMProvider()
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://testserver")
