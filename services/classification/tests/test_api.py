import io
import os
import sys

import pytest
from fastapi.testclient import TestClient
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import app as appmod  # noqa: E402

client = TestClient(appmod.app)


def img_bytes(fmt="PNG"):
    b = io.BytesIO()
    Image.new("RGB", (64, 48), (10, 20, 30)).save(b, format=fmt)
    return b.getvalue()


@pytest.fixture
def mock_infer(monkeypatch):
    def fake(image, top_k):
        return "cpu", [{"label": f"c{i}", "index": i, "probability": 0.5 / (i + 1)} for i in range(top_k)]
    monkeypatch.setattr(appmod, "run_inference", fake)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_predict_ok(mock_infer):
    r = client.post("/predict?top_k=3", files={"file": ("a.png", img_bytes(), "image/png")})
    assert r.status_code == 200
    j = r.json()
    assert j["top_k"] == 3 and len(j["predictions"]) == 3
    assert set(j["predictions"][0]) == {"label", "index", "probability"}


def test_invalid_image(mock_infer):
    r = client.post("/predict", files={"file": ("a.txt", b"not an image", "text/plain")})
    assert r.status_code == 400


def test_empty_file(mock_infer):
    assert client.post("/predict", files={"file": ("a.png", b"", "image/png")}).status_code == 400


def test_missing_file():
    assert client.post("/predict").status_code == 422


@pytest.mark.parametrize("k", [0, 21, -1])
def test_bad_top_k(mock_infer, k):
    r = client.post(f"/predict?top_k={k}", files={"file": ("a.png", img_bytes(), "image/png")})
    assert r.status_code == 422


def test_too_large(mock_infer, monkeypatch):
    monkeypatch.setattr(appmod, "MAX_BYTES", 10)
    r = client.post("/predict", files={"file": ("a.png", img_bytes(), "image/png")})
    assert r.status_code == 413


def test_pixel_cap(mock_infer, monkeypatch):
    monkeypatch.setattr(appmod, "MAX_PIXELS", 64 * 48 - 1)
    r = client.post("/predict", files={"file": ("a.png", img_bytes(), "image/png")})
    assert r.status_code == 413


def test_decompression_bomb(mock_infer, monkeypatch):
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 1000)  # 2x 초과 시 DecompressionBombError
    b = io.BytesIO()
    Image.new("RGB", (100, 100)).save(b, format="PNG")
    r = client.post("/predict", files={"file": ("a.png", b.getvalue(), "image/png")})
    assert r.status_code == 413


def test_real_model_random_weights(monkeypatch):
    """실제 torch 경로(무작위 가중치, 오프라인)로 추론 파이프라인만 검증. 정확도는 검증하지 않음."""
    pytest.importorskip("torchvision")
    monkeypatch.setenv("CLS_WEIGHTS", "none")
    for k in ("model", "preprocess", "labels", "device"):
        appmod._state[k] = None
    r = client.post("/predict?top_k=5", files={"file": ("a.jpg", img_bytes("JPEG"), "image/jpeg")})
    assert r.status_code == 200, r.text
    ps = r.json()["predictions"]
    assert len(ps) == 5 and abs(sum(p["probability"] for p in ps)) <= 1.0
    assert ps == sorted(ps, key=lambda p: -p["probability"])
    for k in ("model", "preprocess", "labels", "device"):
        appmod._state[k] = None
