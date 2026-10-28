import httpx
import pytest
from apiroute import HttpxClientTransport


class Recorder:
    """A MockTransport handler that records requests and answers with queued responses."""

    def __init__(self):
        self.requests: list[httpx.Request] = []
        self._responses: list[httpx.Response] = []

    def respond(self, *responses: httpx.Response) -> None:
        self._responses.extend(responses)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self._responses.pop(0) if self._responses else httpx.Response(200, json={})

    @property
    def last(self) -> httpx.Request:
        return self.requests[-1]


@pytest.fixture
def recorder() -> Recorder:
    return Recorder()


@pytest.fixture
def transport(recorder) -> HttpxClientTransport:
    return HttpxClientTransport(httpx.Client(transport=httpx.MockTransport(recorder)))
