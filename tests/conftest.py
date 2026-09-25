"""Contains fixtures."""

from unittest.mock import AsyncMock

import pytest

from aiopapouch import PapouchHTTPClient


@pytest.fixture(
    params=[("TME", "NONAME"), ("TME", None), (None, "NONAME"), (None, None)]
)
def mock_http_client(request):
    """Async mock PapouchHTTPClient."""

    client = AsyncMock(spec=PapouchHTTPClient)
    client.get_device_info.return_value = request.param
    return client
