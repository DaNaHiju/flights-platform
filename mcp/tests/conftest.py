import json
from pathlib import Path

import httpx
import pytest

from brisa_mcp.client import BrisaClient

FIXTURES = Path(__file__).parent / "fixtures"
BASE = "http://brisa.test/api"


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


@pytest.fixture
def make_client():
    """make_client(handler) -> (BrisaClient, requests); every request is recorded."""

    def factory(handler):
        requests: list[httpx.Request] = []

        def recording(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return handler(request)

        return BrisaClient(BASE, 5.0, transport=httpx.MockTransport(recording)), requests

    return factory


def json_response(body: dict, status: int = 200) -> httpx.Response:
    return httpx.Response(status, json=body)
