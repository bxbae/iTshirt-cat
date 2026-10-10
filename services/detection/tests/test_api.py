"""API contract tests with the model mocked (no weights / network needed).
The final test runs the real architecture with random weights if torchvision is installed.
Run from services/detection:  python -m pytest -q
"""
import io
import os
import sys

import pytest
from fastapi.testclient import TestClient
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app as appmod  # noqa: E402

client = TestClient(appmod.app)


def img_bytes(fmt="PNG", size=(200, 100)):
    buf = io.BytesIO()
    Image.new("RGB", size, (10, 120, 200)).save(buf, format=fmt)
    return buf.getvalue()


FAKE = [
    appmod.Detection(label="cat", label_id=17, score=0.9, bbox=appmod.Box(x1=10, y1=10, x2=100, y2=80)),
    appmod.Detection(label="dog", label_id=18, score=0.6, bbox=appmod.Box(x1=50, y1=20, x2=150, y2=90)),
]


@pytest.fixture
def mocked(monkeypatch):
    def fake(img, thr, max_det):
        return [d for d in FAKE if d.score >= thr][:max_det]

    monkeypatch.setattr(appmod, "_infer", fake)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_detect_ok(mocked):
    r = client.post("/detect", files={"file": ("a.png", img_bytes(), "image/png")}, data={"score_threshold": "0.5"})
    assert r.status_code == 200
    j = r.json()
    assert j["count"] == 2 and j["width"] == 200 and j["height"] == 100
    assert set(j["detections"][0]) == {"label", "label_id", "score", "bbox"}
    assert set(j["detections"][0]["bbox"]) == {"x1", "y1", "x2", "y2"}


def test_threshold_filters(mocked):
    r = client.post("/detect", files={"file": ("a.png", img_bytes(), "image/png")}, data={"score_threshold": "0.8"})
    assert r.json()["count"] == 1


def test_default_threshold(mocked):
    r = client.post("/detect", files={"file": ("a.jpg", img_bytes("JPEG"), "image/jpeg")})
    assert r.status_code == 200


@pytest.mark.parametrize("thr", ["1.5", "-0.1", "abc"])
def test_bad_threshold(mocked, thr):
    r = client.post("/detect", files={"file": ("a.png", img_bytes(), "image/png")}, data={"score_threshold": thr})
    assert r.status_code == 422


def test_missing_file():
    assert client.post("/detect").status_code == 422


def test_not_an_image(mocked):
    r = client.post("/detect", files={"file": ("a.png", b"hello", "image/png")})
    assert r.status_code == 400


def test_empty_file(mocked):
    assert client.post("/detect", files={"file": ("a.png", b"", "image/png")}).status_code == 400


def test_wrong_content_type(mocked):
    r = client.post("/detect", files={"file": ("a.txt", b"x", "text/plain")})
    assert r.status_code == 415


def test_too_large(mocked, monkeypatch):
    monkeypatch.setattr(appmod, "MAX_BYTES", 10)
    r = client.post("/detect", files={"file": ("a.png", img_bytes(), "image/png")})
    assert r.status_code == 413


def test_model_failure_is_503(monkeypatch):
    def boom(*a):
        raise RuntimeError("no weights")

    monkeypatch.setattr(appmod, "_infer", boom)
    r = client.post("/detect", files={"file": ("a.png", img_bytes(), "image/png")})
    assert r.status_code == 503


def test_detect_image(mocked):
    r = client.post("/detect/image", files={"file": ("a.png", img_bytes(), "image/png")})
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert r.headers["x-detection-count"] == "2"
    out = Image.open(io.BytesIO(r.content))
    assert out.size == (200, 100)
    assert out.getpixel((10, 40)) != (10, 120, 200)  # box edge was drawn


def test_real_architecture_random_weights(monkeypatch):
    """Real torchvision forward pass with random weights (no download). Not a quality check."""
    pytest.importorskip("torchvision")
    monkeypatch.setenv("DETECTION_WEIGHTS", "none")
    monkeypatch.setenv("DETECTION_DEVICE", "cpu")
    for k in ("model", "categories", "device", "transform"):
        appmod._state[k] = None
    r = client.post(
        "/detect",
        files={"file": ("a.png", img_bytes(size=(320, 240)), "image/png")},
        data={"score_threshold": "0.0", "max_detections": "5"},
    )
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["count"] <= 5
    for d in j["detections"]:
        assert isinstance(d["label"], str)
    assert client.get("/health").json()["loaded"] is True
    for k in ("model", "categories", "device", "transform"):
        appmod._state[k] = None
