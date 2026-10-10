import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import pytest
from fastapi.testclient import TestClient
import app as appmod


class Fake:
    device = "cpu"

    def predict(self, texts, top_k):
        return [[{"label": f"l{i}", "score": 1 / (i + 1)} for i in range(top_k)] for _ in texts]


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(appmod, "get_predictor", lambda: Fake())
    return TestClient(appmod.app)


def test_health(client):
    j = client.get("/health").json()
    assert j["status"] == "ok" and "model_id" in j


def test_predict_ok(client):
    r = client.post("/predict", json={"texts": ["기뻐요", "슬퍼요"], "top_k": 2})
    assert r.status_code == 200
    j = r.json()
    assert len(j["results"]) == 2 and len(j["results"][0]) == 2
    assert set(j["results"][0][0]) == {"label", "score"}


@pytest.mark.parametrize("body", [
    {"texts": []}, {"texts": ["  "]}, {"texts": ["a"], "top_k": 0}, {"texts": "x"}, {},
    {"texts": ["a" * (appmod.MAX_CHARS + 1)]}, {"texts": ["a"] * (appmod.MAX_TEXTS + 1)},
])
def test_predict_invalid(client, body):
    assert client.post("/predict", json=body).status_code == 422


def test_load_failure_503(monkeypatch):
    def boom():
        raise OSError("no network")
    monkeypatch.setattr(appmod, "get_predictor", boom)
    assert TestClient(appmod.app).post("/predict", json={"texts": ["안녕"]}).status_code == 503
