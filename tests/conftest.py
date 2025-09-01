"""
Pytest configuration and fixtures for Carlos test suite
"""
import pytest
import asyncio
import tempfile
import os
from unittest.mock import Mock, AsyncMock

# Configure pytest-asyncio
pytest_plugins = ['pytest_asyncio']


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def mock_api_endpoint():
    """Mock API endpoint for testing"""
    return "http://localhost:1234"


@pytest.fixture
def mock_db_uri():
    """Mock database URI for testing"""
    return "mongodb://localhost:27017/test_carlos"


@pytest.fixture
def test_user():
    """Test user name"""
    return "test_user"