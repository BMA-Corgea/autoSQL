"""T-111 (a-chk's T-85 check, LOW 2): a bare JSON array nested thousands deep answers its 422, never a 500.

FastAPI's own reply to a body that fails validation echoes the request's ``input``, and ``jsonable_encoder``
recursed into a bare array 1,000-8,000 deep until RecursionError: HTTP 500 on /api/pick and on the dashboard's
answer alike. Deeper bodies, past the JSON reader, already get T-85's handling; shallower ones the normal 422.
Now the reply that can't echo its input leaves the input out; every other reply is FastAPI's, byte for byte.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from demo.server.app import app

H = {"content-type": "application/json"}
ROUTES = ("/api/pick", "/api/dashboard/answer")


@pytest.fixture(scope="module")
def client():
    return TestClient(app, raise_server_exceptions=False)


def _bare(n: int) -> str:
    return "[" * n + "]" * n


@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize("depth", [1000, 3000, 5000])
def test_a_bare_array_thousands_deep_answers_its_422_in_words(client, route, depth):
    r = client.post(route, content=_bare(depth), headers=H)
    assert r.status_code == 422, (r.status_code, r.text[:120])
    assert r.json() == {"detail": [{"type": "dict_type", "loc": ["body"], "msg": "Input should be a valid dictionary"}]}


@pytest.mark.parametrize("route", ROUTES)
def test_a_shallow_bare_array_keeps_fastapis_own_reply_with_its_input(client, route):
    r = client.post(route, content=_bare(3), headers=H)
    assert r.status_code == 422
    assert r.json() == {"detail": [{"type": "dict_type", "loc": ["body"], "msg": "Input should be a valid dictionary",
                                    "input": [[[]]]}]}
